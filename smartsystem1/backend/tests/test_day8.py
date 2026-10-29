import base64
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from app.core.db import session_factory
from app.core.redis import redis_client
from app.main import app
from app.models.complaint import Complaint
from app.models.issue import Issue
from app.services.otp import _key
from app.services.pipeline import analyze_media, run_pipeline

pytestmark = pytest.mark.integration

BLR = (77.5946, 12.9716)
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


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


async def _file_and_process(client: httpx.AsyncClient, token: str, desc: str) -> str:
    cid = (
        await client.post(
            "/api/v1/complaints",
            headers=_auth(token),
            json={"description": desc, "location": {"type": "Point", "coordinates": list(BLR)}},
        )
    ).json()["id"]
    await run_pipeline(cid)
    return cid


async def test_cv_analyzes_photo_and_feeds_priority() -> None:
    async with _client() as client:
        token = await _citizen(client)
        cid = await _file_and_process(client, token, "Huge pothole cratering the main road")

        presign = await client.post(
            f"/api/v1/complaints/{cid}/media/presign",
            headers=_auth(token),
            json={"mime": "image/png", "bytes": len(PNG)},
        )
        key = presign.json()["object_key"]
        async with httpx.AsyncClient() as raw:
            await raw.put(
                presign.json()["upload_url"], content=PNG, headers={"Content-Type": "image/png"}
            )
        confirm = await client.post(
            f"/api/v1/complaints/{cid}/media/confirm",
            headers=_auth(token),
            json={"object_key": key, "mime": "image/png"},
        )
        media_id = confirm.json()["id"]

        # run CV explicitly (inline pipeline is off in tests)
        result = await analyze_media(media_id)
        assert result["action"] == "done"

        async with session_factory() as db:
            row = (
                (
                    await db.execute(
                        text(
                            "SELECT cv_status::text, cv_result FROM complaint_media WHERE id = :id"
                        ),
                        {"id": media_id},
                    )
                )
                .mappings()
                .one()
            )
            assert row["cv_status"] == "done"
            # category hint was Pothole → CV label should be "pothole"
            assert row["cv_result"]["labels"][0]["label"] == "pothole"

            complaint = await db.get(Complaint, cid)
            issue = await db.get(Issue, complaint.issue_id)
            assert issue.priority_factors["cv"] > 0  # CV severity fed into priority


async def test_citizen_can_confirm_and_reopen() -> None:
    async with _client() as client:
        token = await _citizen(client)
        cid = await _file_and_process(client, token, "Streetlight out for confirm test")
        async with session_factory() as db:
            complaint = await db.get(Complaint, cid)
            issue_id = complaint.issue_id
            # force the issue into 'resolved' so the citizen can confirm/reopen
            await db.execute(
                text("UPDATE issues SET status='resolved', resolved_at=now() WHERE id=:i"),
                {"i": issue_id},
            )
            await db.commit()

        reopen = await client.post(
            f"/api/v1/issues/{issue_id}/reopen",
            headers=_auth(token),
            json={"reason": "Still not fixed, pothole remains"},
        )
        assert reopen.status_code == 200
        assert reopen.json()["status"] == "reopened"

        # resolve again, then confirm closes it
        async with session_factory() as db:
            await db.execute(
                text("UPDATE issues SET status='resolved', resolved_at=now() WHERE id=:i"),
                {"i": issue_id},
            )
            await db.commit()
        confirm = await client.post(
            f"/api/v1/issues/{issue_id}/confirm-resolution", headers=_auth(token)
        )
        assert confirm.status_code == 200
        assert confirm.json()["status"] == "closed"


async def test_sla_scan_flags_overdue() -> None:
    async with _client() as client:
        token = await _citizen(client)
        cid = await _file_and_process(client, token, "Overdue issue for SLA scan")
        async with session_factory() as db:
            complaint = await db.get(Complaint, cid)
            await db.execute(
                text(
                    "UPDATE issues SET sla_due_at = now() - interval '2 days', "
                    "sla_breached=false, status='open' WHERE id=:i"
                ),
                {"i": complaint.issue_id},
            )
            await db.commit()

        admin = await _admin(client)
        scan = await client.post("/api/v1/admin/jobs/scan-sla", headers=_auth(admin))
        assert scan.status_code == 200
        assert scan.json()["breached"] >= 1

        async with session_factory() as db:
            complaint = await db.get(Complaint, cid)
            issue = await db.get(Issue, complaint.issue_id)
            assert issue.sla_breached is True


async def test_weekly_report_generation() -> None:
    async with _client() as client:
        admin = await _admin(client)
        gen = await client.post("/api/v1/reports/generate", headers=_auth(admin))
        assert gen.status_code == 201
        body = gen.json()
        assert body["content_md"] and len(body["content_md"]) > 0
        assert "new_issues" in body["stats"]

        listed = await client.get("/api/v1/reports", headers=_auth(admin))
        assert any(r["id"] == body["id"] for r in listed.json())

        detail = await client.get(f"/api/v1/reports/{body['id']}", headers=_auth(admin))
        assert detail.json()["content_md"] == body["content_md"]


async def test_day8_rbac() -> None:
    async with _client() as client:
        token = await _citizen(client)
        assert (
            await client.post("/api/v1/admin/jobs/scan-sla", headers=_auth(token))
        ).status_code == 403
        assert (
            await client.post("/api/v1/reports/generate", headers=_auth(token))
        ).status_code == 403
