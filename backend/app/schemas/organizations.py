import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models import Role


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    roles: list[Role]


class ActivityEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    subject_type: str
    subject_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    occurred_at: datetime
