from uuid import uuid4

import httpx
import pytest

from app.core.db import session_factory
from app.core.redis import redis_client
from app.main import app
from app.services.analytics import rebuild_daily_stats
from app.services.otp import _key
from app.services.pipeline import run_pipeline

pytestmark = pytest.mark.integration

BLR = (77.5946, 12.9716)


@pytest.fixture(autouse=True)
async def _reset_rate_limits() -> None:
    keys = await redis_client.keys("rl:*")
    if keys:
        await redis_client.delete(*keys)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


async def _citizen(client: httpx.AsyncClient) -> str:
    email = f"cit+{uuid4().hex[:8]}@example.com"
    pw = "supersecret123"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": pw, "full_name": "C"}
    )
    otp = await redis_client.get(_key(email))
    await client.post("/api/v1/auth/verify-email", json={"email": email, "otp": otp})
    return (await client.post("/api/v1/auth/login", json={"email": email, "password": pw})).json()[
        "access_token"
    ]


async def _admin(client: httpx.AsyncClient) -> str:
    return (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@civicpulse.gov.in", "password": "civicpulse123"},
        )
    ).json()["access_token"]


async def test_rebuild_and_dashboards() -> None:
    async with _client() as client:
        # guarantee at least one fresh issue exists, then rebuild aggregates
        token = await _citizen(client)
        created = await client.post(
            "/api/v1/complaints",
            headers=_auth(token),
            json={
                "description": "Big pothole for analytics test",
                "location": {"type": "Point", "coordinates": list(BLR)},
            },
        )
        await run_pipeline(created.json()["id"])

        async with session_factory() as db:
            rows = await rebuild_daily_stats(db)
        assert rows > 0

        admin = await _admin(client)
        heat = await client.get("/api/v1/analytics/heatmap", headers=_auth(admin))
        assert heat.status_code == 200 and len(heat.json()) >= 1
        assert {"lng", "lat", "weight"} == set(heat.json()[0].keys())

        trends = await client.get("/api/v1/analytics/trends?weeks=12", headers=_auth(admin))
        assert trends.status_code == 200

        depts = await client.get("/api/v1/analytics/departments", headers=_auth(admin))
        assert depts.status_code == 200 and len(depts.json()) == 7
        assert "sla_breach_pct" in depts.json()[0]


async def test_public_endpoints_need_no_auth_and_hide_pii() -> None:
    async with _client() as client:
        stats = await client.get("/api/v1/public/stats")  # no Authorization header
        assert stats.status_code == 200
        body = stats.json()
        assert body["total_issues"] >= 0
        assert 0 <= body["resolved_pct"] <= 100

        issues = await client.get("/api/v1/public/issues?limit=20")
        assert issues.status_code == 200
        if issues.json():
            item = issues.json()[0]
            # no reporter / citizen fields leak; coords are rounded to ~3 dp
            assert "citizen_id" not in item and "reporter" not in item
            assert round(item["lng"], 3) == item["lng"]


async def test_analytics_requires_staff() -> None:
    async with _client() as client:
        token = await _citizen(client)
        r = await client.get("/api/v1/analytics/heatmap", headers=_auth(token))
        assert r.status_code == 403
        # departments is admin-only — a citizen is forbidden
        r2 = await client.get("/api/v1/analytics/departments", headers=_auth(token))
        assert r2.status_code == 403
