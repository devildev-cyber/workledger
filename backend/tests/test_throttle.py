from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.config import Settings
from app.core.mail import MemoryEmailSender
from app.models import AuthAttempt
from app.services import throttle
from app.services.users import create_user

EMAIL = "alex@example.com"
PASSWORD = "correct horse battery staple"
ClientFactory = Callable[[Settings | None], TestClient]


@pytest.fixture(autouse=True)
def registered_user(db_session: Session) -> None:
    create_user(db_session, email=EMAIL, full_name="Alex Rivera", password=PASSWORD)
    create_user(db_session, email="sam@example.com", full_name="Sam Okafor", password=PASSWORD)
    db_session.commit()


def sign_in(client: TestClient, email: str = EMAIL, password: str = "wrong password") -> int:
    return client.post("/api/auth/sign-in", json={"email": email, "password": password}).status_code


def settings(**overrides: int | bool) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def attempts(db: Session) -> list[AuthAttempt]:
    db.expire_all()
    return list(db.scalars(select(AuthAttempt)))


# --- Signing in --------------------------------------------------------------------------


def test_repeated_wrong_passwords_lock_the_account_for_a_while(client_factory: ClientFactory):
    client = client_factory(settings(sign_in_max_failures=3))

    assert [sign_in(client) for _ in range(3)] == [401, 401, 401]
    locked = client.post("/api/auth/sign-in", json={"email": EMAIL, "password": "wrong again"})

    assert locked.status_code == 429
    assert "Too many failed sign-in attempts" in locked.json()["detail"]
    assert 0 < int(locked.headers["retry-after"]) <= 15 * 60


def test_a_locked_account_refuses_even_the_right_password(client_factory: ClientFactory):
    client = client_factory(settings(sign_in_max_failures=2))
    sign_in(client)
    sign_in(client)

    assert sign_in(client, password=PASSWORD) == 429
    assert "workledger_session" not in client.cookies


def test_the_lock_ends_when_the_window_has_passed(
    client_factory: ClientFactory, db_session: Session
):
    client = client_factory(settings(sign_in_max_failures=2, sign_in_window_minutes=15))
    sign_in(client)
    sign_in(client)
    assert sign_in(client, password=PASSWORD) == 429

    db_session.execute(update(AuthAttempt).values(created_at=utc_now() - timedelta(minutes=16)))
    db_session.commit()

    assert sign_in(client, password=PASSWORD) == 200


def test_a_wait_counts_from_the_oldest_failure_in_the_window(
    client_factory: ClientFactory, db_session: Session
):
    client = client_factory(settings(sign_in_max_failures=2, sign_in_window_minutes=15))
    sign_in(client)
    sign_in(client)
    oldest = utc_now() - timedelta(minutes=10)
    db_session.execute(update(AuthAttempt).values(created_at=oldest))
    db_session.commit()

    wait = int(
        client.post("/api/auth/sign-in", json={"email": EMAIL, "password": "x"}).headers[
            "retry-after"
        ]
    )

    assert 4 * 60 < wait <= 5 * 60 + 2


def test_attempts_during_the_lock_do_not_extend_it(
    client_factory: ClientFactory, db_session: Session
):
    client = client_factory(settings(sign_in_max_failures=2))
    sign_in(client)
    sign_in(client)
    for _ in range(5):
        assert sign_in(client) == 429

    assert len(attempts(db_session)) == 2


def test_a_correct_password_clears_earlier_failures(
    client_factory: ClientFactory, db_session: Session
):
    client = client_factory(settings(sign_in_max_failures=3))
    sign_in(client)
    sign_in(client)

    assert sign_in(client, password=PASSWORD) == 200
    assert attempts(db_session) == []
    # The run starts again from zero.
    other = client_factory(settings(sign_in_max_failures=3))
    assert [sign_in(other), sign_in(other)] == [401, 401]


def test_one_account_being_locked_does_not_lock_another(client_factory: ClientFactory):
    client = client_factory(settings(sign_in_max_failures=2, sign_in_max_failures_per_address=99))
    sign_in(client)
    sign_in(client)

    assert sign_in(client) == 429
    assert sign_in(client, email="sam@example.com", password=PASSWORD) == 200


def test_an_email_that_has_no_account_is_counted_the_same_way(client_factory: ClientFactory):
    client = client_factory(settings(sign_in_max_failures=2))

    assert [sign_in(client, email="nobody@example.com") for _ in range(2)] == [401, 401]

    assert sign_in(client, email="nobody@example.com") == 429


def test_one_address_trying_many_accounts_is_slowed_down(client_factory: ClientFactory):
    client = client_factory(settings(sign_in_max_failures=99, sign_in_max_failures_per_address=3))

    assert [sign_in(client, email=f"guess{n}@example.com") for n in range(3)] == [401] * 3

    assert sign_in(client, email="sam@example.com", password=PASSWORD) == 429


def test_the_email_spelling_does_not_get_around_the_lock(client_factory: ClientFactory):
    client = client_factory(settings(sign_in_max_failures=2))
    sign_in(client, email="Alex@Example.com")
    sign_in(client, email=" alex@example.COM ")

    assert sign_in(client, email=EMAIL, password=PASSWORD) == 429


