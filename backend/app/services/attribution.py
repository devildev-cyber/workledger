"""Who did something, in the role they did it in (decision 0023).

A history entry names its author. Staff also need to know whether that was a manager, the
resident, a contractor or the property owner, because the same name can mean different
authority. A person with several roles is shown with the most senior one.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Membership, MembershipRole, Role

SENIORITY: tuple[Role, ...] = (
    Role.ADMINISTRATOR,
    Role.MANAGER,
    Role.PROPERTY_OWNER,
    Role.CONTRACTOR,
    Role.RESIDENT,
)


def display_roles(
    db: Session, *, organization_id: uuid.UUID, user_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, Role]:
    """The role to show beside each person. Someone who has since left has none."""
    wanted = {user_id for user_id in user_ids if user_id is not None}
    if not wanted:
        return {}
    held: dict[uuid.UUID, set[Role]] = {}
    rows = db.execute(
        select(Membership.user_id, MembershipRole.role)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .where(Membership.organization_id == organization_id, Membership.user_id.in_(wanted))
    )
    for user_id, role in rows:
        held.setdefault(user_id, set()).add(Role(role))
    return {
        user_id: next(role for role in SENIORITY if role in roles)
        for user_id, roles in held.items()
    }
