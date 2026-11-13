import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models import EstimateStatus, RequestCategory, Urgency, WorkOrderStatus
from app.schemas.directory import OptionalText, Text

# --- Input ------------------------------------------------------------------------------


class EstimateIn(BaseModel):
    # Whole minor units (cents) in the property's currency, so amounts never pass through
    # floating point.
    amount_cents: int = Field(ge=1, le=10**12)
    description: Annotated[Text, Field(min_length=3, max_length=2000)]
    # Who quoted it, such as the contractor's firm.
    provider_name: OptionalText = Field(default=None, max_length=200)


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    # Needed to reject. Optional when approving.
    reason: OptionalText = Field(default=None, max_length=1000)


# --- Output: staff ----------------------------------------------------------------------


class EstimateOut(BaseModel):
    id: uuid.UUID
    version: int
    amount_cents: int
    currency: str
    description: str
    provider_name: str | None
    status: EstimateStatus
    approval_required: bool
    threshold_cents: int | None
    # Whether this is the estimate the work order is currently held to.
    current: bool
    submitted_by_name: str
    submitted_at: datetime
    decided_by_name: str | None
    decided_at: datetime | None
    decision_reason: str | None


class CostCheckOut(BaseModel):
    estimate_cents: int | None
    over_estimate_cents: int | None
    above_approval: bool


# --- Output: the property owner's workspace ---------------------------------------------


class ApprovalSummaryOut(BaseModel):
    id: uuid.UUID
    version: int
    reference: str
    title: str
    work_order_status: WorkOrderStatus
    property_name: str
    location: str | None
    amount_cents: int
    currency: str
    status: EstimateStatus
    current: bool
    # Whether this person can decide on it right now.
    decidable: bool
    submitted_at: datetime
    decided_at: datetime | None


class ApprovalVersionOut(BaseModel):
    id: uuid.UUID
    version: int
    amount_cents: int
    currency: str
    description: str
    provider_name: str | None
    status: EstimateStatus
    approval_required: bool
    current: bool
    submitted_by_name: str
    submitted_at: datetime
    decided_by_name: str | None
    decided_at: datetime | None
    decision_reason: str | None


class ApprovalOut(ApprovalSummaryOut):
    description: str
    provider_name: str | None
    submitted_by_name: str
    decided_by_name: str | None
    decision_reason: str | None
    threshold_cents: int | None
    # The work requested. Nothing from the internal record is included.
    scope: str
    category: RequestCategory
    priority: Urgency
    due_date: date | None
    street: str
    city: str
    region: str
    postal_code: str
    versions: list[ApprovalVersionOut]
