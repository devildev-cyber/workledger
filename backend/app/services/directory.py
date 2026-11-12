import re
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import PropertyScope
from app.models import Building, EventType, Property, Unit, User
from app.services.activity import record_event


class DuplicateNameError(Exception):
    pass


class BuildingNotInPropertyError(Exception):
    pass


def _natural_key(text: str) -> list[tuple[int, int | str]]:
    """Sorts "2" before "10" and "4B" after "4A", as people expect for unit numbers."""
    return [
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.split(r"(\d+)", text)
        if part
    ]


def _changes(record: object, new_values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field, new in new_values.items():
        old = getattr(record, field)
        if old != new:
            before[field] = old
            after[field] = new
    return before, after


# --- Properties -------------------------------------------------------------------------


def _property_name_taken(
    db: Session, organization_id: uuid.UUID, name: str, *, excluding: uuid.UUID | None = None
) -> bool:
    statement = select(Property.id).where(
        Property.organization_id == organization_id, func.lower(Property.name) == name.lower()
    )
    if excluding is not None:
        statement = statement.where(Property.id != excluding)
    return db.scalar(statement) is not None


def create_property(
    db: Session, *, organization_id: uuid.UUID, actor: User, values: dict[str, Any]
) -> Property:
    if _property_name_taken(db, organization_id, values["name"]):
        raise DuplicateNameError(values["name"])

    property_ = Property(organization_id=organization_id, **values)
    db.add(property_)
    db.flush()
    record_event(
        db,
        event_type=EventType.PROPERTY_CREATED,
        organization_id=organization_id,
        actor=actor,
        subject_type="property",
        subject_id=property_.id,
        after=values,
    )
    return property_


def update_property(
    db: Session, property_: Property, *, actor: User, values: dict[str, Any]
) -> Property:
    before, after = _changes(property_, values)
    if not after:
        return property_
    if "name" in after and _property_name_taken(
        db, property_.organization_id, values["name"], excluding=property_.id
    ):
        raise DuplicateNameError(values["name"])

    for field, value in after.items():
        setattr(property_, field, value)
    db.flush()
    record_event(
        db,
        event_type=EventType.PROPERTY_UPDATED,
        organization_id=property_.organization_id,
        actor=actor,
        subject_type="property",
        subject_id=property_.id,
        before=before,
        after=after,
    )
    return property_


def get_property(
    db: Session, *, organization_id: uuid.UUID, property_id: uuid.UUID
) -> Property | None:
    return db.scalar(
        select(Property).where(
            Property.id == property_id, Property.organization_id == organization_id
        )
    )


def list_properties(
    db: Session, *, organization_id: uuid.UUID, scope: PropertyScope
) -> list[Property]:
    statement = select(Property).where(Property.organization_id == organization_id)
    if not scope.unrestricted:
        statement = statement.where(Property.id.in_(scope.property_ids))
    return list(db.scalars(statement.order_by(func.lower(Property.name))))


def unit_counts(db: Session, property_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, int]:
    ids = list(property_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Unit.property_id, func.count())
        .where(Unit.property_id.in_(ids))
        .group_by(Unit.property_id)
    )
    return {property_id: count for property_id, count in rows}


# --- Buildings --------------------------------------------------------------------------


def list_buildings(db: Session, property_id: uuid.UUID) -> list[Building]:
    buildings = db.scalars(select(Building).where(Building.property_id == property_id))
    return sorted(buildings, key=lambda building: _natural_key(building.name))


def get_building(
    db: Session, *, organization_id: uuid.UUID, property_id: uuid.UUID, building_id: uuid.UUID
) -> Building | None:
    return db.scalar(
        select(Building).where(
            Building.id == building_id,
            Building.property_id == property_id,
            Building.organization_id == organization_id,
        )
    )


def _building_name_taken(
    db: Session, property_id: uuid.UUID, name: str, *, excluding: uuid.UUID | None = None
) -> bool:
    statement = select(Building.id).where(
        Building.property_id == property_id, func.lower(Building.name) == name.lower()
    )
    if excluding is not None:
        statement = statement.where(Building.id != excluding)
    return db.scalar(statement) is not None


