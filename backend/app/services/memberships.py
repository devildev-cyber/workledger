import uuid
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EventType, Membership, MembershipRole, Organization, Role, User
from app.services.activity import record_event
from app.services.assignments import clear_assignments
from app.services.organizations import NoRolesError


class LastAdministratorError(Exception):
    pass


def list_members(session: Session, *, organization_id: uuid.UUID) -> list[Membership]:
    statement = (
        select(Membership)
        .join(Membership.user)
        .where(Membership.organization_id == organization_id)
        .order_by(User.full_name, User.email)
    )
    return list(session.scalars(statement))


def get_organization_membership(
    session: Session, *, organization_id: uuid.UUID, membership_id: uuid.UUID
) -> Membership | None:
    """Only finds memberships of the given organization, so IDs from other firms look missing."""
    return session.scalar(
        select(Membership).where(
            Membership.id == membership_id, Membership.organization_id == organization_id
        )
    )


def _lock_organization(session: Session, organization_id: uuid.UUID) -> None:
    # Two administrators demoting each other at the same moment must not leave the organization
    # with none. PostgreSQL makes the second request wait here; SQLite ignores the hint, and
    # serializes writers on its own.
    session.execute(
        select(Organization.id).where(Organization.id == organization_id).with_for_update()
    )


def _administrator_count(session: Session, organization_id: uuid.UUID) -> int:
    statement = (
        select(func.count())
        .select_from(MembershipRole)
        .join(Membership, Membership.id == MembershipRole.membership_id)
        .where(
            Membership.organization_id == organization_id,
            MembershipRole.role == Role.ADMINISTRATOR,
        )
    )
    return session.scalar(statement) or 0


def _refuse_if_last_administrator(session: Session, membership: Membership) -> None:
    if _administrator_count(session, membership.organization_id) <= 1:
        raise LastAdministratorError("An organization needs at least one administrator")


def change_roles(
    session: Session, membership: Membership, *, roles: Iterable[Role], actor: User
) -> Membership:
    new_roles = set(roles)
    if not new_roles:
        raise NoRolesError("A membership needs at least one role")

    _lock_organization(session, membership.organization_id)
    session.refresh(membership)
    current_roles = set(membership.roles)
    if new_roles == current_roles:
        return membership

    if Role.ADMINISTRATOR in current_roles and Role.ADMINISTRATOR not in new_roles:
        _refuse_if_last_administrator(session, membership)
    if Role.MANAGER in current_roles and Role.MANAGER not in new_roles:
        # Access to properties ends with the role, not later.
        clear_assignments(session, membership.id)

    # Only the differences are written, so roles that stay are not deleted and re-inserted.
    for assignment in list(membership.role_assignments):
        if assignment.role not in new_roles:
            membership.role_assignments.remove(assignment)
    for role in sorted(new_roles - current_roles):
        membership.role_assignments.append(MembershipRole(role=role))
    session.flush()

    record_event(
        session,
        event_type=EventType.MEMBERSHIP_ROLES_CHANGED,
        organization_id=membership.organization_id,
        actor=actor,
        subject_type="membership",
        subject_id=membership.id,
        before={"user_id": str(membership.user_id), "roles": sorted(current_roles)},
        after={"user_id": str(membership.user_id), "roles": sorted(new_roles)},
    )
    return membership


def remove_member(session: Session, membership: Membership, *, actor: User) -> None:
    """End someone's membership. Their account, and their other organizations, are untouched."""
    _lock_organization(session, membership.organization_id)
    session.refresh(membership)
    roles = set(membership.roles)
    if Role.ADMINISTRATOR in roles:
        _refuse_if_last_administrator(session, membership)

    clear_assignments(session, membership.id)
    membership_id, organization_id, user_id = (
        membership.id,
        membership.organization_id,
        membership.user_id,
    )
    session.delete(membership)
    session.flush()

    record_event(
        session,
        event_type=EventType.MEMBERSHIP_REMOVED,
        organization_id=organization_id,
        actor=actor,
        subject_type="membership",
        subject_id=membership_id,
        before={"user_id": str(user_id), "roles": sorted(roles)},
    )
