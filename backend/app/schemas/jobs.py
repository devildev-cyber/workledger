"""What a contractor may see of a work order (decision 0020).

These models have no fields for the resident's phone or email, internal notes, other
contractors, costs, or the people on the manager's side, so a contractor response cannot
include them by accident.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models import (
    AssignmentResponse,
    EntryKind,
    RequestCategory,
    Urgency,
    WorkOrderStatus,
)
from app.schemas.directory import OptionalText, Text


class DeclineJobIn(BaseModel):
    reason: Annotated[Text, Field(min_length=3, max_length=1000)]


class JobStatusIn(BaseModel):
    status: WorkOrderStatus
    note: OptionalText = Field(default=None, max_length=1000)


class JobEntryIn(BaseModel):
    body: Annotated[Text, Field(min_length=1, max_length=2000)]
    kind: EntryKind = EntryKind.NOTE


class JobSummaryOut(BaseModel):
    id: uuid.UUID
    reference: str
    title: str
    status: WorkOrderStatus
    priority: Urgency
    category: RequestCategory
    due_date: date | None
    overdue: bool
    property_name: str
    unit_label: str | None
    building_name: str | None
    response: AssignmentResponse


class JobEntryOut(BaseModel):
    id: uuid.UUID
    kind: EntryKind
    # Withheld on status changes made by someone else, in case the reason is internal.
    body: str | None
    status: WorkOrderStatus | None
    author: str
    created_at: datetime


class JobAttachmentOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    mine: bool
    created_at: datetime


class JobOut(JobSummaryOut):
    scope: str
    street: str
    city: str
    region: str
    postal_code: str
    # Resident first names and entry instructions come only after the job is accepted.
    residents: list[str]
    access_notes: list[str]
    can_accept: bool
    can_decline: bool
    allowed_statuses: list[WorkOrderStatus]
    timeline: list[JobEntryOut]
    attachments: list[JobAttachmentOut]
