import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession
from app.models import Building, Property, Resident, Role, Unit
from app.schemas.directory import (
    BuildingIn,
    BuildingOut,
    EndTenancyIn,
    ManagerOut,
    MyHomeOut,
    PropertyIn,
    PropertyOut,
    ResidentIn,
    ResidentOut,
    ResidentRefOut,
    SetManagersIn,
    StartTenancyIn,
    TenancyOut,
    UnitIn,
    UnitOut,
)
from app.services import assignments, directory, residents
from app.services.residents import Placement, TenancyError

router = APIRouter(prefix="/organizations/{organization_id}", tags=["directory"])

# Only administrators change the directory. Managers read what is in their properties
# (decisions 0008 and 0015). Everyone else has no access to it, except residents to their home.
AdminContext = Annotated[OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR))]
StaffContext = Annotated[
    OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR, Role.MANAGER))
]
ResidentContext = Annotated[OrganizationContext, Depends(require_roles(Role.RESIDENT))]

NAME_TAKEN = "That name is already used here"


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


# --- Lookups that respect organization and property scope -------------------------------


def _property_for(db: DbSession, context: OrganizationContext, property_id: uuid.UUID) -> Property:
    """A property of this organization the member may act on. Others look like missing ones."""
    found = directory.get_property(
        db, organization_id=context.organization.id, property_id=property_id
    )
    if found is None or not context.property_scope.allows(found.id):
        raise _not_found("Property")
    return found


def _unit_in(db: DbSession, property_: Property, unit_id: uuid.UUID) -> Unit:
    found = directory.get_unit(db, organization_id=property_.organization_id, unit_id=unit_id)
    if found is None or found.property_id != property_.id:
        raise _not_found("Unit")
    return found


def _resident_for(db: DbSession, context: OrganizationContext, resident_id: uuid.UUID) -> Resident:
    found = residents.get_resident(
        db, organization_id=context.organization.id, resident_id=resident_id
    )
    if found is None:
        raise _not_found("Resident")
    if not context.property_scope.unrestricted:
        visible = residents.placements_for_residents(
            db,
            organization_id=context.organization.id,
            resident_ids=[found.id],
            scope=context.property_scope,
        )
        if not visible[found.id]:
            raise _not_found("Resident")
    return found


# --- Output builders --------------------------------------------------------------------


def _property_out(db: DbSession, property_: Property, unit_count: int | None = None) -> PropertyOut:
    if unit_count is None:
        unit_count = directory.unit_counts(db, [property_.id]).get(property_.id, 0)
    return PropertyOut(
        id=property_.id,
        name=property_.name,
        street=property_.street,
        city=property_.city,
        region=property_.region,
        postal_code=property_.postal_code,
        currency=property_.currency,
        approval_threshold_cents=property_.approval_threshold_cents,
        unit_count=unit_count,
        buildings=[
            BuildingOut(id=building.id, name=building.name)
            for building in directory.list_buildings(db, property_.id)
        ],
    )


def _unit_out(unit: Unit, current: list[Resident]) -> UnitOut:
    return UnitOut(
        id=unit.id,
        property_id=unit.property_id,
        building_id=unit.building_id,
        label=unit.label,
        current_residents=[ResidentRefOut(id=r.id, full_name=r.full_name) for r in current],
    )


def _tenancy_out(placement: Placement, on: date) -> TenancyOut:
    return TenancyOut(
        id=placement.tenancy.id,
        unit_id=placement.unit.id,
        unit_label=placement.unit.label,
        building_name=placement.building.name if placement.building else None,
        property_id=placement.property.id,
        property_name=placement.property.name,
        move_in_date=placement.tenancy.move_in_date,
        move_out_date=placement.tenancy.move_out_date,
        is_current=placement.is_current(on),
    )


def _resident_out(resident: Resident, placements: list[Placement], on: date) -> ResidentOut:
    return ResidentOut(
        id=resident.id,
        full_name=resident.full_name,
        email=resident.email,
        phone=resident.phone,
        access_instructions=resident.access_instructions,
        has_account=resident.user_id is not None,
        tenancies=[_tenancy_out(placement, on) for placement in placements],
    )


def _managers_out(db: DbSession, property_: Property) -> list[ManagerOut]:
    assigned = assignments.assigned_membership_ids(db, property_.id)
    return [
        ManagerOut(
            membership_id=membership.id,
            full_name=membership.user.full_name,
            email=membership.user.email,
            assigned=membership.id in assigned,
        )
        for membership in assignments.manager_memberships(db, property_.organization_id)
    ]


# --- Properties -------------------------------------------------------------------------


@router.get("/properties")
def list_properties(context: StaffContext, db: DbSession) -> list[PropertyOut]:
    found = directory.list_properties(
        db, organization_id=context.organization.id, scope=context.property_scope
    )
    counts = directory.unit_counts(db, [property_.id for property_ in found])
    return [_property_out(db, item, counts.get(item.id, 0)) for item in found]


