"""Reports and exports for managers and administrators (decision 0024).

Everything is limited to the organization and to the properties in the reader's scope. A
property outside that scope is reported as missing, exactly as in every other endpoint.
"""

import uuid
from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.access import OrganizationContext, require_roles
from app.api.deps import DbSession
from app.models import EventType, Role
from app.schemas.reports import ReportOut
from app.services import directory, exports, reports, residents
from app.services.activity import record_event
from app.services.exports import Export, ExportTooLargeError
from app.services.reports import Period, ReportError

router = APIRouter(prefix="/organizations/{organization_id}/reports", tags=["reports"])

StaffContext = Annotated[
    OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR, Role.MANAGER))
]
StartDate = Annotated[date | None, Query(alias="from")]
EndDate = Annotated[date | None, Query(alias="to")]


def resolve_period(start: date | None, end: date | None) -> Period:
    try:
        return reports.resolve_period(start, end, today=residents.today())
    except ReportError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


def check_property(
    db: DbSession, context: OrganizationContext, property_id: uuid.UUID | None
) -> None:
    if property_id is None:
        return
    found = directory.get_property(
        db, organization_id=context.organization.id, property_id=property_id
    )
    if found is None or not context.property_scope.allows(found.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")


@router.get("")
def read_report(
    context: StaffContext,
    db: DbSession,
    start: StartDate = None,
    end: EndDate = None,
    property_id: uuid.UUID | None = None,
) -> ReportOut:
    period = resolve_period(start, end)
    check_property(db, context, property_id)
    return ReportOut(
        **reports.staff_report(
            db,
            organization_id=context.organization.id,
            scope=context.property_scope,
            period=period,
            property_id=property_id,
            today=residents.today(),
        )
    )


def download(
    name: str,
    period: Period,
    context: OrganizationContext,
    db: DbSession,
    build: Callable[[], Export],
) -> Response:
    try:
        export = build()
    except ExportTooLargeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    # Taking data out of the system is worth a record of who did it and how much.
    record_event(
        db,
        event_type=EventType.REPORT_EXPORTED,
        organization_id=context.organization.id,
        actor=context.user,
        subject_type="organization",
        subject_id=context.organization.id,
        after={
            "export": name,
            "period_start": period.start.isoformat(),
            "period_end": period.end.isoformat(),
            "rows": export.rows,
        },
    )
    db.commit()
    return Response(
        content=export.content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}-{period.start}-{period.end}.csv"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/export/work-orders.csv")
def export_work_orders(
    context: StaffContext,
    db: DbSession,
    start: StartDate = None,
    end: EndDate = None,
    property_id: uuid.UUID | None = None,
) -> Response:
    period = resolve_period(start, end)
    check_property(db, context, property_id)
    return download(
        "work-orders",
        period,
        context,
        db,
        lambda: exports.work_orders_csv(
            db,
            organization_id=context.organization.id,
            scope=context.property_scope,
            period=period,
            property_id=property_id,
            today=residents.today(),
        ),
    )


@router.get("/export/requests.csv")
def export_requests(
    context: StaffContext,
    db: DbSession,
    start: StartDate = None,
    end: EndDate = None,
    property_id: uuid.UUID | None = None,
) -> Response:
    period = resolve_period(start, end)
    check_property(db, context, property_id)
    return download(
        "requests",
        period,
        context,
        db,
        lambda: exports.requests_csv(
            db,
            organization_id=context.organization.id,
            scope=context.property_scope,
            period=period,
            property_id=property_id,
        ),
    )


@router.get("/export/estimates.csv")
def export_estimates(
    context: StaffContext,
    db: DbSession,
    start: StartDate = None,
    end: EndDate = None,
    property_id: uuid.UUID | None = None,
) -> Response:
    period = resolve_period(start, end)
    check_property(db, context, property_id)
    return download(
        "estimates",
        period,
        context,
        db,
        lambda: exports.estimates_csv(
            db,
            organization_id=context.organization.id,
            scope=context.property_scope,
            period=period,
            property_id=property_id,
        ),
    )
