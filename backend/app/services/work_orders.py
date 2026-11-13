import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.permissions import PropertyScope
from app.models import (
    ADMINISTRATOR_ONLY_FROM,
    FINAL_STATUSES,
    PROGRESS_STATUSES,
    REVIEW_MOVES,
    SYSTEM_STATUSES,
    TRANSITIONS,
    AssignmentEnd,
    Building,
    EntryKind,
    Estimate,
    EstimateStatus,
    EventType,
    MaintenanceRequest,
    Property,
    RequestCategory,
    RequestStatus,
    Unit,
    Urgency,
    User,
    Visibility,
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderCounter,
    WorkOrderEntry,
    WorkOrderStatus,
)
from app.services import requests
from app.services.activity import record_event
from app.services.numbering import next_number

REFERENCE_PREFIX = "WO-"
LIST_LIMIT = 200
EDITABLE_FIELDS = ("title", "scope", "category", "priority", "due_date")

# What a resident is told about their request as the work order moves along.
REQUEST_STATUS_FOR: dict[WorkOrderStatus, RequestStatus] = {
    WorkOrderStatus.OPEN: RequestStatus.IN_REVIEW,
    WorkOrderStatus.ASSIGNED: RequestStatus.IN_PROGRESS,
    WorkOrderStatus.IN_PROGRESS: RequestStatus.IN_PROGRESS,
    WorkOrderStatus.ON_HOLD: RequestStatus.IN_PROGRESS,
    WorkOrderStatus.AWAITING_APPROVAL: RequestStatus.IN_PROGRESS,
    WorkOrderStatus.READY_FOR_REVIEW: RequestStatus.IN_PROGRESS,
    WorkOrderStatus.COMPLETED: RequestStatus.RESOLVED,
    WorkOrderStatus.CLOSED: RequestStatus.CLOSED,
    WorkOrderStatus.CANCELLED: RequestStatus.CLOSED,
}


class WorkOrderError(Exception):
    """A change the work order's current state does not allow. The message is safe to show."""


class NotPermittedError(WorkOrderError):
    """The change is valid, but only for a more senior role."""


class ApprovalRequiredError(WorkOrderError):
    """The work order's spending needs a property owner's approval first (decision 0022)."""


@dataclass(frozen=True)
class WorkOrderRow:
    work_order: WorkOrder
    property: Property
    unit: Unit | None
    building: Building | None


def reference_for(number: int) -> str:
    return f"{REFERENCE_PREFIX}{number:04d}"


def is_overdue(work_order: WorkOrder, today: date) -> bool:
    return (
        work_order.due_date is not None
        and work_order.due_date < today
        and WorkOrderStatus(work_order.status) not in FINAL_STATUSES
    )


def approval_hold(db: Session, work_order: WorkOrder) -> str | None:
    """Why work cannot go ahead yet, or None if it can.

    Work is held while the current estimate is above the property's threshold and has not been
    approved. Every status change passes through here, so no route can skip the owner. The
    message is written to be safe for anyone to read, including the contractor: no amounts.
    """
    current = db.scalar(
        select(Estimate).where(
            Estimate.work_order_id == work_order.id, Estimate.superseded_at.is_(None)
        )
    )
    if current is None or not current.approval_required:
        return None
    if current.status == EstimateStatus.APPROVED:
        return None
    if current.status == EstimateStatus.REJECTED:
        return "The property owner did not approve this work. Ask the property team"
    return "This work is waiting for the property owner's approval"


def allowed_next_statuses(
    current: WorkOrderStatus, *, is_administrator: bool
) -> list[WorkOrderStatus]:
    """What this person can move the work order to by hand, in a stable order."""
    if current in ADMINISTRATOR_ONLY_FROM and not is_administrator:
        return []
    reviewed = {new for old, new in REVIEW_MOVES if old == current}
    reachable = TRANSITIONS[current] - SYSTEM_STATUSES - reviewed
    return [status for status in WorkOrderStatus if status in reachable]


# --- History ----------------------------------------------------------------------------


def add_entry(
    db: Session,
    work_order: WorkOrder,
    *,
    actor: User | None,
    kind: EntryKind,
    visibility: Visibility = Visibility.INTERNAL,
    body: str | None = None,
    status_after: WorkOrderStatus | None = None,
    details: dict[str, Any] | None = None,
    contractor_visible: bool = False,
) -> WorkOrderEntry:
    entry = WorkOrderEntry(
        organization_id=work_order.organization_id,
        work_order_id=work_order.id,
        author_user_id=actor.id if actor else None,
        kind=kind,
        visibility=visibility,
        body=body,
        status_after=status_after,
        details=details,
        contractor_visible=contractor_visible,
    )
    db.add(entry)
    db.flush()
    return entry


# --- Creating ---------------------------------------------------------------------------


