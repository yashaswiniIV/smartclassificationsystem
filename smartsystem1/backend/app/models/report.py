from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Report(Base):
    """A generated period report. `stats` is the numbers we computed and handed to
    the LLM — kept so every figure in `content_md` is traceable (the LLM narrates,
    it never invents)."""

    __tablename__ = "reports"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    scope: Mapped[str] = mapped_column(String, server_default="city")
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_md: Mapped[str | None] = mapped_column(Text)
    pdf_key: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
