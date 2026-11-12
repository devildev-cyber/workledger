import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from app.models import Role

# Which roles each role may invite (decision 0011). Roles not listed cannot invite.
INVITABLE_ROLES: dict[Role, frozenset[Role]] = {
    Role.ADMINISTRATOR: frozenset(Role),
    Role.MANAGER: frozenset({Role.RESIDENT, Role.CONTRACTOR}),
}


def invitable_roles(held_roles: Iterable[Role]) -> frozenset[Role]:
    allowed: set[Role] = set()
    for role in held_roles:
        allowed |= INVITABLE_ROLES.get(role, frozenset())
    return frozenset(allowed)


@dataclass(frozen=True)
class PropertyScope:
    """Which properties a member may act on within one organization (decision 0008)."""

    unrestricted: bool
    property_ids: frozenset[uuid.UUID] = frozenset()

    @classmethod
    def everything(cls) -> "PropertyScope":
        return cls(unrestricted=True)

    @classmethod
    def limited_to(cls, property_ids: Iterable[uuid.UUID]) -> "PropertyScope":
        return cls(unrestricted=False, property_ids=frozenset(property_ids))

    def allows(self, property_id: uuid.UUID) -> bool:
        return self.unrestricted or property_id in self.property_ids
