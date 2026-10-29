from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import IssueStatus


class IssueStatusHistory(Base):
    """Append-only audit log of every issue status transition. This table — not
    issues.updated_at — is the source of truth for resolution-time analytics."""

    __tablename__ = "issue_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"))
    from_status: Mapped[IssueStatus | None] = mapped_column(
        Enum(IssueStatus, name="issue_status", values_callable=lambda e: [m.value for m in e])
    )
    to_status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, name="issue_status", values_callable=lambda e: [m.value for m in e])
    )
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IssueUpdate(Base):
    """Official timeline entries on an issue (public progress notes or internal notes)."""

    __tablename__ = "issue_updates"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    photo_key: Mapped[str | None] = mapped_column(String)
    is_internal: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
