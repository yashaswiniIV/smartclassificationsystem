"""Transparent, rule-based priority score (v1). Every factor is stored in
issue.priority_factors so the UI can show *why* a number is what it is. When months
of corrections + resolution data exist, a learned re-ranker can replace this — but
honest rules beat a black box trained on nothing (see ADR-10 / PRD risk table).
"""

import math
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.issue import Issue
from app.models.org import Category

WEIGHTS = {"severity": 0.35, "volume": 0.25, "age": 0.20, "cv": 0.10, "poi": 0.10}


async def recompute(db: AsyncSession, issue: Issue) -> None:
    category = await db.get(Category, issue.category_id)
    severity = (category.severity_weight if category else 3) / 5.0

    reach = issue.complaint_count + issue.upvote_count
    volume = math.log1p(reach) / math.log1p(50)  # saturates ~50 reporters

    first = issue.first_reported_at
    if first.tzinfo is None:
        first = first.replace(tzinfo=UTC)
    age_days = (datetime.now(UTC) - first).total_seconds() / 86400
    age = min(age_days / 14, 1.0)

    # CV signal: strongest defect severity any photo on this issue showed (Day 8).
    cv_row = (
        await db.execute(
            text(
                "SELECT max((cm.cv_result->>'severity')::float) "
                "FROM complaint_media cm JOIN complaints c ON c.id = cm.complaint_id "
                "WHERE c.issue_id = :iid AND cm.cv_result IS NOT NULL"
            ),
            {"iid": issue.id},
        )
    ).scalar()
    cv = float(cv_row) if cv_row is not None else 0.0
    poi = 0.0  # proximity to schools/hospitals — later

    factors = {
        "severity": round(severity, 4),
        "volume": round(volume, 4),
        "age": round(age, 4),
        "cv": cv,
        "poi": poi,
    }
    raw = sum(WEIGHTS[k] * factors[k] for k in WEIGHTS)
    issue.priority_score = round(100 * min(raw, 1.0), 2)
    issue.priority_factors = factors
