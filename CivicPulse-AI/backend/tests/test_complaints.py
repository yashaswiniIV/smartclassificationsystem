import base64
from uuid import uuid4

import httpx
import pytest

from app.core.redis import redis_client
from app.main import app
from app.services.otp import _key

pytestmark = pytest.mark.integration

# MG Road, Bengaluru → falls inside a real BBMP ward (Shantala Nagar)
BLR = (77.5946, 12.9716)
# Mumbai → outside the seeded city, ward derivation should yield null
MUMBAI = (72.8777, 19.0760)

# 1x1 transparent PNG
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
async def _reset_rate_limits() -> None:
    keys = await redis_client.keys("rl:*")
    if keys:
        await redis_client.delete(*keys)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _auth_citizen(client: httpx.AsyncClient) -> str:
    """Register + verify + login a fresh citizen; return the access token."""
    email = f"cit+{uuid4().hex[:8]}@example.com"
    pw = "supersecret123"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pw, "full_name": "Cit Test"},
    )
    otp = await redis_client.get(_key(email))
    await client.post("/api/v1/auth/verify-email", json={"email": email, "otp": otp})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_complaint_derives_ward() -> None:
    async with _client() as client:
        token = await _auth_citizen(client)
        r = await client.post(
            "/api/v1/complaints",
            headers=_auth(token),
            json={
                "description": "Large pothole near the bus stop, two bikes fell",
                "location": {"type": "Point", "coordinates": list(BLR)},
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["ward_id"] is not None  # point-in-polygon found a ward
        assert body["processing_status"] == "queued"
        assert body["public_code"].startswith("CP-")
        assert body["location"]["coordinates"] == list(BLR)


async def test_complaint_outside_city_has_null_ward() -> None:
    async with _client() as client:
        token = await _auth_citizen(client)
        r = await client.post(
            "/api/v1/complaints",
            headers=_auth(token),
            json={
                "description": "This is outside the pilot city boundary",
                "location": {"type": "Point", "coordinates": list(MUMBAI)},
            },
        )
        assert r.status_code == 201
        assert r.json()["ward_id"] is None  # still accepted, just unassigned


async def test_mine_lists_only_own_complaints() -> None:
    async with _client() as client:
        token_a = await _auth_citizen(client)
        await client.post(
            "/api/v1/complaints",
            headers=_auth(token_a),
            json={
                "description": "Streetlight is out on my street",
                "location": {"type": "Point", "coordinates": list(BLR)},
            },
        )
        mine = await client.get("/api/v1/complaints/mine", headers=_auth(token_a))
        assert mine.status_code == 200
        assert len(mine.json()) == 1


async def test_citizen_cannot_read_others_complaint() -> None:
    async with _client() as client:
        token_a = await _auth_citizen(client)
        created = await client.post(
            "/api/v1/complaints",
            headers=_auth(token_a),
            json={
                "description": "Garbage pile not collected for a week",
                "location": {"type": "Point", "coordinates": list(BLR)},
            },
        )
        cid = created.json()["id"]

        token_b = await _auth_citizen(client)
        r = await client.get(f"/api/v1/complaints/{cid}", headers=_auth(token_b))
        assert r.status_code == 404  # existence hidden, not 403


async def test_presign_rejects_bad_mime_and_oversize() -> None:
    async with _client() as client:
        token = await _auth_citizen(client)
        created = await client.post(
            "/api/v1/complaints",
            headers=_auth(token),
            json={
                "description": "Test complaint for media validation",
                "location": {"type": "Point", "coordinates": list(BLR)},
            },
        )
        cid = created.json()["id"]

        bad_mime = await client.post(
            f"/api/v1/complaints/{cid}/media/presign",
            headers=_auth(token),
            json={"mime": "application/pdf", "bytes": 1000},
        )
        assert bad_mime.status_code == 422

        too_big = await client.post(
            f"/api/v1/complaints/{cid}/media/presign",
            headers=_auth(token),
            json={"mime": "image/png", "bytes": 20_000_000},
        )
        assert too_big.status_code == 422


async def test_full_media_upload_flow() -> None:
    """Presign → real PUT to MinIO → confirm → media visible on the complaint."""
    async with _client() as client:
        token = await _auth_citizen(client)
        created = await client.post(
            "/api/v1/complaints",
            headers=_auth(token),
            json={
                "description": "Pothole with a photo attached",
                "location": {"type": "Point", "coordinates": list(BLR)},
            },
        )
        cid = created.json()["id"]

        presign = await client.post(
            f"/api/v1/complaints/{cid}/media/presign",
            headers=_auth(token),
            json={"mime": "image/png", "bytes": len(PNG_BYTES)},
        )
        assert presign.status_code == 200
        upload_url = presign.json()["upload_url"]
        object_key = presign.json()["object_key"]

        # Real upload straight to MinIO via the presigned URL (bypasses our API).
        async with httpx.AsyncClient() as raw:
            put = await raw.put(
                upload_url, content=PNG_BYTES, headers={"Content-Type": "image/png"}
            )
            assert put.status_code in (200, 204)

        confirm = await client.post(
            f"/api/v1/complaints/{cid}/media/confirm",
            headers=_auth(token),
            json={"object_key": object_key, "mime": "image/png"},
        )
        assert confirm.status_code == 200
        assert confirm.json()["cv_status"] == "pending"

        detail = await client.get(f"/api/v1/complaints/{cid}", headers=_auth(token))
        assert len(detail.json()["media"]) == 1


async def test_ward_list_requires_auth() -> None:
    async with _client() as client:
        assert (await client.get("/api/v1/wards")).status_code == 401
        token = await _auth_citizen(client)
        r = await client.get("/api/v1/wards", headers=_auth(token))
        assert r.status_code == 200
        assert len(r.json()) == 243  # all BBMP wards seeded
