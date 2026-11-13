import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession, FileStoreDep
from app.api.uploads import FilenameQuery, file_response, read_upload
from app.api.work_orders import build_work_order
from app.models import (
    FINISHED_STATUSES,
    MaintenanceRequest,
    RequestAttachment,
    RequestStatus,
    Role,
    Urgency,
    Visibility,
    WorkOrderStatus,
)
from app.schemas.requests import (
    AttachmentOut,
    MessageIn,
    RequesterOut,
    RequestIn,
    RequestLinkOut,
    RequestSummaryOut,
    ResidentRequestOut,
    StaffAttachmentOut,
    StaffRequestIn,
    StaffRequestOut,
    StaffRequestSummaryOut,
    StaffTimelineEntryOut,
    StaffUpdateIn,
    TimelineEntryOut,
    WorkOrderLinkOut,
)
from app.schemas.work_orders import ConvertIn, DeclineIn, DuplicateIn, WorkOrderOut
from app.services import attachments, directory, requests, residents, work_orders
from app.services.attachments import AttachmentError, AttachmentLimitError
from app.services.requests import RequestError, RequestRow

router = APIRouter(prefix="/organizations/{organization_id}", tags=["requests"])

ResidentContext = Annotated[OrganizationContext, Depends(require_roles(Role.RESIDENT))]
StaffContext = Annotated[
    OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR, Role.MANAGER))
]


def _not_found(what: str = "Request") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


# --- Resident output --------------------------------------------------------------------


def _summary_fields(row: RequestRow) -> dict[str, object]:
    return {
        "id": row.request.id,
        "reference": requests.reference_for(row.request.number),
        "status": row.request.status,
        "category": row.request.category,
        "urgency": row.request.urgency,
        "title": row.request.title,
        "property_name": row.property.name,
        "unit_label": row.unit.label,
        "building_name": row.building.name if row.building else None,
        "created_at": row.request.created_at,
        "updated_at": row.request.updated_at,
    }


def _resident_summary(row: RequestRow) -> RequestSummaryOut:
    return RequestSummaryOut.model_validate(_summary_fields(row))


def _resident_detail(
    db: DbSession, context: OrganizationContext, row: RequestRow
) -> ResidentRequestOut:
    """Built only from resident-visible rows. Internal entries are never loaded."""
    finished = row.request.status in FINISHED_STATUSES
    return ResidentRequestOut(
        **_summary_fields(row),
        description=row.request.description,
        location=row.request.location,
        access_notes=row.request.access_notes,
        can_cancel=requests.can_withdraw(row.request),
        can_message=not finished,
        timeline=[
            TimelineEntryOut(
                id=entry.id,
                kind=entry.kind,
                body=entry.body,
                status=entry.status_after,
                created_at=entry.created_at,
                author="You" if entry.author_user_id == context.user.id else "Property team",
            )
            for entry, _author in requests.timeline(db, row.request.id, include_internal=False)
        ],
        attachments=[
            AttachmentOut.model_validate(item, from_attributes=True)
            for item in requests.attachments_for(db, row.request.id, include_internal=False)
        ],
    )


# --- Staff output -----------------------------------------------------------------------


WorkOrderLinks = dict[uuid.UUID, tuple[int, WorkOrderStatus]]


def _work_order_links(db: DbSession, rows: list[RequestRow]) -> WorkOrderLinks:
    ids = {row.request.work_order_id for row in rows if row.request.work_order_id}
    return work_orders.numbers_and_statuses(db, ids)


def _staff_summary(row: RequestRow, links: WorkOrderLinks) -> StaffRequestSummaryOut:
    linked = links.get(row.request.work_order_id) if row.request.work_order_id else None
    return StaffRequestSummaryOut(
        **_summary_fields(row),
        property_id=row.request.property_id,
        resident_name=row.resident.full_name,
        submitted_on_behalf=row.request.submitted_on_behalf,
        work_order=WorkOrderLinkOut(
            id=row.request.work_order_id,
            reference=work_orders.reference_for(linked[0]),
            status=linked[1],
        )
        if linked and row.request.work_order_id
        else None,
        needs_triage=requests.needs_triage(row.request),
    )


