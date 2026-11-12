import uuid

from pydantic import BaseModel, Field

from app.models import Role


class SignInRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    roles: list[Role]


class CurrentUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    memberships: list[MembershipOut]


class SessionOut(BaseModel):
    user: CurrentUserOut
    # Must be sent back as the X-CSRF-Token header on every non-read request.
    csrf_token: str
