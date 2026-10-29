from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import IssueStatus
from app.schemas.geo import GeoPoint


class IssueListItem(BaseModel):
    id: UUID
    public_code: str
    title: str
    status: IssueStatus
    priority_score: float
    category_id: int
    department_id: int
    ward_id: int
    complaint_count: int
    sla_due_at: datetime
    sla_breached: bool
    assigned_to: UUID | None
    assigned_to_name: str | None
    created_at: datetime


class IssueDetail(IssueListItem):
    location: GeoPoint
    first_reported_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None


class IssuePage(BaseModel):
    items: list[IssueListItem]
    total: int
    page: int
    page_size: int


class StatusTransitionIn(BaseModel):
    to_status: IssueStatus
    note: str | None = Field(default=None, max_length=1000)


class AssignIn(BaseModel):
    assignee_id: UUID


class ReopenIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class IssueUpdateIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    is_internal: bool = False


class TimelineEntry(BaseModel):
    kind: str  # "status" | "update"
    created_at: datetime
    actor_id: UUID | None
    text: str | None  # note or update body
    from_status: IssueStatus | None = None
    to_status: IssueStatus | None = None
    is_internal: bool = False


class CreateIssueIn(BaseModel):
    category_id: int
    title: str | None = Field(default=None, max_length=200)


class TriageQueueItem(BaseModel):
    id: UUID
    public_code: str
    description: str
    address_text: str | None
    ward_id: int | None
    processing_status: str
    location: GeoPoint
    created_at: datetime
