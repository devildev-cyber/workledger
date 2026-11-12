from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import User

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidPasswordError(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidPasswordError(
            f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters long"
        )


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == normalize_email(email)))


def create_user(session: Session, *, email: str, full_name: str, password: str) -> User:
    validate_password(password)
    if get_user_by_email(session, email) is not None:
        raise EmailAlreadyRegisteredError(normalize_email(email))

    user = User(
        email=normalize_email(email),
        full_name=full_name.strip(),
        password_hash=hash_password(password),
    )
    session.add(user)
    session.flush()
    return user
