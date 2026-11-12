from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import User
from app.services.users import (
    EmailAlreadyRegisteredError,
    InvalidPasswordError,
    create_user,
    get_user_by_email,
)

PASSWORD = "correct horse battery staple"


def test_create_user_hashes_password_and_normalizes_email(db_session: Session) -> None:
    user = create_user(
        db_session, email="  Alex.Rivera@Example.COM ", full_name="Alex Rivera", password=PASSWORD
    )

    assert user.email == "alex.rivera@example.com"
    assert user.password_hash != PASSWORD
    assert verify_password(user.password_hash, PASSWORD)
    assert user.is_active


def test_email_is_unique_regardless_of_case(db_session: Session) -> None:
    create_user(db_session, email="alex@example.com", full_name="Alex", password=PASSWORD)

    with pytest.raises(EmailAlreadyRegisteredError):
        create_user(db_session, email="ALEX@example.com", full_name="Alex", password=PASSWORD)


def test_database_rejects_duplicate_emails(db_session: Session) -> None:
    db_session.add(User(email="sam@example.com", full_name="Sam", password_hash="x"))
    db_session.add(User(email="sam@example.com", full_name="Sam", password_hash="x"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_find_user_by_email_ignores_case(db_session: Session) -> None:
    user = create_user(db_session, email="jo@example.com", full_name="Jo", password=PASSWORD)

    assert get_user_by_email(db_session, " JO@Example.com") == user
    assert get_user_by_email(db_session, "nobody@example.com") is None


@pytest.mark.parametrize("password", ["too short", "x" * 129])
def test_password_length_is_enforced(db_session: Session, password: str) -> None:
    with pytest.raises(InvalidPasswordError):
        create_user(db_session, email="kim@example.com", full_name="Kim", password=password)


def test_timestamps_are_stored_and_loaded_as_utc(db_session: Session) -> None:
    user = create_user(db_session, email="lee@example.com", full_name="Lee", password=PASSWORD)
    db_session.commit()
    db_session.expire_all()

    reloaded = db_session.get(User, user.id)

    assert reloaded is not None
    assert reloaded.created_at.utcoffset() == timedelta(0)
    assert reloaded.updated_at.utcoffset() == timedelta(0)