def create_work_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor: User,
    property_: Property,
    unit: Unit | None,
    title: str,
    scope: str,
    category: RequestCategory,
    priority: Urgency,
    due_date: date | None,
) -> WorkOrder:
    work_order = WorkOrder(
        organization_id=organization_id,
        number=next_number(db, WorkOrderCounter, organization_id),
        property_id=property_.id,
        unit_id=unit.id if unit else None,
        title=title,
        scope=scope,
        category=category,
        priority=priority,
        status=WorkOrderStatus.OPEN,
        due_date=due_date,
        created_by_user_id=actor.id,
    )
    db.add(work_order)
    db.flush()
    add_entry(
        db, work_order, actor=actor, kind=EntryKind.CREATED, status_after=WorkOrderStatus.OPEN
    )
    record_event(
        db,
        event_type=EventType.WORK_ORDER_CREATED,
        organization_id=organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=work_order.id,
        after={
            "reference": reference_for(work_order.number),
            "property_id": str(property_.id),
            "priority": priority,
        },
    )
    return work_order


def link_request(
    db: Session, work_order: WorkOrder, request: MaintenanceRequest, *, actor: User
) -> None:
    """Attach a request to a work order. From now on the work order decides its status."""
    request.work_order_id = work_order.id
    add_entry(
        db,
        work_order,
        actor=actor,
        kind=EntryKind.REQUEST_LINKED,
        body=f"{requests.reference_for(request.number)} linked",
    )
    requests.change_status_for_work_order(
        db,
        request,
        actor=actor,
        new_status=REQUEST_STATUS_FOR[WorkOrderStatus(work_order.status)],
    )


def convert_request(
    db: Session,
    request: MaintenanceRequest,
    *,
    actor: User,
    property_: Property,
    unit: Unit | None,
    title: str,
    scope: str,
    category: RequestCategory,
    priority: Urgency,
    due_date: date | None,
) -> WorkOrder:
    """Turn a request into a work order, bringing along any reports marked as duplicates."""
    requests.require_triageable(request)
    work_order = create_work_order(
        db,
        organization_id=request.organization_id,
        actor=actor,
        property_=property_,
        unit=unit,
        title=title,
        scope=scope,
        category=category,
        priority=priority,
        due_date=due_date,
    )
    link_request(db, work_order, request, actor=actor)
    duplicates = db.scalars(
        select(MaintenanceRequest).where(
            MaintenanceRequest.duplicate_of_id == request.id,
            MaintenanceRequest.work_order_id.is_(None),
        )
    )
    for duplicate in duplicates:
        link_request(db, work_order, duplicate, actor=actor)
    record_event(
        db,
        event_type=EventType.REQUEST_CONVERTED,
        organization_id=request.organization_id,
        actor=actor,
        subject_type="maintenance_request",
        subject_id=request.id,
        after={
            "reference": requests.reference_for(request.number),
            "work_order": reference_for(work_order.number),
        },
    )
    return work_order


def mark_duplicate(
    db: Session, request: MaintenanceRequest, original: MaintenanceRequest, *, actor: User
) -> None:
    """Mark a request as a repeat report. If the original already has a work order, the
    repeat joins it and follows its progress."""
    requests.mark_duplicate(db, request, original, actor=actor)
    if original.work_order_id is not None:
        work_order = db.get(WorkOrder, original.work_order_id)
        assert work_order is not None
        link_request(db, work_order, request, actor=actor)


# --- Changing ---------------------------------------------------------------------------


def sync_requests(db: Session, work_order: WorkOrder, *, actor: User) -> None:
    target = REQUEST_STATUS_FOR[WorkOrderStatus(work_order.status)]
    for request in db.scalars(
        select(MaintenanceRequest).where(MaintenanceRequest.work_order_id == work_order.id)
    ):
        requests.change_status_for_work_order(db, request, actor=actor, new_status=target)


