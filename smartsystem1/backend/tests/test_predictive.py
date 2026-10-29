from uuid import uuid4

import httpx
import pytest

from app.core.redis import redis_client
from app.main import app
from app.services.otp import _key

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _reset_rate_limits() -> None:
    keys = await redis_client.keys("rl:*")
    if keys:
        await redis_client.delete(*keys)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


async def _admin(client: httpx.AsyncClient) -> str:
    return (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@civicpulse.gov.in", "password": "civicpulse123"},
        )
    ).json()["access_token"]


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


async def test_hotspots_structure() -> None:
    async with _client() as client:
        admin = await _admin(client)
        r = await client.get("/api/v1/analytics/hotspots", headers=_auth(admin))
        assert r.status_code == 200
        for h in r.json():
            assert h["ratio"] >= 2.0  # only emerging cells are returned
            assert h["recent_per_week"] >= h["baseline_per_week"]
            assert {"ward_id", "category_name", "lng", "lat"} <= set(h.keys())


async def test_forecast_has_ci_or_insufficient() -> None:
    async with _client() as client:
        admin = await _admin(client)
        cats = (await client.get("/api/v1/categories", headers=_auth(admin))).json()
        cat_id = cats[0]["id"]
        r = await client.get(
            f"/api/v1/analytics/forecast?category_id={cat_id}", headers=_auth(admin)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "insufficient_history")
        if body["status"] == "ok":
            assert len(body["forecast"]) == 4
            for p in body["forecast"]:
                assert p["lower"] <= p["mean"] <= p["upper"]  # CI brackets the mean


async def test_ward_risk_scores_in_range() -> None:
    async with _client() as client:
        admin = await _admin(client)
        r = await client.get("/api/v1/analytics/wards/risk", headers=_auth(admin))
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) <= 12
        for w in rows:
            assert 0 <= w["risk_score"] <= 100
            assert {"open_density", "sla_breach_rate", "rising_trend"} <= set(w["factors"])
        # sorted by risk descending
        scores = [w["risk_score"] for w in rows]
        assert scores == sorted(scores, reverse=True)


async def test_root_cause_returns_hypothesis() -> None:
    async with _client() as client:
        admin = await _admin(client)
        r = await client.get("/api/v1/analytics/wards/1/root-cause", headers=_auth(admin))
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["hypothesis"], str) and len(body["hypothesis"]) > 0


async def test_predictive_rbac() -> None:
    async with _client() as client:
        citizen = await _citizen(client)
        assert (
            await client.get("/api/v1/analytics/hotspots", headers=_auth(citizen))
        ).status_code == 403
        assert (
            await client.get("/api/v1/analytics/wards/risk", headers=_auth(citizen))
        ).status_code == 403
