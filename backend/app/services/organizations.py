import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EventType,
    Membership,
    MembershipRole,
    Organization,
    RequestCounter,
    Role,
    User,
)
from app.services.activity import record_event


class AlreadyMemberError(Exception):
    pass


class NoRolesError(Exception):
    pass


def create_organization(session: Session, *, name: str, actor: User | None) -> Organization:
    organization = Organization(name=name.strip())
    session.add(organization)
    session.flush()
    session.add(RequestCounter(organization_id=organization.id, last_number=0))

    record_event(
        session,
        event_type=EventType.ORGANIZATION_CREATED,
        organization_id=organization.id,
        actor=actor,
        subject_type="organization",
        subject_id=organization.id,
        after={"name": organization.name},
    )
    return organization


def get_membership(
    session: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> Membership | None:
    return session.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
        )
    )


def list_memberships_for_user(session: Session, user_id: uuid.UUID) -> list[Membership]:
    statement = (
        select(Membership)
        .join(Membership.organization)
        .where(Membership.user_id == user_id)
        .order_by(Organization.name)
    )
    return list(session.scalars(statement))


def add_membership(
    session: Session,
    *,
    organization: Organization,
    user: User,
    roles: Iterable[Role],
    actor: User | None,
) -> Membership:
    role_set = set(roles)
    if not role_set:
        raise NoRolesError("A membership needs at least one role")
    if get_membership(session, organization_id=organization.id, user_id=user.id) is not None:
        raise AlreadyMemberError(f"{user.email} is already a member of {organization.name}")

    membership = Membership(
        organization=organization,
        user=user,
        role_assignments=[MembershipRole(role=role) for role in sorted(role_set)],
    )
    session.add(membership)
    session.flush()

    record_event(
        session,
        event_type=EventType.MEMBERSHIP_CREATED,
        organization_id=organization.id,
        actor=actor,
        subject_type="membership",
        subject_id=membership.id,
        after={"user_id": str(user.id), "roles": sorted(role_set)},
    )
    return membership