def change_status(
    db: Session,
    work_order: WorkOrder,
    *,
    actor: User,
    new_status: WorkOrderStatus,
    note: str | None,
    is_administrator: bool,
    system: bool = False,
    review: bool = False,
) -> None:
    """Move a work order along its lifecycle.

    `system` is for dispatch, which sets the assigned status as a side effect of assigning.
    `review` is for verification, which verifies or sends back work that is ready for review.

    Every check happens before anything is changed, so a refused move leaves the work order,
    its history, and its requests exactly as they were.
    """
    current = WorkOrderStatus(work_order.status)
    if new_status == current:
        raise WorkOrderError("The work order already has this status")
    if new_status not in TRANSITIONS[current]:
        raise WorkOrderError(f"A work order cannot move from {current.value} to {new_status.value}")
    if new_status in SYSTEM_STATUSES and not system:
        raise WorkOrderError("That status is set automatically by assignment and approvals")
    if (current, new_status) in REVIEW_MOVES and not review:
        raise WorkOrderError(
            "Work that is ready for review is verified, or sent back with a reason"
        )
    if current in ADMINISTRATOR_ONLY_FROM and not is_administrator:
        raise NotPermittedError("Only an administrator can reopen a finished work order")
    if new_status == WorkOrderStatus.CLOSED and not work_order.resolution:
        raise WorkOrderError("Verify the work before closing the work order")
    if new_status in PROGRESS_STATUSES and (hold := approval_hold(db, work_order)):
        raise ApprovalRequiredError(hold)

    if current in (WorkOrderStatus.COMPLETED, WorkOrderStatus.CLOSED) and (
        new_status == WorkOrderStatus.IN_PROGRESS
    ):
        # Reopened: the old outcome no longer applies. The history keeps what was recorded.
        work_order.resolution = None
        work_order.final_cost_cents = None
        work_order.currency = None
        work_order.verified_by_user_id = None
        work_order.verified_at = None
    work_order.status = new_status
    work_order.updated_at = utc_now()
    add_entry(
        db,
        work_order,
        actor=actor,
        kind=EntryKind.STATUS_CHANGED,
        body=note,
        status_after=new_status,
        contractor_visible=True,
    )
    record_event(
        db,
        event_type=EventType.WORK_ORDER_STATUS_CHANGED,
        organization_id=work_order.organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=work_order.id,
        before={"status": current},
        after={"status": new_status},
    )
    if new_status == WorkOrderStatus.CANCELLED:
        # A cancelled job disappears from the contractor's list.
        end_current_assignment(db, work_order, reason=AssignmentEnd.CANCELLED)
    sync_requests(db, work_order, actor=actor)


def current_assignee_id(db: Session, work_order_id: uuid.UUID) -> uuid.UUID | None:
    """The membership of the contractor now responsible, if there is one."""
    return db.scalar(
        select(WorkOrderAssignment.contractor_membership_id).where(
            WorkOrderAssignment.work_order_id == work_order_id,
            WorkOrderAssignment.ended_at.is_(None),
        )
    )


def end_current_assignment(
    db: Session, work_order: WorkOrder, *, reason: AssignmentEnd
) -> WorkOrderAssignment | None:
    """Stop the current assignment, keeping the row as history."""
    current = db.scalar(
        select(WorkOrderAssignment).where(
            WorkOrderAssignment.work_order_id == work_order.id,
            WorkOrderAssignment.ended_at.is_(None),
        )
    )
    if current is not None:
        current.ended_at = utc_now()
        current.ended_reason = reason
        db.flush()
    return current


def update_details(
    db: Session, work_order: WorkOrder, *, actor: User, values: dict[str, Any]
) -> bool:
    """Edit scope, priority and the like. Returns whether anything changed."""
    if WorkOrderStatus(work_order.status) in ADMINISTRATOR_ONLY_FROM:
        raise WorkOrderError("A finished work order cannot be edited. Reopen it first")

    changes: dict[str, list[Any]] = {}
    for field in EDITABLE_FIELDS:
        before = getattr(work_order, field)
        after = values[field]
        if before != after:
            changes[field] = [_plain(before), _plain(after)]
            setattr(work_order, field, after)
    if not changes:
        return False

    work_order.updated_at = utc_now()
    add_entry(
        db,
        work_order,
        actor=actor,
        kind=EntryKind.EDITED,
        details=changes,
        contractor_visible=True,
    )
    record_event(
        db,
        event_type=EventType.WORK_ORDER_UPDATED,
        organization_id=work_order.organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=work_order.id,
        after={"changed": list(changes)},
    )
    return True


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


def add_note(
    db: Session,
    work_order: WorkOrder,
    *,
    actor: User,
    body: str,
    visibility: Visibility,
    share_with_contractor: bool = False,
) -> WorkOrderEntry:
    """A note on the work order. One shared with the resident also appears on every linked
    request, because that is where the resident looks."""
    entry = add_entry(
        db,
        work_order,
        actor=actor,
        kind=EntryKind.NOTE,
        visibility=visibility,
        body=body,
        contractor_visible=share_with_contractor,
    )
    work_order.updated_at = utc_now()
    if visibility == Visibility.RESIDENT:
        for request in db.scalars(
            select(MaintenanceRequest).where(MaintenanceRequest.work_order_id == work_order.id)
        ):
            requests.add_staff_message(db, request, actor=actor, body=body)
    return entry


# --- Reading ----------------------------------------------------------------------------


