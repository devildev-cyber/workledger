"""Which members own which properties (decision 0022).

A property owner decides on spending at their own properties and sees nothing else. Only
members who hold the property owner role can be given a property.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    EventType,
    Membership,
    MembershipRole,
    Property,
    PropertyOwnership,
    Role,
    User,
)
from app.services.activity import record_event


class NotAnOwnerError(Exception):
    pass


def owner_memberships(db: Session, organization_id: uuid.UUID) -> list[Membership]:
    """Everyone in the organization who holds the property owner role, by name."""
    statement = (
        select(Membership)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .join(Membership.user)
        .where(
            Membership.organization_id == organization_id,
            MembershipRole.role == Role.PROPERTY_OWNER,
        )
        .order_by(User.full_name, User.email)
    )
    return list(db.scalars(statement))


def owned_membership_ids(db: Session, property_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(PropertyOwnership.membership_id).where(
                PropertyOwnership.property_id == property_id
            )
        )
    )


def owned_property_ids(db: Session, membership_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(PropertyOwnership.property_id).where(
                PropertyOwnership.membership_id == membership_id
            )
        )
    )


def is_owner(db: Session, *, property_id: uuid.UUID, membership_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(PropertyOwnership.id).where(
                PropertyOwnership.property_id == property_id,
                PropertyOwnership.membership_id == membership_id,
            )
        )
        is not None
    )


def owner_names(db: Session, property_id: uuid.UUID) -> list[str]:
    """The people who can decide on spending at a property, by name."""
    statement = (
        select(User.full_name)
        .join(Membership, Membership.user_id == User.id)
        .join(PropertyOwnership, PropertyOwnership.membership_id == Membership.id)
        .where(PropertyOwnership.property_id == property_id)
        .order_by(User.full_name, User.email)
    )
    return list(db.scalars(statement))


def set_property_owners(
    db: Session, property_: Property, *, membership_ids: Iterable[uuid.UUID], actor: User
) -> set[uuid.UUID]:
    """Replace the owners of a property. Only members who hold the owner role qualify."""
    wanted = set(membership_ids)
    eligible = {m.id for m in owner_memberships(db, property_.organization_id)}
    if not wanted <= eligible:
        raise NotAnOwnerError("Only members with the property owner role can be given a property")

    current = owned_membership_ids(db, property_.id)
    if wanted == current:
        return current

    for membership_id in sorted(wanted - current):
        db.add(
            PropertyOwnership(
                organization_id=property_.organization_id,
                property_id=property_.id,
                membership_id=membership_id,
            )
        )
    if current - wanted:
        db.execute(
            delete(PropertyOwnership).where(
                PropertyOwnership.property_id == property_.id,
                PropertyOwnership.membership_id.in_(current - wanted),
            )
        )
    db.flush()
    record_event(
        db,
        event_type=EventType.PROPERTY_OWNERS_CHANGED,
        organization_id=property_.organization_id,
        actor=actor,
        subject_type="property",
        subject_id=property_.id,
        before={"membership_ids": sorted(str(item) for item in current)},
        after={"membership_ids": sorted(str(item) for item in wanted)},
    )
    return wanted


def clear_ownerships(db: Session, membership_id: uuid.UUID) -> None:
    """Called when someone stops being an owner or leaves, so authority ends with the role."""
    db.execute(delete(PropertyOwnership).where(PropertyOwnership.membership_id == membership_id))
