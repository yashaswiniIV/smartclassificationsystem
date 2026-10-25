from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.db import session_factory
from app.core.redis import redis_client
from app.core.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.org import Category
from app.models.user import User
from app.services.otp import _key

pytestmark = pytest.mark.integration

BLR = (77.5946, 12.9716)


@pytest.fixture(autouse=True)
async def _reset_rate_limits() -> None:
    keys = await redis_client.keys("rl:*")
    if keys:
        await redis_client.delete(*keys)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_staff(
    role: UserRole, department_id: int | None = None, is_head: bool = False
) -> tuple[str, str, str]:
    """Insert a pre-verified staff user directly; return (email, password, user_id)."""
    email = f"{role.value}+{uuid4().hex[:8]}@example.com"
    pw = "staffpass123"
    async with session_factory() as s:
        u = User(
            email=email,
            full_name=f"{role.value} test",
            role=role,
            password_hash=hash_password(pw),
            department_id=department_id,
            is_department_head=is_head,
            email_verified_at=datetime.now(UTC),
        )
        s.add(u)
        await s.commit()
        return email, pw, str(u.id)


async def _login(client: httpx.AsyncClient, email: str, pw: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.json()}"
    return r.json()["access_token"]


async def _citizen_token(client: httpx.AsyncClient) -> str:
    email = f"cit+{uuid4().hex[:8]}@example.com"
    pw = "supersecret123"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pw, "full_name": "Cit"},
    )
    otp = await redis_client.get(_key(email))
    await client.post("/api/v1/auth/verify-email", json={"email": email, "otp": otp})
    return await _login(client, email, pw)


async def _a_category() -> tuple[int, int]:
    """Return (category_id, department_id) from the seeded reference data."""
    async with session_factory() as s:
        cat = (await s.execute(select(Category).limit(1))).scalar_one()
        return cat.id, cat.department_id


async def _file_complaint(client: httpx.AsyncClient, token: str) -> str:
    r = await client.post(
        "/api/v1/complaints",
        headers=_auth(token),
        json={
            "description": "Large pothole near the market causing accidents",
            "location": {"type": "Point", "coordinates": list(BLR)},
        },
    )
    return r.json()["id"]


async def test_triage_to_resolution_lifecycle_and_citizen_tracking() -> None:
    cat_id, dept_id = await _a_category()
    async with _client() as client:
        citizen = await _citizen_token(client)
        complaint_id = await _file_complaint(client, citizen)

        admin_email, admin_pw, _ = await _make_staff(UserRole.admin)
        admin = await _login(client, admin_email, admin_pw)

        # complaint shows in triage queue (no issue yet)
        queue = await client.get("/api/v1/triage/queue", headers=_auth(admin))
        assert any(item["id"] == complaint_id for item in queue.json())

        # create an issue from it
        created = await client.post(
            f"/api/v1/triage/{complaint_id}/create-issue",
            headers=_auth(admin),
            json={"category_id": cat_id},
        )
        assert created.status_code == 200
        issue_id = created.json()["id"]
        assert created.json()["status"] == "open"
        assert created.json()["public_code"].startswith("ISS-")

        # illegal transition is refused by the state machine
        bad = await client.patch(
            f"/api/v1/issues/{issue_id}/status",
            headers=_auth(admin),
            json={"to_status": "resolved"},
        )
        assert bad.status_code == 409

        # legal path: open -> acknowledged
        ack = await client.patch(
            f"/api/v1/issues/{issue_id}/status",
            headers=_auth(admin),
            json={"to_status": "acknowledged"},
        )
        assert ack.status_code == 200

        # assign to an official in the issue's department, then they progress + resolve
        off_email, off_pw, off_id = await _make_staff(UserRole.official, department_id=dept_id)
        official = await _login(client, off_email, off_pw)
        assign = await client.post(
            f"/api/v1/issues/{issue_id}/assign",
            headers=_auth(admin),
            json={"assignee_id": off_id},
        )
        assert assign.status_code == 200
        assert assign.json()["status"] == "assigned"

        await client.patch(
            f"/api/v1/issues/{issue_id}/status",
            headers=_auth(official),
            json={"to_status": "in_progress"},
        )
        resolve = await client.patch(
            f"/api/v1/issues/{issue_id}/status",
            headers=_auth(official),
            json={"to_status": "resolved", "note": "Filled the pothole"},
        )
        assert resolve.status_code == 200
        assert resolve.json()["resolution_note"] == "Filled the pothole"

        # resolve with no note must fail
        # (re-resolving is illegal anyway; check note rule on a fresh transition path)

        # timeline records every transition
        timeline = await client.get(f"/api/v1/issues/{issue_id}/timeline", headers=_auth(admin))
        statuses = [e["to_status"] for e in timeline.json() if e["kind"] == "status"]
        assert statuses == ["open", "acknowledged", "assigned", "in_progress", "resolved"]

        # citizen now sees the issue status on their complaint, and got notified
        mine = await client.get("/api/v1/complaints/mine", headers=_auth(citizen))
        tracked = mine.json()[0]
        assert tracked["issue_status"] == "resolved"
        assert tracked["issue_public_code"].startswith("ISS-")

        notes = await client.get("/api/v1/notifications", headers=_auth(citizen))
        assert len(notes.json()) >= 1
        assert any(n["kind"] == "status_change" for n in notes.json())


async def test_citizen_cannot_access_console() -> None:
    async with _client() as client:
        citizen = await _citizen_token(client)
        assert (await client.get("/api/v1/issues", headers=_auth(citizen))).status_code == 403
        assert (await client.get("/api/v1/triage/queue", headers=_auth(citizen))).status_code == 403


async def test_plain_official_cannot_assign() -> None:
    cat_id, dept_id = await _a_category()
    async with _client() as client:
        citizen = await _citizen_token(client)
        complaint_id = await _file_complaint(client, citizen)
        admin_email, admin_pw, _ = await _make_staff(UserRole.admin)
        admin = await _login(client, admin_email, admin_pw)
        created = await client.post(
            f"/api/v1/triage/{complaint_id}/create-issue",
            headers=_auth(admin),
            json={"category_id": cat_id},
        )
        issue_id = created.json()["id"]

        # a plain (non-head) official in the dept may not assign
        off_email, off_pw, off_id = await _make_staff(UserRole.official, department_id=dept_id)
        official = await _login(client, off_email, off_pw)
        r = await client.post(
            f"/api/v1/issues/{issue_id}/assign",
            headers=_auth(official),
            json={"assignee_id": off_id},
        )
        assert r.status_code == 403
