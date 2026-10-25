from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ProcessingStatus
from app.schemas.geo import GeoPoint


class ComplaintCreate(BaseModel):
    description: str = Field(min_length=5, max_length=2000)
    location: GeoPoint
    address_text: str | None = Field(default=None, max_length=300)
    declined_intercept: bool = False


class SimilarCheckIn(BaseModel):
    description: str = Field(min_length=5, max_length=2000)
    location: GeoPoint


class SimilarIssueOut(BaseModel):
    issue_id: str
    public_code: str
    title: str
    status: str
    complaint_count: int
    upvote_count: int
    similarity: float
    distance_m: float


class SimilarCheckOut(BaseModel):
    candidates: list[SimilarIssueOut]


class MediaPresignIn(BaseModel):
    mime: str
    bytes: int = Field(gt=0)


class MediaPresignOut(BaseModel):
    upload_url: str
    object_key: str


class MediaConfirmIn(BaseModel):
    object_key: str
    mime: str
    width: int | None = None
    height: int | None = None


class MediaOut(BaseModel):
    id: UUID
    object_key: str
    mime: str
    url: str
    cv_status: str
    cv_result: dict | None = None
    moderation: str | None = None


class ComplaintOut(BaseModel):
    id: UUID
    public_code: str
    description: str
    address_text: str | None
    ward_id: int | None
    processing_status: ProcessingStatus
    issue_id: UUID | None
    # The citizen tracks the *issue's* status once their complaint is triaged.
    issue_status: str | None = None
    issue_public_code: str | None = None
    location: GeoPoint
    created_at: datetime
    media: list[MediaOut] = []
