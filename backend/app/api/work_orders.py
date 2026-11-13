import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession
from app.models import Role, Urgency, WorkOrderStatus
from app.schemas.work_orders import (
    LinkedRequestOut,
    NoteIn,
    StatusChangeIn,
    WorkOrderEditIn,
    WorkOrderEntryOut,
    WorkOrderIn,
    WorkOrderOut,
    WorkOrderSummaryOut,
)
from app.services import directory, requests, residents, work_orders
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


def _summary(row: WorkOrderRow, request_count: int) -> WorkOrderSummaryOut:
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
    return WorkOrderOut(
        **_summary(row, len(linked)).model_dump(),
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
        allowed_statuses=work_orders.allowed_next_statuses(
            current, is_administrator=_is_administrator(context)
        ),
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
    q: Annotated[str | None, Query(max_length=100)] = None,
    older_than_days: Annotated[int | None, Query(ge=0, le=3650)] = None,
) -> list[WorkOrderSummaryOut]:
    rows = work_orders.list_for_staff(
        db,
        organization_id=context.organization.id,
        scope=context.property_scope,
        status=work_order_status,
        open_only=open_only,
        priority=priority,
        property_id=property_id,
        search=q,
        older_than_days=older_than_days,
    )
    counts = work_orders.request_counts(db, [row.work_order.id for row in rows])
    return [_summary(row, counts.get(row.work_order.id, 0)) for row in rows]


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


@router.post("/work-orders/{work_order_id}/notes", status_code=status.HTTP_201_CREATED)
def add_work_order_note(
    work_order_id: uuid.UUID, body: NoteIn, context: StaffContext, db: DbSession
) -> WorkOrderOut:
    row = _get(db, context, work_order_id)
    work_orders.add_note(
        db, row.work_order, actor=context.user, body=body.body, visibility=body.visibility
    )
    db.commit()
    return build_work_order(db, context, work_order_id)
