"""Managers assigning work orders to contractors, and sharing files with them."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession, FileStoreDep
from app.api.uploads import FilenameQuery, file_response, read_upload
from app.api.work_orders import build_work_order
from app.models import Role, WorkOrder, WorkOrderAttachment
from app.schemas.work_orders import AssignIn, ContractorOut, WorkOrderAttachmentOut, WorkOrderOut
from app.services import attachments, dispatch, work_orders
from app.services.attachments import AttachmentError, AttachmentLimitError
from app.services.work_orders import WorkOrderError

router = APIRouter(prefix="/organizations/{organization_id}", tags=["dispatch"])

StaffContext = Annotated[
    OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR, Role.MANAGER))
]


def _work_order(db: DbSession, context: OrganizationContext, work_order_id: uuid.UUID) -> WorkOrder:
    row = work_orders.get_for_staff(
        db,
        organization_id=context.organization.id,
        scope=context.property_scope,
        work_order_id=work_order_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found")
    return row.work_order


@router.get("/contractors")
def list_contractors(context: StaffContext, db: DbSession) -> list[ContractorOut]:
    return [
        ContractorOut(
            id=item.membership.id,
            full_name=item.user.full_name,
            email=item.user.email,
            active_jobs=item.active_jobs,
        )
        for item in dispatch.contractors(db, context.organization.id)
    ]


@router.post("/work-orders/{work_order_id}/assign")
def assign_work_order(
    work_order_id: uuid.UUID, body: AssignIn, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    work_order = _work_order(db, context, work_order_id)
    contractor = dispatch.get_contractor(
        db, organization_id=context.organization.id, membership_id=body.contractor_id
    )
    if contractor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contractor not found")
    try:
        dispatch.assign(db, work_order, actor=context.user, contractor=contractor)
    except WorkOrderError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    return build_work_order(db, context, work_order_id)


@router.post("/work-orders/{work_order_id}/unassign")
def unassign_work_order(
    work_order_id: uuid.UUID, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    work_order = _work_order(db, context, work_order_id)
    try:
        dispatch.unassign(db, work_order, actor=context.user)
    except WorkOrderError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    return build_work_order(db, context, work_order_id)


def _attachment_out(item: WorkOrderAttachment, uploader: str | None) -> WorkOrderAttachmentOut:
    return WorkOrderAttachmentOut(
        id=item.id,
        filename=item.filename,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        contractor_visible=item.contractor_visible,
        uploaded_by_name=uploader,
        created_at=item.created_at,
    )


@router.post("/work-orders/{work_order_id}/attachments", status_code=status.HTTP_201_CREATED)
async def attach_to_work_order(
    work_order_id: uuid.UUID,
    request: Request,
    context: StaffContext,
    db: DbSession,
    store: FileStoreDep,
    filename: FilenameQuery,
    contractor_visible: bool = False,
) -> WorkOrderAttachmentOut:
    work_order = await run_in_threadpool(_work_order, db, context, work_order_id)
    data = await read_upload(request, request.app.state.settings.max_upload_bytes)

    def save() -> WorkOrderAttachmentOut:
        try:
            saved = attachments.add_work_order_attachment(
                db,
                store,
                work_order,
                actor=context.user,
                filename=filename,
                data=data,
                contractor_visible=contractor_visible,
            )
        except AttachmentLimitError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except AttachmentError as error:
            raise HTTPException(422, str(error)) from error
        db.commit()
        db.refresh(saved)
        return _attachment_out(saved, context.user.full_name)

    return await run_in_threadpool(save)


@router.get("/work-orders/{work_order_id}/attachments/{attachment_id}")
def download_work_order_attachment(
    work_order_id: uuid.UUID,
    attachment_id: uuid.UUID,
    context: StaffContext,
    db: DbSession,
    store: FileStoreDep,
) -> Response:
    work_order = _work_order(db, context, work_order_id)
    item = attachments.get_work_order_attachment(
        db, work_order_id=work_order.id, attachment_id=attachment_id, contractor_only=False
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return file_response(store, item)
