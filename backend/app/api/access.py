import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.deps import AuthenticatedSession, DbSession
from app.core.permissions import PropertyScope
from app.models import Membership, Organization, Role, User
from app.services.assignments import assigned_property_ids
from app.services.organizations import get_membership


@dataclass(frozen=True)
class OrganizationContext:
    """The signed-in user acting inside one organization they belong to."""

    user: User
    organization: Organization
    membership: Membership
    property_scope: PropertyScope

    @property
    def roles(self) -> frozenset[Role]:
        return self.membership.roles


def _property_scope(db: DbSession, membership: Membership) -> PropertyScope:
    """Administrators act on every property; managers only on the ones assigned to them."""
    if Role.ADMINISTRATOR in membership.roles:
        return PropertyScope.everything()
    if Role.MANAGER in membership.roles:
        return PropertyScope.limited_to(assigned_property_ids(db, membership.id))
    return PropertyScope.limited_to(())


def get_organization_context(
    organization_id: uuid.UUID, session: AuthenticatedSession, db: DbSession
) -> OrganizationContext:
    """Resolve the organization named in the URL, for members only.

    A non-member gets the same 404 as for an organization that does not exist, so
    organization IDs cannot be probed.
    """
    membership = get_membership(db, organization_id=organization_id, user_id=session.user_id)
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return OrganizationContext(
        user=session.user,
        organization=membership.organization,
        membership=membership,
        property_scope=_property_scope(db, membership),
    )


MemberContext = Annotated[OrganizationContext, Depends(get_organization_context)]


def require_roles(*allowed: Role) -> Callable[[OrganizationContext], OrganizationContext]:
    """Allow a request only if the member holds at least one of the given roles."""
    if not allowed:
        raise ValueError("require_roles needs at least one role")
    allowed_roles = frozenset(allowed)

    def check_roles(context: MemberContext) -> OrganizationContext:
        if context.roles.isdisjoint(allowed_roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this")
        return context

    return check_roles
