from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utc_now
from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.membership import Role

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class Invitation(Base):
    """A single-use, expiring offer to join an organization. Only the token's hash is stored."""

    __tablename__ = "invitations"
    __table_args__ = (Index("ix_invitations_organization_id_email", "organization_id", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Stored normalized to lowercase, like user emails.
    email: Mapped[str] = mapped_column(String(320))
    # Role values; the membership created on acceptance enforces the allowed set.
    role_values: Mapped[list[str]] = mapped_column("roles", JSON)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    organization: Mapped[Organization] = relationship()
    invited_by: Mapped[User] = relationship()

    @property
    def roles(self) -> frozenset[Role]:
        return frozenset(Role(value) for value in self.role_values)

    def status(self, now: datetime) -> str:
        if self.accepted_at is not None:
            return "accepted"
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at <= now:
            return "expired"
        return "pending"
