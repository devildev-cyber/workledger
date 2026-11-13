"""Reports for managers and owners, with each metric defined in decision 0024.

Every query is limited to the organization, to the properties the reader may see (the
manager's scope, or the owner's properties) and, when asked, to one property. A metric that
cannot be computed from data the reader can see is not offered. Money is never added across
currencies: totals are given per currency.

Periods are whole UTC days, both ends included. Counts of "now" (open requests, work orders
by status, overdue, blocked, contractor workload) ignore the period; counts of "what happened"
(created, completed, spent, estimated) use it.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import PropertyScope
from app.models import (
    FINAL_STATUSES,
    Estimate,
    EstimateStatus,
    MaintenanceRequest,
    Membership,
    Property,
    RequestStatus,
    Unit,
    User,
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderEntry,
    WorkOrderStatus,
)
from app.models.work_orders import AssignmentResponse, EntryKind
from app.services.work_orders import BLOCKED_REASONS, reference_for

DEFAULT_DAYS = 90
MAX_DAYS = 3660
# How many work order references are listed under one repeat issue.
REFERENCES_SHOWN = 10
# A long period in a big portfolio can repeat hundreds of small things; the report shows the worst.
REPEAT_ISSUES_SHOWN = 50

# A request is open until the resident's problem is resolved, closed, withdrawn, or declined.
OPEN_REQUEST_STATUSES = frozenset(
    {RequestStatus.SUBMITTED, RequestStatus.IN_REVIEW, RequestStatus.IN_PROGRESS}
)
AWAITING_TRIAGE_STATUSES = frozenset({RequestStatus.SUBMITTED, RequestStatus.IN_REVIEW})


class ReportError(Exception):
    """A report that cannot be built as asked. The message is safe to show."""


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @property
    def start_at(self) -> datetime:
        return datetime.combine(self.start, time.min, tzinfo=UTC)

    @property
    def end_at(self) -> datetime:
        """The first moment after the period, so a comparison with < includes the last day."""
        return datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=UTC)


def resolve_period(start: date | None, end: date | None, *, today: date) -> Period:
    """The last 90 days up to today unless dates are given."""
    last = end or today
    first = start or last - timedelta(days=DEFAULT_DAYS - 1)
    if first > last:
        raise ReportError("The start date must not be after the end date")
    if (last - first).days >= MAX_DAYS:
        raise ReportError("Choose a period of ten years or less")
    return Period(first, last)


def within(column: Any, period: Period) -> list[Any]:
    return [column >= period.start_at, column < period.end_at]


def scope_clauses(column: Any, scope: PropertyScope, property_id: uuid.UUID | None) -> list[Any]:
    clauses: list[Any] = []
    if not scope.unrestricted:
        clauses.append(column.in_(scope.property_ids))
    if property_id is not None:
        clauses.append(column == property_id)
    return clauses


def _hours(delta: timedelta) -> float:
    return max(delta.total_seconds(), 0.0) / 3600


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _by_currency(totals: dict[str, int]) -> list[dict[str, Any]]:
    return [{"currency": code, "total_cents": totals[code]} for code in sorted(totals)]


# --- Requests ---------------------------------------------------------------------------


def request_metrics(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
) -> dict[str, Any]:
    where = [
        MaintenanceRequest.organization_id == organization_id,
        *scope_clauses(MaintenanceRequest.property_id, scope, property_id),
    ]
    by_status = {
        status: count
        for status, count in db.execute(
            select(MaintenanceRequest.status, func.count())
            .where(*where)
            .group_by(MaintenanceRequest.status)
        )
    }
    needing_triage = db.scalar(
        select(func.count()).where(
            *where,
            MaintenanceRequest.status.in_(AWAITING_TRIAGE_STATUSES),
            MaintenanceRequest.work_order_id.is_(None),
            MaintenanceRequest.duplicate_of_id.is_(None),
        )
    )
    submitted = db.scalar(
        select(func.count()).where(*where, *within(MaintenanceRequest.created_at, period))
    )
    return {
        "open": sum(
            count for status, count in by_status.items() if status in OPEN_REQUEST_STATUSES
        ),
        "waiting_for_triage": needing_triage or 0,
        "submitted_in_period": submitted or 0,
        "by_status": dict(sorted(by_status.items())),
    }


# --- Work orders ------------------------------------------------------------------------


def work_order_metrics(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
    today: date,
) -> dict[str, Any]:
    where = [
        WorkOrder.organization_id == organization_id,
        *scope_clauses(WorkOrder.property_id, scope, property_id),
    ]
    by_status = {
        status: count
        for status, count in db.execute(
            select(WorkOrder.status, func.count()).where(*where).group_by(WorkOrder.status)
        )
    }
    overdue = db.scalar(
        select(func.count()).where(
            *where,
            WorkOrder.due_date.is_not(None),
            WorkOrder.due_date < today,
            WorkOrder.status.not_in(list(FINAL_STATUSES)),
        )
    )
    created = db.execute(
        select(WorkOrder.property_id, Property.name, WorkOrder.category)
        .join(Property, Property.id == WorkOrder.property_id)
        .where(*where, *within(WorkOrder.created_at, period))
    ).all()
    by_category: dict[str, int] = defaultdict(int)
    by_property: dict[uuid.UUID, dict[str, Any]] = {}
    for found_property_id, name, category in created:
        by_category[category] += 1
        entry = by_property.setdefault(found_property_id, {"name": name, "count": 0})
        entry["count"] += 1
    return {
        "by_status": dict(sorted(by_status.items())),
        "open": sum(count for status, count in by_status.items() if status not in FINAL_STATUSES),
        "overdue": overdue or 0,
        "blocked": sum(count for status, count in by_status.items() if status in BLOCKED_REASONS),
        "created_in_period": len(created),
        "created_by_category": dict(sorted(by_category.items())),
        "created_by_property": [
            {"property_id": key, "property_name": value["name"], "count": value["count"]}
            for key, value in sorted(by_property.items(), key=lambda item: item[1]["name"])
        ],
    }


def resolution_metrics(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
) -> dict[str, Any]:
    """How long it took to put right the work that was verified in the period.

    A work order's clock starts when its earliest linked request was submitted (the resident's
    wait), or when the work order was created if no request is linked. It stops when the work
    was verified. Work that was reopened is measured from its latest verification.
    """
    verified = db.execute(
        select(WorkOrder.id, WorkOrder.created_at, WorkOrder.verified_at, WorkOrder.priority).where(
            WorkOrder.organization_id == organization_id,
            *scope_clauses(WorkOrder.property_id, scope, property_id),
            *within(WorkOrder.verified_at, period),
        )
    ).all()
    ids = [row.id for row in verified]
    submitted: dict[uuid.UUID, datetime] = {}
    if ids:
        submitted = {
            work_order_id: first
            for work_order_id, first in db.execute(
                select(MaintenanceRequest.work_order_id, func.min(MaintenanceRequest.created_at))
                .where(MaintenanceRequest.work_order_id.in_(ids))
                .group_by(MaintenanceRequest.work_order_id)
            )
        }
    hours: list[float] = []
    by_priority: dict[str, list[float]] = defaultdict(list)
    for row in verified:
        started = submitted.get(row.id, row.created_at)
        taken = _hours(row.verified_at - started)
        hours.append(taken)
        by_priority[row.priority].append(taken)
    return {
        "completed": len(hours),
        "average_hours": _average(hours),
        "slowest_hours": round(max(hours), 1) if hours else None,
        "by_priority": [
            {"priority": priority, "completed": len(values), "average_hours": _average(values)}
            for priority, values in sorted(by_priority.items())
        ],
    }


# --- Contractors ------------------------------------------------------------------------


def contractor_workload(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
    today: date,
) -> list[dict[str, Any]]:
    """Each contractor's jobs now, and what they did in the period.

    Rework is a job sent back after the contractor marked it ready. It is counted against the
    contractor who held the job when it was sent back.
    """
    in_scope = [
        WorkOrder.organization_id == organization_id,
        *scope_clauses(WorkOrder.property_id, scope, property_id),
    ]
    stats: dict[uuid.UUID, dict[str, int]] = defaultdict(
        lambda: {
            "active_jobs": 0,
            "awaiting_response": 0,
            "overdue": 0,
            "completed": 0,
            "sent_back": 0,
            "declined": 0,
        }
    )

    current = db.execute(
        select(
            WorkOrderAssignment.contractor_membership_id,
            WorkOrder.status,
            WorkOrder.due_date,
            WorkOrderAssignment.response,
            WorkOrder.verified_at,
        )
        .join(WorkOrder, WorkOrder.id == WorkOrderAssignment.work_order_id)
        .where(*in_scope, WorkOrderAssignment.ended_at.is_(None))
    )
    for membership_id, status, due, response, verified_at in current:
        if WorkOrderStatus(status) not in FINAL_STATUSES:
            stats[membership_id]["active_jobs"] += 1
            if response == AssignmentResponse.PENDING:
                stats[membership_id]["awaiting_response"] += 1
            if due is not None and due < today:
                stats[membership_id]["overdue"] += 1
        if verified_at is not None and period.start_at <= verified_at < period.end_at:
            stats[membership_id]["completed"] += 1

    sent_back = db.execute(
        select(WorkOrderAssignment.contractor_membership_id, func.count(WorkOrderEntry.id))
        .join(WorkOrder, WorkOrder.id == WorkOrderAssignment.work_order_id)
        .join(
            WorkOrderEntry,
            (WorkOrderEntry.work_order_id == WorkOrderAssignment.work_order_id)
            & (WorkOrderEntry.created_at >= WorkOrderAssignment.assigned_at)
            & (
                WorkOrderAssignment.ended_at.is_(None)
                | (WorkOrderEntry.created_at < WorkOrderAssignment.ended_at)
            ),
        )
        .where(
            *in_scope,
            WorkOrderEntry.kind == EntryKind.SENT_BACK,
            *within(WorkOrderEntry.created_at, period),
        )
        .group_by(WorkOrderAssignment.contractor_membership_id)
    )
    for membership_id, count in sent_back:
        stats[membership_id]["sent_back"] += count

    declined = db.execute(
        select(WorkOrderAssignment.contractor_membership_id, func.count())
        .join(WorkOrder, WorkOrder.id == WorkOrderAssignment.work_order_id)
        .where(
            *in_scope,
            WorkOrderAssignment.response == AssignmentResponse.DECLINED,
            *within(WorkOrderAssignment.responded_at, period),
        )
        .group_by(WorkOrderAssignment.contractor_membership_id)
    )
    for membership_id, count in declined:
        stats[membership_id]["declined"] += count

    if not stats:
        return []
    names = {
        membership_id: name
        for membership_id, name in db.execute(
            select(Membership.id, User.full_name)
            .join(User, User.id == Membership.user_id)
            .where(Membership.id.in_(stats))
        )
    }
    return [
        {"contractor_id": membership_id, "name": names.get(membership_id, "Unknown"), **counts}
        for membership_id, counts in sorted(
            stats.items(), key=lambda item: names.get(item[0], "Unknown").lower()
        )
    ]


# --- Repeat issues ----------------------------------------------------------------------


def repeat_issues(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    """The same kind of problem recurring in the same place.

    A repeat issue is two or more work orders of one category, created in the period and not
    cancelled, at the same unit, or in the common areas of the same property (work orders
    without a unit).
    """
    rows = db.execute(
        select(
            WorkOrder.number,
            WorkOrder.property_id,
            Property.name,
            WorkOrder.unit_id,
            Unit.label,
            WorkOrder.category,
        )
        .join(Property, Property.id == WorkOrder.property_id)
        .outerjoin(Unit, Unit.id == WorkOrder.unit_id)
        .where(
            WorkOrder.organization_id == organization_id,
            *scope_clauses(WorkOrder.property_id, scope, property_id),
            *within(WorkOrder.created_at, period),
            WorkOrder.status != WorkOrderStatus.CANCELLED,
        )
        .order_by(WorkOrder.number)
    ).all()
    groups: dict[tuple[uuid.UUID, uuid.UUID | None, str], dict[str, Any]] = {}
    for number, found_property_id, property_name, unit_id, unit_label, category in rows:
        group = groups.setdefault(
            (found_property_id, unit_id, category),
            {
                "property_id": found_property_id,
                "property_name": property_name,
                "unit_label": unit_label,
                "category": category,
                "numbers": [],
            },
        )
        group["numbers"].append(number)
    repeated = [group for group in groups.values() if len(group["numbers"]) >= 2]
    repeated.sort(
        key=lambda group: (
            -len(group["numbers"]),
            group["property_name"],
            group["unit_label"] or "",
        )
    )
    return [
        {
            "property_id": group["property_id"],
            "property_name": group["property_name"],
            "unit_label": group["unit_label"],
            "category": group["category"],
            "count": len(group["numbers"]),
            "references": [
                reference_for(number) for number in group["numbers"][-REFERENCES_SHOWN:]
            ],
        }
        for group in repeated[:REPEAT_ISSUES_SHOWN]
    ]


# --- Spending and approvals -------------------------------------------------------------


def spend_metrics(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
) -> dict[str, Any]:
    """What verified work cost: the final cost of work verified in the period."""
    rows = db.execute(
        select(
            WorkOrder.property_id,
            Property.name,
            WorkOrder.category,
            WorkOrder.currency,
            WorkOrder.final_cost_cents,
        )
        .join(Property, Property.id == WorkOrder.property_id)
        .where(
            WorkOrder.organization_id == organization_id,
            *scope_clauses(WorkOrder.property_id, scope, property_id),
            *within(WorkOrder.verified_at, period),
            WorkOrder.final_cost_cents.is_not(None),
        )
    ).all()
    total: dict[str, int] = defaultdict(int)
    by_property: dict[tuple[uuid.UUID, str], dict[str, Any]] = {}
    by_category: dict[tuple[str, str], int] = defaultdict(int)
    for found_property_id, name, category, currency, cents in rows:
        code = currency or "USD"
        total[code] += cents
        entry = by_property.setdefault(
            (found_property_id, code),
            {"property_id": found_property_id, "property_name": name, "currency": code,
             "total_cents": 0, "work_orders": 0},
        )  # fmt: skip
        entry["total_cents"] += cents
        entry["work_orders"] += 1
        by_category[(category, code)] += cents
    return {
        "work_orders": len(rows),
        "total": _by_currency(total),
        "by_property": sorted(
            by_property.values(), key=lambda item: (item["property_name"], item["currency"])
        ),
        "by_category": [
            {"category": category, "currency": code, "total_cents": cents}
            for (category, code), cents in sorted(by_category.items())
        ],
    }


def approval_metrics(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Estimates recorded in the period, and what the owners decided about the large ones.

    "Needed approval" counts estimate versions above the property's threshold. Each is
    pending (waiting now), approved, rejected, or replaced (a newer estimate arrived before
    anyone decided). Amounts are the estimated amounts, not what was later spent.
    """
    rows = db.execute(
        select(Estimate, WorkOrder.property_id, Property.name)
        .join(WorkOrder, WorkOrder.id == Estimate.work_order_id)
        .join(Property, Property.id == WorkOrder.property_id)
        .where(
            Estimate.organization_id == organization_id,
            *scope_clauses(WorkOrder.property_id, scope, property_id),
            *within(Estimate.created_at, period),
        )
    ).all()
    counts = {"pending": 0, "approved": 0, "rejected": 0, "replaced": 0}
    amounts: dict[str, dict[str, int]] = {
        "pending": defaultdict(int),
        "approved": defaultdict(int),
        "rejected": defaultdict(int),
    }
    decision_hours: list[float] = []
    by_property: dict[uuid.UUID, dict[str, Any]] = {}
    needed = 0
    for estimate, found_property_id, name in rows:
        entry = by_property.setdefault(
            found_property_id,
            {"property_id": found_property_id, "property_name": name, "needed_approval": 0,
             "pending": 0, "approved": 0, "rejected": 0},
        )  # fmt: skip
        if not estimate.approval_required:
            continue
        needed += 1
        entry["needed_approval"] += 1
        if estimate.status == EstimateStatus.PENDING and estimate.superseded_at is not None:
            counts["replaced"] += 1
            continue
        state = EstimateStatus(estimate.status).value
        counts[state] += 1
        entry[state] += 1
        amounts[state][estimate.currency] += estimate.amount_cents
        if estimate.decided_at is not None:
            decision_hours.append(_hours(estimate.decided_at - estimate.created_at))
    return {
        "estimates_recorded": len(rows),
        "needed_approval": needed,
        **counts,
        "pending_amounts": _by_currency(amounts["pending"]),
        "approved_amounts": _by_currency(amounts["approved"]),
        "rejected_amounts": _by_currency(amounts["rejected"]),
        "average_decision_hours": _average(decision_hours),
        "by_property": sorted(by_property.values(), key=lambda item: item["property_name"]),
    }


def staff_report(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
    today: date,
) -> dict[str, Any]:
    """Everything a manager or administrator sees, for the properties in their scope."""
    common = {
        "organization_id": organization_id,
        "scope": scope,
        "period": period,
        "property_id": property_id,
    }
    return {
        "period_start": period.start,
        "period_end": period.end,
        "requests": request_metrics(db, **common),
        "work_orders": work_order_metrics(db, **common, today=today),
        "resolution": resolution_metrics(db, **common),
        "contractors": contractor_workload(db, **common, today=today),
        "repeat_issues": repeat_issues(db, **common),
        "spend": spend_metrics(db, **common),
        "approvals": approval_metrics(db, **common),
    }
