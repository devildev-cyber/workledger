"""Each person's own notifications in one organization (decision 0023).

Every query is limited to the signed-in member in the organization named in the URL, so one
person can never read, or even detect, another person's notifications.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.access import MemberContext
from app.api.deps import DbSession
from app.models import Notification
from app.schemas.notifications import (
    NotificationListOut,
    NotificationOut,
    NotificationPreferencesIn,
    NotificationPreferencesOut,
)
from app.services import notifications

router = APIRouter(prefix="/organizations/{organization_id}/notifications", tags=["notifications"])


def _out(item: Notification) -> NotificationOut:
    return NotificationOut(
        id=item.id,
        kind=item.kind,
        title=item.title,
        path=notifications.path_for(item),
        read=item.read_at is not None,
        created_at=item.created_at,
    )


def _list(db: DbSession, context: MemberContext, *, unread_only: bool) -> NotificationListOut:
    found = notifications.list_for(
        db,
        organization_id=context.organization.id,
        user_id=context.user.id,
        unread_only=unread_only,
    )
    return NotificationListOut(
        items=[_out(item) for item in found.items], unread_count=found.unread_count
    )


@router.get("")
def list_notifications(
    context: MemberContext, db: DbSession, unread_only: bool = False
) -> NotificationListOut:
    return _list(db, context, unread_only=unread_only)


@router.post("/read")
def mark_all_read(context: MemberContext, db: DbSession) -> NotificationListOut:
    notifications.mark_all_read(
        db, organization_id=context.organization.id, user_id=context.user.id
    )
    db.commit()
    return _list(db, context, unread_only=False)


@router.get("/preferences")
def read_preferences(context: MemberContext) -> NotificationPreferencesOut:
    return NotificationPreferencesOut(email_enabled=context.membership.email_notifications)


@router.put("/preferences")
def save_preferences(
    body: NotificationPreferencesIn, context: MemberContext, db: DbSession
) -> NotificationPreferencesOut:
    notifications.set_email_enabled(db, context.membership, enabled=body.email_enabled)
    db.commit()
    return NotificationPreferencesOut(email_enabled=context.membership.email_notifications)


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: uuid.UUID, context: MemberContext, db: DbSession
) -> NotificationListOut:
    found = notifications.mark_read(
        db,
        organization_id=context.organization.id,
        user_id=context.user.id,
        notification_id=notification_id,
    )
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    db.commit()
    return _list(db, context, unread_only=False)
