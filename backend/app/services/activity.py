import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityEvent, EventType, User


def record_event(
    session: Session,
    *,
    event_type: EventType,
    organization_id: uuid.UUID | None,
    actor: User | None,
    subject_type: str,
    subject_id: uuid.UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> ActivityEvent:
    """Add an event to the session so it is saved in the same transaction as the change."""
    activity_event = ActivityEvent(
        event_type=event_type,
        organization_id=organization_id,
        actor_user_id=actor.id if actor else None,
        subject_type=subject_type,
        subject_id=subject_id,
        before=before,
        after=after,
    )
    session.add(activity_event)
    return activity_event


def list_events(
    session: Session, *, organization_id: uuid.UUID, limit: int = 50
) -> list[ActivityEvent]:
    """Newest first. Always filtered by organization, so one firm never sees another's history."""
    statement = (
        select(ActivityEvent)
        .where(ActivityEvent.organization_id == organization_id)
        .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id)
        .limit(limit)
    )
    return list(session.scalars(statement))
