import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.clock import utc_now
from app.models import User, UserSession

TOKEN_BYTES = 32
# Avoid a database write on every request just to record activity.
LAST_SEEN_REFRESH_INTERVAL = timedelta(minutes=1)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: Session, user: User, *, max_age: timedelta, now: datetime | None = None
) -> tuple[UserSession, str]:
    """Start a session. Returns the record and the raw token, which is never stored."""
    now = now or utc_now()
    token = secrets.token_urlsafe(TOKEN_BYTES)
    record = UserSession(
        user=user,
        token_hash=hash_token(token),
        csrf_token=secrets.token_urlsafe(TOKEN_BYTES),
        created_at=now,
        last_seen_at=now,
        expires_at=now + max_age,
    )
    db.add(record)
    db.flush()
    return record, token


def get_valid_session(
    db: Session, token: str, *, idle_timeout: timedelta, now: datetime | None = None
) -> UserSession | None:
    """Find a usable session, deleting it if it has expired or its user was deactivated.

    The caller must commit, so that deletions and activity updates are saved.
    """
    now = now or utc_now()
    record = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user))
        .where(UserSession.token_hash == hash_token(token))
    )
    if record is None:
        return None

    expired = record.expires_at <= now or now - record.last_seen_at > idle_timeout
    if expired or not record.user.is_active:
        db.delete(record)
        return None

    if now - record.last_seen_at >= LAST_SEEN_REFRESH_INTERVAL:
        record.last_seen_at = now
    return record


def end_session(db: Session, record: UserSession) -> None:
    db.delete(record)
