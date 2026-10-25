"""Weekly AI report: compute the period's figures, have the LLM narrate them
(numbers passed in, never invented), and archive both the stats and the prose.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import llm
from app.models.report import Report
from app.services import predictive


async def _period_stats(db: AsyncSession, start: date, end: date) -> dict[str, Any]:
    row = (
        (
            await db.execute(
                text(
                    """
                SELECT COALESCE(sum(new_issues), 0) AS new_issues,
                       COALESCE(sum(resolved_issues), 0) AS resolved_issues,
                       COALESCE(sum(sla_breaches), 0) AS sla_breaches,
                       COALESCE(sum(new_complaints), 0) AS new_complaints
                FROM daily_stats WHERE day >= :start AND day <= :end
                """
                ),
                {"start": start, "end": end},
            )
        )
        .mappings()
        .one()
    )
    top = (
        (
            await db.execute(
                text(
                    """
                SELECT c.name, sum(ds.new_issues) AS n
                FROM daily_stats ds JOIN categories c ON c.id = ds.category_id
                WHERE ds.day >= :start AND ds.day <= :end
                GROUP BY c.name ORDER BY n DESC LIMIT 1
                """
                ),
                {"start": start, "end": end},
            )
        )
        .mappings()
        .first()
    )
    new_issues = int(row["new_issues"])
    resolved = int(row["resolved_issues"])
    hotspots = await predictive.emerging_hotspots(db)
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "new_issues": new_issues,
        "new_complaints": int(row["new_complaints"]),
        "resolved_issues": resolved,
        "resolved_pct": round(100 * resolved / new_issues, 1) if new_issues else 0.0,
        "sla_breaches": int(row["sla_breaches"]),
        "top_category": top["name"] if top else "n/a",
        "emerging_hotspots": len(hotspots),
    }


async def generate_report(db: AsyncSession, period_days: int = 7) -> Report:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=period_days)
    stats = await _period_stats(db, start, end)
    content_md = await llm.narrate_report(stats)
    report = Report(
        period_start=start, period_end=end, scope="city", stats=stats, content_md=content_md
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report
