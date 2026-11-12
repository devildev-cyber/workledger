import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.permissions import PropertyScope
from app.models import (
    Building,
    EventType,
    Membership,
    MembershipRole,
    Property,
    Resident,
    Role,
    Tenancy,
    Unit,
    User,
)
from app.services.activity import record_event
from app.services.users import get_user_by_email

PRIVATE_FIELDS = ("email", "phone", "access_instructions")


class TenancyError(Exception):
    """A move-in or move-out that does not make sense. The message is safe to show."""


@dataclass(frozen=True)
class Placement:
    """A tenancy together with the unit, building, and property it refers to."""

    tenancy: Tenancy
    unit: Unit
    property: Property
    building: Building | None

    def is_current(self, today: date) -> bool:
        return self.tenancy.move_in_date <= today and (
            self.tenancy.move_out_date is None or self.tenancy.move_out_date >= today
        )


def today() -> date:
    return utc_now().date()


# --- Residents --------------------------------------------------------------------------


def create_resident(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor: User,
    full_name: str,
    email: str | None,
    phone: str | None,
    access_instructions: str | None,
) -> Resident:
    resident = Resident(
        organization_id=organization_id,
        full_name=full_name,
        email=email,
        phone=phone,
        access_instructions=access_instructions,
    )
    db.add(resident)
    db.flush()
    link_resident_to_member(db, resident)
    record_event(
        db,
        event_type=EventType.RESIDENT_CREATED,
        organization_id=organization_id,
        actor=actor,
        subject_type="resident",
        subject_id=resident.id,
        # Contact details are private, so the shared activity history keeps only the name.
        after={"full_name": full_name},
    )
    return resident


def update_resident(
    db: Session,
    resident: Resident,
    *,
    actor: User,
    full_name: str,
    email: str | None,
    phone: str | None,
    access_instructions: str | None,
) -> Resident:
    new_values = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "access_instructions": access_instructions,
    }
    changed = [field for field, value in new_values.items() if getattr(resident, field) != value]
    if not changed:
        return resident

    for field in changed:
        setattr(resident, field, new_values[field])
    if "email" in changed:
        resident.user_id = None
        link_resident_to_member(db, resident)
    db.flush()
    record_event(
        db,
        event_type=EventType.RESIDENT_UPDATED,
        organization_id=resident.organization_id,
        actor=actor,
        subject_type="resident",
        subject_id=resident.id,
        # Which fields changed, never their values: some are private.
        after={"changed": changed},
    )
    return resident


def get_resident(
    db: Session, *, organization_id: uuid.UUID, resident_id: uuid.UUID
) -> Resident | None:
    return db.scalar(
        select(Resident).where(
            Resident.id == resident_id, Resident.organization_id == organization_id
        )
    )


def list_residents(
    db: Session, *, organization_id: uuid.UUID, scope: PropertyScope
) -> list[Resident]:
    """Administrators see everyone. Others see only residents who have lived in their properties."""
    statement = select(Resident).where(Resident.organization_id == organization_id)
    if not scope.unrestricted:
        in_scope = (
            select(Tenancy.resident_id)
            .join(Unit, Unit.id == Tenancy.unit_id)
            .where(
                Tenancy.organization_id == organization_id,
                Unit.property_id.in_(scope.property_ids),
            )
        )
        statement = statement.where(Resident.id.in_(in_scope))
    return list(db.scalars(statement.order_by(func.lower(Resident.full_name))))


# --- Linking residents to accounts ------------------------------------------------------


def _is_resident_member(db: Session, organization_id: uuid.UUID, user: User) -> bool:
    return (
        db.scalar(
            select(Membership.id)
            .join(MembershipRole, MembershipRole.membership_id == Membership.id)
            .where(
                Membership.organization_id == organization_id,
                Membership.user_id == user.id,
                MembershipRole.role == Role.RESIDENT,
            )
        )
        is not None
    )


def link_resident_to_member(db: Session, resident: Resident) -> None:
    """Connect a resident to the account with the same email, if that person is a resident member.

    The account's email was confirmed when the invitation to that address was accepted, so a
    matching address is the link. Nothing else ties a sign-in to a directory record.
    """
    if resident.email is None or resident.user_id is not None:
        return
    user = get_user_by_email(db, resident.email)
    if user is not None and _is_resident_member(db, resident.organization_id, user):
        resident.user_id = user.id


def link_residents_for_member(db: Session, *, organization_id: uuid.UUID, user: User) -> None:
    """Called when someone joins as a resident, to claim directory records waiting for them."""
    waiting = db.scalars(
        select(Resident).where(
            Resident.organization_id == organization_id,
            Resident.user_id.is_(None),
            func.lower(Resident.email) == user.email.lower(),
        )
    )
    for resident in waiting:
        resident.user_id = user.id
    db.flush()


# --- Move-ins and move-outs -------------------------------------------------------------


