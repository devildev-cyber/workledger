"""Estimates, and the property owner's decision on those above the threshold (decision 0022).

Services flush but never commit. Every check runs before anything is changed, so a refused
action leaves the estimate, the work order, and its history as they were.

The gate itself is `work_orders.approval_hold`, which `change_status` consults for every move
that spends or records spending, whichever route it came through.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.models import (
    FINAL_STATUSES,
    Building,
    EntryKind,
    Estimate,
    EstimateStatus,
    EventType,
    Property,
    Unit,
    User,
    WorkOrder,
    WorkOrderStatus,
)
from app.services import ownerships, work_orders
from app.services.activity import record_event
from app.services.work_orders import NotPermittedError, WorkOrderError

S = WorkOrderStatus

MAX_AMOUNT_CENTS = 10**12
LIST_LIMIT = 200
# An estimate can be recorded or revised while work is still planned or under way.
ESTIMATABLE = frozenset({S.OPEN, S.ASSIGNED, S.IN_PROGRESS, S.ON_HOLD, S.AWAITING_APPROVAL})
WAITING_NOTE = "Waiting for the property owner's approval"


class EstimateError(WorkOrderError):
    """An estimate action the current state does not allow. The message is safe to show."""


@dataclass(frozen=True)
class EstimateRecord:
    estimate: Estimate
    submitted_by_name: str
    decided_by_name: str | None


@dataclass(frozen=True)
class OwnerRow:
    estimate: Estimate
    work_order: WorkOrder
    property: Property
    unit: Unit | None
    building: Building | None


def needs_approval(property_: Property, amount_cents: int) -> bool:
    """Only an amount above the threshold needs a decision. No threshold means none does."""
    threshold = property_.approval_threshold_cents
    return threshold is not None and amount_cents > threshold


def current_estimate(db: Session, work_order_id: uuid.UUID) -> Estimate | None:
    return db.scalar(
        select(Estimate).where(
            Estimate.work_order_id == work_order_id, Estimate.superseded_at.is_(None)
        )
    )


def _resume_status(db: Session, work_order: WorkOrder, previous: Estimate | None) -> S:
    """Where the work order goes back to after approval."""
    current = S(work_order.status)
    if current != S.AWAITING_APPROVAL:
        return current
    if previous is not None and previous.resume_status:
        return S(previous.resume_status)
    return S.OPEN


def _usable(db: Session, work_order: WorkOrder, target: S) -> S:
    """A work order cannot go back to assigned if its contractor has since left."""
    if target == S.ASSIGNED and work_orders.current_assignee_id(db, work_order.id) is None:
        return S.OPEN
    return target


def _details(estimate: Estimate) -> dict[str, Any]:
    return {
        "estimate_id": str(estimate.id),
        "version": estimate.version,
        "amount_cents": estimate.amount_cents,
        "currency": estimate.currency,
        "approval_required": estimate.approval_required,
        "threshold_cents": estimate.threshold_cents,
    }


# --- Recording ------------------------------------------------------------------------


def submit(
    db: Session,
    work_order: WorkOrder,
    *,
    actor: User,
    property_: Property,
    amount_cents: int,
    description: str,
    provider_name: str | None,
) -> Estimate:
    """Record an estimate. It replaces the current one, and above the threshold it holds the
    work until a property owner decides."""
    current_status = S(work_order.status)
    if current_status not in ESTIMATABLE:
        raise EstimateError("An estimate can no longer be recorded for this work order")
    if not 1 <= amount_cents <= MAX_AMOUNT_CENTS:
        raise EstimateError("The estimate is not a valid amount")
    if not description.strip():
        raise EstimateError("Describe what the estimate covers")

    previous = current_estimate(db, work_order.id)
    resume = _resume_status(db, work_order, previous)
    required = needs_approval(property_, amount_cents)
    if previous is not None:
        previous.superseded_at = utc_now()
        db.flush()

    estimate = Estimate(
        organization_id=work_order.organization_id,
        work_order_id=work_order.id,
        version=previous.version + 1 if previous else 1,
        amount_cents=amount_cents,
        currency=property_.currency,
        description=description.strip(),
        provider_name=provider_name.strip() if provider_name and provider_name.strip() else None,
        submitted_by_user_id=actor.id,
        approval_required=required,
        threshold_cents=property_.approval_threshold_cents,
        status=EstimateStatus.PENDING if required else EstimateStatus.NOT_REQUIRED,
        resume_status=resume if required else None,
    )
    db.add(estimate)
    db.flush()

    work_orders.add_entry(
        db,
        work_order,
        actor=actor,
        kind=EntryKind.ESTIMATE_SUBMITTED,
        body=estimate.description,
        details={**_details(estimate), "provider_name": estimate.provider_name},
    )
    record_event(
        db,
        event_type=EventType.ESTIMATE_SUBMITTED,
        organization_id=work_order.organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=work_order.id,
        after=_details(estimate),
    )
    work_order.updated_at = utc_now()

    if required and current_status != S.AWAITING_APPROVAL:
        work_orders.change_status(
            db,
            work_order,
            actor=actor,
            new_status=S.AWAITING_APPROVAL,
            note=WAITING_NOTE,
            is_administrator=False,
            system=True,
        )
    elif not required and current_status == S.AWAITING_APPROVAL:
        # A revision that no longer needs a decision releases the work straight away.
        work_orders.change_status(
            db,
            work_order,
            actor=actor,
            new_status=_usable(db, work_order, resume),
            note=None,
            is_administrator=False,
            system=True,
        )
    return estimate


# --- Deciding -------------------------------------------------------------------------


def is_decidable(estimate: Estimate, work_order: WorkOrder, *, user_id: uuid.UUID) -> bool:
    """Whether this person could decide on it now, ownership aside."""
    return (
        estimate.superseded_at is None
        and estimate.status == EstimateStatus.PENDING
        and S(work_order.status) not in FINAL_STATUSES
        and estimate.submitted_by_user_id != user_id
    )


def decide(
    db: Session,
    estimate: Estimate,
    work_order: WorkOrder,
    *,
    actor: User,
    membership_id: uuid.UUID,
    approve: bool,
    reason: str | None,
) -> None:
    """A property owner approves or rejects. Rejecting needs a reason."""
    if not ownerships.is_owner(db, property_id=work_order.property_id, membership_id=membership_id):
        raise NotPermittedError("Only an owner of this property can decide on its spending")
    if estimate.superseded_at is not None:
        raise EstimateError("A newer estimate has replaced this one")
    if estimate.status != EstimateStatus.PENDING:
        raise EstimateError("A decision has already been recorded for this estimate")
    if S(work_order.status) in FINAL_STATUSES:
        raise EstimateError("This work order is no longer active")
    if estimate.submitted_by_user_id == actor.id:
        raise NotPermittedError("You cannot decide on an estimate you recorded yourself")
    cleaned = reason.strip() if reason and reason.strip() else None
    if not approve and cleaned is None:
        raise EstimateError("Say why the estimate is rejected")

    now = utc_now()
    estimate.status = EstimateStatus.APPROVED if approve else EstimateStatus.REJECTED
    estimate.decided_by_user_id = actor.id
    estimate.decided_at = now
    estimate.decision_reason = cleaned
    db.flush()
    work_orders.add_entry(
        db,
        work_order,
        actor=actor,
        kind=EntryKind.ESTIMATE_APPROVED if approve else EntryKind.ESTIMATE_REJECTED,
        body=cleaned,
        details=_details(estimate),
    )
    record_event(
        db,
        event_type=EventType.ESTIMATE_DECIDED,
        organization_id=work_order.organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=work_order.id,
        before={"status": EstimateStatus.PENDING},
        after={**_details(estimate), "status": estimate.status, "reason": cleaned},
    )
    work_order.updated_at = now

    if S(work_order.status) == S.AWAITING_APPROVAL:
        # Approved work carries on where it was. Rejected work stops until a manager decides.
        target = (
            _usable(db, work_order, S(estimate.resume_status or S.OPEN)) if approve else S.ON_HOLD
        )
        work_orders.change_status(
            db,
            work_order,
            actor=actor,
            new_status=target,
            note=None,
            is_administrator=False,
            system=True,
        )


# --- The cost check on verification ---------------------------------------------------


def cost_check(
    db: Session, work_order: WorkOrder, property_: Property, final_cost_cents: int | None
) -> dict[str, Any] | None:
    """Compare what the work cost with what was estimated and approved.

    Verification is never refused over this, because the money is already spent. It is made
    visible instead: the overrun, and spending above the threshold that no approval covered.
    """
    if final_cost_cents is None:
        return None
    current = current_estimate(db, work_order.id)
    estimate_cents = current.amount_cents if current else None
    over = final_cost_cents - estimate_cents if estimate_cents is not None else None
    threshold = property_.approval_threshold_cents
    covered = (
        current is not None
        and current.status == EstimateStatus.APPROVED
        and final_cost_cents <= current.amount_cents
    )
    return {
        "estimate_cents": estimate_cents,
        "over_estimate_cents": over if over is not None and over > 0 else None,
        "above_approval": threshold is not None and final_cost_cents > threshold and not covered,
    }


# --- Reading --------------------------------------------------------------------------


def _names(db: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    return {
        user.id: user.full_name for user in db.scalars(select(User).where(User.id.in_(user_ids)))
    }


def records_for(db: Session, work_order_id: uuid.UUID) -> list[EstimateRecord]:
    """Every estimate the work order has had, newest first."""
    found = list(
        db.scalars(
            select(Estimate)
            .where(Estimate.work_order_id == work_order_id)
            .order_by(Estimate.version.desc())
        )
    )
    users = {item.submitted_by_user_id for item in found} | {
        item.decided_by_user_id for item in found if item.decided_by_user_id
    }
    names = _names(db, users)
    return [
        EstimateRecord(
            estimate=item,
            submitted_by_name=names.get(item.submitted_by_user_id, "Unknown"),
            decided_by_name=names.get(item.decided_by_user_id) if item.decided_by_user_id else None,
        )
        for item in found
    ]


def _owner_rows(db: Session, statement: Any) -> list[OwnerRow]:
    result = db.execute(
        statement.join(WorkOrder, WorkOrder.id == Estimate.work_order_id)
        .join(Property, Property.id == WorkOrder.property_id)
        .outerjoin(Unit, Unit.id == WorkOrder.unit_id)
        .outerjoin(Building, Building.id == Unit.building_id)
        .add_columns(WorkOrder, Property, Unit, Building)
    )
    return [
        OwnerRow(estimate=e, work_order=w, property=p, unit=u, building=b)
        for e, w, p, u, b in result
    ]


def list_for_owner(
    db: Session, *, organization_id: uuid.UUID, property_ids: frozenset[uuid.UUID]
) -> list[OwnerRow]:
    """Estimates that needed a decision, at the properties this person owns. Newest first."""
    if not property_ids:
        return []
    statement = (
        select(Estimate)
        .where(
            Estimate.organization_id == organization_id,
            Estimate.approval_required.is_(True),
            WorkOrder.property_id.in_(property_ids),
        )
        .order_by(Estimate.created_at.desc(), Estimate.id)
        .limit(LIST_LIMIT)
    )
    return _owner_rows(db, statement)


def get_for_owner(
    db: Session,
    *,
    organization_id: uuid.UUID,
    property_ids: frozenset[uuid.UUID],
    estimate_id: uuid.UUID,
) -> OwnerRow | None:
    """One estimate, only if it is at a property this person owns. Others look missing."""
    if not property_ids:
        return None
    statement = select(Estimate).where(
        Estimate.id == estimate_id,
        Estimate.organization_id == organization_id,
        Estimate.approval_required.is_(True),
        WorkOrder.property_id.in_(property_ids),
    )
    rows = _owner_rows(db, statement)
    return rows[0] if rows else None
