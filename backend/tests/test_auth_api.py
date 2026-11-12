from collections.abc import Callable
from datetime import timedelta

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.core.clock import utc_now
from app.core.config import Settings
from app.core.security import verify_password
from app.models import Role, User, UserSession
from app.services.organizations import add_membership, create_organization
from app.services.sessions import hash_token
from app.services.users import create_user

EMAIL = "alex@example.com"
PASSWORD = "correct horse battery staple"
CREDENTIALS = {"email": EMAIL, "password": PASSWORD}


@pytest.fixture(autouse=True)
def registered_user(db_session: Session) -> None:
    user = create_user(db_session, email=EMAIL, full_name="Alex Rivera", password=PASSWORD)
    harbor = create_organization(db_session, name="Harbor", actor=None)
    add_membership(db_session, organization=harbor, user=user, roles=[Role.MANAGER], actor=None)
    db_session.commit()


def sign_in(client: TestClient) -> str:
    response = client.post("/api/auth/sign-in", json=CREDENTIALS)
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_sign_in_returns_user_memberships_and_csrf_token(client: TestClient) -> None:
    response = client.post("/api/auth/sign-in", json=CREDENTIALS)

    assert response.status_code == 200
    body = response.json()
    assert body["csrf_token"]
    assert body["user"]["email"] == EMAIL
    assert body["user"]["full_name"] == "Alex Rivera"
    [membership] = body["user"]["memberships"]
    assert membership["organization_name"] == "Harbor"
    assert membership["roles"] == ["manager"]
    assert "password" not in response.text


def test_session_cookie_is_http_only_and_same_site(client: TestClient) -> None:
    response = client.post("/api/auth/sign-in", json=CREDENTIALS)

    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie


def test_session_cookie_is_secure_in_production(
    client_factory: Callable[[Settings | None], TestClient],
) -> None:
    production = Settings(_env_file=None, environment="production")

    response = client_factory(production).post("/api/auth/sign-in", json=CREDENTIALS)

    assert "secure" in response.headers["set-cookie"].lower()


def test_only_a_hash_of_the_token_is_stored(client: TestClient, db_session: Session) -> None:
    client.post("/api/auth/sign-in", json=CREDENTIALS)
    token = client.cookies[SESSION_COOKIE_NAME]

    stored = db_session.scalars(select(UserSession)).one()

    assert stored.token_hash == hash_token(token)
    assert token not in stored.token_hash


def test_email_is_matched_ignoring_case_and_spaces(client: TestClient) -> None:
    response = client.post(
        "/api/auth/sign-in", json={"email": " ALEX@Example.com ", "password": PASSWORD}
    )

    assert response.status_code == 200


def test_wrong_password_and_unknown_email_look_identical(client: TestClient) -> None:
    wrong_password = client.post(
        "/api/auth/sign-in", json={"email": EMAIL, "password": "not the right password"}
    )
    unknown_email = client.post(
        "/api/auth/sign-in", json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert SESSION_COOKIE_NAME not in wrong_password.headers.get("set-cookie", "")


def test_deactivated_user_cannot_sign_in(client: TestClient, db_session: Session) -> None:
    db_session.execute(update(User).values(is_active=False))
    db_session.commit()

    response = client.post("/api/auth/sign-in", json=CREDENTIALS)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_current_user_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_current_user_after_sign_in(client: TestClient) -> None:
    csrf_token = sign_in(client)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == EMAIL
    assert response.json()["csrf_token"] == csrf_token


def test_an_unknown_token_is_rejected(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, "made-up-token")

    assert client.get("/api/auth/me").status_code == 401


def test_sign_out_needs_a_session(client: TestClient) -> None:
    assert client.post("/api/auth/sign-out").status_code == 401


def test_sign_out_needs_the_csrf_token(client: TestClient) -> None:
    sign_in(client)

    missing = client.post("/api/auth/sign-out")
    wrong = client.post("/api/auth/sign-out", headers={CSRF_HEADER_NAME: "wrong"})

    assert missing.status_code == wrong.status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_sign_out_ends_the_session_on_the_server(client: TestClient, db_session: Session) -> None:
    csrf_token = sign_in(client)
    token = client.cookies[SESSION_COOKIE_NAME]

    response = client.post("/api/auth/sign-out", headers={CSRF_HEADER_NAME: csrf_token})

    assert response.status_code == 204
    assert db_session.scalars(select(UserSession)).all() == []
    # A copied token is useless once the session has ended.
    client.cookies.set(SESSION_COOKIE_NAME, token)
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected_and_removed(client: TestClient, db_session: Session) -> None:
    sign_in(client)
    db_session.execute(update(UserSession).values(expires_at=utc_now() - timedelta(minutes=1)))
    db_session.commit()

    assert client.get("/api/auth/me").status_code == 401
    assert db_session.scalars(select(UserSession)).all() == []


def test_idle_session_is_rejected(client: TestClient, db_session: Session) -> None:
    sign_in(client)
    db_session.execute(update(UserSession).values(last_seen_at=utc_now() - timedelta(hours=13)))
    db_session.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_activity_extends_an_idle_session(client: TestClient, db_session: Session) -> None:
    sign_in(client)
    db_session.execute(update(UserSession).values(last_seen_at=utc_now() - timedelta(hours=11)))
    db_session.commit()

    assert client.get("/api/auth/me").status_code == 200
    db_session.expire_all()
    stored = db_session.scalars(select(UserSession)).one()
    assert utc_now() - stored.last_seen_at < timedelta(minutes=1)


def test_deactivating_a_user_ends_their_session(client: TestClient, db_session: Session) -> None:
    sign_in(client)
    db_session.execute(update(User).values(is_active=False))
    db_session.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_sessions_are_separate_per_sign_in(
    client_factory: Callable[[Settings | None], TestClient], db_session: Session
) -> None:
    laptop, phone = client_factory(None), client_factory(None)
    laptop_csrf = sign_in(laptop)
    sign_in(phone)

    laptop.post("/api/auth/sign-out", headers={CSRF_HEADER_NAME: laptop_csrf})

    assert laptop.get("/api/auth/me").status_code == 401
    assert phone.get("/api/auth/me").status_code == 200
    assert len(db_session.scalars(select(UserSession)).all()) == 1


def test_sign_in_upgrades_an_outdated_password_hash(
    client: TestClient, db_session: Session
) -> None:
    weak_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    db_session.execute(update(User).values(password_hash=weak_hash))
    db_session.commit()

    assert client.post("/api/auth/sign-in", json=CREDENTIALS).status_code == 200

    db_session.expire_all()
    upgraded = db_session.scalars(select(User)).one().password_hash
    assert upgraded != weak_hash
    assert verify_password(upgraded, PASSWORD)
