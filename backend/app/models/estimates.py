"""Estimates and the owner decisions on them (decision 0022).

An estimate is one quoted amount for a work order. It is never edited: a revision is a new
estimate that replaces the current one, so every amount ever quoted, and every decision on
it, stays on record.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime


class EstimateStatus(enum.StrEnum):
    # Above the property's threshold and waiting for a property owner.
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    # At or below the threshold, so nobody needs to decide.
    NOT_REQUIRED = "not_required"


class Estimate(TimestampMixin, Base):
    __tablename__ = "estimates"
    __table_args__ = (
        Index("uq_estimates_work_order_id_version", "work_order_id", "version", unique=True),
        # At most one estimate per work order is the current one.
        Index(
            "uq_estimates_current",
            "work_order_id",
            unique=True,
            sqlite_where=text("superseded_at IS NULL"),
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    work_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_orders.id"), index=True)
    # 1 for the first estimate, then one more for each revision.
    version: Mapped[int] = mapped_column(Integer)
    # Whole minor units (cents) in the property's currency, never a floating-point number.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(Text)
    # Who quoted it, in the manager's words, such as the contractor's firm.
    provider_name: Mapped[str | None] = mapped_column(String(200))
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Decided when the estimate was recorded and kept as it was, even if the property's
    # threshold changes later.
    approval_required: Mapped[bool] = mapped_column(Boolean)
    threshold_cents: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    # Where the work order goes back to once this estimate is approved.
    resume_status: Mapped[str | None] = mapped_column(String(32))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    # Set when a newer estimate replaces this one.
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
