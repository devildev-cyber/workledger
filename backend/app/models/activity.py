import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, event
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utc_now
from app.db.base import Base
from app.db.types import UTCDateTime


class EventType(enum.StrEnum):
    ORGANIZATION_CREATED = "organization.created"
    MEMBERSHIP_CREATED = "membership.created"
    INVITATION_CREATED = "invitation.created"
    INVITATION_REVOKED = "invitation.revoked"
    INVITATION_ACCEPTED = "invitation.accepted"


class ActivityEventImmutableError(Exception):
    pass


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_events_organization_id_occurred_at", "organization_id", "occurred_at"),
        Index("ix_activity_events_subject", "subject_type", "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Empty for account-level events that belong to no organization.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    # Empty when the system or an operator tool acted rather than a signed-in user.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(64))
    subject_type: Mapped[str] = mapped_column(String(64))
    subject_id: Mapped[uuid.UUID]
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)


@event.listens_for(ActivityEvent, "before_update")
def _reject_update(_mapper: Any, _connection: Any, _target: ActivityEvent) -> None:
    raise ActivityEventImmutableError("Activity events cannot be changed")


@event.listens_for(ActivityEvent, "before_delete")
def _reject_delete(_mapper: Any, _connection: Any, _target: ActivityEvent) -> None:
    raise ActivityEventImmutableError("Activity events cannot be deleted")
