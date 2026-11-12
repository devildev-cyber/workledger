from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.access import MemberContext, OrganizationContext, require_roles
from app.api.deps import DbSession
from app.models import Role
from app.schemas.organizations import ActivityEventOut, OrganizationOut
from app.services.activity import list_events

router = APIRouter(prefix="/organizations/{organization_id}", tags=["organizations"])


@router.get("")
def read_organization(context: MemberContext) -> OrganizationOut:
    return OrganizationOut(
        id=context.organization.id,
        name=context.organization.name,
        roles=sorted(context.roles),
    )


@router.get("/activity")
def read_activity(
    context: Annotated[OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR))],
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ActivityEventOut]:
    events = list_events(db, organization_id=context.organization.id, limit=limit)
    return [ActivityEventOut.model_validate(event, from_attributes=True) for event in events]
