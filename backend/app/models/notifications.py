"""Notifications: a short message saying something needs one person's attention (decision 0023).

A notification is written for its recipient. It carries only what that person is already allowed
to see (a reference and a title), and says where to look, so it can never become a side door
into records the recipient cannot open.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime


class NotificationKind(enum.StrEnum):
    REQUEST_SUBMITTED = "request_submitted"
    REQUEST_MESSAGE = "request_message"
    REQUEST_UPDATED = "request_updated"
    WORK_ORDER_ASSIGNED = "work_order_assigned"
    WORK_ORDER_UNASSIGNED = "work_order_unassigned"
    ASSIGNMENT_ACCEPTED = "assignment_accepted"
    ASSIGNMENT_DECLINED = "assignment_declined"
    WORK_ORDER_STATUS_CHANGED = "work_order_status_changed"
    WORK_ORDER_READY_FOR_REVIEW = "work_order_ready_for_review"
    WORK_ORDER_VERIFIED = "work_order_verified"
    WORK_ORDER_SENT_BACK = "work_order_sent_back"
    ESTIMATE_NEEDS_DECISION = "estimate_needs_decision"
    ESTIMATE_DECIDED = "estimate_decided"
    APPROVED_WORK_COMPLETED = "approved_work_completed"


class LinkKind(enum.StrEnum):
    """Which screen the notification opens. It depends on who is reading, because a manager,
    a contractor and a resident each look at the same record in a different place."""

    STAFF_REQUEST = "staff_request"
    STAFF_WORK_ORDER = "staff_work_order"
    MY_REQUEST = "my_request"
    JOB = "job"
    MY_JOBS = "my_jobs"
    APPROVAL = "approval"


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_recipient_user_id_organization_id_created_at",
            "recipient_user_id",
            "organization_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(48))
    link_kind: Mapped[str] = mapped_column(String(32))
    # The request, work order, or estimate the link opens.
    subject_id: Mapped[uuid.UUID]
    title: Mapped[str] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Set once the email copy has been handed to the email sender.
    emailed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