def _staff_detail(db: DbSession, row: RequestRow) -> StaffRequestOut:
    original = (
        db.get(MaintenanceRequest, row.request.duplicate_of_id)
        if row.request.duplicate_of_id
        else None
    )
    return StaffRequestOut(
        **_staff_summary(row, _work_order_links(db, [row])).model_dump(),
        duplicate_of=RequestLinkOut(
            id=original.id, reference=requests.reference_for(original.number)
        )
        if original
        else None,
        description=row.request.description,
        location=row.request.location,
        access_notes=row.request.access_notes,
        resident=RequesterOut(
            id=row.resident.id,
            full_name=row.resident.full_name,
            email=row.resident.email,
            phone=row.resident.phone,
            access_instructions=row.resident.access_instructions,
            has_account=row.resident.user_id is not None,
        ),
        timeline=[
            StaffTimelineEntryOut(
                id=entry.id,
                kind=entry.kind,
                visibility=entry.visibility,
                body=entry.body,
                status=entry.status_after,
                created_at=entry.created_at,
                author_name=author.full_name if author else None,
            )
            for entry, author in requests.timeline(db, row.request.id, include_internal=True)
        ],
        attachments=[
            StaffAttachmentOut.model_validate(item, from_attributes=True)
            for item in requests.attachments_for(db, row.request.id, include_internal=True)
        ],
    )


# --- Lookups ----------------------------------------------------------------------------


def _own_request(db: DbSession, context: OrganizationContext, request_id: uuid.UUID) -> RequestRow:
    """A request about the signed-in resident. Anyone else's looks like a missing one."""
    row = requests.get_for_resident(
        db,
        organization_id=context.organization.id,
        user_id=context.user.id,
        request_id=request_id,
    )
    if row is None:
        raise _not_found()
    return row


def _staff_request(
    db: DbSession, context: OrganizationContext, request_id: uuid.UUID
) -> RequestRow:
    row = requests.get_for_staff(
        db,
        organization_id=context.organization.id,
        scope=context.property_scope,
        request_id=request_id,
    )
    if row is None:
        raise _not_found()
    return row


def _refuse(error: RequestError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(error))


# --- Resident endpoints -----------------------------------------------------------------


@router.get("/my-requests")
def list_my_requests(context: ResidentContext, db: DbSession) -> list[RequestSummaryOut]:
    rows = requests.list_for_resident(
        db, organization_id=context.organization.id, user_id=context.user.id
    )
    return [_resident_summary(row) for row in rows]


@router.post("/my-requests", status_code=status.HTTP_201_CREATED)
def submit_my_request(
    body: RequestIn, context: ResidentContext, db: DbSession
) -> ResidentRequestOut:
    placements = residents.current_placements_for_user(
        db,
        organization_id=context.organization.id,
        user_id=context.user.id,
        on=residents.today(),
    )
    placement = next((item for item in placements if item.unit.id == body.unit_id), None)
    if placement is None:
        raise HTTPException(422, "Choose one of your current homes")

    resident = residents.get_resident(
        db, organization_id=context.organization.id, resident_id=placement.tenancy.resident_id
    )
    assert resident is not None
    created = requests.create_request(
        db,
        organization_id=context.organization.id,
        actor=context.user,
        resident=resident,
        unit=placement.unit,
        category=body.category,
        urgency=body.urgency,
        title=body.title,
        description=body.description,
        location=body.location,
        access_notes=body.access_notes,
        on_behalf=False,
    )
    db.commit()
    return _resident_detail(db, context, _own_request(db, context, created.id))


@router.get("/my-requests/{request_id}")
def read_my_request(
    request_id: uuid.UUID, context: ResidentContext, db: DbSession
) -> ResidentRequestOut:
    return _resident_detail(db, context, _own_request(db, context, request_id))


@router.post("/my-requests/{request_id}/messages", status_code=status.HTTP_201_CREATED)
def message_on_my_request(
    request_id: uuid.UUID, body: MessageIn, context: ResidentContext, db: DbSession
) -> ResidentRequestOut:
    row = _own_request(db, context, request_id)
    try:
        requests.post_resident_message(db, row.request, actor=context.user, body=body.body)
    except RequestError as error:
        raise _refuse(error) from error
    db.commit()
    return _resident_detail(db, context, _own_request(db, context, request_id))


