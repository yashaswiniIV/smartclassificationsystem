"""Generate a realistic ~14-month history of Bengaluru civic complaints so the
dashboards and (Day 7) forecasting have real structure to show.

Model:
  - Poisson arrivals per ward x category x day at a low base rate.
  - Monsoon seasonality: Jun-Sep boosts waterlogging / water-supply categories.
  - One injected HOTSPOT ward where potholes ramp up over the last ~10 weeks
    (so emerging-hotspot detection and forecasting have a signal to find).
  - Issues age realistically: older ones mostly resolved/closed (with resolution
    times), recent ones in progress; SLA breaches derived from due vs resolved.

Bypasses the AI pipeline on purpose (no embeddings) — analytics reads aggregates,
not vectors, and this keeps generation fast.

Run from backend/:  uv run python -m scripts.generate_synthetic
"""

import asyncio
import math
import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, text

from app.core.db import session_factory
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.org import Category
from app.models.user import User
from app.services.analytics import rebuild_daily_stats

random.seed(42)

DAYS = 430  # ~14 months back from today
NUM_WARDS = 50  # subset for density
NUM_CITIZENS = 25
BASE_LAMBDA = 0.012  # baseline issues per ward x category x day
MONSOON_MONTHS = {6, 7, 8, 9}
MONSOON_CATEGORIES = {"Waterlogging / flooding", "Water pipe leakage", "No water supply"}
MONSOON_LAMBDA = 0.25  # water categories surge in monsoon (absolute daily rate)
HOTSPOT_CATEGORY = "Pothole"
HOTSPOT_SURGE_DAYS = 21  # the hotspot ward spikes over the last 3 weeks
HOTSPOT_LAMBDA = 0.8  # ~11 pothole reports in 14 days vs a near-zero baseline

DESC = {
    "Pothole": "Pothole on the road causing problems for commuters",
    "default": "Civic issue reported by a resident",
}


def _poisson(lam: float) -> int:
    if lam <= 0:
        return 0
    target = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= target:
            return k - 1


async def _citizen_ids(db) -> list:
    ids = []
    for i in range(NUM_CITIZENS):
        email = f"synth.citizen.{i}@example.com"
        existing = (
            await db.execute(select(User.id).where(User.email == email))
        ).scalar_one_or_none()
        if existing:
            ids.append(existing)
            continue
        u = User(
            email=email,
            full_name=f"Synthetic Citizen {i}",
            role=UserRole.citizen,
            password_hash=hash_password("synthetic123"),
            email_verified_at=datetime.now(UTC),
        )
        db.add(u)
        await db.flush()
        ids.append(u.id)
    await db.commit()
    return ids


def _lambda(ward_id: int, cat_name: str, day: datetime, hotspot_ward: int, today) -> float:
    days_ago = (today - day.date()).days
    lam = BASE_LAMBDA
    # Monsoon: water categories surge Jun–Sep (seasonality the forecast can show).
    if day.month in MONSOON_MONTHS and cat_name in MONSOON_CATEGORIES:
        lam = MONSOON_LAMBDA
    # Hotspot: one ward's potholes spike sharply in the last 3 weeks (emerging signal).
    if ward_id == hotspot_ward and cat_name == HOTSPOT_CATEGORY and days_ago <= HOTSPOT_SURGE_DAYS:
        lam = HOTSPOT_LAMBDA
    return lam


