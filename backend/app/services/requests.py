import uuid
from dataclasses import dataclass

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.permissions import PropertyScope
from app.models import (
    CANCELLABLE_STATUSES,
    FINISHED_STATUSES,
    Building,
    EventType,
    MaintenanceRequest,
    Property,
    RequestAttachment,
    RequestCategory,
    RequestCounter,
    RequestStatus,
    RequestUpdate,
    Resident,
    Unit,
    UpdateKind,
    Urgency,
    User,
    Visibility,
)
from app.services.activity import record_event

REFERENCE_PREFIX = "REQ-"
LIST_LIMIT = 200


class RequestError(Exception):
    """An action the request's current state does not allow. The message is safe to show."""


@dataclass(frozen=True)
class RequestRow:
    """A request with the place and person it refers to."""

    request: MaintenanceRequest
    property: Property
    unit: Unit
    building: Building | None
    resident: Resident


def reference_for(number: int) -> str:
    return f"{REFERENCE_PREFIX}{number:04d}"


def _next_number(db: Session, organization_id: uuid.UUID) -> int:
    """Give out the next reference number. The UPDATE locks the counter row until commit, so
    two requests submitted at once cannot receive the same number."""
    if db.get(RequestCounter, organization_id) is None:
        db.add(RequestCounter(organization_id=organization_id, last_number=0))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise RequestError("Please try submitting again") from None
    db.execute(
        update(RequestCounter)
        .where(RequestCounter.organization_id == organization_id)
        .values(last_number=RequestCounter.last_number + 1)
    )
    number = db.scalar(
        select(RequestCounter.last_number).where(RequestCounter.organization_id == organization_id)
    )
    assert number is not None
    return number


# --- Creating and changing ---------------------------------------------------------------


def create_request(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor: User,
    resident: Resident,
    unit: Unit,
    category: RequestCategory,
    urgency: Urgency,
    title: str,
    description: str,
    location: str | None,
    access_notes: str | None,
    on_behalf: bool,
) -> MaintenanceRequest:
    request = MaintenanceRequest(
        organization_id=organization_id,
        number=_next_number(db, organization_id),
        property_id=unit.property_id,
        unit_id=unit.id,
        resident_id=resident.id,
        submitted_by_user_id=actor.id,
        submitted_on_behalf=on_behalf,
        category=category,
        urgency=urgency,
        status=RequestStatus.SUBMITTED,
        title=title,
        description=description,
        location=location,
        access_notes=access_notes,
    )
    db.add(request)
    db.flush()
    _add_update(
        db,
        request,
        actor=actor,
        kind=UpdateKind.SUBMITTED,
        visibility=Visibility.RESIDENT,
        body=None,
        status_after=RequestStatus.SUBMITTED,
    )
    record_event(
        db,
        event_type=EventType.REQUEST_SUBMITTED,
        organization_id=organization_id,
        actor=actor,
        subject_type="maintenance_request",
        subject_id=request.id,
        # The wording of the report stays on the request itself, out of the shared history.
        after={
            "reference": reference_for(request.number),
            "unit_id": str(unit.id),
            "category": category,
            "urgency": urgency,
            "on_behalf": on_behalf,
        },
    )
    return request


def _add_update(
    db: Session,
    request: MaintenanceRequest,
    *,
    actor: User | None,
    kind: UpdateKind,
    visibility: Visibility,
    body: str | None,
    status_after: RequestStatus | None = None,
) -> RequestUpdate:
    update_ = RequestUpdate(
        organization_id=request.organization_id,
        request_id=request.id,
        author_user_id=actor.id if actor else None,
        kind=kind,
        visibility=visibility,
        body=body,
        status_after=status_after,
    )
    db.add(update_)
    db.flush()
    return update_


def post_staff_update(
    db: Session,
    request: MaintenanceRequest,
    *,
    actor: User,
    body: str | None,
    visibility: Visibility,
    new_status: RequestStatus | None,
) -> list[RequestUpdate]:
    """A manager's note or message, optionally moving the request to a new status.

    A status change is always visible to the resident, because they are following it. The
    note that goes with it is visible only if the manager chose so.
    """
    entries: list[RequestUpdate] = []
    if new_status is not None:
        entries.append(_change_status(db, request, actor=actor, new_status=new_status))
    if body:
        kind = UpdateKind.MESSAGE if visibility == Visibility.RESIDENT else UpdateKind.NOTE
        entries.append(
            _add_update(db, request, actor=actor, kind=kind, visibility=visibility, body=body)
        )
    request.updated_at = utc_now()
    return entries


def _change_status(
    db: Session, request: MaintenanceRequest, *, actor: User, new_status: RequestStatus
) -> RequestUpdate:
    if request.status in FINISHED_STATUSES:
        raise RequestError("This request is finished and can no longer change status")
    if request.status == new_status:
        raise RequestError("The request already has this status")
    if new_status == RequestStatus.SUBMITTED:
        raise RequestError("A request cannot go back to submitted")

    before = request.status
    request.status = new_status
    entry = _add_update(
        db,
        request,
        actor=actor,
        kind=UpdateKind.STATUS_CHANGED,
        visibility=Visibility.RESIDENT,
        body=None,
        status_after=new_status,
    )
    record_event(
        db,
        event_type=EventType.REQUEST_STATUS_CHANGED,
        organization_id=request.organization_id,
        actor=actor,
        subject_type="maintenance_request",
        subject_id=request.id,
        before={"status": before},
        after={"status": new_status},
    )
    return entry