def test_neither_the_email_nor_the_address_is_stored(
    client_factory: ClientFactory, db_session: Session
):
    client = client_factory(None)
    sign_in(client, email="private.person@example.com")

    [row] = attempts(db_session)

    dump = f"{row.kind} {row.account_key} {row.address_key}"
    assert "private.person" not in dump
    assert "testclient" not in dump
    assert len(row.account_key) == 64
    assert row.address_key is not None and len(row.address_key) == 64


def test_the_keys_depend_on_the_secret_so_they_cannot_be_looked_up_elsewhere():
    one = throttle.caller_for(settings(), email=EMAIL, address="203.0.113.7")
    other_secret = Settings(_env_file=None, secret_key="another-secret-key-that-is-long-enough!!")  # type: ignore[arg-type]
    other = throttle.caller_for(other_secret, email=EMAIL, address="203.0.113.7")

    assert one.account_key != other.account_key
    assert one.address_key != other.address_key
    # The same input always gives the same key, or counting would not work.
    assert one == throttle.caller_for(settings(), email=EMAIL, address="203.0.113.7")


def test_a_forwarded_address_is_ignored_unless_a_proxy_is_trusted(
    client_factory: ClientFactory, db_session: Session
):
    plain = client_factory(settings())
    sign_in(plain)
    plain.post(
        "/api/auth/sign-in",
        json={"email": EMAIL, "password": "x"},
        headers={"X-Forwarded-For": "198.51.100.9"},
    )
    behind_proxy = client_factory(settings(trust_forwarded_for=True))
    behind_proxy.post(
        "/api/auth/sign-in",
        json={"email": EMAIL, "password": "x"},
        headers={"X-Forwarded-For": "6.6.6.6, 198.51.100.9"},
    )

    keys = [row.address_key for row in attempts(db_session)]

    # The first two came from the same connection however the header was set. The third used the
    # last entry, which is the one a proxy we run added, not what the sender claimed.
    assert keys[0] == keys[1]
    assert keys[2] != keys[0]
    expected = throttle.caller_for(settings(), email=EMAIL, address="198.51.100.9").address_key
    assert keys[2] == expected


# --- Password reset requests -------------------------------------------------------------


def ask_for_reset(client: TestClient, email: str = EMAIL) -> tuple[int, str]:
    response = client.post("/api/auth/password-reset/request", json={"email": email})
    return response.status_code, response.json()["detail"]


def test_reset_requests_past_the_limit_get_the_same_answer_but_no_email(
    client_factory: ClientFactory, outbox: MemoryEmailSender
):
    client = client_factory(settings(reset_requests_per_hour=2))

    answers = [ask_for_reset(client) for _ in range(4)]

    assert len(set(answers)) == 1
    assert answers[0][0] == 202
    assert len(outbox.sent) == 2


def test_an_unknown_email_looks_exactly_like_a_limited_one(
    client_factory: ClientFactory, outbox: MemoryEmailSender
):
    client = client_factory(settings(reset_requests_per_hour=1))

    known = [ask_for_reset(client) for _ in range(2)]
    unknown = [ask_for_reset(client, "nobody@example.com") for _ in range(2)]

    assert set(known) == set(unknown)
    assert len(outbox.sent) == 1


def test_the_reset_limit_is_per_account_and_resets_after_an_hour(
    client_factory: ClientFactory, outbox: MemoryEmailSender, db_session: Session
):
    client = client_factory(
        settings(reset_requests_per_hour=1, reset_requests_per_address_per_hour=99)
    )
    ask_for_reset(client)
    ask_for_reset(client, "sam@example.com")
    assert len(outbox.sent) == 2

    ask_for_reset(client)
    assert len(outbox.sent) == 2

    db_session.execute(update(AuthAttempt).values(created_at=utc_now() - timedelta(minutes=61)))
    db_session.commit()
    ask_for_reset(client)
    assert len(outbox.sent) == 3


def test_one_address_cannot_flood_many_accounts_with_reset_emails(
    client_factory: ClientFactory, outbox: MemoryEmailSender
):
    client = client_factory(settings(reset_requests_per_address_per_hour=1))

    ask_for_reset(client)
    ask_for_reset(client, "sam@example.com")

    assert len(outbox.sent) == 1


def test_failed_sign_ins_and_reset_requests_are_counted_separately(
    client_factory: ClientFactory, outbox: MemoryEmailSender
):
    client = client_factory(settings(sign_in_max_failures=2, reset_requests_per_hour=5))
    sign_in(client)
    sign_in(client)

    assert sign_in(client) == 429
    ask_for_reset(client)
    assert len(outbox.sent) == 1


# --- Housekeeping ------------------------------------------------------------------------


def test_old_counts_are_purged(db_session: Session):
    caller = throttle.caller_for(settings(), email=EMAIL, address="203.0.113.7")
    throttle.record(db_session, caller, kind=throttle.SIGN_IN)
    throttle.record(db_session, caller, kind=throttle.SIGN_IN)
    old = attempts(db_session)[0]
    old.created_at = utc_now() - timedelta(days=3)
    db_session.commit()

    removed = throttle.purge(db_session, older_than=utc_now() - timedelta(days=1))
    db_session.commit()

    assert removed == 1
    assert len(attempts(db_session)) == 1
