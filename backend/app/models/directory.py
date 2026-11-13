"""The portfolio: properties, buildings, units, residents, and who manages what (decision 0015).

Every row carries its organization_id, even where it could be found through a parent. Queries
always filter on it, so a mistake in one join cannot leak another firm's records.
"""

import uuid
from datetime import date

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Property(TimestampMixin, Base):
    __tablename__ = "properties"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    street: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    region: Mapped[str] = mapped_column(String(120), default="")
    postal_code: Mapped[str] = mapped_column(String(32), default="")
    # Estimates above the threshold need a property owner's decision (decision 0022). No
    # threshold means no estimate needs approval.
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    approval_threshold_cents: Mapped[int | None] = mapped_column(Integer)


class Building(TimestampMixin, Base):
    __tablename__ = "buildings"
    __table_args__ = (UniqueConstraint("property_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))


class Unit(TimestampMixin, Base):
    __tablename__ = "units"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    building_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("buildings.id"))
    # "4B", "Unit 12", "Garden flat". Unique per property and building, checked in the service
    # because a database constraint treats two empty buildings as different.
    label: Mapped[str] = mapped_column(String(100))


class Resident(TimestampMixin, Base):
    """A person who lives, or lived, in the organization's units.

    Contact details and access instructions are private to the roles that need them. The
    link to a user account is optional: a resident can exist in the directory before, or
    without, ever signing in.
    """

    __tablename__ = "residents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    access_instructions: Mapped[str | None] = mapped_column(Text)


class Tenancy(TimestampMixin, Base):
    """One resident living in one unit, from a move-in date until an optional move-out date."""

    __tablename__ = "tenancies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"), index=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residents.id"), index=True)
    move_in_date: Mapped[date]
    move_out_date: Mapped[date | None]


class PropertyAssignment(TimestampMixin, Base):
    """A manager acts on this property (decision 0008)."""

    __tablename__ = "property_assignments"
    __table_args__ = (UniqueConstraint("property_id", "membership_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memberships.id"), index=True)


class PropertyOwnership(TimestampMixin, Base):
    """A property owner decides on spending at this property (decision 0022)."""

    __tablename__ = "property_ownerships"
    __table_args__ = (UniqueConstraint("property_id", "membership_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memberships.id"), index=True)
