import uuid
from collections.abc import Iterable
from dataclasses import dataclass


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