@router.post("/my-requests/{request_id}/cancel")
def cancel_my_request(
    request_id: uuid.UUID, context: ResidentContext, db: DbSession
) -> ResidentRequestOut:
    row = _own_request(db, context, request_id)
    try:
        requests.cancel_request(db, row.request, actor=context.user)
    except RequestError as error:
        raise _refuse(error) from error
    db.commit()
    return _resident_detail(db, context, _own_request(db, context, request_id))


# --- Staff endpoints --------------------------------------------------------------------


@router.get("/requests")
def list_requests(
    context: StaffContext,
    db: DbSession,
    request_status: Annotated[RequestStatus | None, Query(alias="status")] = None,
    property_id: uuid.UUID | None = None,
    urgency: Urgency | None = None,
    needs_triage: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    older_than_days: Annotated[int | None, Query(ge=0, le=3650)] = None,
) -> list[StaffRequestSummaryOut]:
    rows = requests.list_for_staff(
        db,
        organization_id=context.organization.id,
        scope=context.property_scope,
        status=request_status,
        property_id=property_id,
        urgency=urgency,
        needs_triage=needs_triage,
        search=q,
        older_than_days=older_than_days,
    )
    links = _work_order_links(db, rows)
    return [_staff_summary(row, links) for row in rows]


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def submit_request_for_resident(
    body: StaffRequestIn, context: StaffContext, db: DbSession
) -> StaffRequestOut:
    unit = directory.get_unit(db, organization_id=context.organization.id, unit_id=body.unit_id)
    if unit is None or not context.property_scope.allows(unit.property_id):
        raise _not_found("Unit")
    resident = residents.get_resident(
        db, organization_id=context.organization.id, resident_id=body.resident_id
    )
    if resident is None:
        raise _not_found("Resident")

    placements = residents.placements_for_residents(
        db,
        organization_id=context.organization.id,
        resident_ids=[resident.id],
        scope=context.property_scope,
    )[resident.id]
    today = residents.today()
    if not any(item.unit.id == unit.id and item.is_current(today) for item in placements):
        raise HTTPException(422, "That resident does not currently live in this unit")

    created = requests.create_request(
        db,
        organization_id=context.organization.id,
        actor=context.user,
        resident=resident,
        unit=unit,
        category=body.category,
        urgency=body.urgency,
        title=body.title,
        description=body.description,
        location=body.location,
        access_notes=body.access_notes,
        on_behalf=True,
    )
    db.commit()
    return _staff_detail(db, _staff_request(db, context, created.id))


@router.get("/requests/{request_id}")
def read_request(request_id: uuid.UUID, context: StaffContext, db: DbSession) -> StaffRequestOut:
    return _staff_detail(db, _staff_request(db, context, request_id))


@router.post("/requests/{request_id}/updates", status_code=status.HTTP_201_CREATED)
def update_request(
    request_id: uuid.UUID, body: StaffUpdateIn, context: StaffContext, db: DbSession
) -> StaffRequestOut:
    row = _staff_request(db, context, request_id)
    try:
        requests.post_staff_update(
            db,
            row.request,
            actor=context.user,
            body=body.body,
            visibility=body.visibility,
            new_status=body.status,
        )
    except RequestError as error:
        raise _refuse(error) from error
    db.commit()
    return _staff_detail(db, _staff_request(db, context, request_id))


# --- Triage -----------------------------------------------------------------------------


