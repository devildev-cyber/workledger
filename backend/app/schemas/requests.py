import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from app.models import RequestCategory, RequestStatus, UpdateKind, Urgency, Visibility
from app.schemas.directory import OptionalText, Text

# --- Input ------------------------------------------------------------------------------


class RequestIn(BaseModel):
    unit_id: uuid.UUID
    category: RequestCategory
    urgency: Urgency
    title: Annotated[Text, Field(min_length=3, max_length=200)]
    description: Annotated[Text, Field(min_length=1, max_length=5000)]
    location: Annotated[OptionalText, Field(max_length=200)] = None
    access_notes: Annotated[OptionalText, Field(max_length=1000)] = None


class StaffRequestIn(RequestIn):
    """A request entered by staff for a resident, for example after a phone call."""

    resident_id: uuid.UUID


class MessageIn(BaseModel):
    body: Annotated[Text, Field(min_length=1, max_length=2000)]


class StaffUpdateIn(BaseModel):
    body: Annotated[OptionalText, Field(max_length=2000)] = None
    # Internal unless the manager chooses otherwise, so a note is never shown by accident.
    visibility: Visibility = Visibility.INTERNAL
    status: RequestStatus | None = None

    @model_validator(mode="after")
    def has_something_to_record(self) -> "StaffUpdateIn":
        if self.body is None and self.status is None:
            raise ValueError("Write a note or choose a new status")
        return self


# --- Output a resident may receive ------------------------------------------------------
# These models have no field for internal notes, staff identities, or other people's
# details, so a resident response cannot include them by accident (decision 0017).


class AttachmentOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class TimelineEntryOut(BaseModel):
    id: uuid.UUID
    kind: UpdateKind
    body: str | None
    status: RequestStatus | None
    created_at: datetime
    # "You", or "Property team" for anyone on the staff.
    author: str


class RequestSummaryOut(BaseModel):
    id: uuid.UUID
    reference: str
    status: RequestStatus
    category: RequestCategory
    urgency: Urgency
    title: str
    property_name: str
    unit_label: str
    building_name: str | None
    created_at: datetime
    updated_at: datetime


class ResidentRequestOut(RequestSummaryOut):
    description: str
    location: str | None
    access_notes: str | None
    can_cancel: bool
    can_message: bool
    timeline: list[TimelineEntryOut]
    attachments: list[AttachmentOut]


# --- Output for staff -------------------------------------------------------------------


class StaffAttachmentOut(AttachmentOut):
    visibility: Visibility


class StaffTimelineEntryOut(BaseModel):
    id: uuid.UUID
    kind: UpdateKind
    visibility: Visibility
    body: str | None
    status: RequestStatus | None
    created_at: datetime
    author_name: str | None


class RequesterOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    access_instructions: str | None
    has_account: bool


class StaffRequestSummaryOut(RequestSummaryOut):
    property_id: uuid.UUID
    resident_name: str
    submitted_on_behalf: bool


class StaffRequestOut(StaffRequestSummaryOut):
    description: str
    location: str | None
    access_notes: str | None
    resident: RequesterOut
    timeline: list[StaffTimelineEntryOut]
    attachments: list[StaffAttachmentOut]
