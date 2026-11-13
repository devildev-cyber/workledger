"""Assigning work orders to contractors, and what a contractor may do with a job (decision 0020).

Services flush but never commit. Every check runs before anything is changed, so a refused
action leaves the assignment, the work order, and its history as they were.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.models import (
    FINAL_STATUSES,
    AssignmentEnd,
    AssignmentResponse,
    EntryKind,
    EventType,
    Membership,
    MembershipRole,
    Role,
    User,
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderEntry,
    WorkOrderStatus,
)
from app.services import notifications, work_orders
from app.services.activity import record_event
from app.services.work_orders import WorkOrderError, WorkOrderRow

S = WorkOrderStatus

# A job can be handed over while work is still expected, but not once it is waiting for
# review, finished, or in the approval gate that Phase 7 adds.
ASSIGNABLE = frozenset({S.OPEN, S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD})

# The only moves a contractor makes themselves. Everything else is the manager's call.
CONTRACTOR_MOVES = frozenset(
    {
        (S.ASSIGNED, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.ON_HOLD),
        (S.ON_HOLD, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.READY_FOR_REVIEW),
    }
)
# These need words: why the job is paused, and what was done.
NOTE_REQUIRED = frozenset({S.ON_HOLD, S.READY_FOR_REVIEW})

CONTRACTOR_ENTRY_KINDS = frozenset({EntryKind.NOTE, EntryKind.PROGRESS, EntryKind.CLARIFICATION})


class DispatchError(WorkOrderError):
    """A dispatch action the job's current state does not allow. The message is safe to show."""


@dataclass(frozen=True)
class Contractor:
    membership: Membership
    user: User
    active_jobs: int


@dataclass(frozen=True)
class Assignee:
    assignment: WorkOrderAssignment
    name: str


# --- Who can be assigned -----------------------------------------------------------------


def contractors(db: Session, organization_id: uuid.UUID) -> list[Contractor]:
    """Everyone in the organization who holds the contractor role, with their open jobs."""
    statement = (
        select(Membership, User)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == organization_id, MembershipRole.role == Role.CONTRACTOR
        )
        .order_by(User.full_name, User.email)
    )
    counts = {
        membership_id: count
        for membership_id, count in db.execute(
            select(WorkOrderAssignment.contractor_membership_id, func.count())
            .join(WorkOrder, WorkOrder.id == WorkOrderAssignment.work_order_id)
            .where(
                WorkOrderAssignment.organization_id == organization_id,
                WorkOrderAssignment.ended_at.is_(None),
                WorkOrder.status.not_in(list(FINAL_STATUSES)),
            )
            .group_by(WorkOrderAssignment.contractor_membership_id)
        )
    }
    return [
        Contractor(membership=membership, user=user, active_jobs=counts.get(membership.id, 0))
        for membership, user in db.execute(statement)
    ]


def get_contractor(
    db: Session, *, organization_id: uuid.UUID, membership_id: uuid.UUID
) -> Contractor | None:
    return next(
        (item for item in contractors(db, organization_id) if item.membership.id == membership_id),
        None,
    )


# --- Reading -----------------------------------------------------------------------------


def current_assignment(db: Session, work_order_id: uuid.UUID) -> WorkOrderAssignment | None:
    return db.scalar(
        select(WorkOrderAssignment).where(
            WorkOrderAssignment.work_order_id == work_order_id,
            WorkOrderAssignment.ended_at.is_(None),
        )
    )


def assignees_for(db: Session, work_order_ids: list[uuid.UUID]) -> dict[uuid.UUID, Assignee]:
    """The current contractor on each work order, for lists."""
    if not work_order_ids:
        return {}
    statement = (
        select(WorkOrderAssignment, User.full_name)
        .join(Membership, Membership.id == WorkOrderAssignment.contractor_membership_id)
        .join(User, User.id == Membership.user_id)
        .where(
            WorkOrderAssignment.work_order_id.in_(work_order_ids),
            WorkOrderAssignment.ended_at.is_(None),
        )
    )
    return {
        assignment.work_order_id: Assignee(assignment=assignment, name=name)
        for assignment, name in db.execute(statement)
    }


@dataclass(frozen=True)
class AssignmentRecord:
    assignment: WorkOrderAssignment
    contractor_name: str
    assigned_by_name: str


def assignment_history(db: Session, work_order_id: uuid.UUID) -> list[AssignmentRecord]:
    """Every assignment the work order has had, oldest first."""
    assigner = User.__table__.alias("assigner")
    statement = (
        select(WorkOrderAssignment, User.full_name, assigner.c.full_name)
        .join(Membership, Membership.id == WorkOrderAssignment.contractor_membership_id)
        .join(User, User.id == Membership.user_id)
        .join(assigner, assigner.c.id == WorkOrderAssignment.assigned_by_user_id)
        .where(WorkOrderAssignment.work_order_id == work_order_id)
        .order_by(WorkOrderAssignment.assigned_at, WorkOrderAssignment.id)
    )
    return [AssignmentRecord(a, name, by) for a, name, by in db.execute(statement)]