@router.post("/properties", status_code=status.HTTP_201_CREATED)
def create_property(body: PropertyIn, context: AdminContext, db: DbSession) -> PropertyOut:
    try:
        created = directory.create_property(
            db,
            organization_id=context.organization.id,
            actor=context.user,
            values=body.model_dump(),
        )
    except directory.DuplicateNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A property with this name exists") from None
    db.commit()
    return _property_out(db, created)


@router.get("/properties/{property_id}")
def read_property(property_id: uuid.UUID, context: StaffContext, db: DbSession) -> PropertyOut:
    return _property_out(db, _property_for(db, context, property_id))


@router.put("/properties/{property_id}")
def update_property(
    property_id: uuid.UUID, body: PropertyIn, context: AdminContext, db: DbSession
) -> PropertyOut:
    property_ = _property_for(db, context, property_id)
    try:
        directory.update_property(db, property_, actor=context.user, values=body.model_dump())
    except directory.DuplicateNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A property with this name exists") from None
    db.commit()
    return _property_out(db, property_)


# --- Buildings --------------------------------------------------------------------------


@router.post("/properties/{property_id}/buildings", status_code=status.HTTP_201_CREATED)
def create_building(
    property_id: uuid.UUID, body: BuildingIn, context: AdminContext, db: DbSession
) -> BuildingOut:
    property_ = _property_for(db, context, property_id)
    try:
        building = directory.create_building(db, property_, actor=context.user, name=body.name)
    except directory.DuplicateNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A building with this name exists") from None
    db.commit()
    return BuildingOut(id=building.id, name=building.name)


@router.put("/properties/{property_id}/buildings/{building_id}")
def rename_building(
    property_id: uuid.UUID,
    building_id: uuid.UUID,
    body: BuildingIn,
    context: AdminContext,
    db: DbSession,
) -> BuildingOut:
    property_ = _property_for(db, context, property_id)
    building: Building | None = directory.get_building(
        db,
        organization_id=property_.organization_id,
        property_id=property_.id,
        building_id=building_id,
    )
    if building is None:
        raise _not_found("Building")
    try:
        directory.rename_building(db, building, actor=context.user, name=body.name)
    except directory.DuplicateNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A building with this name exists") from None
    db.commit()
    return BuildingOut(id=building.id, name=building.name)


# --- Units ------------------------------------------------------------------------------


@router.get("/properties/{property_id}/units")
def list_units(property_id: uuid.UUID, context: StaffContext, db: DbSession) -> list[UnitOut]:
    property_ = _property_for(db, context, property_id)
    units = directory.list_units(db, property_.id)
    current = residents.current_residents_by_unit(
        db,
        organization_id=property_.organization_id,
        unit_ids=[unit.id for unit in units],
        on=residents.today(),
    )
    return [_unit_out(unit, current[unit.id]) for unit in units]


@router.post("/properties/{property_id}/units", status_code=status.HTTP_201_CREATED)
def create_unit(
    property_id: uuid.UUID, body: UnitIn, context: AdminContext, db: DbSession
) -> UnitOut:
    property_ = _property_for(db, context, property_id)
    try:
        unit = directory.create_unit(
            db, property_, actor=context.user, label=body.label, building_id=body.building_id
        )
    except directory.BuildingNotInPropertyError:
        raise _not_found("Building") from None
    except directory.DuplicateNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A unit with this name exists here") from None
    db.commit()
    return _unit_out(unit, [])


@router.put("/properties/{property_id}/units/{unit_id}")
def update_unit(
    property_id: uuid.UUID,
    unit_id: uuid.UUID,
    body: UnitIn,
    context: AdminContext,
    db: DbSession,
) -> UnitOut:
    property_ = _property_for(db, context, property_id)
    unit = _unit_in(db, property_, unit_id)
    try:
        directory.update_unit(
            db, unit, property_, actor=context.user, label=body.label, building_id=body.building_id
        )
    except directory.BuildingNotInPropertyError:
        raise _not_found("Building") from None
    except directory.DuplicateNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A unit with this name exists here") from None
    db.commit()
    current = residents.current_residents_by_unit(
        db, organization_id=unit.organization_id, unit_ids=[unit.id], on=residents.today()
    )
    return _unit_out(unit, current[unit.id])


# --- Managers of a property -------------------------------------------------------------


@router.get("/properties/{property_id}/managers")
def list_property_managers(
    property_id: uuid.UUID, context: AdminContext, db: DbSession
) -> list[ManagerOut]:
    return _managers_out(db, _property_for(db, context, property_id))


