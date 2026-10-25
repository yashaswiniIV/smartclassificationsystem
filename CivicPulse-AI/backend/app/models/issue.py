from datetime import datetime
from typing import Any
from uuid import UUID

from geoalchemy2 import Geography
from sqlalchemy import (
    REAL,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import IssueStatus


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    public_code: Mapped[str] = mapped_column(String, unique=True)
    title: Mapped[str] = mapped_column(String)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    ward_id: Mapped[int] = mapped_column(ForeignKey("wards.id"))
    centroid: Mapped[object] = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, name="issue_status", values_callable=lambda e: [m.value for m in e]),
        server_default=text("'open'"),
    )
    priority_score: Mapped[float] = mapped_column(REAL, server_default="0")
    priority_factors: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    complaint_count: Mapped[int] = mapped_column(Integer, server_default="0")
    upvote_count: Mapped[int] = mapped_column(Integer, server_default="0")
    first_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sla_breached: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_count: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
