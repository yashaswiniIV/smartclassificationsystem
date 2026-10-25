from datetime import date

from sqlalchemy import REAL, Date, ForeignKey, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyStat(Base):
    """Pre-aggregated daily counts per ward x category. Dashboards and forecasting
    read ONLY this table — never a raw scan of complaints/issues (the #1 dashboard
    performance lesson). Rebuilt nightly (and after the synthetic seed)."""

    __tablename__ = "daily_stats"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    ward_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("wards.id"), primary_key=True)
    category_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("categories.id"), primary_key=True
    )
    new_complaints: Mapped[int] = mapped_column(Integer, server_default="0")
    new_issues: Mapped[int] = mapped_column(Integer, server_default="0")
    resolved_issues: Mapped[int] = mapped_column(Integer, server_default="0")
    reopened_issues: Mapped[int] = mapped_column(Integer, server_default="0")
    sla_breaches: Mapped[int] = mapped_column(Integer, server_default="0")
    upvotes: Mapped[int] = mapped_column(Integer, server_default="0")
    avg_resolution_hours: Mapped[float | None] = mapped_column(REAL)
