from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.security import hash_password, hash_token, new_token
from app.models import EventType, PasswordResetToken, User, UserSession
from app.services.activity import record_event
from app.services.users import validate_password


class InvalidResetTokenError(Exception):
    pass


def create_reset_token(
    db: Session, user: User, *, ttl: timedelta, now: datetime | None = None
) -> str:
    """Issue a reset token, cancelling any earlier unused one. Returns the raw token.

    The caller must commit, and should send the email afterwards.
    """
    now = now or utc_now()
    db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
        )
    )
    token = new_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + ttl,
        )
    )
    db.flush()
    return token


def reset_password(
    db: Session, *, token: str, new_password: str, now: datetime | None = None
) -> User:
    """Set a new password using a reset token, and sign the user out everywhere.

    Raises InvalidPasswordError for a weak password without using up the token, and
    InvalidResetTokenError for an unknown, used, or expired token. The caller must commit.
    """
    validate_password(new_password)
    now = now or utc_now()

    record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
    )
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise InvalidResetTokenError()
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise InvalidResetTokenError()

    # A single conditional UPDATE, so two simultaneous attempts cannot both succeed.
    claimed = db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.id == record.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    if claimed.rowcount != 1:
        raise InvalidResetTokenError()

    user.password_hash = hash_password(new_password)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
        )
    )
    record_event(
        db,
        event_type=EventType.PASSWORD_RESET,
        organization_id=None,
        actor=user,
        subject_type="user",
        subject_id=user.id,
    )
    return user
