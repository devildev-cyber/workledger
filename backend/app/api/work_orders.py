import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession
from app.models import PROGRESS_STATUSES, Role, Urgency, User, WorkOrderStatus
from app.schemas.estimates import CostCheckOut, EstimateIn, EstimateOut
from app.schemas.work_orders import (
    AssignmentOut,
    LinkedRequestOut,
    NoteIn,
    SendBackIn,
    StatusChangeIn,
    VerifyIn,
    WorkOrderAttachmentOut,
    WorkOrderEditIn,
    WorkOrderEntryOut,
    WorkOrderIn,
    WorkOrderOut,
    WorkOrderSummaryOut,
)
from app.services import (
    attachments,
    directory,
    dispatch,
    estimates,
    ownerships,
    requests,
    residents,
    verification,
    work_orders,
)
from app.services.work_orders import NotPermittedError, WorkOrderError, WorkOrderRow

router = APIRouter(prefix="/organizations/{organization_id}", tags=["work orders"])

StaffContext = Annotated[
    OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR, Role.MANAGER))
]


def _not_found(what: str = "Work order") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def _refuse(error: WorkOrderError) -> HTTPException:
    code = status.HTTP_403_FORBIDDEN if isinstance(error, NotPermittedError) else 409
    return HTTPException(code, str(error))


def _is_administrator(context: OrganizationContext) -> bool:
    return Role.ADMINISTRATOR in context.roles


def _summary(
    row: WorkOrderRow, request_count: int, assignee: dispatch.Assignee | None
) -> WorkOrderSummaryOut:
    work_order = row.work_order
    return WorkOrderSummaryOut(
        id=work_order.id,
        reference=work_orders.reference_for(work_order.number),
        title=work_order.title,
        status=work_order.status,
        priority=work_order.priority,
        category=work_order.category,
        property_id=row.property.id,
        property_name=row.property.name,
        unit_label=row.unit.label if row.unit else None,
        building_name=row.building.name if row.building else None,
        due_date=work_order.due_date,
        overdue=work_orders.is_overdue(work_order, residents.today()),
        request_count=request_count,
        assignee_id=assignee.assignment.contractor_membership_id if assignee else None,
        assignee_name=assignee.name if assignee else None,
        assignment_response=assignee.assignment.response if assignee else None,
        final_cost_cents=work_order.final_cost_cents,
        currency=work_order.currency,
        created_at=work_order.created_at,
        updated_at=work_order.updated_at,
    )


def build_work_order(
    db: DbSession, context: OrganizationContext, work_order_id: uuid.UUID
) -> WorkOrderOut:
    row = _get(db, context, work_order_id)
    linked = requests.list_for_work_order(
        db, organization_id=context.organization.id, work_order_id=work_order_id
    )
    current = WorkOrderStatus(row.work_order.status)
    assignee = dispatch.assignees_for(db, [work_order_id]).get(work_order_id)
    history = dispatch.assignment_history(db, work_order_id)
    files = attachments.work_order_attachments(db, work_order_id, contractor_only=False)
    uploaders = {
        user.id: user.full_name
        for user in db.scalars(
            select(User).where(User.id.in_({item.uploaded_by_user_id for item in files}))
        )
    }
    verifier = (
        db.get(User, row.work_order.verified_by_user_id)
        if row.work_order.verified_by_user_id
        else None
    )
    hold = work_orders.approval_hold(db, row.work_order)
    allowed = work_orders.allowed_next_statuses(
        current, is_administrator=_is_administrator(context)
    )
    check = estimates.cost_check(db, row.work_order, row.property, row.work_order.final_cost_cents)
    return WorkOrderOut(
        **_summary(row, len(linked), assignee).model_dump(),
        scope=row.work_order.scope,
        linked_requests=[
            LinkedRequestOut(
                id=item.request.id,
                reference=requests.reference_for(item.request.number),
                title=item.request.title,
                status=item.request.status,
                resident_name=item.resident.full_name,
            )
            for item in linked
        ],
        history=[
            WorkOrderEntryOut(
                id=entry.id,
                kind=entry.kind,
                visibility=entry.visibility,
                body=entry.body,
                status=entry.status_after,
                details=entry.details,
                author_name=author.full_name if author else None,
                created_at=entry.created_at,
            )
            for entry, author in work_orders.history(db, work_order_id)
        ],
        assignment=next(
            (assignment_out(item) for item in history if item.assignment.ended_at is None), None
        ),
        assignment_history=[assignment_out(item) for item in history],
        attachments=[
            WorkOrderAttachmentOut(
                id=item.id,
                filename=item.filename,
                content_type=item.content_type,
                size_bytes=item.size_bytes,
                contractor_visible=item.contractor_visible,
                uploaded_by_name=uploaders.get(item.uploaded_by_user_id),
                created_at=item.created_at,
            )
            for item in files
        ],
        property_currency=row.property.currency,
        resolution=row.work_order.resolution,
        verified_by_name=verifier.full_name if verifier else None,
        verified_at=row.work_order.verified_at,
        estimates=[estimate_out(record) for record in estimates.records_for(db, work_order_id)],
        approval_threshold_cents=row.property.approval_threshold_cents,
        owner_names=ownerships.owner_names(db, row.property.id),
        approval_hold=hold,
        can_record_estimate=current in estimates.ESTIMATABLE,
        cost_check=CostCheckOut(**check) if check else None,
        # Work that is held for approval cannot be moved on by hand either.
        allowed_statuses=[
            item for item in allowed if hold is None or item not in PROGRESS_STATUSES
        ],
    )