# --- Managers: assigning -----------------------------------------------------------------


def assign(
    db: Session, work_order: WorkOrder, *, actor: User, contractor: Contractor
) -> WorkOrderAssignment:
    """Hand the work order to a contractor, replacing the current one if there is one."""
    current_status = WorkOrderStatus(work_order.status)
    if current_status not in ASSIGNABLE:
        raise DispatchError("This work order can no longer be assigned")
    current = current_assignment(db, work_order.id)
    if current is not None and current.contractor_membership_id == contractor.membership.id:
        raise DispatchError("This work order is already assigned to them")

    previous_name = None
    if current is not None:
        previous = get_contractor(
            db,
            organization_id=work_order.organization_id,
            membership_id=current.contractor_membership_id,
        )
        previous_name = previous.user.full_name if previous else "another contractor"
        work_orders.end_current_assignment(db, work_order, reason=AssignmentEnd.REASSIGNED)

    now = utc_now()
    assignment = WorkOrderAssignment(
        organization_id=work_order.organization_id,
        work_order_id=work_order.id,
        contractor_membership_id=contractor.membership.id,
        assigned_by_user_id=actor.id,
        assigned_at=now,
        response=AssignmentResponse.PENDING,
    )
    db.add(assignment)
    db.flush()

    name = contractor.user.full_name
    reference = work_orders.reference_for(work_order.number)
    if current is not None:
        notifications.work_order_unassigned(
            db,
            organization_id=work_order.organization_id,
            work_order_id=work_order.id,
            reference=reference,
            contractor_membership_id=current.contractor_membership_id,
            actor=actor,
        )
    notifications.work_order_assigned(
        db,
        organization_id=work_order.organization_id,
        work_order_id=work_order.id,
        reference=reference,
        title=work_order.title,
        contractor_membership_id=contractor.membership.id,
        actor=actor,
    )
    work_orders.add_entry(
        db,
        work_order,
        actor=actor,
        kind=EntryKind.ASSIGNED,
        body=f"Reassigned from {previous_name} to {name}"
        if previous_name
        else f"Assigned to {name}",
    )
    record_event(
        db,
        event_type=EventType.WORK_ORDER_ASSIGNED,
        organization_id=work_order.organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=work_order.id,
        after={
            "contractor_membership_id": str(contractor.membership.id),
            "reassigned": bool(current),
        },
    )
    if current_status in (S.OPEN, S.ON_HOLD):
        work_orders.change_status(
            db,
            work_order,
            actor=actor,
            new_status=S.ASSIGNED,
            note=None,
            is_administrator=False,
            system=True,
        )
    work_order.updated_at = now
    return assignment


def unassign(db: Session, work_order: WorkOrder, *, actor: User) -> None:
    """Take the contractor off the job without naming a replacement."""
    current = current_assignment(db, work_order.id)
    if current is None:
        raise DispatchError("No one is assigned to this work order")
    current_status = WorkOrderStatus(work_order.status)
    if current_status not in ASSIGNABLE:
        raise DispatchError("This work order can no longer be reassigned")

    work_orders.end_current_assignment(db, work_order, reason=AssignmentEnd.UNASSIGNED)
    work_orders.add_entry(
        db, work_order, actor=actor, kind=EntryKind.UNASSIGNED, body="Contractor removed"
    )
    record_event(
        db,
        event_type=EventType.WORK_ORDER_UNASSIGNED,
        organization_id=work_order.organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=work_order.id,
        before={"contractor_membership_id": str(current.contractor_membership_id)},
    )
    notifications.work_order_unassigned(
        db,
        organization_id=work_order.organization_id,
        work_order_id=work_order.id,
        reference=work_orders.reference_for(work_order.number),
        contractor_membership_id=current.contractor_membership_id,
        actor=actor,
    )
    _return_to_open(db, work_order, actor=actor)


def _return_to_open(db: Session, work_order: WorkOrder, *, actor: User) -> None:
    if WorkOrderStatus(work_order.status) == S.ASSIGNED:
        work_orders.change_status(
            db, work_order, actor=actor, new_status=S.OPEN, note=None, is_administrator=False
        )


# --- Contractors: their jobs -------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    row: WorkOrderRow
    assignment: WorkOrderAssignment


def jobs_for(db: Session, *, organization_id: uuid.UUID, membership_id: uuid.UUID) -> list[Job]:
    """The jobs currently assigned to this contractor, and no one else's."""
    statement = (
        select(WorkOrder, WorkOrderAssignment)
        .join(WorkOrderAssignment, WorkOrderAssignment.work_order_id == WorkOrder.id)
        .where(
            WorkOrder.organization_id == organization_id,
            WorkOrderAssignment.contractor_membership_id == membership_id,
            WorkOrderAssignment.ended_at.is_(None),
        )
        .order_by(WorkOrder.due_date.is_(None), WorkOrder.due_date, WorkOrder.number)
    )
    pairs = db.execute(statement).all()
    rows = {
        row.work_order.id: row
        for row in work_orders.rows_for_ids(db, [order.id for order, _ in pairs])
    }
    return [Job(row=rows[order.id], assignment=assignment) for order, assignment in pairs]