@router.post("/requests/{request_id}/convert", status_code=status.HTTP_201_CREATED)
def convert_request(
    request_id: uuid.UUID, body: ConvertIn, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    row = _staff_request(db, context, request_id)
    request = row.request
    try:
        created = work_orders.convert_request(
            db,
            request,
            actor=context.user,
            property_=row.property,
            unit=row.unit,
            title=body.title or request.title,
            scope=body.scope or request.description,
            category=body.category or request.category,
            priority=body.priority or request.urgency,
            due_date=body.due_date,
        )
    except RequestError as error:
        raise _refuse(error) from error
    db.commit()
    return build_work_order(db, context, created.id)


@router.post("/requests/{request_id}/duplicate")
def mark_request_duplicate(
    request_id: uuid.UUID, body: DuplicateIn, context: StaffContext, db: DbSession
) -> StaffRequestOut:
    row = _staff_request(db, context, request_id)
    if body.duplicate_of_id == request_id:
        raise HTTPException(422, "A request cannot be a duplicate of itself")
    original = _staff_request(db, context, body.duplicate_of_id)
    try:
        work_orders.mark_duplicate(db, row.request, original.request, actor=context.user)
    except RequestError as error:
        raise _refuse(error) from error
    db.commit()
    return _staff_detail(db, _staff_request(db, context, request_id))


@router.post("/requests/{request_id}/decline")
def decline_request(
    request_id: uuid.UUID, body: DeclineIn, context: StaffContext, db: DbSession
) -> StaffRequestOut:
    row = _staff_request(db, context, request_id)
    try:
        requests.decline_request(db, row.request, actor=context.user, reason=body.reason)
    except RequestError as error:
        raise _refuse(error) from error
    db.commit()
    return _staff_detail(db, _staff_request(db, context, request_id))


# --- Attachments ------------------------------------------------------------------------


def _save_attachment(
    db: DbSession,
    store: FileStoreDep,
    row: RequestRow,
    context: OrganizationContext,
    filename: str,
    data: bytes,
    visibility: Visibility,
) -> RequestAttachment:
    try:
        saved = attachments.add_attachment(
            db,
            store,
            row.request,
            actor=context.user,
            filename=filename,
            data=data,
            visibility=visibility,
        )
    except AttachmentLimitError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except AttachmentError as error:
        raise HTTPException(422, str(error)) from error
    db.commit()
    db.refresh(saved)
    return saved


@router.post("/my-requests/{request_id}/attachments", status_code=status.HTTP_201_CREATED)
async def attach_to_my_request(
    request_id: uuid.UUID,
    request: Request,
    context: ResidentContext,
    db: DbSession,
    store: FileStoreDep,
    filename: FilenameQuery,
) -> AttachmentOut:
    row = await run_in_threadpool(_own_request, db, context, request_id)
    if row.request.status in FINISHED_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "This request is finished")
    data = await read_upload(request, request.app.state.settings.max_upload_bytes)
    saved = await run_in_threadpool(
        _save_attachment, db, store, row, context, filename, data, Visibility.RESIDENT
    )
    return AttachmentOut.model_validate(saved, from_attributes=True)


@router.get("/my-requests/{request_id}/attachments/{attachment_id}")
def download_my_attachment(
    request_id: uuid.UUID,
    attachment_id: uuid.UUID,
    context: ResidentContext,
    db: DbSession,
    store: FileStoreDep,
) -> Response:
    row = _own_request(db, context, request_id)
    item = attachments.get_attachment(
        db, request=row.request, attachment_id=attachment_id, include_internal=False
    )
    if item is None:
        raise _not_found("File")
    return file_response(store, item)


@router.post("/requests/{request_id}/attachments", status_code=status.HTTP_201_CREATED)
async def attach_to_request(
    request_id: uuid.UUID,
    request: Request,
    context: StaffContext,
    db: DbSession,
    store: FileStoreDep,
    filename: FilenameQuery,
    visibility: Visibility = Visibility.INTERNAL,
) -> StaffAttachmentOut:
    row = await run_in_threadpool(_staff_request, db, context, request_id)
    data = await read_upload(request, request.app.state.settings.max_upload_bytes)
    saved = await run_in_threadpool(
        _save_attachment, db, store, row, context, filename, data, visibility
    )
    return StaffAttachmentOut.model_validate(saved, from_attributes=True)


@router.get("/requests/{request_id}/attachments/{attachment_id}")
def download_attachment(
    request_id: uuid.UUID,
    attachment_id: uuid.UUID,
    context: StaffContext,
    db: DbSession,
    store: FileStoreDep,
) -> Response:
    row = _staff_request(db, context, request_id)
    item = attachments.get_attachment(
        db, request=row.request, attachment_id=attachment_id, include_internal=True
    )
    if item is None:
        raise _not_found("File")
    return file_response(store, item)