async def main() -> None:
    async with session_factory() as db:
        citizens = await _citizen_ids(db)
        wards = (
            (
                await db.execute(
                    text(
                        "SELECT id, ST_X(ST_PointOnSurface(geom)) AS lng, "
                        "ST_Y(ST_PointOnSurface(geom)) AS lat "
                        "FROM wards ORDER BY id LIMIT :n"
                    ),
                    {"n": NUM_WARDS},
                )
            )
            .mappings()
            .all()
        )
        cats = (await db.execute(select(Category))).scalars().all()
        if not wards or not cats:
            print("No wards/categories — run scripts.seed first.")
            return

        hotspot_ward = wards[0]["id"]
        today = datetime.now(UTC).date()
        run = uuid4().hex[:6]

        issue_rows: list[dict] = []
        complaint_rows: list[dict] = []
        seq = 0

        for d in range(DAYS):
            day_dt = datetime.now(UTC) - timedelta(days=DAYS - d)
            age_days = (today - day_dt.date()).days
            for w in wards:
                for cat in cats:
                    n = _poisson(_lambda(w["id"], cat.name, day_dt, hotspot_ward, today))
                    for _ in range(n):
                        seq += 1
                        lng = w["lng"] + random.uniform(-0.004, 0.004)
                        lat = w["lat"] + random.uniform(-0.004, 0.004)
                        sla_due = day_dt + timedelta(hours=cat.sla_hours)

                        resolved_at = None
                        if age_days > 21 and random.random() < 0.82:
                            status = random.choice(["closed", "closed", "resolved"])
                            resolved_at = day_dt + timedelta(
                                hours=random.uniform(6, cat.sla_hours * 1.6)
                            )
                        elif age_days > 3:
                            status = random.choice(
                                ["acknowledged", "assigned", "in_progress", "in_progress"]
                            )
                        else:
                            status = "open"

                        now = datetime.now(UTC)
                        if resolved_at is not None:
                            breached = resolved_at > sla_due
                        else:
                            breached = now > sla_due

                        issue_id = uuid4()
                        issue_rows.append(
                            {
                                "id": issue_id,
                                "public_code": f"ISS-SYN-{run}-{seq}",
                                "title": f"{cat.name} near reported location",
                                "category_id": cat.id,
                                "department_id": cat.department_id,
                                "ward_id": w["id"],
                                "lng": lng,
                                "lat": lat,
                                "status": status,
                                "priority": round(random.uniform(10, 90), 1),
                                "first": day_dt,
                                "sla_due": sla_due,
                                "breached": breached,
                                "resolved_at": resolved_at,
                            }
                        )
                        for _c in range(1 + _poisson(0.8)):
                            complaint_rows.append(
                                {
                                    "id": uuid4(),
                                    "public_code": f"CP-SYN-{run}-{len(complaint_rows)}",
                                    "citizen_id": random.choice(citizens),
                                    "issue_id": issue_id,
                                    "description": DESC.get(cat.name, DESC["default"]),
                                    "lng": lng + random.uniform(-0.0008, 0.0008),
                                    "lat": lat + random.uniform(-0.0008, 0.0008),
                                    "ward_id": w["id"],
                                    "category_id": cat.id,
                                    "created_at": day_dt,
                                }
                            )

        await _bulk_insert_issues(db, issue_rows)
        await _bulk_insert_complaints(db, complaint_rows)
        await db.commit()
        print(f"inserted issues={len(issue_rows)} complaints={len(complaint_rows)}")

        total = await rebuild_daily_stats(db)
        print(f"daily_stats rows: {total}  (hotspot ward id={hotspot_ward})")


_ISSUE_SQL = text(
    """
    INSERT INTO issues (id, public_code, title, category_id, department_id, ward_id,
        centroid, status, priority_score, complaint_count, first_reported_at,
        sla_due_at, sla_breached, resolved_at, created_at, updated_at)
    VALUES (:id, :public_code, :title, :category_id, :department_id, :ward_id,
        ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, CAST(:status AS issue_status),
        :priority, 1, :first, :sla_due, :breached, :resolved_at, :first, :first)
    """
)

_COMPLAINT_SQL = text(
    """
    INSERT INTO complaints (id, public_code, citizen_id, issue_id, description,
        location, ward_id, category_id, processing_status, created_at, updated_at)
    VALUES (:id, :public_code, :citizen_id, :issue_id, :description,
        ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :ward_id, :category_id,
        'triaged', :created_at, :created_at)
    """
)


async def _bulk_insert_issues(db, rows: list[dict]) -> None:
    for i in range(0, len(rows), 500):
        await db.execute(_ISSUE_SQL, rows[i : i + 500])
    # set complaint_count to the real number per issue afterwards (cheap, one update)


async def _bulk_insert_complaints(db, rows: list[dict]) -> None:
    for i in range(0, len(rows), 500):
        await db.execute(_COMPLAINT_SQL, rows[i : i + 500])
    await db.execute(
        text(
            "UPDATE issues i SET complaint_count = sub.n FROM "
            "(SELECT issue_id, count(*) n FROM complaints WHERE issue_id IS NOT NULL "
            "GROUP BY issue_id) sub WHERE sub.issue_id = i.id"
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
