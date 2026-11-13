import uuid
from datetime import date

from pydantic import BaseModel

from app.models import RequestCategory, Urgency


class RequestMetricsOut(BaseModel):
    open: int
    waiting_for_triage: int
    submitted_in_period: int
    by_status: dict[str, int]


class PropertyCountOut(BaseModel):
    property_id: uuid.UUID
    property_name: str
    count: int


class WorkOrderMetricsOut(BaseModel):
    by_status: dict[str, int]
    open: int
    overdue: int
    blocked: int
    created_in_period: int
    created_by_category: dict[str, int]
    created_by_property: list[PropertyCountOut]


class PriorityResolutionOut(BaseModel):
    priority: Urgency
    completed: int
    average_hours: float | None


class ResolutionOut(BaseModel):
    completed: int
    average_hours: float | None
    slowest_hours: float | None
    by_priority: list[PriorityResolutionOut]


class ContractorWorkloadOut(BaseModel):
    contractor_id: uuid.UUID
    name: str
    active_jobs: int
    awaiting_response: int
    overdue: int
    completed: int
    sent_back: int
    declined: int


class RepeatIssueOut(BaseModel):
    property_id: uuid.UUID
    property_name: str
    unit_label: str | None
    category: RequestCategory
    count: int
    references: list[str]


class CurrencyTotalOut(BaseModel):
    currency: str
    total_cents: int


class PropertySpendOut(BaseModel):
    property_id: uuid.UUID
    property_name: str
    currency: str
    total_cents: int
    work_orders: int


class CategorySpendOut(BaseModel):
    category: RequestCategory
    currency: str
    total_cents: int


class SpendOut(BaseModel):
    work_orders: int
    total: list[CurrencyTotalOut]
    by_property: list[PropertySpendOut]
    by_category: list[CategorySpendOut]


class PropertyApprovalsOut(BaseModel):
    property_id: uuid.UUID
    property_name: str
    needed_approval: int
    pending: int
    approved: int
    rejected: int


class ApprovalMetricsOut(BaseModel):
    estimates_recorded: int
    needed_approval: int
    pending: int
    approved: int
    rejected: int
    replaced: int
    pending_amounts: list[CurrencyTotalOut]
    approved_amounts: list[CurrencyTotalOut]
    rejected_amounts: list[CurrencyTotalOut]
    average_decision_hours: float | None
    by_property: list[PropertyApprovalsOut]


class ReportOut(BaseModel):
    period_start: date
    period_end: date
    requests: RequestMetricsOut
    work_orders: WorkOrderMetricsOut
    resolution: ResolutionOut
    contractors: list[ContractorWorkloadOut]
    repeat_issues: list[RepeatIssueOut]
    spend: SpendOut
    approvals: ApprovalMetricsOut


class OwnerSummaryOut(BaseModel):
    period_start: date
    period_end: date
    approvals: ApprovalMetricsOut
