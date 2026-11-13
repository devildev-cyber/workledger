import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field

from app.models import (
    AssignmentResponse,
    EntryKind,
    RequestCategory,
    RequestStatus,
    Urgency,
    Visibility,
    WorkOrderStatus,
)
from app.schemas.directory import OptionalText, Text

Title = Annotated[Text, Field(min_length=3, max_length=200)]
Scope = Annotated[Text, Field(min_length=1, max_length=5000)]

# --- Input ------------------------------------------------------------------------------


class WorkOrderIn(BaseModel):
    property_id: uuid.UUID
    unit_id: uuid.UUID | None = None
    title: Title
    scope: Scope
    category: RequestCategory
    priority: Urgency
    due_date: date | None = None


class ConvertIn(BaseModel):
    """Anything left out is taken from the request."""

    title: Title | None = None
    scope: Scope | None = None
    category: RequestCategory | None = None
    priority: Urgency | None = None
    due_date: date | None = None


class WorkOrderEditIn(BaseModel):
    title: Title
    scope: Scope
    category: RequestCategory
    priority: Urgency
    due_date: date | None = None


class StatusChangeIn(BaseModel):
    status: WorkOrderStatus
    note: OptionalText = Field(default=None, max_length=1000)


class VerifyIn(BaseModel):
    # What was done, in the manager's words. Required: it is the record that closes the loop.
    resolution: Annotated[Text, Field(min_length=3, max_length=2000)]
    # Whole minor units (cents), so amounts never pass through floating point. Leave out when
    # there was no charge to record. The currency defaults to the property's.
    final_cost_cents: int | None = Field(default=None, ge=0, le=10**12)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class SendBackIn(BaseModel):
    reason: Annotated[Text, Field(min_length=3, max_length=1000)]


class NoteIn(BaseModel):
    body: Annotated[Text, Field(min_length=1, max_length=2000)]
    visibility: Visibility = Visibility.INTERNAL
    # Notes are for staff only unless the manager also shares them with the contractor.
    share_with_contractor: bool = False


class AssignIn(BaseModel):
    # The contractor's membership ID, as listed by GET /contractors.
    contractor_id: uuid.UUID


class DeclineIn(BaseModel):
    reason: Annotated[Text, Field(min_length=3, max_length=1000)]


class DuplicateIn(BaseModel):
    duplicate_of_id: uuid.UUID


# --- Output -----------------------------------------------------------------------------


class WorkOrderRefOut(BaseModel):
    id: uuid.UUID
    reference: str
    status: WorkOrderStatus


class AssignmentOut(BaseModel):
    id: uuid.UUID
    contractor_id: uuid.UUID
    contractor_name: str
    assigned_by_name: str
    assigned_at: datetime
    response: AssignmentResponse
    responded_at: datetime | None
    decline_reason: str | None
    ended_at: datetime | None
    ended_reason: str | None


class ContractorOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    active_jobs: int


class WorkOrderAttachmentOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    contractor_visible: bool
    uploaded_by_name: str | None
    created_at: datetime


class WorkOrderSummaryOut(BaseModel):
    id: uuid.UUID
    reference: str
    title: str
    status: WorkOrderStatus
    priority: Urgency
    category: RequestCategory
    property_id: uuid.UUID
    property_name: str
    unit_label: str | None
    building_name: str | None
    due_date: date | None
    overdue: bool
    request_count: int
    assignee_id: uuid.UUID | None
    assignee_name: str | None
    assignment_response: AssignmentResponse | None
    final_cost_cents: int | None
    currency: str | None
    created_at: datetime
    updated_at: datetime


class LinkedRequestOut(BaseModel):
    id: uuid.UUID
    reference: str
    title: str
    status: RequestStatus
    resident_name: str


class WorkOrderEntryOut(BaseModel):
    id: uuid.UUID
    kind: EntryKind
    visibility: Visibility
    body: str | None
    status: WorkOrderStatus | None
    details: dict[str, Any] | None
    author_name: str | None
    created_at: datetime


class WorkOrderOut(WorkOrderSummaryOut):
    scope: str
    linked_requests: list[LinkedRequestOut]
    history: list[WorkOrderEntryOut]
    assignment: AssignmentOut | None
    assignment_history: list[AssignmentOut]
    attachments: list[WorkOrderAttachmentOut]
    # The currency suggested when recording a final cost.
    property_currency: str
    resolution: str | None
    verified_by_name: str | None
    verified_at: datetime | None
    # What this person can move it to by hand right now.
    allowed_statuses: list[WorkOrderStatus]
