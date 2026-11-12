import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession, FileStoreDep
from app.core.storage import FileNotStoredError
from app.models import (
    CANCELLABLE_STATUSES,
    FINISHED_STATUSES,
    RequestAttachment,
    RequestStatus,
    Role,
    Visibility,
)
from app.schemas.requests import (
    AttachmentOut,
    MessageIn,
    RequesterOut,
    RequestIn,
    RequestSummaryOut,
    ResidentRequestOut,
    StaffAttachmentOut,
    StaffRequestIn,
    StaffRequestOut,
    StaffRequestSummaryOut,
    StaffTimelineEntryOut,
    StaffUpdateIn,
    TimelineEntryOut,
)
from app.services import attachments, directory, requests, residents
from app.services.attachments import AttachmentError, AttachmentLimitError
from app.services.requests import RequestError, RequestRow

router = APIRouter(prefix="/organizations/{organization_id}", tags=["requests"])

ResidentContext = Annotated[OrganizationContext, Depends(require_roles(Role.RESIDENT))]
StaffContext = Annotated[
    OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR, Role.MANAGER))
]

# Images are shown in the page. Everything else is downloaded.
INLINE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


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
        can_cancel=row.request.status in CANCELLABLE_STATUSES,
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


def _staff_summary(row: RequestRow) -> StaffRequestSummaryOut:
    return StaffRequestSummaryOut(
        **_summary_fields(row),
        property_id=row.request.property_id,
        resident_name=row.resident.full_name,
        submitted_on_behalf=row.request.submitted_on_behalf,
    )


def _staff_detail(db: DbSession, row: RequestRow) -> StaffRequestOut:
    return StaffRequestOut(
        **_staff_summary(row).model_dump(),
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
) -> list[StaffRequestSummaryOut]:
    rows = requests.list_for_staff(
        db,
        organization_id=context.organization.id,
        scope=context.property_scope,
        status=request_status,
        property_id=property_id,
    )
    return [_staff_summary(row) for row in rows]


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


# --- Attachments ------------------------------------------------------------------------


async def _read_upload(request: Request, limit: int) -> bytes:
    """Read the body, refusing as soon as it is too large rather than after it is all in memory."""
    too_large = HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        f"Files can be at most {limit // (1024 * 1024)} MB",
    )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_large

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


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


def _file_response(store: FileStoreDep, item: RequestAttachment) -> Response:
    try:
        data = store.read(item.storage_key)
    except FileNotStoredError as error:
        raise _not_found("File") from error
    disposition = "inline" if item.content_type in INLINE_TYPES else "attachment"
    return Response(
        content=data,
        media_type=item.content_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(item.filename)}",
            # The type was decided from the file's bytes. Browsers must not second-guess it.
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


FilenameQuery = Annotated[str, Query(min_length=1, max_length=255)]


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
    data = await _read_upload(request, request.app.state.settings.max_upload_bytes)
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
    return _file_response(store, item)


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
    data = await _read_upload(request, request.app.state.settings.max_upload_bytes)
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
    return _file_response(store, item)
