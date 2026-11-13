"""The property owner's workspace: estimates above the threshold, at their own properties.

Every lookup goes through the properties this owner has been given. An estimate at someone
else's property, or in another organization, looks exactly like one that does not exist. An
owner never receives the internal record: no notes, history, residents, files, or contractors.
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession
from app.api.reports import download, resolve_period
from app.core.permissions import PropertyScope
from app.models import Role
from app.schemas.estimates import (
    ApprovalOut,
    ApprovalSummaryOut,
    ApprovalVersionOut,
    DecisionIn,
)
from app.schemas.reports import OwnerSummaryOut
from app.services import estimates, exports, ownerships, reports
from app.services.estimates import OwnerRow
from app.services.work_orders import NotPermittedError, WorkOrderError, reference_for

router = APIRouter(prefix="/organizations/{organization_id}/my-approvals", tags=["approvals"])

OwnerContext = Annotated[OrganizationContext, Depends(require_roles(Role.PROPERTY_OWNER))]


def _owned(db: DbSession, context: OrganizationContext) -> frozenset[uuid.UUID]:
    return frozenset(ownerships.owned_property_ids(db, context.membership.id))


def _location(row: OwnerRow) -> str | None:
    if row.unit is None:
        return None
    building = f"{row.building.name} · " if row.building else ""
    return f"{building}{row.unit.label}"


def _summary_fields(row: OwnerRow, context: OrganizationContext) -> dict[str, object]:
    item = row.estimate
    return {
        "id": item.id,
        "version": item.version,
        "reference": reference_for(row.work_order.number),
        "title": row.work_order.title,
        "work_order_status": row.work_order.status,
        "property_name": row.property.name,
        "location": _location(row),
        "amount_cents": item.amount_cents,
        "currency": item.currency,
        "status": item.status,
        "current": item.superseded_at is None,
        "decidable": estimates.is_decidable(item, row.work_order, user_id=context.user.id),
        "submitted_at": item.created_at,
        "decided_at": item.decided_at,
    }


def _detail(db: DbSession, context: OrganizationContext, row: OwnerRow) -> ApprovalOut:
    records = estimates.records_for(db, row.work_order.id)
    current = next(record for record in records if record.estimate.id == row.estimate.id)
    return ApprovalOut(
        **_summary_fields(row, context),
        description=row.estimate.description,
        provider_name=row.estimate.provider_name,
        submitted_by_name=current.submitted_by_name,
        decided_by_name=current.decided_by_name,
        decision_reason=row.estimate.decision_reason,
        threshold_cents=row.estimate.threshold_cents,
        scope=row.work_order.scope,
        category=row.work_order.category,
        priority=row.work_order.priority,
        due_date=row.work_order.due_date,
        street=row.property.street,
        city=row.property.city,
        region=row.property.region,
        postal_code=row.property.postal_code,
        versions=[
            ApprovalVersionOut(
                id=record.estimate.id,
                version=record.estimate.version,
                amount_cents=record.estimate.amount_cents,
                currency=record.estimate.currency,
                description=record.estimate.description,
                provider_name=record.estimate.provider_name,
                status=record.estimate.status,
                approval_required=record.estimate.approval_required,
                current=record.estimate.superseded_at is None,
                submitted_by_name=record.submitted_by_name,
                submitted_at=record.estimate.created_at,
                decided_by_name=record.decided_by_name,
                decided_at=record.estimate.decided_at,
                decision_reason=record.estimate.decision_reason,
            )
            for record in records
        ],
    )


def _row(db: DbSession, context: OrganizationContext, estimate_id: uuid.UUID) -> OwnerRow:
    row = estimates.get_for_owner(
        db,
        organization_id=context.organization.id,
        property_ids=_owned(db, context),
        estimate_id=estimate_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estimate not found")
    return row


@router.get("")
def list_approvals(context: OwnerContext, db: DbSession) -> list[ApprovalSummaryOut]:
    rows = estimates.list_for_owner(
        db, organization_id=context.organization.id, property_ids=_owned(db, context)
    )
    return [ApprovalSummaryOut(**_summary_fields(row, context)) for row in rows]


StartDate = Annotated[date | None, Query(alias="from")]
EndDate = Annotated[date | None, Query(alias="to")]


@router.get("/summary")
def read_summary(
    context: OwnerContext, db: DbSession, start: StartDate = None, end: EndDate = None
) -> OwnerSummaryOut:
    """The owner's own approval activity. Spending and the rest of the report stay with staff."""
    period = resolve_period(start, end)
    scope = PropertyScope(unrestricted=False, property_ids=_owned(db, context))
    return OwnerSummaryOut(
        period_start=period.start,
        period_end=period.end,
        approvals=reports.approval_metrics(
            db,
            organization_id=context.organization.id,
            scope=scope,
            period=period,
            property_id=None,
        ),
    )


@router.get("/export.csv")
def export_estimates(
    context: OwnerContext, db: DbSession, start: StartDate = None, end: EndDate = None
) -> Response:
    period = resolve_period(start, end)
    owned = _owned(db, context)
    return download(
        "approvals",
        period,
        context,
        db,
        lambda: exports.owner_estimates_csv(
            db, organization_id=context.organization.id, property_ids=owned, period=period
        ),
    )


@router.get("/{estimate_id}")
def read_approval(estimate_id: uuid.UUID, context: OwnerContext, db: DbSession) -> ApprovalOut:
    return _detail(db, context, _row(db, context, estimate_id))


@router.post("/{estimate_id}/decision")
def decide(
    estimate_id: uuid.UUID, body: DecisionIn, context: OwnerContext, db: DbSession
) -> ApprovalOut:
    row = _row(db, context, estimate_id)
    try:
        estimates.decide(
            db,
            row.estimate,
            row.work_order,
            actor=context.user,
            membership_id=context.membership.id,
            approve=body.decision == "approve",
            reason=body.reason,
        )
    except NotPermittedError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except WorkOrderError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.commit()
    return _detail(db, context, _row(db, context, estimate_id))