@router.put("/properties/{property_id}/managers")
def set_property_managers(
    property_id: uuid.UUID, body: SetManagersIn, context: AdminContext, db: DbSession
) -> list[ManagerOut]:
    property_ = _property_for(db, context, property_id)
    try:
        assignments.set_property_managers(
            db, property_, membership_ids=body.membership_ids, actor=context.user
        )
    except assignments.NotAManagerError:
        raise HTTPException(422, "Only members with the manager role can be assigned") from None
    db.commit()
    return _managers_out(db, property_)


# --- Residents --------------------------------------------------------------------------


@router.get("/residents")
def list_residents(context: StaffContext, db: DbSession) -> list[ResidentOut]:
    found = residents.list_residents(
        db, organization_id=context.organization.id, scope=context.property_scope
    )
    placements = residents.placements_for_residents(
        db,
        organization_id=context.organization.id,
        resident_ids=[resident.id for resident in found],
        scope=context.property_scope,
    )
    on = residents.today()
    return [_resident_out(resident, placements[resident.id], on) for resident in found]


def _resident_response(
    db: DbSession, context: OrganizationContext, resident: Resident
) -> ResidentOut:
    placements = residents.placements_for_residents(
        db,
        organization_id=context.organization.id,
        resident_ids=[resident.id],
        scope=context.property_scope,
    )
    return _resident_out(resident, placements[resident.id], residents.today())


@router.post("/residents", status_code=status.HTTP_201_CREATED)
def create_resident(body: ResidentIn, context: AdminContext, db: DbSession) -> ResidentOut:
    created = residents.create_resident(
        db, organization_id=context.organization.id, actor=context.user, **body.model_dump()
    )
    db.commit()
    return _resident_response(db, context, created)


@router.get("/residents/{resident_id}")
def read_resident(resident_id: uuid.UUID, context: StaffContext, db: DbSession) -> ResidentOut:
    return _resident_response(db, context, _resident_for(db, context, resident_id))


@router.put("/residents/{resident_id}")
def update_resident(
    resident_id: uuid.UUID, body: ResidentIn, context: AdminContext, db: DbSession
) -> ResidentOut:
    resident = _resident_for(db, context, resident_id)
    residents.update_resident(db, resident, actor=context.user, **body.model_dump())
    db.commit()
    return _resident_response(db, context, resident)


# --- Move-ins and move-outs -------------------------------------------------------------


@router.post("/tenancies", status_code=status.HTTP_201_CREATED)
def start_tenancy(body: StartTenancyIn, context: AdminContext, db: DbSession) -> TenancyOut:
    unit = directory.get_unit(db, organization_id=context.organization.id, unit_id=body.unit_id)
    if unit is None:
        raise _not_found("Unit")
    resident = _resident_for(db, context, body.resident_id)
    try:
        tenancy = residents.start_tenancy(
            db, unit=unit, resident=resident, move_in_date=body.move_in_date, actor=context.user
        )
    except TenancyError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    db.commit()
    return _tenancy_response(db, context, tenancy.id)


@router.post("/tenancies/{tenancy_id}/end")
def end_tenancy(
    tenancy_id: uuid.UUID, body: EndTenancyIn, context: AdminContext, db: DbSession
) -> TenancyOut:
    tenancy = residents.get_tenancy(
        db, organization_id=context.organization.id, tenancy_id=tenancy_id
    )
    if tenancy is None:
        raise _not_found("Move-in")
    try:
        residents.end_tenancy(db, tenancy, move_out_date=body.move_out_date, actor=context.user)
    except TenancyError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    db.commit()
    return _tenancy_response(db, context, tenancy.id)


def _tenancy_response(
    db: DbSession, context: OrganizationContext, tenancy_id: uuid.UUID
) -> TenancyOut:
    tenancy = residents.get_tenancy(
        db, organization_id=context.organization.id, tenancy_id=tenancy_id
    )
    assert tenancy is not None
    placements = residents.placements_for_residents(
        db,
        organization_id=context.organization.id,
        resident_ids=[tenancy.resident_id],
        scope=context.property_scope,
    )
    placement = next(
        item for item in placements[tenancy.resident_id] if item.tenancy.id == tenancy.id
    )
    return _tenancy_out(placement, residents.today())


# --- A resident's own home --------------------------------------------------------------


@router.get("/my-home")
def read_my_home(context: ResidentContext, db: DbSession) -> list[MyHomeOut]:
    placements = residents.current_placements_for_user(
        db,
        organization_id=context.organization.id,
        user_id=context.user.id,
        on=residents.today(),
    )
    return [
        MyHomeOut(
            tenancy_id=placement.tenancy.id,
            unit_id=placement.unit.id,
            property_name=placement.property.name,
            street=placement.property.street,
            city=placement.property.city,
            region=placement.property.region,
            postal_code=placement.property.postal_code,
            building_name=placement.building.name if placement.building else None,
            unit_label=placement.unit.label,
            move_in_date=placement.tenancy.move_in_date,
            move_out_date=placement.tenancy.move_out_date,
        )
        for placement in placements
    ]
