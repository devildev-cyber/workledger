import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import Role


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    roles: list[Role]
    is_active: bool
    joined_at: datetime


class UpdateMemberRolesRequest(BaseModel):
    roles: list[Role] = Field(min_length=1)
