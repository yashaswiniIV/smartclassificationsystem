from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ReportListItem(BaseModel):
    id: UUID
    period_start: date
    period_end: date
    scope: str
    created_at: datetime


class ReportOut(ReportListItem):
    stats: dict[str, Any]
    content_md: str | None
