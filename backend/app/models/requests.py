"""Maintenance requests: what a resident reported, and the record of what happened next.

A request is a report, not a commitment to do work (decision 0017). Everything shown on its
timeline or attached to it is either visible to the resident or internal, and that flag is
stored on each row so no later feature has to guess.
"""

import enum
import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RequestCategory(enum.StrEnum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    HEATING_COOLING = "heating_cooling"
    APPLIANCES = "appliances"
    DOORS_WINDOWS = "doors_windows"
    PESTS = "pests"
    STRUCTURE = "structure"
    OTHER = "other"


class Urgency(enum.StrEnum):
    ROUTINE = "routine"
    SOON = "soon"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class RequestStatus(enum.StrEnum):
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    # Turned down by staff, always with a reason the resident can read.
    DECLINED = "declined"


# Nothing changes once a request reaches one of these.
FINISHED_STATUSES = frozenset(
    {RequestStatus.CLOSED, RequestStatus.CANCELLED, RequestStatus.DECLINED}
)
# A resident may still withdraw a request that nobody has started work on.
CANCELLABLE_STATUSES = frozenset({RequestStatus.SUBMITTED, RequestStatus.IN_REVIEW})


class Visibility(enum.StrEnum):
    RESIDENT = "resident"
    INTERNAL = "internal"


class UpdateKind(enum.StrEnum):
    SUBMITTED = "submitted"
    STATUS_CHANGED = "status_changed"
    MESSAGE = "message"
    NOTE = "note"


class RequestCounter(Base):
    """The last reference number given out in each organization."""

    __tablename__ = "request_counters"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer, default=0)


class MaintenanceRequest(TimestampMixin, Base):
    __tablename__ = "maintenance_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "number"),
        Index("ix_maintenance_requests_property_id_status", "property_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    # Shown as REQ-0042. Numbered per organization, so every firm starts at 1.
    number: Mapped[int] = mapped_column(Integer)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"), index=True)
    # The resident the request is about. Their link to an account decides who may read it,
    # so a resident who has since moved out still sees what they reported.
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residents.id"), index=True)
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_on_behalf: Mapped[bool] = mapped_column(default=False)

    category: Mapped[str] = mapped_column(String(32))
    urgency: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default=RequestStatus.SUBMITTED)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    access_notes: Mapped[str | None] = mapped_column(Text)
    # Set when the request was turned into, or linked to, a work order. From then on the work
    # order decides the request's status.
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_orders.id"), index=True
    )
    # Set when staff found this to be another report of the same problem.
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("maintenance_requests.id"))


class RequestUpdate(TimestampMixin, Base):
    """One entry on a request's timeline."""

    __tablename__ = "request_updates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("maintenance_requests.id"), index=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))
    visibility: Mapped[str] = mapped_column(String(16))
    body: Mapped[str | None] = mapped_column(Text)
    # Set on entries that moved the request to a new status.
    status_after: Mapped[str | None] = mapped_column(String(32))


class RequestAttachment(TimestampMixin, Base):
    __tablename__ = "request_attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("maintenance_requests.id"), index=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    visibility: Mapped[str] = mapped_column(String(16))
    # The name the person's device gave the file, cleaned for display. It is never used as a path.
    filename: Mapped[str] = mapped_column(String(200))
    # Worked out from the file's own bytes, not from what the browser claimed.
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
