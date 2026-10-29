from datetime import datetime
from typing import Any
from uuid import UUID

from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    REAL,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import CvStatus, ModerationStatus, ProcessingStatus


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    public_code: Mapped[str] = mapped_column(String, unique=True)
    citizen_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    issue_id: Mapped[UUID | None] = mapped_column(ForeignKey("issues.id"))
    description: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(2))
    location: Mapped[object] = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    address_text: Mapped[str | None] = mapped_column(String)
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("wards.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    ai_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    ai_category_confidence: Mapped[float | None] = mapped_column(REAL)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(
            ProcessingStatus,
            name="processing_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        server_default=text("'queued'"),
    )
    declined_intercept: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    submitted_via: Mapped[str] = mapped_column(String, server_default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ComplaintMedia(Base):
    __tablename__ = "complaint_media"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    complaint_id: Mapped[UUID] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"))
    object_key: Mapped[str] = mapped_column(String)
    mime: Mapped[str] = mapped_column(String)
    bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    exif_gps: Mapped[object | None] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False)
    )
    cv_status: Mapped[CvStatus] = mapped_column(
        Enum(CvStatus, name="cv_status", values_callable=lambda e: [m.value for m in e]),
        server_default=text("'pending'"),
    )
    cv_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    moderation: Mapped[ModerationStatus] = mapped_column(
        Enum(
            ModerationStatus,
            name="moderation_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