def estimate_out(record: estimates.EstimateRecord) -> EstimateOut:
    item = record.estimate
    return EstimateOut(
        id=item.id,
        version=item.version,
        amount_cents=item.amount_cents,
        currency=item.currency,
        description=item.description,
        provider_name=item.provider_name,
        status=item.status,
        approval_required=item.approval_required,
        threshold_cents=item.threshold_cents,
        current=item.superseded_at is None,
        submitted_by_name=record.submitted_by_name,
        submitted_at=item.created_at,
        decided_by_name=record.decided_by_name,
        decided_at=item.decided_at,
        decision_reason=item.decision_reason,
    )


def assignment_out(record: dispatch.AssignmentRecord) -> AssignmentOut:
    item = record.assignment
    return AssignmentOut(
        id=item.id,
        contractor_id=item.contractor_membership_id,
        contractor_name=record.contractor_name,
        assigned_by_name=record.assigned_by_name,
        assigned_at=item.assigned_at,
        response=item.response,
        responded_at=item.responded_at,
        decline_reason=item.decline_reason,
        ended_at=item.ended_at,
        ended_reason=item.ended_reason,
    )


def _get(db: DbSession, context: OrganizationContext, work_order_id: uuid.UUID) -> WorkOrderRow:
    row = work_orders.get_for_staff(
        db,
        organization_id=context.organization.id,
        scope=context.property_scope,
        work_order_id=work_order_id,
    )
    if row is None:
        raise _not_found()
    return row


@router.get("/work-orders")
def list_work_orders(
    context: StaffContext,
    db: DbSession,
    work_order_status: Annotated[WorkOrderStatus | None, Query(alias="status")] = None,
    open_only: bool = False,
    priority: Urgency | None = None,
    property_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    history_only: bool = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    older_than_days: Annotated[int | None, Query(ge=0, le=3650)] = None,
    assignee_id: uuid.UUID | None = None,
    unassigned: bool = False,
) -> list[WorkOrderSummaryOut]:
    rows = work_orders.list_for_staff(
        db,
        organization_id=context.organization.id,
        scope=context.property_scope,
        status=work_order_status,
        open_only=open_only,
        priority=priority,
        property_id=property_id,
        unit_id=unit_id,
        history_only=history_only,
        search=q,
        older_than_days=older_than_days,
        assignee_id=assignee_id,
        unassigned=unassigned,
    )
    ids = [row.work_order.id for row in rows]
    counts = work_orders.request_counts(db, ids)
    assignees = dispatch.assignees_for(db, ids)
    return [
        _summary(row, counts.get(row.work_order.id, 0), assignees.get(row.work_order.id))
        for row in rows
    ]


