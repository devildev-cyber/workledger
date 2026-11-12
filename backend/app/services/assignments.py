import uuid
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    EventType,
    Membership,
    MembershipRole,
    Property,
    PropertyAssignment,
    Role,
    User,
)
from app.services.activity import record_event


class NotAManagerError(Exception):
    pass


def manager_memberships(db: Session, organization_id: uuid.UUID) -> list[Membership]:
    """Everyone in the organization who holds the manager role, by name."""
    statement = (
        select(Membership)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .join(Membership.user)
        .where(Membership.organization_id == organization_id, MembershipRole.role == Role.MANAGER)
        .order_by(User.full_name, User.email)
    )
    return list(db.scalars(statement))


def assigned_membership_ids(db: Session, property_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(PropertyAssignment.membership_id).where(
                PropertyAssignment.property_id == property_id
            )
        )
    )


def assigned_property_ids(db: Session, membership_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(PropertyAssignment.property_id).where(
                PropertyAssignment.membership_id == membership_id
            )
        )
    )


def set_property_managers(
    db: Session, property_: Property, *, membership_ids: Iterable[uuid.UUID], actor: User
) -> set[uuid.UUID]:
    """Replace the managers of a property. Only members who hold the manager role qualify."""
    wanted = set(membership_ids)
    eligible = {m.id for m in manager_memberships(db, property_.organization_id)}
    if not wanted <= eligible:
        raise NotAManagerError("Only members with the manager role can be assigned")

    current = assigned_membership_ids(db, property_.id)
    if wanted == current:
        return current

    for membership_id in sorted(wanted - current):
        db.add(
            PropertyAssignment(
                organization_id=property_.organization_id,
                property_id=property_.id,
                membership_id=membership_id,
            )
        )
    if current - wanted:
        db.execute(
            delete(PropertyAssignment).where(
                PropertyAssignment.property_id == property_.id,
                PropertyAssignment.membership_id.in_(current - wanted),
            )
        )
    db.flush()
    record_event(
        db,
        event_type=EventType.PROPERTY_MANAGERS_CHANGED,
        organization_id=property_.organization_id,
        actor=actor,
        subject_type="property",
        subject_id=property_.id,
        before={"membership_ids": sorted(str(item) for item in current)},
        after={"membership_ids": sorted(str(item) for item in wanted)},
    )
    return wanted


def clear_assignments(db: Session, membership_id: uuid.UUID) -> None:
    """Called when someone stops being a manager or leaves, so access ends with the role."""
    db.execute(delete(PropertyAssignment).where(PropertyAssignment.membership_id == membership_id))
