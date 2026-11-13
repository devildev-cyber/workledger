"""Deleting records that have outlived their purpose (decision 0025).

Only operational leftovers are removed here: expired sign-ins, used or expired links, failed
sign-in counts, and old notifications. Business records, and the activity history that proves
who did what, are never deleted by this code.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, or_
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.models import Invitation, Notification, PasswordResetToken, UserSession
from app.services import throttle

# How long each kind of leftover is kept after it stops being useful.
RESET_TOKEN_KEPT = timedelta(days=1)
INVITATION_KEPT = timedelta(days=90)
AUTH_ATTEMPT_KEPT = timedelta(days=1)
NOTIFICATION_KEPT = timedelta(days=365)


@dataclass(frozen=True)
class PurgeResult:
    sessions: int
    reset_tokens: int
    invitations: int
    auth_attempts: int
    notifications: int

    @property
    def total(self) -> int:
        return (
            self.sessions
            + self.reset_tokens
            + self.invitations
            + self.auth_attempts
            + self.notifications
        )


def purge_expired(
    db: Session, *, idle_timeout: timedelta, now: datetime | None = None
) -> PurgeResult:
    """Delete what is no longer needed. The caller commits."""
    now = now or utc_now()

    sessions = db.execute(
        delete(UserSession).where(
            or_(UserSession.expires_at <= now, UserSession.last_seen_at < now - idle_timeout)
        )
    ).rowcount
    reset_tokens = db.execute(
        delete(PasswordResetToken).where(
            or_(
                PasswordResetToken.expires_at < now - RESET_TOKEN_KEPT,
                PasswordResetToken.used_at < now - RESET_TOKEN_KEPT,
            )
        )
    ).rowcount
    cutoff = now - INVITATION_KEPT
    invitations = db.execute(
        delete(Invitation).where(
            or_(
                Invitation.expires_at < cutoff,
                and_(Invitation.accepted_at.is_not(None), Invitation.accepted_at < cutoff),
                and_(Invitation.revoked_at.is_not(None), Invitation.revoked_at < cutoff),
            )
        )
    ).rowcount
    attempts = throttle.purge(db, older_than=now - AUTH_ATTEMPT_KEPT)
    notifications = db.execute(
        delete(Notification).where(Notification.created_at < now - NOTIFICATION_KEPT)
    ).rowcount

    return PurgeResult(
        sessions=sessions or 0,
        reset_tokens=reset_tokens or 0,
        invitations=invitations or 0,
        auth_attempts=attempts,
        notifications=notifications or 0,
    )