def get_job(
    db: Session,
    *,
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    work_order_id: uuid.UUID,
) -> Job | None:
    """A job by ID, only if it is assigned to this contractor. Anyone else's looks missing."""
    return next(
        (
            job
            for job in jobs_for(db, organization_id=organization_id, membership_id=membership_id)
            if job.row.work_order.id == work_order_id
        ),
        None,
    )


def contractor_entries(
    db: Session, work_order_id: uuid.UUID
) -> list[tuple[WorkOrderEntry, User | None]]:
    """The history a contractor may read, oldest first."""
    statement = (
        select(WorkOrderEntry, User)
        .outerjoin(User, User.id == WorkOrderEntry.author_user_id)
        .where(
            WorkOrderEntry.work_order_id == work_order_id,
            WorkOrderEntry.contractor_visible.is_(True),
        )
        .order_by(WorkOrderEntry.created_at, WorkOrderEntry.id)
    )
    return [(entry, author) for entry, author in db.execute(statement)]


# --- Contractors: acting on a job --------------------------------------------------------


def accept(db: Session, job: Job, *, actor: User) -> None:
    assignment = job.assignment
    if assignment.response != AssignmentResponse.PENDING:
        raise DispatchError("You have already responded to this job")
    assignment.response = AssignmentResponse.ACCEPTED
    assignment.responded_at = utc_now()
    work_orders.add_entry(
        db,
        job.row.work_order,
        actor=actor,
        kind=EntryKind.ASSIGNMENT_ACCEPTED,
        contractor_visible=True,
    )
    _record_response(db, job, actor=actor, response=AssignmentResponse.ACCEPTED)


def decline(db: Session, job: Job, *, actor: User, reason: str) -> None:
    """Turn the job down before starting. The job goes back to the manager, with the reason."""
    assignment = job.assignment
    if assignment.response != AssignmentResponse.PENDING:
        raise DispatchError("Only a job you have not yet accepted can be declined")
    work_order = job.row.work_order
    assignment.response = AssignmentResponse.DECLINED
    assignment.responded_at = utc_now()
    assignment.decline_reason = reason
    work_orders.end_current_assignment(db, work_order, reason=AssignmentEnd.DECLINED)
    work_orders.add_entry(
        db, work_order, actor=actor, kind=EntryKind.ASSIGNMENT_DECLINED, body=reason
    )
    _record_response(db, job, actor=actor, response=AssignmentResponse.DECLINED)
    _return_to_open(db, work_order, actor=actor)


def _record_response(db: Session, job: Job, *, actor: User, response: AssignmentResponse) -> None:
    work_order = job.row.work_order
    notifications.assignment_responded(
        db,
        organization_id=work_order.organization_id,
        property_id=work_order.property_id,
        work_order_id=work_order.id,
        reference=work_orders.reference_for(work_order.number),
        accepted=response == AssignmentResponse.ACCEPTED,
        actor=actor,
    )
    record_event(
        db,
        event_type=EventType.WORK_ORDER_ASSIGNMENT_RESPONDED,
        organization_id=job.assignment.organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=job.row.work_order.id,
        after={"response": response},
    )


def change_status(
    db: Session, job: Job, *, actor: User, new_status: WorkOrderStatus, note: str | None
) -> None:
    """A contractor starts, pauses, resumes, or finishes their job."""
    work_order = job.row.work_order
    if job.assignment.response != AssignmentResponse.ACCEPTED:
        raise DispatchError("Accept the job first")
    current = WorkOrderStatus(work_order.status)
    if (current, new_status) not in CONTRACTOR_MOVES:
        raise DispatchError(f"You cannot move this job from {current.value} to {new_status.value}")
    if new_status in NOTE_REQUIRED and not (note and note.strip()):
        raise DispatchError(
            "Say why the job is on hold"
            if new_status == S.ON_HOLD
            else "Describe what was done before marking the work ready for review"
        )
    work_orders.change_status(
        db, work_order, actor=actor, new_status=new_status, note=note, is_administrator=False
    )


def add_entry(db: Session, job: Job, *, actor: User, kind: EntryKind, body: str) -> WorkOrderEntry:
    """A note, progress update, or question about the job. The manager can read all of them."""
    if kind not in CONTRACTOR_ENTRY_KINDS:
        raise DispatchError("That kind of entry is not available")
    work_order = job.row.work_order
    if WorkOrderStatus(work_order.status) in FINAL_STATUSES:
        raise DispatchError("This job is finished")
    if job.assignment.response != AssignmentResponse.ACCEPTED:
        raise DispatchError("Accept the job first")
    entry = work_orders.add_entry(
        db, work_order, actor=actor, kind=kind, body=body, contractor_visible=True
    )
    work_order.updated_at = utc_now()
    return entry
