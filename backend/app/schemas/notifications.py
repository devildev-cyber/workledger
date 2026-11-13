import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    # Where in the app it leads, written for this reader.
    path: str
    read: bool
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int


class NotificationPreferencesIn(BaseModel):
    email_enabled: bool


class NotificationPreferencesOut(BaseModel):
    email_enabled: bool
