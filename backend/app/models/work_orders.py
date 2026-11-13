"""Work orders: the operational response to one or more requests (decision 0019).

A request records what a resident reported. A work order records what the organization does
about it. Several reports of the same problem can share one work order.
"""

import enum
import uuid
from datetime import date
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


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
    S.OPEN: frozenset({S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD, S.CANCELLED}),
    S.ASSIGNED: frozenset({S.OPEN, S.IN_PROGRESS, S.ON_HOLD, S.AWAITING_APPROVAL, S.CANCELLED}),
    S.IN_PROGRESS: frozenset({S.ON_HOLD, S.AWAITING_APPROVAL, S.READY_FOR_REVIEW, S.CANCELLED}),
    S.ON_HOLD: frozenset({S.OPEN, S.ASSIGNED, S.IN_PROGRESS, S.CANCELLED}),
    S.AWAITING_APPROVAL: frozenset({S.IN_PROGRESS, S.ASSIGNED, S.CANCELLED}),
    S.READY_FOR_REVIEW: frozenset({S.IN_PROGRESS, S.COMPLETED}),
    S.COMPLETED: frozenset({S.CLOSED, S.IN_PROGRESS}),
    S.CLOSED: frozenset({S.IN_PROGRESS}),
    S.CANCELLED: frozenset({S.OPEN}),
}
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