def _placements(db: Session, statement: Select[tuple[Tenancy]]) -> list[Placement]:
    rows = db.execute(
        statement.join(Unit, Unit.id == Tenancy.unit_id)
        .join(Property, Property.id == Unit.property_id)
        .outerjoin(Building, Building.id == Unit.building_id)
        .add_columns(Unit, Property, Building)
        .order_by(Tenancy.move_in_date.desc(), Tenancy.id)
    )
    return [
        Placement(tenancy=tenancy, unit=unit, property=property_, building=building)
        for tenancy, unit, property_, building in rows
    ]


def placements_for_residents(
    db: Session,
    *,
    organization_id: uuid.UUID,
    resident_ids: Iterable[uuid.UUID],
    scope: PropertyScope,
) -> dict[uuid.UUID, list[Placement]]:
    """Each resident's tenancies, limited to the properties the viewer may see."""
    ids = list(resident_ids)
    grouped: dict[uuid.UUID, list[Placement]] = {resident_id: [] for resident_id in ids}
    if not ids:
        return grouped

    statement = select(Tenancy).where(
        Tenancy.organization_id == organization_id, Tenancy.resident_id.in_(ids)
    )
    if not scope.unrestricted:
        statement = statement.where(Unit.property_id.in_(scope.property_ids))
    for placement in _placements(db, statement):
        grouped[placement.tenancy.resident_id].append(placement)
    return grouped


def current_residents_by_unit(
    db: Session, *, organization_id: uuid.UUID, unit_ids: Iterable[uuid.UUID], on: date
) -> dict[uuid.UUID, list[Resident]]:
    ids = list(unit_ids)
    grouped: dict[uuid.UUID, list[Resident]] = {unit_id: [] for unit_id in ids}
    if not ids:
        return grouped

    rows = db.execute(
        select(Tenancy.unit_id, Resident)
        .join(Resident, Resident.id == Tenancy.resident_id)
        .where(
            Tenancy.organization_id == organization_id,
            Tenancy.unit_id.in_(ids),
            Tenancy.move_in_date <= on,
            (Tenancy.move_out_date.is_(None)) | (Tenancy.move_out_date >= on),
        )
        .order_by(func.lower(Resident.full_name))
    )
    for unit_id, resident in rows:
        grouped[unit_id].append(resident)
    return grouped


def get_tenancy(
    db: Session, *, organization_id: uuid.UUID, tenancy_id: uuid.UUID
) -> Tenancy | None:
    return db.scalar(
        select(Tenancy).where(Tenancy.id == tenancy_id, Tenancy.organization_id == organization_id)
    )


def start_tenancy(
    db: Session, *, unit: Unit, resident: Resident, move_in_date: date, actor: User
) -> Tenancy:
    overlapping = db.scalar(
        select(Tenancy.id).where(
            Tenancy.unit_id == unit.id,
            Tenancy.resident_id == resident.id,
            (Tenancy.move_out_date.is_(None)) | (Tenancy.move_out_date >= move_in_date),
        )
    )
    if overlapping is not None:
        raise TenancyError("This resident already lives in this unit during that time")

    tenancy = Tenancy(
        organization_id=unit.organization_id,
        unit_id=unit.id,
        resident_id=resident.id,
        move_in_date=move_in_date,
    )
    db.add(tenancy)
    db.flush()
    record_event(
        db,
        event_type=EventType.TENANCY_STARTED,
        organization_id=unit.organization_id,
        actor=actor,
        subject_type="tenancy",
        subject_id=tenancy.id,
        after={
            "unit_id": str(unit.id),
            "resident_id": str(resident.id),
            "move_in_date": move_in_date.isoformat(),
        },
    )
    return tenancy


def end_tenancy(db: Session, tenancy: Tenancy, *, move_out_date: date, actor: User) -> Tenancy:
    if tenancy.move_out_date is not None:
        raise TenancyError("This move-out has already been recorded")
    if move_out_date < tenancy.move_in_date:
        raise TenancyError("The move-out date cannot be before the move-in date")

    tenancy.move_out_date = move_out_date
    db.flush()
    record_event(
        db,
        event_type=EventType.TENANCY_ENDED,
        organization_id=tenancy.organization_id,
        actor=actor,
        subject_type="tenancy",
        subject_id=tenancy.id,
        before={"move_out_date": None},
        after={"move_out_date": move_out_date.isoformat()},
    )
    return tenancy


def current_placements_for_user(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID, on: date
) -> list[Placement]:
    """The units a signed-in resident lives in today. Past homes are not included."""
    statement = (
        select(Tenancy)
        .join(Resident, Resident.id == Tenancy.resident_id)
        .where(
            Tenancy.organization_id == organization_id,
            Resident.organization_id == organization_id,
            Resident.user_id == user_id,
        )
    )
    placements = _placements(db, statement)
    return [placement for placement in placements if placement.is_current(on)]
