from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.core.db import SessionDep
from app.schemas.analytics import PublicIssue, PublicStats
from app.services import analytics

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/stats", response_model=PublicStats)
async def stats(db: SessionDep) -> PublicStats:
    """City-wide anonymized counters — no auth, no PII."""
    return PublicStats(**await analytics.public_stats(db))


@router.get("/issues", response_model=list[PublicIssue])
async def public_issues(
    db: SessionDep, limit: Annotated[int, Query(ge=1, le=500)] = 200
) -> list[PublicIssue]:
    """Anonymized open/recent issues for the transparency map. No reporter data;
    coordinates rounded to ~100 m so a point can't be tied back to a person."""
    rows = (
        await db.execute(
            text(
                """
                SELECT i.public_code, i.title, i.status::text AS status,
                       c.name AS category, w.name AS ward,
                       round(ST_X(i.centroid::geometry)::numeric, 3) AS lng,
                       round(ST_Y(i.centroid::geometry)::numeric, 3) AS lat,
                       i.created_at
                FROM issues i
                JOIN categories c ON c.id = i.category_id
                JOIN wards w ON w.id = i.ward_id
                WHERE i.status NOT IN ('rejected')
                ORDER BY i.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).mappings()
    return [
        PublicIssue(
            public_code=r["public_code"],
            title=r["title"],
            status=r["status"],
            category=r["category"],
            ward=r["ward"],
            lng=float(r["lng"]),
            lat=float(r["lat"]),
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]
