from functools import cache

from sqlalchemy.orm import Session

from app.core.security import hash_password, password_needs_rehash, verify_password
from app.models import User
from app.services.users import get_user_by_email


@cache
def _unknown_user_hash() -> str:
    return hash_password("a password that belongs to nobody")


def authenticate(db: Session, *, email: str, password: str) -> User | None:
    """Return the user if the credentials are valid, otherwise None.

    Every failure takes about as long as a wrong password, so response time does not
    reveal which email addresses have accounts. The caller must commit.
    """
    user = get_user_by_email(db, email)
    if user is None:
        verify_password(_unknown_user_hash(), password)
        return None

    if not verify_password(user.password_hash, password) or not user.is_active:
        return None

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user
