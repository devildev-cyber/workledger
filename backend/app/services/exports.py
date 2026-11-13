"""CSV exports of records for operational review (decision 0024).

An export holds the same rows the reader could already see on screen and no more: the
reader's properties only, and never free text written by or about people (descriptions, notes,
access instructions, reasons) or residents' names and contact details. Spreadsheet programs
run any cell that starts with =, +, - or @ as a formula, so such cells are defused.
"""

import csv
import io
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import PropertyScope
from app.models import (
    FINAL_STATUSES,
    Estimate,
    MaintenanceRequest,
    Membership,
    Property,
    Unit,
    User,
    WorkOrder,
    WorkOrderAssignment,
)
from app.services import requests as request_service
from app.services.reports import Period, scope_clauses, within
from app.services.work_orders import reference_for

MAX_ROWS = 20_000
# Lets Excel read the file as UTF-8, so accented names are not garbled.
BYTE_ORDER_MARK = "\ufeff"
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


class ExportTooLargeError(Exception):
    """More rows than an export may hold. The message is safe to show."""


def safe_cell(value: Any) -> str:
    """A cell's text, made harmless to open in a spreadsheet."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(FORMULA_STARTS):
        return f"'{text}"
    return text


def money(cents: int | None) -> str:
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    return f"{sign}{whole}.{part:02d}"


def day(value: datetime | date | None) -> str:
    return (
        value.date().isoformat()
        if isinstance(value, datetime)
        else (value.isoformat() if value else "")
    )


@dataclass(frozen=True)
class Export:
    content: str
    rows: int


def render(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Export:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(header)
    count = 0
    for row in rows:
        count += 1
        if count > MAX_ROWS:
            raise ExportTooLargeError("Too many rows to export. Choose a shorter period")
        writer.writerow([safe_cell(cell) for cell in row])
    return Export(BYTE_ORDER_MARK + out.getvalue(), count)


# --- Staff ------------------------------------------------------------------------------


def work_orders_csv(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
    today: date,
) -> Export:
    """Work orders created in the period."""
    current = {
        assignment.work_order_id: name
        for assignment, name in db.execute(
            select(WorkOrderAssignment, User.full_name)
            .join(Membership, Membership.id == WorkOrderAssignment.contractor_membership_id)
            .join(User, User.id == Membership.user_id)
            .where(
                WorkOrderAssignment.organization_id == organization_id,
                WorkOrderAssignment.ended_at.is_(None),
            )
        )
    }
    found = db.execute(
        select(WorkOrder, Property.name, Unit.label)
        .join(Property, Property.id == WorkOrder.property_id)
        .outerjoin(Unit, Unit.id == WorkOrder.unit_id)
        .where(
            WorkOrder.organization_id == organization_id,
            *scope_clauses(WorkOrder.property_id, scope, property_id),
            *within(WorkOrder.created_at, period),
        )
        .order_by(WorkOrder.number)
        .limit(MAX_ROWS + 1)
    ).all()
    earliest = _earliest_requests(db, [order.id for order, _, _ in found])

    def rows() -> Iterable[list[Any]]:
        for order, property_name, unit_label in found:
            started = earliest.get(order.id, order.created_at)
            hours = (
                f"{max((order.verified_at - started).total_seconds(), 0) / 3600:.1f}"
                if order.verified_at
                else ""
            )
            overdue = (
                order.due_date is not None
                and order.due_date < today
                and order.status not in FINAL_STATUSES
            )
            yield [
                reference_for(order.number),
                property_name,
                unit_label,
                order.title,
                order.category,
                order.priority,
                order.status,
                day(order.created_at),
                day(order.due_date),
                "Yes" if overdue else "No",
                current.get(order.id),
                day(order.verified_at),
                hours,
                money(order.final_cost_cents),
                order.currency,
            ]

    return render(
        [
            "Reference", "Property", "Unit", "Title", "Category", "Priority", "Status",
            "Created", "Due", "Overdue", "Contractor", "Verified", "Hours to resolve",
            "Final cost", "Currency",
        ],
        rows(),
    )  # fmt: skip


def _earliest_requests(db: Session, work_order_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    if not work_order_ids:
        return {}
    return {
        work_order_id: first
        for work_order_id, first in db.execute(
            select(MaintenanceRequest.work_order_id, func.min(MaintenanceRequest.created_at))
            .where(MaintenanceRequest.work_order_id.in_(work_order_ids))
            .group_by(MaintenanceRequest.work_order_id)
        )
    }


def requests_csv(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
) -> Export:
    """Requests submitted in the period. No resident is named and no description is included."""
    found = db.execute(
        select(MaintenanceRequest, Property.name, Unit.label, WorkOrder.number)
        .join(Property, Property.id == MaintenanceRequest.property_id)
        .join(Unit, Unit.id == MaintenanceRequest.unit_id)
        .outerjoin(WorkOrder, WorkOrder.id == MaintenanceRequest.work_order_id)
        .where(
            MaintenanceRequest.organization_id == organization_id,
            *scope_clauses(MaintenanceRequest.property_id, scope, property_id),
            *within(MaintenanceRequest.created_at, period),
        )
        .order_by(MaintenanceRequest.number)
        .limit(MAX_ROWS + 1)
    ).all()
    return render(
        [
            "Reference", "Property", "Unit", "Title", "Category", "Urgency", "Status",
            "Submitted", "Work order",
        ],
        (
            [
                request_service.reference_for(item.number),
                property_name,
                unit_label,
                item.title,
                item.category,
                item.urgency,
                item.status,
                day(item.created_at),
                reference_for(work_order_number) if work_order_number else "",
            ]
            for item, property_name, unit_label, work_order_number in found
        ),
    )  # fmt: skip


def estimates_csv(
    db: Session,
    *,
    organization_id: uuid.UUID,
    scope: PropertyScope,
    period: Period,
    property_id: uuid.UUID | None,
) -> Export:
    """Every estimate recorded in the period, with how it was decided."""
    found = db.execute(
        select(Estimate, WorkOrder.number, Property.name, User.full_name)
        .join(WorkOrder, WorkOrder.id == Estimate.work_order_id)
        .join(Property, Property.id == WorkOrder.property_id)
        .outerjoin(User, User.id == Estimate.decided_by_user_id)
        .where(
            Estimate.organization_id == organization_id,
            *scope_clauses(WorkOrder.property_id, scope, property_id),
            *within(Estimate.created_at, period),
        )
        .order_by(WorkOrder.number, Estimate.version)
        .limit(MAX_ROWS + 1)
    ).all()
    return render(
        [
            "Work order", "Property", "Version", "Amount", "Currency", "Threshold",
            "Needed approval", "Status", "Current", "Recorded", "Decided", "Decided by",
        ],
        (
            [
                reference_for(number),
                property_name,
                item.version,
                money(item.amount_cents),
                item.currency,
                money(item.threshold_cents),
                "Yes" if item.approval_required else "No",
                item.status,
                "Yes" if item.superseded_at is None else "No",
                day(item.created_at),
                day(item.decided_at),
                decided_by,
            ]
            for item, number, property_name, decided_by in found
        ),
    )  # fmt: skip


# --- Owners -----------------------------------------------------------------------------


def owner_estimates_csv(
    db: Session,
    *,
    organization_id: uuid.UUID,
    property_ids: frozenset[uuid.UUID],
    period: Period,
) -> Export:
    """The estimates that needed a decision at the owner's own properties, and the decisions."""
    if not property_ids:
        return render(_OWNER_HEADER, [])
    found = db.execute(
        select(Estimate, WorkOrder.number, WorkOrder.title, Property.name, User.full_name)
        .join(WorkOrder, WorkOrder.id == Estimate.work_order_id)
        .join(Property, Property.id == WorkOrder.property_id)
        .outerjoin(User, User.id == Estimate.decided_by_user_id)
        .where(
            Estimate.organization_id == organization_id,
            Estimate.approval_required.is_(True),
            WorkOrder.property_id.in_(property_ids),
            *within(Estimate.created_at, period),
        )
        .order_by(WorkOrder.number, Estimate.version)
        .limit(MAX_ROWS + 1)
    ).all()
    return render(
        _OWNER_HEADER,
        (
            [
                reference_for(number),
                title,
                property_name,
                item.version,
                money(item.amount_cents),
                item.currency,
                item.status,
                "Yes" if item.superseded_at is None else "No",
                day(item.created_at),
                day(item.decided_at),
                decided_by,
                item.decision_reason,
            ]
            for item, number, title, property_name, decided_by in found
        ),
    )


_OWNER_HEADER = [
    "Work order", "Title", "Property", "Version", "Amount", "Currency", "Status", "Current",
    "Recorded", "Decided", "Decided by", "Reason",
]  # fmt: skip
