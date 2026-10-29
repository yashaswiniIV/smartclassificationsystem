"""Analytics: nightly pre-aggregation into daily_stats, plus the read queries the
dashboards use. Dashboards read daily_stats / aggregates, never raw row scans.
"""

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# --- aggregation (rebuild daily_stats from scratch; correct + simple) -------------

_REBUILD_STEPS = [
    "TRUNCATE daily_stats",
    # new complaints per day/ward/category
    """
    INSERT INTO daily_stats (day, ward_id, category_id, new_complaints)
    SELECT created_at::date, ward_id, category_id, count(*)
    FROM complaints
    WHERE ward_id IS NOT NULL AND category_id IS NOT NULL
    GROUP BY 1, 2, 3
    ON CONFLICT (day, ward_id, category_id)
    DO UPDATE SET new_complaints = EXCLUDED.new_complaints
    """,
    # new issues (keyed by first report date)
    """
    INSERT INTO daily_stats (day, ward_id, category_id, new_issues)
    SELECT first_reported_at::date, ward_id, category_id, count(*)
    FROM issues
    GROUP BY 1, 2, 3
    ON CONFLICT (day, ward_id, category_id)
    DO UPDATE SET new_issues = EXCLUDED.new_issues
    """,
    # resolved issues + average resolution hours (keyed by resolution date)
    """
    INSERT INTO daily_stats (day, ward_id, category_id, resolved_issues, avg_resolution_hours)
    SELECT resolved_at::date, ward_id, category_id, count(*),
           avg(EXTRACT(EPOCH FROM (resolved_at - first_reported_at)) / 3600.0)
    FROM issues
    WHERE resolved_at IS NOT NULL
    GROUP BY 1, 2, 3
    ON CONFLICT (day, ward_id, category_id)
    DO UPDATE SET resolved_issues = EXCLUDED.resolved_issues,
                  avg_resolution_hours = EXCLUDED.avg_resolution_hours
    """,
    # SLA breaches (keyed by first report date)
    """
    INSERT INTO daily_stats (day, ward_id, category_id, sla_breaches)
    SELECT first_reported_at::date, ward_id, category_id, count(*)
    FROM issues
    WHERE sla_breached
    GROUP BY 1, 2, 3
    ON CONFLICT (day, ward_id, category_id)
    DO UPDATE SET sla_breaches = EXCLUDED.sla_breaches
    """,
    # upvotes
    """
    INSERT INTO daily_stats (day, ward_id, category_id, upvotes)
    SELECT u.created_at::date, i.ward_id, i.category_id, count(*)
    FROM issue_upvotes u JOIN issues i ON i.id = u.issue_id
    GROUP BY 1, 2, 3
    ON CONFLICT (day, ward_id, category_id)
    DO UPDATE SET upvotes = EXCLUDED.upvotes
    """,
]


async def rebuild_daily_stats(db: AsyncSession) -> int:
    for stmt in _REBUILD_STEPS:
        await db.execute(text(stmt))
    await db.commit()
    total = (await db.execute(text("SELECT count(*) FROM daily_stats"))).scalar_one()
    return int(total)


# --- read queries -----------------------------------------------------------------


async def heatmap(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    category_id: int | None,
) -> list[dict[str, float]]:
    """Grid-aggregated complaint density (~400 m cells) — never ship 100k raw points."""
    rows = (
        await db.execute(
            text(
                """
                SELECT ST_X(g) AS lng, ST_Y(g) AS lat, count(*) AS weight
                FROM (
                    SELECT ST_SnapToGrid(location::geometry, 0.004) AS g
                    FROM complaints
                    WHERE ((:date_from)::date IS NULL OR created_at >= (:date_from)::date)
                      AND ((:date_to)::date IS NULL OR created_at < ((:date_to)::date + 1))
                      AND ((:category_id)::int IS NULL OR category_id = (:category_id)::int)
                ) t
                GROUP BY g
                """
            ),
            {"date_from": date_from, "date_to": date_to, "category_id": category_id},
        )
    ).mappings()
    return [{"lng": r["lng"], "lat": r["lat"], "weight": r["weight"]} for r in rows]


