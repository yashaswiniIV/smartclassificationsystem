from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str | None
    issue_id: UUID | None
    read_at: datetime | None
    created_at: datetime


class MarkReadIn(BaseModel):
    ids: list[UUID] | None = None  # None = mark all read
