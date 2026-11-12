import re
from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.config import Settings
from app.core.mail import MemoryEmailSender
from app.models import ActivityEvent, EventType, PasswordResetToken, User, UserSession
from app.services.users import create_user

EMAIL = "alex@example.com"
PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a brand new passphrase"
ClientFactory = Callable[[Settings | None], TestClient]


@pytest.fixture(autouse=True)
def registered_user(db_session: Session) -> None:
    create_user(db_session, email=EMAIL, full_name="Alex Rivera", password=PASSWORD)
    db_session.commit()


def request_reset(client: TestClient, email: str = EMAIL):
    return client.post("/api/auth/password-reset/request", json={"email": email})


def confirm_reset(client: TestClient, token: str, password: str = NEW_PASSWORD):
    return client.post(
        "/api/auth/password-reset/confirm", json={"token": token, "password": password}
    )


def token_in(outbox: MemoryEmailSender) -> str:
    match = re.search(r"#token=([\w-]+)", outbox.sent[-1].body)
    assert match, outbox.sent[-1].body
    return match.group(1)


def sign_in(client: TestClient, password: str):
    return client.post("/api/auth/sign-in", json={"email": EMAIL, "password": password})


# --- Asking for a reset link ------------------------------------------------------------


def test_requesting_a_reset_emails_a_link(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    response = request_reset(client)

    assert response.status_code == 202
    [message] = outbox.sent
    assert message.to == EMAIL
    assert "Reset your WorkLedger password" in message.subject
    assert "http://localhost:5173/password-reset#token=" in message.body

    stored = db_session.scalars(select(PasswordResetToken)).one()
    assert token_in(outbox) not in stored.token_hash
    assert stored.expires_at - stored.created_at == timedelta(minutes=60)
    assert stored.used_at is None


def test_the_response_does_not_reveal_whether_an_account_exists(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    known = request_reset(client)
    sent_after_known = len(outbox.sent)
    unknown = request_reset(client, "nobody@example.com")

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(outbox.sent) == sent_after_known == 1
    assert len(db_session.scalars(select(PasswordResetToken)).all()) == 1


def test_deactivated_accounts_get_the_same_answer_and_no_email(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    db_session.execute(update(User).values(is_active=False))
    db_session.commit()

    response = request_reset(client)

    assert response.status_code == 202
    assert outbox.sent == []


def test_the_email_address_is_matched_ignoring_case_and_spaces(
    client: TestClient, outbox: MemoryEmailSender
) -> None:
    request_reset(client, "  ALEX@Example.com ")

    assert len(outbox.sent) == 1


def test_a_new_request_cancels_the_previous_link(
    client: TestClient, outbox: MemoryEmailSender
) -> None:
    request_reset(client)
    first = token_in(outbox)
    request_reset(client)
    second = token_in(outbox)

    assert confirm_reset(client, first).status_code == 404
    assert confirm_reset(client, second).status_code == 204


# --- Choosing a new password ------------------------------------------------------------


def test_the_new_password_replaces_the_old_one(
    client: TestClient, client_factory: ClientFactory, outbox: MemoryEmailSender
) -> None:
    request_reset(client)

    response = confirm_reset(client, token_in(outbox))

    assert response.status_code == 204
    assert sign_in(client_factory(None), PASSWORD).status_code == 401
    assert sign_in(client_factory(None), NEW_PASSWORD).status_code == 200


def test_a_link_works_only_once(client: TestClient, outbox: MemoryEmailSender) -> None:
    request_reset(client)
    token = token_in(outbox)

    assert confirm_reset(client, token).status_code == 204
    again = confirm_reset(client, token, "yet another passphrase")

    assert again.status_code == 404
    assert "not valid" in again.json()["detail"]


def test_resetting_signs_the_user_out_everywhere(
    client_factory: ClientFactory, outbox: MemoryEmailSender, db_session: Session
) -> None:
    laptop, phone = client_factory(None), client_factory(None)
    assert sign_in(laptop, PASSWORD).status_code == 200
    assert sign_in(phone, PASSWORD).status_code == 200
    request_reset(laptop)

    confirm_reset(laptop, token_in(outbox))

    assert laptop.get("/api/auth/me").status_code == 401
    assert phone.get("/api/auth/me").status_code == 401
    assert db_session.scalars(select(UserSession)).all() == []


def test_the_user_is_told_their_password_changed(
    client: TestClient, outbox: MemoryEmailSender
) -> None:
    request_reset(client)

    confirm_reset(client, token_in(outbox))

    notice = outbox.sent[-1]
    assert notice.to == EMAIL
    assert "password was changed" in notice.subject
    assert NEW_PASSWORD not in notice.body


def test_a_reset_is_recorded_as_an_account_event(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    request_reset(client)
    confirm_reset(client, token_in(outbox))

    event = db_session.scalars(
        select(ActivityEvent).where(ActivityEvent.event_type == EventType.PASSWORD_RESET)
    ).one()
    user = db_session.scalars(select(User)).one()
    assert event.organization_id is None
    assert event.actor_user_id == event.subject_id == user.id
    assert event.before is None and event.after is None


def test_a_weak_password_is_refused_without_using_up_the_link(
    client: TestClient, outbox: MemoryEmailSender
) -> None:
    request_reset(client)
    token = token_in(outbox)

    weak = confirm_reset(client, token, "short")
    retry = confirm_reset(client, token)

    assert weak.status_code == 422
    assert retry.status_code == 204


def test_expired_links_are_refused(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    request_reset(client)
    token = token_in(outbox)
    db_session.execute(
        update(PasswordResetToken).values(expires_at=utc_now() - timedelta(minutes=1))
    )
    db_session.commit()

    assert confirm_reset(client, token).status_code == 404


def test_unknown_links_are_refused_like_expired_ones(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    request_reset(client)
    token = token_in(outbox)
    db_session.execute(
        update(PasswordResetToken).values(expires_at=utc_now() - timedelta(minutes=1))
    )
    db_session.commit()

    expired = confirm_reset(client, token)
    unknown = confirm_reset(client, "made-up-token")

    assert expired.status_code == unknown.status_code == 404
    assert expired.json() == unknown.json()


def test_a_link_stops_working_if_the_account_is_deactivated(
    client: TestClient, outbox: MemoryEmailSender, db_session: Session
) -> None:
    request_reset(client)
    token = token_in(outbox)
    db_session.execute(update(User).values(is_active=False))
    db_session.commit()

    assert confirm_reset(client, token).status_code == 404