async def trends(
    db: AsyncSession, *, ward_id: int | None, category_id: int | None, weeks: int
) -> list[dict[str, Any]]:
    """Weekly new vs resolved issues, from the pre-aggregated table."""
    rows = (
        await db.execute(
            text(
                """
                SELECT date_trunc('week', day)::date AS week,
                       sum(new_issues) AS new_issues,
                       sum(resolved_issues) AS resolved_issues
                FROM daily_stats
                WHERE day >= (current_date - (:weeks * 7))
                  AND ((:ward_id)::int IS NULL OR ward_id = (:ward_id)::int)
                  AND ((:category_id)::int IS NULL OR category_id = (:category_id)::int)
                GROUP BY week
                ORDER BY week
                """
            ),
            {"weeks": weeks, "ward_id": ward_id, "category_id": category_id},
        )
    ).mappings()
    return [
        {
            "week": r["week"].isoformat(),
            "new_issues": int(r["new_issues"] or 0),
            "resolved_issues": int(r["resolved_issues"] or 0),
        }
        for r in rows
    ]


async def department_performance(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT d.id, d.name,
                  count(i.id) AS total,
                  count(i.id) FILTER (
                      WHERE i.status NOT IN ('resolved','closed','rejected')
                  ) AS open_count,
                  count(i.id) FILTER (WHERE i.sla_breached) AS breached,
                  count(i.id) FILTER (WHERE i.reopen_count > 0) AS reopened,
                  percentile_cont(0.5) WITHIN GROUP (
                      ORDER BY EXTRACT(EPOCH FROM (i.resolved_at - i.first_reported_at)) / 3600
                  ) FILTER (WHERE i.resolved_at IS NOT NULL) AS median_hours
                FROM departments d
                LEFT JOIN issues i ON i.department_id = d.id
                GROUP BY d.id, d.name
                ORDER BY d.name
                """
            )
        )
    ).mappings()
    out = []
    for r in rows:
        total = int(r["total"] or 0)
        out.append(
            {
                "department_id": r["id"],
                "name": r["name"],
                "open_count": int(r["open_count"] or 0),
                "total": total,
                "sla_breach_pct": round(100 * (r["breached"] or 0) / total, 1) if total else 0.0,
                "reopened_pct": round(100 * (r["reopened"] or 0) / total, 1) if total else 0.0,
                "median_resolution_hours": round(float(r["median_hours"]), 1)
                if r["median_hours"] is not None
                else None,
            }
        )
    return out


async def public_stats(db: AsyncSession) -> dict[str, Any]:
    """City-wide, fully anonymized counters for the public dashboard."""
    row = (
        (
            await db.execute(
                text(
                    """
                SELECT
                  count(*) AS total_issues,
                  count(*) FILTER (WHERE status IN ('resolved','closed')) AS resolved,
                  count(*) FILTER (
                      WHERE status NOT IN ('resolved','closed','rejected')
                  ) AS open_issues
                FROM issues
                """
                )
            )
        )
        .mappings()
        .one()
    )
    by_category = (
        await db.execute(
            text(
                """
                SELECT c.name, count(i.id) AS n
                FROM categories c LEFT JOIN issues i ON i.category_id = c.id
                GROUP BY c.name HAVING count(i.id) > 0
                ORDER BY n DESC LIMIT 8
                """
            )
        )
    ).mappings()
    total = int(row["total_issues"] or 0)
    resolved = int(row["resolved"] or 0)
    return {
        "total_issues": total,
        "open_issues": int(row["open_issues"] or 0),
        "resolved_issues": resolved,
        "resolved_pct": round(100 * resolved / total, 1) if total else 0.0,
        "top_categories": [{"name": r["name"], "count": int(r["n"])} for r in by_category],
    }
