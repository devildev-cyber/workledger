from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class Role(enum.StrEnum):
    ADMINISTRATOR = "administrator"
    MANAGER = "manager"
    RESIDENT = "resident"
    CONTRACTOR = "contractor"
    PROPERTY_OWNER = "property_owner"


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
    role_assignments: Mapped[list[MembershipRole]] = relationship(
        back_populates="membership", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def roles(self) -> frozenset[Role]:
        return frozenset(assignment.role for assignment in self.role_assignments)


class MembershipRole(Base):
    __tablename__ = "membership_roles"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            name="role",
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda roles: [role.value for role in roles],
        ),
        primary_key=True,
    )

    membership: Mapped[Membership] = relationship(back_populates="role_assignments")
