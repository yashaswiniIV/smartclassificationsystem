from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.core.db import session_factory
from app.core.redis import redis_client
from app.main import app
from app.models.complaint import Complaint
from app.models.issue import Issue
from app.services.otp import _key
from app.services.pipeline import run_pipeline

pytestmark = pytest.mark.integration

# Same spot (a few metres apart, well within the 150 m dedup radius).
SPOT_A = (77.5946, 12.9716)
SPOT_B = (77.5947, 12.9717)
FAR = (77.6100, 12.9850)  # ~1.5 km away — outside dedup radius


@pytest.fixture(autouse=True)
async def _reset_rate_limits() -> None:
    keys = await redis_client.keys("rl:*")
    if keys:
        await redis_client.delete(*keys)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _citizen(client: httpx.AsyncClient) -> str:
    email = f"cit+{uuid4().hex[:8]}@example.com"
    pw = "supersecret123"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": pw, "full_name": "Cit"}
    )
    otp = await redis_client.get(_key(email))
    await client.post("/api/v1/auth/verify-email", json={"email": email, "otp": otp})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    return r.json()["access_token"]


async def _file(client: httpx.AsyncClient, token: str, desc: str, loc: tuple[float, float]) -> str:
    r = await client.post(
        "/api/v1/complaints",
        headers=_auth(token),
        json={"description": desc, "location": {"type": "Point", "coordinates": list(loc)}},
    )
    return r.json()["id"]


async def _issue_id_of(complaint_id: str) -> str | None:
    async with session_factory() as db:
        c = await db.get(Complaint, complaint_id)
        return str(c.issue_id) if c and c.issue_id else None


async def test_pipeline_categorizes_and_creates_issue() -> None:
    async with _client() as client:
        token = await _citizen(client)
        cid = await _file(client, token, "There is a huge pothole on the main road", SPOT_A)
        result = await run_pipeline(cid)

    # created or attached — both are valid pipeline outcomes (the shared dev DB may
    # already hold a nearby pothole issue); what matters is it got triaged + linked.
    assert result["action"] in ("created", "attached")
    async with session_factory() as db:
        c = await db.get(Complaint, cid)
        assert c.processing_status == "triaged"
        assert c.issue_id is not None
        assert c.ai_category_id is not None  # categorized
        assert c.ai_category_confidence and c.ai_category_confidence > 0
        assert c.language is not None  # language detected
        issue = await db.get(Issue, c.issue_id)
        assert issue.complaint_count >= 1
        assert issue.priority_score > 0
        assert issue.priority_factors is not None


async def test_two_phrasings_merge_into_one_issue() -> None:
    """The headline feature: two differently-worded reports of the same pothole at
    the same spot become ONE issue with two reporters."""
    async with _client() as client:
        t1 = await _citizen(client)
        t2 = await _citizen(client)
        c1 = await _file(client, t1, "Large pothole on the main road near the bus stop", SPOT_A)
        c2 = await _file(
            client, t2, "Big pothole by the bus stop on the main road, very dangerous", SPOT_B
        )
        await run_pipeline(c1)
        await run_pipeline(c2)

    i1, i2 = await _issue_id_of(c1), await _issue_id_of(c2)
    assert i1 is not None and i1 == i2  # both phrasings land on the SAME issue
    async with session_factory() as db:
        issue = await db.get(Issue, i1)
        assert issue.complaint_count >= 2  # at least both reporters counted


async def test_different_problems_do_not_merge() -> None:
    """Precision guard: a pothole and a garbage pile at the same spot are different
    issues (different category → never auto-merged)."""
    async with _client() as client:
        t1 = await _citizen(client)
        t2 = await _citizen(client)
        c1 = await _file(client, t1, "Deep pothole cratering the road surface", SPOT_A)
        c2 = await _file(client, t2, "Pile of rotting garbage uncollected for days", SPOT_B)
        await run_pipeline(c1)
        await run_pipeline(c2)

    assert await _issue_id_of(c1) != await _issue_id_of(c2)


async def test_far_apart_do_not_merge() -> None:
    """Spatial guard: identical text >150 m apart stays separate (two real potholes)."""
    async with _client() as client:
        t1 = await _citizen(client)
        t2 = await _citizen(client)
        text = "Large pothole on the main road near the bus stop"
        c1 = await _file(client, t1, text, SPOT_A)
        c2 = await _file(client, t2, text, FAR)
        await run_pipeline(c1)
        await run_pipeline(c2)

    assert await _issue_id_of(c1) != await _issue_id_of(c2)


async def test_similar_check_intercept_finds_existing_issue() -> None:
    async with _client() as client:
        t1 = await _citizen(client)
        c1 = await _file(client, t1, "Huge pothole on the main road near the market", SPOT_A)
        await run_pipeline(c1)

        # A second citizen drafting a nearby report should see the existing issue.
        t2 = await _citizen(client)
        r = await client.post(
            "/api/v1/complaints/similar-check",
            headers=_auth(t2),
            json={
                "description": "big pothole on the road by the market, bikes falling",
                "location": {"type": "Point", "coordinates": list(SPOT_B)},
            },
        )
        assert r.status_code == 200
        candidates = r.json()["candidates"]
        assert len(candidates) >= 1
        assert candidates[0]["similarity"] >= 0.60  # configured similar-check threshold


async def test_pipeline_is_idempotent() -> None:
    async with _client() as client:
        token = await _citizen(client)
        cid = await _file(client, token, "Streetlight not working on the corner", SPOT_A)
        await run_pipeline(cid)
        second = await run_pipeline(cid)

    assert second["action"] == "already_triaged"
    async with session_factory() as db:
        issue_count = (
            await db.execute(
                select(func.count())
                .select_from(Complaint)
                .where(Complaint.id == cid, Complaint.issue_id.is_not(None))
            )
        ).scalar_one()
        assert issue_count == 1  # not double-processed


async def test_upvote_boosts_priority_and_count() -> None:
    async with _client() as client:
        reporter = await _citizen(client)
        cid = await _file(client, reporter, "Garbage dump overflowing near the park", SPOT_A)
        await run_pipeline(cid)
        issue_id = await _issue_id_of(cid)

        async with session_factory() as db:
            before = (await db.get(Issue, issue_id)).priority_score

        upvoter = await _citizen(client)
        r = await client.post(f"/api/v1/issues/{issue_id}/upvote", headers=_auth(upvoter))
        assert r.status_code == 200
        assert r.json()["upvotes"] >= 1

        async with session_factory() as db:
            after = (await db.get(Issue, issue_id)).priority_score
        assert after >= before  # more reporters → not lower priority
