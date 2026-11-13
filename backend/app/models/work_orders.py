"""Work orders: the operational response to one or more requests (decision 0019).

A request records what a resident reported. A work order records what the organization does
about it. Several reports of the same problem can share one work order.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime


class WorkOrderStatus(enum.StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    AWAITING_APPROVAL = "awaiting_approval"
    READY_FOR_REVIEW = "ready_for_review"
    COMPLETED = "completed"
    CLOSED = "closed"
    CANCELLED = "cancelled"


S = WorkOrderStatus

# Every move a work order may make. Anything not listed is refused. The statuses for dispatch
# and approval are part of the table now so those phases add behaviour, not new rules.
TRANSITIONS: dict[WorkOrderStatus, frozenset[WorkOrderStatus]] = {
    S.OPEN: frozenset({S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD, S.AWAITING_APPROVAL, S.CANCELLED}),
    S.ASSIGNED: frozenset({S.OPEN, S.IN_PROGRESS, S.ON_HOLD, S.AWAITING_APPROVAL, S.CANCELLED}),
    S.IN_PROGRESS: frozenset({S.ON_HOLD, S.AWAITING_APPROVAL, S.READY_FOR_REVIEW, S.CANCELLED}),
    S.ON_HOLD: frozenset({S.OPEN, S.ASSIGNED, S.IN_PROGRESS, S.AWAITING_APPROVAL, S.CANCELLED}),
    S.AWAITING_APPROVAL: frozenset({S.OPEN, S.IN_PROGRESS, S.ASSIGNED, S.ON_HOLD, S.CANCELLED}),
    S.READY_FOR_REVIEW: frozenset({S.IN_PROGRESS, S.COMPLETED}),
    S.COMPLETED: frozenset({S.CLOSED, S.IN_PROGRESS}),
    S.CLOSED: frozenset({S.IN_PROGRESS}),
    S.CANCELLED: frozenset({S.OPEN}),
}
# Leaving ready-for-review is a review: either the work is verified (with its resolution and
# cost) or it is sent back (with a reason). It is never a plain status change.
REVIEW_MOVES = frozenset({(S.READY_FOR_REVIEW, S.COMPLETED), (S.READY_FOR_REVIEW, S.IN_PROGRESS)})
# Moving into these spends money or records that it was spent, so they wait for any approval
# the current estimate needs (decision 0022).
PROGRESS_STATUSES = frozenset({S.IN_PROGRESS, S.READY_FOR_REVIEW, S.COMPLETED})
# Set by the feature that owns them (assignment in Phase 5, approvals in Phase 7), not by hand.
SYSTEM_STATUSES = frozenset({S.ASSIGNED, S.AWAITING_APPROVAL})
# Leaving these takes an administrator: a finished work order is reopened deliberately.
ADMINISTRATOR_ONLY_FROM = frozenset({S.CLOSED, S.CANCELLED})
# No more work is expected on these.
FINAL_STATUSES = frozenset({S.COMPLETED, S.CLOSED, S.CANCELLED})


class EntryKind(enum.StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    EDITED = "edited"
    NOTE = "note"
    REQUEST_LINKED = "request_linked"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    ASSIGNMENT_ACCEPTED = "assignment_accepted"
    ASSIGNMENT_DECLINED = "assignment_declined"
    # What a contractor writes. A clarification is a question the manager should answer.
    PROGRESS = "progress"
    CLARIFICATION = "clarification"
    # The manager's review of work marked ready (decision 0021).
    VERIFIED = "verified"
    SENT_BACK = "sent_back"
    # Estimates and the owner's decision on them (decision 0022).
    ESTIMATE_SUBMITTED = "estimate_submitted"
    ESTIMATE_APPROVED = "estimate_approved"
    ESTIMATE_REJECTED = "estimate_rejected"


class AssignmentResponse(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class AssignmentEnd(enum.StrEnum):
    """Why an assignment stopped being the current one."""

    REASSIGNED = "reassigned"
    UNASSIGNED = "unassigned"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class WorkOrderCounter(Base):
    """The last work order number given out in each organization."""

    __tablename__ = "work_order_counters"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer, default=0)


class WorkOrder(TimestampMixin, Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        UniqueConstraint("organization_id", "number"),
        Index("ix_work_orders_property_id_status", "property_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    # Shown as WO-0007. Numbered per organization.
    number: Mapped[int] = mapped_column(Integer)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    # Empty for work on common areas or the building as a whole.
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("units.id"))
    title: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32))
    # Uses the same scale as a request's urgency.
    priority: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default=WorkOrderStatus.OPEN)
    due_date: Mapped[date | None]
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # The outcome, set when a manager verifies the work and cleared if it is reopened. The
    # history keeps every verification. Cost is whole minor units (cents) in `currency`.
    resolution: Mapped[str | None] = mapped_column(Text)
    final_cost_cents: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(String(3))
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WorkOrderEntry(TimestampMixin, Base):
    """One line of a work order's history. Nothing here is edited or removed afterwards."""

    __tablename__ = "work_order_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    work_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_orders.id"), index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))
    # Whether a note was also shared with the resident. Everything else here is internal.
    visibility: Mapped[str] = mapped_column(String(16))
    body: Mapped[str | None] = mapped_column(Text)
    status_after: Mapped[str | None] = mapped_column(String(32))
    # For edits: {"field": [before, after]}.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Whether the contractor on the job may read this entry (decision 0020).
    contractor_visible: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class WorkOrderAssignment(TimestampMixin, Base):
    """The contractor responsible for a work order, for a period of time.

    Reassigning ends the current row and adds a new one, so the full history stays. At most
    one assignment per work order is current (decision 0020).
    """

    __tablename__ = "work_order_assignments"
    __table_args__ = (
        Index(
            "uq_work_order_assignments_current",
            "work_order_id",
            unique=True,
            sqlite_where=text("ended_at IS NULL"),
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    work_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_orders.id"), index=True)
    # The contractor's membership in this organization, not their account, so the same person
    # working for two firms has two unrelated sets of jobs.
    contractor_membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id"), index=True
    )
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime)
    response: Mapped[str] = mapped_column(String(16), default=AssignmentResponse.PENDING)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decline_reason: Mapped[str | None] = mapped_column(Text)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ended_reason: Mapped[str | None] = mapped_column(String(16))


class WorkOrderAttachment(TimestampMixin, Base):
    """A photo or document on a work order, such as evidence that the work was done."""

    __tablename__ = "work_order_attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    work_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_orders.id"), index=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # What the contractor on the job may open. Their own uploads always are.
    contractor_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
