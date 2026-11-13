"""The contractor workspace: only the jobs assigned to the signed-in contractor (decision 0020).

Every lookup goes through the contractor's own current assignments. A job that is someone
else's, unassigned, or in another organization looks exactly like one that does not exist.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession, FileStoreDep
from app.api.uploads import FilenameQuery, file_response, read_upload
from app.models import (
    FINAL_STATUSES,
    AssignmentResponse,
    EntryKind,
    Role,
    WorkOrderStatus,
)
from app.schemas.jobs import (
    DeclineJobIn,
    JobAttachmentOut,
    JobEntryIn,
    JobEntryOut,
    JobOut,
    JobStatusIn,
    JobSummaryOut,
)
from app.services import attachments, dispatch, requests, residents, work_orders
from app.services.attachments import AttachmentError, AttachmentLimitError
from app.services.dispatch import CONTRACTOR_MOVES, Job
from app.services.work_orders import WorkOrderError

router = APIRouter(prefix="/organizations/{organization_id}/my-jobs", tags=["contractor jobs"])

ContractorContext = Annotated[OrganizationContext, Depends(require_roles(Role.CONTRACTOR))]


def _summary_fields(job: Job) -> dict[str, object]:
    order = job.row.work_order
    return {
        "id": order.id,
        "reference": work_orders.reference_for(order.number),
        "title": order.title,
        "status": order.status,
        "priority": order.priority,
        "category": order.category,
        "due_date": order.due_date,
        "overdue": work_orders.is_overdue(order, residents.today()),
        "property_name": job.row.property.name,
        "unit_label": job.row.unit.label if job.row.unit else None,
        "building_name": job.row.building.name if job.row.building else None,
        "response": job.assignment.response,
    }


def _first_name(full_name: str) -> str:
    return full_name.split()[0] if full_name.split() else full_name


def _job_detail(db: DbSession, context: OrganizationContext, job: Job) -> JobOut:
    order = job.row.work_order
    accepted = job.assignment.response == AssignmentResponse.ACCEPTED
    pending = job.assignment.response == AssignmentResponse.PENDING
    current = WorkOrderStatus(order.status)

    # The person's name is a first name only, and entry instructions are shown once the job is
    # accepted. A phone number or email is never included: questions go through the manager.
    residents_here: list[str] = []
    access_notes: list[str] = []
    if accepted:
        linked = requests.list_for_work_order(
            db, organization_id=order.organization_id, work_order_id=order.id
        )
        for item in linked:
            for name in (_first_name(item.resident.full_name),):
                if name not in residents_here:
                    residents_here.append(name)
            for note in (item.resident.access_instructions, item.request.access_notes):
                if note and note not in access_notes:
                    access_notes.append(note)

    you = context.user.id
    timeline = []
    for entry, author in dispatch.contractor_entries(db, order.id):
        mine = entry.author_user_id == you
        timeline.append(
            JobEntryOut(
                id=entry.id,
                kind=entry.kind,
                body=entry.body if entry.kind != EntryKind.STATUS_CHANGED or mine else None,
                status=entry.status_after,
                author="You" if mine else ("System" if author is None else "Property team"),
                created_at=entry.created_at,
            )
        )

    allowed = (
        [status_ for status_ in WorkOrderStatus if (current, status_) in CONTRACTOR_MOVES]
        if accepted
        else []
    )
    return JobOut(
        **_summary_fields(job),
        scope=order.scope,
        street=job.row.property.street,
        city=job.row.property.city,
        region=job.row.property.region,
        postal_code=job.row.property.postal_code,
        residents=residents_here,
        access_notes=access_notes,
        can_accept=pending,
        can_decline=pending,
        allowed_statuses=allowed,
        timeline=timeline,
        attachments=[
            JobAttachmentOut(
                id=item.id,
                filename=item.filename,
                content_type=item.content_type,
                size_bytes=item.size_bytes,
                mine=item.uploaded_by_user_id == you,
                created_at=item.created_at,
            )
            for item in attachments.work_order_attachments(db, order.id, contractor_only=True)
        ],
    )


def _job(db: DbSession, context: OrganizationContext, work_order_id: uuid.UUID) -> Job:
    job = dispatch.get_job(
        db,
        organization_id=context.organization.id,
        membership_id=context.membership.id,
        work_order_id=work_order_id,
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


def _refuse(error: WorkOrderError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(error))


@router.get("")
def list_jobs(context: ContractorContext, db: DbSession) -> list[JobSummaryOut]:
    jobs = dispatch.jobs_for(
        db, organization_id=context.organization.id, membership_id=context.membership.id
    )
    return [JobSummaryOut(**_summary_fields(job)) for job in jobs]


@router.get("/{work_order_id}")
def read_job(work_order_id: uuid.UUID, context: ContractorContext, db: DbSession) -> JobOut:
    return _job_detail(db, context, _job(db, context, work_order_id))


@router.post("/{work_order_id}/accept")
def accept_job(work_order_id: uuid.UUID, context: ContractorContext, db: DbSession) -> JobOut:
    job = _job(db, context, work_order_id)
    try:
        dispatch.accept(db, job, actor=context.user)
    except WorkOrderError as error:
        raise _refuse(error) from error
    db.commit()
    return _job_detail(db, context, _job(db, context, work_order_id))


@router.post("/{work_order_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_job(
    work_order_id: uuid.UUID, body: DeclineJobIn, context: ContractorContext, db: DbSession
) -> None:
    job = _job(db, context, work_order_id)
    try:
        dispatch.decline(db, job, actor=context.user, reason=body.reason)
    except WorkOrderError as error:
        raise _refuse(error) from error
    db.commit()


@router.post("/{work_order_id}/status")
def change_job_status(
    work_order_id: uuid.UUID, body: JobStatusIn, context: ContractorContext, db: DbSession
) -> JobOut:
    job = _job(db, context, work_order_id)
    try:
        dispatch.change_status(db, job, actor=context.user, new_status=body.status, note=body.note)
    except WorkOrderError as error:
        raise _refuse(error) from error
    db.commit()
    return _job_detail(db, context, _job(db, context, work_order_id))


@router.post("/{work_order_id}/entries", status_code=status.HTTP_201_CREATED)
def add_job_entry(
    work_order_id: uuid.UUID, body: JobEntryIn, context: ContractorContext, db: DbSession
) -> JobOut:
    job = _job(db, context, work_order_id)
    try:
        dispatch.add_entry(db, job, actor=context.user, kind=body.kind, body=body.body)
    except WorkOrderError as error:
        raise _refuse(error) from error
    db.commit()
    return _job_detail(db, context, _job(db, context, work_order_id))


@router.post("/{work_order_id}/attachments", status_code=status.HTTP_201_CREATED)
async def attach_to_job(
    work_order_id: uuid.UUID,
    request: Request,
    context: ContractorContext,
    db: DbSession,
    store: FileStoreDep,
    filename: FilenameQuery,
) -> JobAttachmentOut:
    job = await run_in_threadpool(_job, db, context, work_order_id)
    if WorkOrderStatus(job.row.work_order.status) in FINAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "This job is finished")
    if job.assignment.response != AssignmentResponse.ACCEPTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Accept the job first")
    data = await read_upload(request, request.app.state.settings.max_upload_bytes)

    def save() -> JobAttachmentOut:
        try:
            saved = attachments.add_work_order_attachment(
                db,
                store,
                job.row.work_order,
                actor=context.user,
                filename=filename,
                data=data,
                contractor_visible=True,
            )
        except AttachmentLimitError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except AttachmentError as error:
            raise HTTPException(422, str(error)) from error
        db.commit()
        db.refresh(saved)
        return JobAttachmentOut(
            id=saved.id,
            filename=saved.filename,
            content_type=saved.content_type,
            size_bytes=saved.size_bytes,
            mine=True,
            created_at=saved.created_at,
        )

    return await run_in_threadpool(save)


@router.get("/{work_order_id}/attachments/{attachment_id}")
def download_job_attachment(
    work_order_id: uuid.UUID,
    attachment_id: uuid.UUID,
    context: ContractorContext,
    db: DbSession,
    store: FileStoreDep,
) -> Response:
    job = _job(db, context, work_order_id)
    item = attachments.get_work_order_attachment(
        db,
        work_order_id=job.row.work_order.id,
        attachment_id=attachment_id,
        contractor_only=True,
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return file_response(store, item)
