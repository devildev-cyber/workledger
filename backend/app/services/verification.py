"""A manager's review of work a contractor marked ready (decision 0021).

Verifying completes the work order and records its resolution and final cost. Sending it back
returns it to the contractor with a reason. Either way every check runs before anything is
changed, so a refused review leaves the work order and its history as they were.
"""

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.models import (
    EntryKind,
    EventType,
    Property,
    User,
    WorkOrder,
    WorkOrderStatus,
)
from app.services import estimates, notifications, work_orders
from app.services.activity import record_event
from app.services.work_orders import WorkOrderError

MAX_COST_CENTS = 10**12
CURRENCY = re.compile(r"^[A-Z]{3}$")


class ReviewError(WorkOrderError):
    """A review the work order's current state does not allow. The message is safe to show."""


def _require_ready(work_order: WorkOrder) -> None:
    if WorkOrderStatus(work_order.status) != WorkOrderStatus.READY_FOR_REVIEW:
        raise ReviewError("Only work that is ready for review can be verified or sent back")


def verify(
    db: Session,
    work_order: WorkOrder,
    *,
    actor: User,
    property_: Property,
    resolution: str,
    final_cost_cents: int | None,
    currency: str | None,
) -> None:
    """Accept the work: it becomes completed, with what was done and what it cost."""
    _require_ready(work_order)
    if not resolution.strip():
        raise ReviewError("Describe the resolution")
    if final_cost_cents is not None and not 0 <= final_cost_cents <= MAX_COST_CENTS:
        raise ReviewError("The final cost is not a valid amount")
    code = (currency or property_.currency).upper()
    if not CURRENCY.match(code):
        raise ReviewError("The currency must be a three-letter code, such as USD")

    work_orders.change_status(
        db,
        work_order,
        actor=actor,
        new_status=WorkOrderStatus.COMPLETED,
        note=None,
        is_administrator=False,
        review=True,
    )
    now = utc_now()
    work_order.resolution = resolution.strip()
    work_order.final_cost_cents = final_cost_cents
    work_order.currency = code if final_cost_cents is not None else None
    work_order.verified_by_user_id = actor.id
    work_order.verified_at = now
    # What the work cost against what was estimated and approved. Recorded, not enforced:
    # the money is already spent, so refusing would only hide it.
    check = estimates.cost_check(db, work_order, property_, final_cost_cents)
    details: dict[str, Any] = {
        "final_cost_cents": final_cost_cents,
        "currency": work_order.currency,
    }
    if check is not None:
        details["cost_check"] = check
    work_orders.add_entry(
        db,
        work_order,
        actor=actor,
        kind=EntryKind.VERIFIED,
        body=work_order.resolution,
        details=details,
    )
    record_event(
        db,
        event_type=EventType.WORK_ORDER_VERIFIED,
        organization_id=work_order.organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=work_order.id,
        after=details,
    )
    notifications.work_order_verified(
        db,
        organization_id=work_order.organization_id,
        work_order_id=work_order.id,
        reference=work_orders.reference_for(work_order.number),
        contractor_user_id=notifications.assignee_user_id(db, work_order.id),
        actor=actor,
    )


def send_back(db: Session, work_order: WorkOrder, *, actor: User, reason: str) -> None:
    """Return the work to the contractor. They are shown the reason, which is written for them."""
    _require_ready(work_order)
    if not reason.strip():
        raise ReviewError("Say what still needs doing")

    work_orders.change_status(
        db,
        work_order,
        actor=actor,
        new_status=WorkOrderStatus.IN_PROGRESS,
        note=None,
        is_administrator=False,
        review=True,
    )
    work_orders.add_entry(
        db,
        work_order,
        actor=actor,
        kind=EntryKind.SENT_BACK,
        body=reason.strip(),
        contractor_visible=True,
    )
    record_event(
        db,
        event_type=EventType.WORK_ORDER_SENT_BACK,
        organization_id=work_order.organization_id,
        actor=actor,
        subject_type="work_order",
        subject_id=work_order.id,
    )
    notifications.work_order_sent_back(
        db,
        organization_id=work_order.organization_id,
        work_order_id=work_order.id,
        reference=work_orders.reference_for(work_order.number),
        contractor_user_id=notifications.assignee_user_id(db, work_order.id),
        actor=actor,
    )
