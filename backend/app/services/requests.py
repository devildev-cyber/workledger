import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import Select, func, or_, select
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
from app.services.numbering import next_number

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
        number=next_number(db, RequestCounter, organization_id),
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
        if request.work_order_id is not None:
            raise RequestError(
                "This request follows its work order. Change the work order's status instead"
            )
        if new_status == RequestStatus.DECLINED:
            raise RequestError("Use Decline, so the resident is given a reason")
        entries.append(_change_status(db, request, actor=actor, new_status=new_status))
    if body:
        kind = UpdateKind.MESSAGE if visibility == Visibility.RESIDENT else UpdateKind.NOTE
        entries.append(
            _add_update(db, request, actor=actor, kind=kind, visibility=visibility, body=body)
        )
    request.updated_at = utc_now()
    return entries


def _change_status(
    db: Session,
    request: MaintenanceRequest,
    *,
    actor: User,
    new_status: RequestStatus,
    allow_reopen: bool = False,
) -> RequestUpdate:
    reopening = allow_reopen and request.status == RequestStatus.CLOSED
    if request.status in FINISHED_STATUSES and not reopening:
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


def change_status_for_work_order(
    db: Session, request: MaintenanceRequest, *, actor: User, new_status: RequestStatus
) -> None:
    """Move a linked request along with its work order, including back out of closed when an
    administrator reopens the work. A request the resident withdrew or that was declined, or
    that already has this status, is left alone rather than treated as an error."""
    if request.status in (RequestStatus.CANCELLED, RequestStatus.DECLINED):
        return
    if request.status == new_status:
        return
    _change_status(db, request, actor=actor, new_status=new_status, allow_reopen=True)
    request.updated_at = utc_now()


def add_staff_message(
    db: Session, request: MaintenanceRequest, *, actor: User, body: str
) -> RequestUpdate:
    """A message the resident can read, posted by staff."""
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


# --- Triage -----------------------------------------------------------------------------


def _require_triageable(request: MaintenanceRequest) -> None:
    if request.status not in (RequestStatus.SUBMITTED, RequestStatus.IN_REVIEW):
        raise RequestError("This request has already been dealt with")
    if request.work_order_id is not None or request.duplicate_of_id is not None:
        raise RequestError("This request is already linked to other work")


def require_triageable(request: MaintenanceRequest) -> None:
    _require_triageable(request)


def needs_triage(request: MaintenanceRequest) -> bool:
    return (
        request.status in (RequestStatus.SUBMITTED, RequestStatus.IN_REVIEW)
        and request.work_order_id is None
        and request.duplicate_of_id is None
    )


def decline_request(db: Session, request: MaintenanceRequest, *, actor: User, reason: str) -> None:
    """Turn a request down. The resident always sees the reason."""
    _require_triageable(request)
    _change_status(db, request, actor=actor, new_status=RequestStatus.DECLINED)
    _add_update(
        db,
        request,
        actor=actor,
        kind=UpdateKind.MESSAGE,
        visibility=Visibility.RESIDENT,
        body=reason,
    )
    request.updated_at = utc_now()
    record_event(
        db,
        event_type=EventType.REQUEST_DECLINED,
        organization_id=request.organization_id,
        actor=actor,
        subject_type="maintenance_request",
        subject_id=request.id,
        after={"reference": reference_for(request.number)},
    )


def mark_duplicate(
    db: Session,
    request: MaintenanceRequest,
    original: MaintenanceRequest,
    *,
    actor: User,
) -> None:
    """Record that this is another report of a problem already reported.

    The resident keeps following their own request. It is tied to the original so that it
    moves with the same work, and it says nothing about who made the other report.
    """
    _require_triageable(request)
    if original.id == request.id:
        raise RequestError("A request cannot be a duplicate of itself")
    if original.organization_id != request.organization_id:
        raise RequestError("That request cannot be found")
    if original.property_id != request.property_id:
        raise RequestError("Duplicates must be at the same property")
    if original.duplicate_of_id is not None:
        raise RequestError("That request is itself a duplicate. Choose the original")
    if original.status in FINISHED_STATUSES:
        raise RequestError("That request is already finished")

    request.duplicate_of_id = original.id
    if request.status == RequestStatus.SUBMITTED:
        _change_status(db, request, actor=actor, new_status=RequestStatus.IN_REVIEW)
    add_staff_message(
        db,
        request,
        actor=actor,
        body="We have linked your report with an earlier report of the same problem. "
        "Updates will appear here.",
    )
    record_event(
        db,
        event_type=EventType.REQUEST_MARKED_DUPLICATE,
        organization_id=request.organization_id,
        actor=actor,
        subject_type="maintenance_request",
        subject_id=request.id,
        after={
            "reference": reference_for(request.number),
            "duplicate_of": reference_for(original.number),
        },
    )


def get_request(
    db: Session, *, organization_id: uuid.UUID, request_id: uuid.UUID
) -> MaintenanceRequest | None:
    return db.scalar(
        select(MaintenanceRequest).where(
            MaintenanceRequest.id == request_id,
            MaintenanceRequest.organization_id == organization_id,
        )
    )


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


def can_withdraw(request: MaintenanceRequest) -> bool:
    """Once a work order exists the work is planned, so the resident messages instead."""
    return request.status in CANCELLABLE_STATUSES and request.work_order_id is None


def cancel_request(db: Session, request: MaintenanceRequest, *, actor: User) -> None:
    if not can_withdraw(request):
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


def _matches(search: str):  # noqa: ANN202 - a SQLAlchemy clause
    """Words in the summary, description, resident's name, or the reference number."""
    text = f"%{search.strip().lower()}%"
    clauses = [
        func.lower(MaintenanceRequest.title).like(text),
        func.lower(MaintenanceRequest.description).like(text),
        func.lower(Resident.full_name).like(text),
    ]
    digits = search.strip().upper().removeprefix(REFERENCE_PREFIX)
    if digits.isdigit():
        clauses.append(MaintenanceRequest.number == int(digits))
    return or_(*clauses)


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
    urgency: Urgency | None = None,
    needs_triage: bool = False,
    search: str | None = None,
    older_than_days: int | None = None,
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
    if urgency is not None:
        statement = statement.where(MaintenanceRequest.urgency == urgency)
    if needs_triage:
        statement = statement.where(
            MaintenanceRequest.status.in_([RequestStatus.SUBMITTED, RequestStatus.IN_REVIEW]),
            MaintenanceRequest.work_order_id.is_(None),
            MaintenanceRequest.duplicate_of_id.is_(None),
        )
    if older_than_days is not None:
        statement = statement.where(
            MaintenanceRequest.created_at <= utc_now() - timedelta(days=older_than_days)
        )
    if search:
        statement = statement.where(_matches(search))
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


def list_for_work_order(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> list[RequestRow]:
    statement = (
        select(MaintenanceRequest)
        .where(
            MaintenanceRequest.organization_id == organization_id,
            MaintenanceRequest.work_order_id == work_order_id,
        )
        .order_by(MaintenanceRequest.number)
    )
    return _rows(db, statement)


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