def _rows(db: Session, statement: Select[tuple[WorkOrder]]) -> list[WorkOrderRow]:
    result = db.execute(
        statement.join(Property, Property.id == WorkOrder.property_id)
        .outerjoin(Unit, Unit.id == WorkOrder.unit_id)
        .outerjoin(Building, Building.id == Unit.building_id)
        .add_columns(Property, Unit, Building)
    )
    return [
        WorkOrderRow(work_order=work_order, property=property_, unit=unit, building=building)
        for work_order, property_, unit, building in result
    ]


def rows_for_ids(db: Session, work_order_ids: list[uuid.UUID]) -> list[WorkOrderRow]:
    """Rows for specific work orders. The caller has already decided they may be seen."""
    if not work_order_ids:
        return []
    return _rows(db, select(WorkOrder).where(WorkOrder.id.in_(work_order_ids)))


def get_for_staff(
    db: Session, *, organization_id: uuid.UUID, scope: PropertyScope, work_order_id: uuid.UUID
) -> WorkOrderRow | None:
    statement = select(WorkOrder).where(
        WorkOrder.id == work_order_id, WorkOrder.organization_id == organization_id
    )
    if not scope.unrestricted:
        statement = statement.where(WorkOrder.property_id.in_(scope.property_ids))
    rows = _rows(db, statement)
    return rows[0] if rows else None


def list_for_staff(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    status: WorkOrderStatus | None = None,
    open_only: bool = False,
    priority: Urgency | None = None,
    property_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    history_only: bool = False,
    search: str | None = None,
    older_than_days: int | None = None,
    assignee_id: uuid.UUID | None = None,
    unassigned: bool = False,
) -> list[WorkOrderRow]:
    statement = select(WorkOrder).where(WorkOrder.organization_id == organization_id)
    current = select(WorkOrderAssignment.work_order_id).where(
        WorkOrderAssignment.ended_at.is_(None)
    )
    if assignee_id is not None:
        current_for = current.where(WorkOrderAssignment.contractor_membership_id == assignee_id)
        statement = statement.where(WorkOrder.id.in_(current_for))
    if unassigned:
        statement = statement.where(WorkOrder.id.not_in(current))
    if not scope.unrestricted:
        statement = statement.where(WorkOrder.property_id.in_(scope.property_ids))
    if status is not None:
        statement = statement.where(WorkOrder.status == status)
    if open_only:
        statement = statement.where(WorkOrder.status.not_in(list(FINAL_STATUSES)))
    if priority is not None:
        statement = statement.where(WorkOrder.priority == priority)
    if property_id is not None:
        statement = statement.where(WorkOrder.property_id == property_id)
    if unit_id is not None:
        statement = statement.where(WorkOrder.unit_id == unit_id)
    if history_only:
        # Maintenance history is work that was done: verified, and possibly closed.
        statement = statement.where(
            WorkOrder.status.in_([WorkOrderStatus.COMPLETED, WorkOrderStatus.CLOSED])
        )
    if older_than_days is not None:
        statement = statement.where(
            WorkOrder.created_at <= utc_now() - timedelta(days=older_than_days)
        )
    if search:
        text = f"%{search.strip().lower()}%"
        clauses = [func.lower(WorkOrder.title).like(text), func.lower(WorkOrder.scope).like(text)]
        digits = search.strip().upper().removeprefix(REFERENCE_PREFIX)
        if digits.isdigit():
            clauses.append(WorkOrder.number == int(digits))
        statement = statement.where(or_(*clauses))
    return _rows(db, statement.order_by(WorkOrder.number.desc()).limit(LIST_LIMIT))


def request_counts(db: Session, work_order_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not work_order_ids:
        return {}
    rows = db.execute(
        select(MaintenanceRequest.work_order_id, func.count())
        .where(MaintenanceRequest.work_order_id.in_(work_order_ids))
        .group_by(MaintenanceRequest.work_order_id)
    )
    return {work_order_id: count for work_order_id, count in rows if work_order_id is not None}


def history(db: Session, work_order_id: uuid.UUID) -> list[tuple[WorkOrderEntry, User | None]]:
    """Oldest first."""
    statement = (
        select(WorkOrderEntry, User)
        .outerjoin(User, User.id == WorkOrderEntry.author_user_id)
        .where(WorkOrderEntry.work_order_id == work_order_id)
        .order_by(WorkOrderEntry.created_at, WorkOrderEntry.id)
    )
    return [(entry, author) for entry, author in db.execute(statement)]


def numbers_and_statuses(
    db: Session, work_order_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, WorkOrderStatus]]:
    """Just enough to show a link to each work order: its number and status."""
    if not work_order_ids:
        return {}
    rows = db.execute(
        select(WorkOrder.id, WorkOrder.number, WorkOrder.status).where(
            WorkOrder.id.in_(work_order_ids)
        )
    )
    return {
        work_order_id: (number, WorkOrderStatus(status)) for work_order_id, number, status in rows
    }
