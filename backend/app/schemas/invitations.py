import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models import Role


class CreateInvitationRequest(BaseModel):
    email: str = Field(max_length=320)
    roles: list[Role] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def email_looks_valid(cls, value: str) -> str:
        value = value.strip()
        local, _, domain = value.partition("@")
        if not local or "." not in domain or any(character.isspace() for character in value):
            raise ValueError("must be a valid email address")
        return value


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    roles: list[Role]
    status: str
    invited_by_name: str
    created_at: datetime
    expires_at: datetime


class InvitationTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class InvitationPreviewOut(BaseModel):
    organization_name: str
    email: str
    roles: list[Role]
    # Tells the browser app whether to ask for a password (new) or for a sign-in (existing).
    has_account: bool


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    # Only needed when the invited email does not have an account yet.
    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=256)
