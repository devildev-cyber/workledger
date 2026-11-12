import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession
from app.models import Membership, Role
from app.schemas.members import MemberOut, UpdateMemberRolesRequest
from app.services.memberships import (
    LastAdministratorError,
    change_roles,
    get_organization_membership,
    list_members,
    remove_member,
)

router = APIRouter(prefix="/organizations/{organization_id}/members", tags=["members"])

# Only administrators manage who belongs to the organization (decision 0013).
AdministratorContext = Annotated[OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR))]

LAST_ADMINISTRATOR = "An organization needs at least one administrator"


def _to_out(membership: Membership) -> MemberOut:
    return MemberOut(
        id=membership.id,
        user_id=membership.user_id,
        email=membership.user.email,
        full_name=membership.user.full_name,
        roles=sorted(membership.roles),
        is_active=membership.user.is_active,
        joined_at=membership.created_at,
    )


def _find_member(
    db: DbSession, context: OrganizationContext, membership_id: uuid.UUID
) -> Membership:
    membership = get_organization_membership(
        db, organization_id=context.organization.id, membership_id=membership_id
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return membership


@router.get("")
def list_organization_members(context: AdministratorContext, db: DbSession) -> list[MemberOut]:
    members = list_members(db, organization_id=context.organization.id)
    return [_to_out(membership) for membership in members]


@router.put("/{membership_id}/roles")
def update_member_roles(
    membership_id: uuid.UUID,
    body: UpdateMemberRolesRequest,
    context: AdministratorContext,
    db: DbSession,
) -> MemberOut:
    membership = _find_member(db, context, membership_id)
    try:
        change_roles(db, membership, roles=body.roles, actor=context.user)
    except LastAdministratorError:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_ADMINISTRATOR) from None
    db.commit()
    return _to_out(membership)


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_organization_member(
    membership_id: uuid.UUID, context: AdministratorContext, db: DbSession
) -> None:
    membership = _find_member(db, context, membership_id)
    try:
        remove_member(db, membership, actor=context.user)
    except LastAdministratorError:
        raise HTTPException(status.HTTP_409_CONFLICT, LAST_ADMINISTRATOR) from None
    db.commit()