@router.post("/work-orders", status_code=status.HTTP_201_CREATED)
def create_work_order(body: WorkOrderIn, context: StaffContext, db: DbSession) -> WorkOrderOut:
    property_ = directory.get_property(
        db, organization_id=context.organization.id, property_id=body.property_id
    )
    if property_ is None or not context.property_scope.allows(property_.id):
        raise _not_found("Property")
    unit = None
    if body.unit_id is not None:
        unit = directory.get_unit(db, organization_id=context.organization.id, unit_id=body.unit_id)
        if unit is None or unit.property_id != property_.id:
            raise HTTPException(422, "That unit is not in this property")
    created = work_orders.create_work_order(
        db,
        organization_id=context.organization.id,
        actor=context.user,
        property_=property_,
        unit=unit,
        title=body.title,
        scope=body.scope,
        category=body.category,
        priority=body.priority,
        due_date=body.due_date,
    )
    db.commit()
    return build_work_order(db, context, created.id)


@router.get("/work-orders/{work_order_id}")
def read_work_order(work_order_id: uuid.UUID, context: StaffContext, db: DbSession) -> WorkOrderOut:
    return build_work_order(db, context, work_order_id)


@router.put("/work-orders/{work_order_id}")
def edit_work_order(
    work_order_id: uuid.UUID, body: WorkOrderEditIn, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    row = _get(db, context, work_order_id)
    try:
        changed = work_orders.update_details(
            db, row.work_order, actor=context.user, values=body.model_dump()
        )
    except WorkOrderError as error:
        raise _refuse(error) from error
    if changed:
        db.commit()
    return build_work_order(db, context, work_order_id)


@router.post("/work-orders/{work_order_id}/status")
def change_work_order_status(
    work_order_id: uuid.UUID, body: StatusChangeIn, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    row = _get(db, context, work_order_id)
    try:
        work_orders.change_status(
            db,
            row.work_order,
            actor=context.user,
            new_status=body.status,
            note=body.note,
            is_administrator=_is_administrator(context),
        )
    except WorkOrderError as error:
        raise _refuse(error) from error
    db.commit()
    return build_work_order(db, context, work_order_id)


@router.post("/work-orders/{work_order_id}/verify")
def verify_work_order(
    work_order_id: uuid.UUID, body: VerifyIn, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    row = _get(db, context, work_order_id)
    try:
        verification.verify(
            db,
            row.work_order,
            actor=context.user,
            property_=row.property,
            resolution=body.resolution,
            final_cost_cents=body.final_cost_cents,
            currency=body.currency,
        )
    except WorkOrderError as error:
        raise _refuse(error) from error
    db.commit()
    return build_work_order(db, context, work_order_id)


@router.post("/work-orders/{work_order_id}/send-back")
def send_back_work_order(
    work_order_id: uuid.UUID, body: SendBackIn, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    row = _get(db, context, work_order_id)
    try:
        verification.send_back(db, row.work_order, actor=context.user, reason=body.reason)
    except WorkOrderError as error:
        raise _refuse(error) from error
    db.commit()
    return build_work_order(db, context, work_order_id)


@router.post("/work-orders/{work_order_id}/estimates", status_code=status.HTTP_201_CREATED)
def record_estimate(
    work_order_id: uuid.UUID, body: EstimateIn, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    row = _get(db, context, work_order_id)
    try:
        estimates.submit(
            db,
            row.work_order,
            actor=context.user,
            property_=row.property,
            amount_cents=body.amount_cents,
            description=body.description,
            provider_name=body.provider_name,
        )
    except WorkOrderError as error:
        raise _refuse(error) from error
    db.commit()
    return build_work_order(db, context, work_order_id)


@router.post("/work-orders/{work_order_id}/notes", status_code=status.HTTP_201_CREATED)
def add_work_order_note(
    work_order_id: uuid.UUID, body: NoteIn, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    row = _get(db, context, work_order_id)
    work_orders.add_note(
        db,
        row.work_order,
        actor=context.user,
        body=body.body,
        visibility=body.visibility,
        share_with_contractor=body.share_with_contractor,
    )
    db.commit()
    return build_work_order(db, context, work_order_id)
