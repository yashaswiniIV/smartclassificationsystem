from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    REAL,
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import AiJobStatus, CorrectionKind


class AiJob(Base):
    """Telemetry for every AI pipeline run/step: model, latency, confidence, outcome.
    Doubles as the pipeline-metrics source the admin UI can chart."""

    __tablename__ = "ai_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String)  # process_complaint | embed | classify | ...
    complaint_id: Mapped[UUID | None] = mapped_column(ForeignKey("complaints.id"))
    status: Mapped[AiJobStatus] = mapped_column(
        Enum(AiJobStatus, name="ai_job_status", values_callable=lambda e: [m.value for m in e]),
        server_default=text("'queued'"),
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    model: Mapped[str | None] = mapped_column(String)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(REAL)
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Correction(Base):
    """THE DATA FLYWHEEL: every time an official overrides an AI decision, log it.
    Months of these = a labeled dataset to train a supervised model later."""

    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    complaint_id: Mapped[UUID] = mapped_column(ForeignKey("complaints.id"))
    official_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[CorrectionKind] = mapped_column(
        Enum(
            CorrectionKind,
            name="correction_kind",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    before: Mapped[dict[str, Any]] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IssueUpvote(Base):
    """A citizen 'me too' on an existing issue (from the duplicate intercept).
    Subscribes them to updates and feeds the priority volume signal."""

    __tablename__ = "issue_upvotes"

    issue_id: Mapped[UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
