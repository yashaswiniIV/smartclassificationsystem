"""Seed reference data: departments, categories, and Bengaluru BBMP wards.

Run from backend/:  uv run python -m scripts.seed
Idempotent — safe to run repeatedly.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text

from app.core.db import session_factory
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.org import Category, Department
from app.models.user import User
from app.services import wards as ward_service

# Bootstrap staff accounts for local/demo use (all pre-verified). Dev passwords only.
# NOTE: domain must pass email-validator — .local/.test are rejected as special-use.
DEMO_PASSWORD = "civicpulse123"
ADMIN_EMAIL = "admin@civicpulse.gov.in"
# one official (department head) per department: official.<dept>@civicpulse.gov.in


WARD_GEOJSON = Path(__file__).resolve().parent.parent / "data" / "bbmp_wards_raw.geojson"

DEPARTMENTS = ["Roads", "Sanitation", "Water", "Electrical", "Parks", "Enforcement", "Health"]

# (name, department, severity_weight, sla_hours) — from docs/03-database-schema.md
CATEGORIES = [
    ("Pothole", "Roads", 4, 72),
    ("Road cracking / damage", "Roads", 3, 168),
    ("Broken footpath", "Roads", 2, 240),
    ("Garbage dump / missed pickup", "Sanitation", 3, 48),
    ("Dead animal", "Sanitation", 4, 24),
    ("Public toilet unclean", "Sanitation", 2, 72),
    ("Water pipe leakage", "Water", 4, 24),
    ("Waterlogging / flooding", "Water", 5, 24),
    ("No water supply", "Water", 4, 48),
    ("Streetlight not working", "Electrical", 3, 96),
    ("Dangling wires", "Electrical", 5, 24),
    ("Fallen tree / branches", "Parks", 4, 48),
    ("Park maintenance", "Parks", 1, 336),
    ("Illegal construction debris", "Enforcement", 2, 168),
    ("Stray animal menace", "Health", 3, 96),
]

# Human-readable descriptions used both for officials and (Day 5) to build the
# category prototype embedding for zero-shot classification.
DESCRIPTIONS = {
    "Pothole": "A hole or depression in the road that can damage vehicles or injure riders.",
    "Road cracking / damage": "Cracks, broken patches, or surface damage on roads.",
    "Broken footpath": "Damaged, broken, or obstructed pedestrian footpath or sidewalk.",
    "Garbage dump / missed pickup": "Accumulated garbage, uncollected waste, or missed pickup.",
    "Dead animal": "A dead animal on the road or in a public area needing removal.",
    "Public toilet unclean": "A dirty, unhygienic, or non-functional public toilet.",
    "Water pipe leakage": "A leaking or burst water pipe wasting water on the road.",
    "Waterlogging / flooding": "Standing water, flooding, or waterlogged roads after rain.",
    "No water supply": "Absence or shortage of piped water supply in an area.",
    "Streetlight not working": "A streetlight that is off, broken, or flickering at night.",
    "Dangling wires": "Hanging, exposed, or dangerous electrical wires.",
    "Fallen tree / branches": "A fallen tree or large branches blocking a road or footpath.",
    "Park maintenance": "Overgrown, damaged, or poorly maintained public park or garden.",
    "Illegal construction debris": "Construction material or debris dumped in a public space.",
    "Stray animal menace": "Aggressive or dangerous stray animals in a residential area.",
}


async def seed_departments(session) -> dict[str, int]:
    ids: dict[str, int] = {}
    for name in DEPARTMENTS:
        existing = (
            await session.execute(select(Department).where(Department.name == name))
        ).scalar_one_or_none()
        if existing is None:
            dept = Department(name=name)
            session.add(dept)
            await session.flush()
            ids[name] = dept.id
        else:
            ids[name] = existing.id
    return ids


async def seed_categories(session, dept_ids: dict[str, int]) -> int:
    added = 0
    for name, dept, severity, sla in CATEGORIES:
        existing = (
            await session.execute(select(Category).where(Category.name == name))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            Category(
                name=name,
                department_id=dept_ids[dept],
                description=DESCRIPTIONS[name],
                severity_weight=severity,
                sla_hours=sla,
            )
        )
        added += 1
    return added


async def seed_staff(session, dept_ids: dict[str, int]) -> int:
    """One admin + one department-head official per department (pre-verified)."""
    added = 0

    async def ensure(email, name, role, dept_id=None, head=False) -> None:
        nonlocal added
        exists = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if exists is not None:
            return
        session.add(
            User(
                email=email,
                full_name=name,
                role=role,
                password_hash=hash_password(DEMO_PASSWORD),
                department_id=dept_id,
                is_department_head=head,
                email_verified_at=datetime.now(UTC),
            )
        )
        added += 1

    await ensure(ADMIN_EMAIL, "City Admin", UserRole.admin)
    for dept, dept_id in dept_ids.items():
        slug = dept.lower().split()[0]
        await ensure(
            f"official.{slug}@civicpulse.gov.in",
            f"{dept} Officer",
            UserRole.official,
            dept_id=dept_id,
            head=True,
        )
    return added


async def main() -> None:
    async with session_factory() as session:
        dept_ids = await seed_departments(session)
        added_cats = await seed_categories(session, dept_ids)
        added_staff = await seed_staff(session, dept_ids)
        await session.commit()
        print(
            f"departments: {len(dept_ids)}, new categories: {added_cats}, "
            f"new staff: {added_staff} (admin={ADMIN_EMAIL}, pw={DEMO_PASSWORD})"
        )

        # Build category prototype embeddings for zero-shot categorization.
        # (Also warms/downloads the embedding model so later runs are fast.)
        from app.ai.categorize import ensure_category_embeddings

        embedded = await ensure_category_embeddings(session)
        print(f"category embeddings computed: {embedded}")

        if WARD_GEOJSON.exists():
            fc = json.loads(WARD_GEOJSON.read_text(encoding="utf-8"))
            n = await ward_service.import_feature_collection(
                session, fc, code_prop="KGISWardCode", name_prop="KGISWardName"
            )
            total = (await session.execute(text("SELECT count(*) FROM wards"))).scalar_one()
            print(f"wards imported/updated: {n} (total in db: {total})")
        else:
            print(f"WARNING: {WARD_GEOJSON} not found — skipping ward import")


if __name__ == "__main__":
    asyncio.run(main())