def create_building(db: Session, property_: Property, *, actor: User, name: str) -> Building:
    if _building_name_taken(db, property_.id, name):
        raise DuplicateNameError(name)

    building = Building(
        organization_id=property_.organization_id, property_id=property_.id, name=name
    )
    db.add(building)
    db.flush()
    record_event(
        db,
        event_type=EventType.BUILDING_CREATED,
        organization_id=property_.organization_id,
        actor=actor,
        subject_type="building",
        subject_id=building.id,
        after={"property_id": str(property_.id), "name": name},
    )
    return building


def rename_building(db: Session, building: Building, *, actor: User, name: str) -> Building:
    if building.name == name:
        return building
    if _building_name_taken(db, building.property_id, name, excluding=building.id):
        raise DuplicateNameError(name)

    before = {"name": building.name}
    building.name = name
    db.flush()
    record_event(
        db,
        event_type=EventType.BUILDING_UPDATED,
        organization_id=building.organization_id,
        actor=actor,
        subject_type="building",
        subject_id=building.id,
        before=before,
        after={"name": name},
    )
    return building


# --- Units ------------------------------------------------------------------------------


def list_units(db: Session, property_id: uuid.UUID) -> list[Unit]:
    units = list(db.scalars(select(Unit).where(Unit.property_id == property_id)))
    building_names = {building.id: building.name for building in list_buildings(db, property_id)}
    return sorted(
        units,
        key=lambda unit: (
            _natural_key(building_names.get(unit.building_id, "")) if unit.building_id else [],
            _natural_key(unit.label),
        ),
    )


def get_unit(db: Session, *, organization_id: uuid.UUID, unit_id: uuid.UUID) -> Unit | None:
    return db.scalar(
        select(Unit).where(Unit.id == unit_id, Unit.organization_id == organization_id)
    )


def _check_building(db: Session, property_: Property, building_id: uuid.UUID | None) -> None:
    if building_id is None:
        return
    found = get_building(
        db,
        organization_id=property_.organization_id,
        property_id=property_.id,
        building_id=building_id,
    )
    if found is None:
        raise BuildingNotInPropertyError(str(building_id))


def _unit_label_taken(
    db: Session,
    property_id: uuid.UUID,
    building_id: uuid.UUID | None,
    label: str,
    *,
    excluding: uuid.UUID | None = None,
) -> bool:
    statement = select(Unit.id).where(
        Unit.property_id == property_id,
        func.lower(Unit.label) == label.lower(),
        Unit.building_id.is_(None) if building_id is None else Unit.building_id == building_id,
    )
    if excluding is not None:
        statement = statement.where(Unit.id != excluding)
    return db.scalar(statement) is not None


def create_unit(
    db: Session, property_: Property, *, actor: User, label: str, building_id: uuid.UUID | None
) -> Unit:
    _check_building(db, property_, building_id)
    if _unit_label_taken(db, property_.id, building_id, label):
        raise DuplicateNameError(label)

    unit = Unit(
        organization_id=property_.organization_id,
        property_id=property_.id,
        building_id=building_id,
        label=label,
    )
    db.add(unit)
    db.flush()
    record_event(
        db,
        event_type=EventType.UNIT_CREATED,
        organization_id=property_.organization_id,
        actor=actor,
        subject_type="unit",
        subject_id=unit.id,
        after={
            "property_id": str(property_.id),
            "building_id": str(building_id) if building_id else None,
            "label": label,
        },
    )
    return unit


def update_unit(
    db: Session,
    unit: Unit,
    property_: Property,
    *,
    actor: User,
    label: str,
    building_id: uuid.UUID | None,
) -> Unit:
    new_values = {"label": label, "building_id": building_id}
    before, after = _changes(unit, new_values)
    if not after:
        return unit

    _check_building(db, property_, building_id)
    if _unit_label_taken(db, unit.property_id, building_id, label, excluding=unit.id):
        raise DuplicateNameError(label)

    for field, value in after.items():
        setattr(unit, field, value)
    db.flush()

    def printable(values: dict[str, Any]) -> dict[str, Any]:
        return {
            key: str(value) if isinstance(value, uuid.UUID) else value
            for key, value in values.items()
        }

    record_event(
        db,
        event_type=EventType.UNIT_UPDATED,
        organization_id=unit.organization_id,
        actor=actor,
        subject_type="unit",
        subject_id=unit.id,
        before=printable(before),
        after=printable(after),
    )
    return unit
