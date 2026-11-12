import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, field_validator


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _blank_to_none(value: object) -> object:
    value = _strip(value)
    return None if value == "" else value


# Text the person typed, with surrounding spaces removed.
Text = Annotated[str, BeforeValidator(_strip)]
RequiredName = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=200)]
OptionalText = Annotated[str | None, BeforeValidator(_blank_to_none)]


# --- Properties and units ---------------------------------------------------------------


class PropertyIn(BaseModel):
    name: RequiredName
    street: Annotated[Text, Field(max_length=200)] = ""
    city: Annotated[Text, Field(max_length=120)] = ""
    region: Annotated[Text, Field(max_length=120)] = ""
    postal_code: Annotated[Text, Field(max_length=32)] = ""
    currency: str = "USD"
    # Whole minor units (cents), so amounts never pass through floating point.
    approval_threshold_cents: int | None = Field(default=None, ge=0, le=10**12)

    @field_validator("currency")
    @classmethod
    def currency_is_a_code(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha() or not value.isascii():
            raise ValueError("must be a three-letter currency code, such as USD")
        return value


class BuildingIn(BaseModel):
    name: RequiredName


class BuildingOut(BaseModel):
    id: uuid.UUID
    name: str


class PropertyOut(BaseModel):
    id: uuid.UUID
    name: str
    street: str
    city: str
    region: str
    postal_code: str
    currency: str
    approval_threshold_cents: int | None
    unit_count: int
    buildings: list[BuildingOut]


class UnitIn(BaseModel):
    label: Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=100)]
    building_id: uuid.UUID | None = None


class ResidentRefOut(BaseModel):
    id: uuid.UUID
    full_name: str


class UnitOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    building_id: uuid.UUID | None
    label: str
    current_residents: list[ResidentRefOut]


# --- Residents --------------------------------------------------------------------------


class ResidentIn(BaseModel):
    full_name: RequiredName
    email: OptionalText = Field(default=None, max_length=320)
    phone: OptionalText = Field(default=None, max_length=50)
    access_instructions: OptionalText = Field(default=None, max_length=2000)

    @field_validator("email")
    @classmethod
    def email_looks_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        local, _, domain = value.partition("@")
        if not local or "." not in domain or any(character.isspace() for character in value):
            raise ValueError("must be a valid email address")
        return value.lower()


class TenancyOut(BaseModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    unit_label: str
    building_name: str | None
    property_id: uuid.UUID
    property_name: str
    move_in_date: date
    move_out_date: date | None
    is_current: bool


class ResidentOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    access_instructions: str | None
    # True once the resident has an account that is linked to this record.
    has_account: bool
    tenancies: list[TenancyOut]


class StartTenancyIn(BaseModel):
    unit_id: uuid.UUID
    resident_id: uuid.UUID
    move_in_date: date


class EndTenancyIn(BaseModel):
    move_out_date: date


class MyHomeOut(BaseModel):
    """What a resident may see about their own home. Nothing about anyone else."""

    tenancy_id: uuid.UUID
    property_name: str
    street: str
    city: str
    region: str
    postal_code: str
    building_name: str | None
    unit_label: str
    move_in_date: date
    move_out_date: date | None


# --- Managers ---------------------------------------------------------------------------


class ManagerOut(BaseModel):
    membership_id: uuid.UUID
    full_name: str
    email: str
    assigned: bool


class SetManagersIn(BaseModel):
    membership_ids: list[uuid.UUID]