def post_resident_message(
    db: Session, request: MaintenanceRequest, *, actor: User, body: str
) -> RequestUpdate:
    if request.status in FINISHED_STATUSES:
        raise RequestError("This request is finished. Submit a new request if the problem is back")
    entry = _add_update(
        db,
        request,
        actor=actor,
        kind=UpdateKind.MESSAGE,
        visibility=Visibility.RESIDENT,
        body=body,
    )
    request.updated_at = utc_now()
    return entry


def cancel_request(db: Session, request: MaintenanceRequest, *, actor: User) -> None:
    if request.status not in CANCELLABLE_STATUSES:
        raise RequestError("Work has already started, so this request can no longer be withdrawn")
    _change_status(db, request, actor=actor, new_status=RequestStatus.CANCELLED)
    request.updated_at = utc_now()


# --- Reading -----------------------------------------------------------------------------


def _rows(db: Session, statement: Select[tuple[MaintenanceRequest]]) -> list[RequestRow]:
    result = db.execute(
        statement.join(Property, Property.id == MaintenanceRequest.property_id)
        .join(Unit, Unit.id == MaintenanceRequest.unit_id)
        .outerjoin(Building, Building.id == Unit.building_id)
        .join(Resident, Resident.id == MaintenanceRequest.resident_id)
        .add_columns(Property, Unit, Building, Resident)
    )
    return [
        RequestRow(request=request, property=property_, unit=unit, building=building, resident=res)
        for request, property_, unit, building, res in result
    ]


def _newest_first(
    statement: Select[tuple[MaintenanceRequest]],
) -> Select[tuple[MaintenanceRequest]]:
    return statement.order_by(MaintenanceRequest.number.desc()).limit(LIST_LIMIT)


def list_for_resident(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> list[RequestRow]:
    """Requests about the person's own directory records, including from homes they have left."""
    statement = select(MaintenanceRequest).where(
        MaintenanceRequest.organization_id == organization_id,
        Resident.user_id == user_id,
        Resident.organization_id == organization_id,
    )
    return _rows(db, _newest_first(statement))


def get_for_resident(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID, request_id: uuid.UUID
) -> RequestRow | None:
    statement = select(MaintenanceRequest).where(
        MaintenanceRequest.id == request_id,
        MaintenanceRequest.organization_id == organization_id,
        Resident.user_id == user_id,
        Resident.organization_id == organization_id,
    )
    rows = _rows(db, statement)
    return rows[0] if rows else None


def list_for_staff(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    status: RequestStatus | None = None,
    property_id: uuid.UUID | None = None,
) -> list[RequestRow]:
    statement = select(MaintenanceRequest).where(
        MaintenanceRequest.organization_id == organization_id
    )
    if not scope.unrestricted:
        statement = statement.where(MaintenanceRequest.property_id.in_(scope.property_ids))
    if status is not None:
        statement = statement.where(MaintenanceRequest.status == status)
    if property_id is not None:
        statement = statement.where(MaintenanceRequest.property_id == property_id)
    return _rows(db, _newest_first(statement))


def get_for_staff(
    db: Session, *, organization_id: uuid.UUID, scope: PropertyScope, request_id: uuid.UUID
) -> RequestRow | None:
    statement = select(MaintenanceRequest).where(
        MaintenanceRequest.id == request_id,
        MaintenanceRequest.organization_id == organization_id,
    )
    if not scope.unrestricted:
        statement = statement.where(MaintenanceRequest.property_id.in_(scope.property_ids))
    rows = _rows(db, statement)
    return rows[0] if rows else None


def timeline(
    db: Session, request_id: uuid.UUID, *, include_internal: bool
) -> list[tuple[RequestUpdate, User | None]]:
    """Oldest first. Callers choose whether internal entries are included, and the resident
    views never ask for them."""
    statement = (
        select(RequestUpdate, User)
        .outerjoin(User, User.id == RequestUpdate.author_user_id)
        .where(RequestUpdate.request_id == request_id)
        .order_by(RequestUpdate.created_at, RequestUpdate.id)
    )
    if not include_internal:
        statement = statement.where(RequestUpdate.visibility == Visibility.RESIDENT)
    return [(entry, author) for entry, author in db.execute(statement)]


def attachments_for(
    db: Session, request_id: uuid.UUID, *, include_internal: bool
) -> list[RequestAttachment]:
    statement = (
        select(RequestAttachment)
        .where(RequestAttachment.request_id == request_id)
        .order_by(RequestAttachment.created_at, RequestAttachment.id)
    )
    if not include_internal:
        statement = statement.where(RequestAttachment.visibility == Visibility.RESIDENT)
    return list(db.scalars(statement))
