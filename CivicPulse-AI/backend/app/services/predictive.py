"""Predictive governance: emerging-hotspot detection, weekly forecasting, ward risk
scores, and LLM root-cause hypotheses. All read the pre-aggregated daily_stats.

Honesty notes (ADR-10): with ~14 months of data we can model TREND, not annual
seasonality — SARIMAX captures the rising signal; forecasts always carry a CI and a
minimum-history rule; the LLM only narrates numbers we compute.
"""

import asyncio
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import llm

RECENT_DAYS = 14
BASELINE_DAYS = 56  # the 8 weeks before the recent window
MIN_RECENT = 3  # ignore low-volume noise (tuned to the per-ward×category scale)
EMERGING_RATIO = 2.0
MIN_HISTORY_WEEKS = 12


# --- emerging hotspots (rate-ratio vs trailing baseline) --------------------------


async def emerging_hotspots(db: AsyncSession, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                WITH recent AS (
                    SELECT ward_id, category_id, sum(new_issues)::int AS n
                    FROM daily_stats WHERE day >= current_date - (:recent)::int
                    GROUP BY 1, 2
                ),
                baseline AS (
                    SELECT ward_id, category_id, sum(new_issues)::int AS n
                    FROM daily_stats
                    WHERE day >= current_date - (:total)::int
                      AND day < current_date - (:recent)::int
                    GROUP BY 1, 2
                )
                SELECT r.ward_id, w.name AS ward_name, r.category_id, c.name AS category_name,
                       r.n AS recent_n, COALESCE(b.n, 0) AS baseline_n,
                       ST_X(ST_PointOnSurface(w.geom)) AS lng,
                       ST_Y(ST_PointOnSurface(w.geom)) AS lat
                FROM recent r
                JOIN wards w ON w.id = r.ward_id
                JOIN categories c ON c.id = r.category_id
                LEFT JOIN baseline b USING (ward_id, category_id)
                WHERE r.n >= (:min_recent)::int
                """
            ),
            {
                "recent": RECENT_DAYS,
                "total": RECENT_DAYS + BASELINE_DAYS,
                "min_recent": MIN_RECENT,
            },
        )
    ).mappings()

    out = []
    for r in rows:
        recent_pw = r["recent_n"] / RECENT_DAYS * 7
        baseline_pw = r["baseline_n"] / BASELINE_DAYS * 7
        ratio = recent_pw / max(baseline_pw, 0.5)
        if ratio >= EMERGING_RATIO:
            out.append(
                {
                    "ward_id": r["ward_id"],
                    "ward_name": r["ward_name"],
                    "category_id": r["category_id"],
                    "category_name": r["category_name"],
                    "recent_per_week": round(recent_pw, 1),
                    "baseline_per_week": round(baseline_pw, 1),
                    "ratio": round(ratio, 1),
                    "lng": r["lng"],
                    "lat": r["lat"],
                }
            )
    out.sort(key=lambda x: x["ratio"], reverse=True)
    return out[:limit]


# --- forecasting ------------------------------------------------------------------


async def _weekly_series(
    db: AsyncSession, category_id: int, ward_id: int | None
) -> list[tuple[date, int]]:
    rows = (
        await db.execute(
            text(
                """
                SELECT date_trunc('week', day)::date AS week, sum(new_issues)::int AS n
                FROM daily_stats
                WHERE category_id = :cat
                  AND ((:ward)::int IS NULL OR ward_id = (:ward)::int)
                GROUP BY week ORDER BY week
                """
            ),
            {"cat": category_id, "ward": ward_id},
        )
    ).all()
    return [(r[0], r[1]) for r in rows]


def _fill_weeks(series: list[tuple[date, int]]) -> tuple[list[str], list[float]]:
    """Fill missing weeks with 0 — time-series models need a regular index."""
    if not series:
        return [], []
    by_week = {w: n for w, n in series}
    weeks, values = [], []
    w = series[0][0]
    end = series[-1][0]
    while w <= end:
        weeks.append(w.isoformat())
        values.append(float(by_week.get(w, 0)))
        w = w + timedelta(days=7)
    return weeks, values


def _sarimax(
    values: list[float], horizon: int
) -> tuple[list[float], list[float], list[float], str]:
    """Fit SARIMAX(1,1,1); on any failure fall back to a naive flat forecast.
    Returns (mean, lower, upper, model_name). Counts clipped at 0."""
    try:
        import warnings

        from statsmodels.tsa.statespace.sarimax import SARIMAX

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = SARIMAX(
                values,
                order=(1, 1, 1),
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False)
            fc = res.get_forecast(horizon)
            mean = [max(0.0, v) for v in fc.predicted_mean]
            ci = fc.conf_int(alpha=0.2)  # 80% interval
            lower = [max(0.0, row[0]) for row in ci]
            upper = [max(0.0, row[1]) for row in ci]
        return mean, lower, upper, "sarimax"
    except Exception:
        tail = values[-4:] or [0.0]
        avg = sum(tail) / len(tail)
        spread = max(1.0, (max(tail) - min(tail)))
        return (
            [round(avg, 1)] * horizon,
            [max(0.0, avg - spread)] * horizon,
            [avg + spread] * horizon,
            "naive",
        )


async def forecast(
    db: AsyncSession, category_id: int, ward_id: int | None, horizon: int = 4
) -> dict[str, Any]:
    series = await _weekly_series(db, category_id, ward_id)
    weeks, values = _fill_weeks(series)
    if len(values) < MIN_HISTORY_WEEKS:
        return {"status": "insufficient_history", "weeks_available": len(values)}

    mean, lower, upper, model = await asyncio.to_thread(_sarimax, values, horizon)

    last_week = date.fromisoformat(weeks[-1])
    forecast_points = []
    for i in range(horizon):
        fw = (last_week + timedelta(days=7 * (i + 1))).isoformat()
        forecast_points.append(
            {
                "week": fw,
                "mean": round(mean[i], 1),
                "lower": round(lower[i], 1),
                "upper": round(upper[i], 1),
            }
        )
    history = [{"week": w, "count": int(v)} for w, v in zip(weeks[-26:], values[-26:], strict=True)]
    return {"status": "ok", "model": model, "history": history, "forecast": forecast_points}


# --- ward risk score (transparent blend) ------------------------------------------


async def ward_risk(db: AsyncSession, limit: int = 12) -> list[dict[str, Any]]:
    base = (
        (
            await db.execute(
                text(
                    """
                SELECT w.id, w.name,
                  count(i.id) FILTER (
                      WHERE i.status NOT IN ('resolved','closed','rejected')
                  ) AS open_n,
                  count(i.id) AS total,
                  count(i.id) FILTER (WHERE i.sla_breached) AS breached
                FROM wards w JOIN issues i ON i.ward_id = w.id
                GROUP BY w.id, w.name
                """
                )
            )
        )
        .mappings()
        .all()
    )
    trend = (
        await db.execute(
            text(
                """
                SELECT ward_id,
                  sum(new_issues) FILTER (WHERE day >= current_date - (:recent)::int) AS recent_n,
                  sum(new_issues) FILTER (
                      WHERE day >= current_date - (:total)::int
                        AND day < current_date - (:recent)::int
                  ) AS baseline_n
                FROM daily_stats GROUP BY ward_id
                """
            ),
            {"recent": RECENT_DAYS, "total": RECENT_DAYS + BASELINE_DAYS},
        )
    ).mappings()
    trend_by_ward = {t["ward_id"]: t for t in trend}

    max_open = max((b["open_n"] or 0 for b in base), default=0) or 1
    rows = []
    for b in base:
        total = b["total"] or 0
        t = trend_by_ward.get(b["id"], {})
        recent_pw = (t.get("recent_n") or 0) / RECENT_DAYS * 7
        baseline_pw = (t.get("baseline_n") or 0) / BASELINE_DAYS * 7
        trend_ratio = recent_pw / max(baseline_pw, 0.5)

        factors = {
            "open_density": round((b["open_n"] or 0) / max_open, 3),
            "sla_breach_rate": round((b["breached"] or 0) / total, 3) if total else 0.0,
            "rising_trend": round(min(trend_ratio / 3, 1.0), 3),
        }
        score = 100 * (
            0.4 * factors["open_density"]
            + 0.3 * factors["sla_breach_rate"]
            + 0.3 * factors["rising_trend"]
        )
        rows.append(
            {
                "ward_id": b["id"],
                "ward_name": b["name"],
                "risk_score": round(score, 1),
                "open_count": b["open_n"] or 0,
                "factors": factors,
            }
        )
    rows.sort(key=lambda x: x["risk_score"], reverse=True)
    return rows[:limit]


# --- root-cause hypothesis --------------------------------------------------------


async def root_cause(db: AsyncSession, ward_id: int) -> dict[str, Any]:
    row = (
        (
            await db.execute(
                text(
                    """
                WITH recent AS (
                    SELECT ds.category_id, c.name AS category_name,
                           sum(ds.new_issues)::int AS recent_n
                    FROM daily_stats ds JOIN categories c ON c.id = ds.category_id
                    WHERE ds.ward_id = :ward AND ds.day >= current_date - (:recent)::int
                    GROUP BY 1, 2 ORDER BY recent_n DESC LIMIT 1
                ),
                baseline AS (
                    SELECT category_id, sum(new_issues)::int AS baseline_n
                    FROM daily_stats
                    WHERE ward_id = :ward
                      AND day >= current_date - (:total)::int
                      AND day < current_date - (:recent)::int
                    GROUP BY 1
                )
                SELECT w.name AS ward_name, r.category_name,
                       r.recent_n, COALESCE(b.baseline_n, 0) AS baseline_n
                FROM recent r
                CROSS JOIN wards w
                LEFT JOIN baseline b ON b.category_id = r.category_id
                WHERE w.id = :ward
                """
                ),
                {"ward": ward_id, "recent": RECENT_DAYS, "total": RECENT_DAYS + BASELINE_DAYS},
            )
        )
        .mappings()
        .first()
    )

    if row is None:
        return {
            "ward_id": ward_id,
            "hypothesis": "Not enough recent data for a hypothesis.",
            "stats": {},
        }

    recent_pw = row["recent_n"] / RECENT_DAYS * 7
    baseline_pw = row["baseline_n"] / BASELINE_DAYS * 7
    stats = {
        "ward_name": row["ward_name"],
        "top_category": row["category_name"],
        "recent_per_week": round(recent_pw, 1),
        "baseline_per_week": round(baseline_pw, 1),
        "ratio": round(recent_pw / max(baseline_pw, 0.5), 1),
    }
    hypothesis = await llm.hypothesize_causes(stats)
    return {
        "ward_id": ward_id,
        "ward_name": row["ward_name"],
        "hypothesis": hypothesis,
        "stats": stats,
    }
