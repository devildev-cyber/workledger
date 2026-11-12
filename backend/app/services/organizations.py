import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Membership, MembershipRole, Organization, Role, User


class AlreadyMemberError(Exception):
    pass


class NoRolesError(Exception):
    pass


def create_organization(session: Session, *, name: str) -> Organization:
    organization = Organization(name=name.strip())
    session.add(organization)
    session.flush()
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
    session: Session, *, organization: Organization, user: User, roles: Iterable[Role]
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
    return membership
