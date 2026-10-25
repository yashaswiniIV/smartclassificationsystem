from uuid import uuid4

import httpx
import pytest

from app.core.redis import redis_client
from app.main import app
from app.services.otp import _key

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _reset_rate_limits() -> None:
    # All test requests share one client IP, so the auth limiter would bleed across
    # tests. Clear the counters before each test (this fixture is local to this
    # integration module, so unit tests never touch Redis).
    keys = await redis_client.keys("rl:*")
    if keys:
        await redis_client.delete(*keys)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _register_and_verify(client: httpx.AsyncClient, email: str, pw: str) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pw, "full_name": "Test User"},
    )
    assert r.status_code == 201
    otp = await redis_client.get(_key(email))
    assert otp is not None  # OTP was issued
    r = await client.post("/api/v1/auth/verify-email", json={"email": email, "otp": otp})
    assert r.status_code == 200


async def test_full_auth_lifecycle() -> None:
    email = f"citizen+{uuid4().hex[:8]}@example.com"
    pw = "supersecret123"

    async with _client() as client:
        await _register_and_verify(client, email, pw)

        # login -> access token + refresh cookie
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 200
        body = r.json()
        access = body["access_token"]
        assert body["user"]["role"] == "citizen"
        assert "refresh_token" in client.cookies

        # /me with the access token
        r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert r.status_code == 200
        assert r.json()["email"] == email

        # refresh rotates the cookie and yields a new access token
        old_cookie = client.cookies["refresh_token"]
        r = await client.post("/api/v1/auth/refresh")
        assert r.status_code == 200
        assert client.cookies["refresh_token"] != old_cookie

        # reusing the OLD (rotated) refresh token must fail AND kill the family
        async with _client() as attacker:
            attacker.cookies.set("refresh_token", old_cookie, path="/api/v1/auth")
            r = await attacker.post("/api/v1/auth/refresh")
            assert r.status_code == 401
            assert r.json()["detail"]["code"] == "session_revoked"

        # the legit current refresh token is now also revoked (family burned)
        r = await client.post("/api/v1/auth/refresh")
        assert r.status_code == 401


async def test_login_unverified_is_forbidden() -> None:
    email = f"unverified+{uuid4().hex[:8]}@example.com"
    pw = "supersecret123"
    async with _client() as client:
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": pw, "full_name": "NV"},
        )
        assert r.status_code == 201
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "email_unverified"


async def test_reregister_unverified_reissues_code() -> None:
    # An unverified email can sign up again (e.g. lost the code) — a fresh code is
    # issued and the latest password wins, since the account is unclaimed.
    email = f"resend+{uuid4().hex[:8]}@example.com"
    async with _client() as client:
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "firstpass123", "full_name": "First"},
        )
        r2 = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "secondpass123", "full_name": "Second"},
        )
        new_otp = await redis_client.get(_key(email))
        assert r2.json().get("dev_otp") == new_otp  # dev returns the fresh code

        verify = await client.post(
            "/api/v1/auth/verify-email", json={"email": email, "otp": new_otp}
        )
        assert verify.status_code == 200

        # the second (latest) password is the one that works
        ok = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "secondpass123"}
        )
        assert ok.status_code == 200


async def test_dev_otp_never_exposed_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    # The dev convenience (returning the code in the response) MUST be dev-only.
    # In prod the code is delivered only via real email; the API never leaks it.
    from app.api.v1 import auth as auth_module

    monkeypatch.setattr(auth_module.settings, "env", "prod")
    email = f"prod+{uuid4().hex[:8]}@example.com"
    async with _client() as client:
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "supersecret123", "full_name": "Prod"},
        )
        assert r.status_code == 201
        assert "dev_otp" not in r.json()  # never in the response body
    # ...but a code WAS issued (it would be emailed in prod), so verification works
    assert await redis_client.get(_key(email)) is not None


async def test_me_requires_auth() -> None:
    async with _client() as client:
        r = await client.get("/api/v1/auth/me")
        assert r.status_code == 401


async def test_auth_rate_limit_kicks_in() -> None:
    # 5 allowed per minute; the 6th attempt must be 429.
    async with _client() as client:
        statuses = []
        for _ in range(6):
            r = await client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "x"},
            )
            statuses.append(r.status_code)
        assert statuses[-1] == 429
        assert 429 not in statuses[:5]


async def test_wrong_password_is_generic_401() -> None:
    email = f"citizen+{uuid4().hex[:8]}@example.com"
    async with _client() as client:
        await _register_and_verify(client, email, "supersecret123")
        r = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrongpassword"}
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "invalid_credentials"


async def test_login_unknown_email_is_generic_401() -> None:
    # Exercises the timing-equalization path (dummy_verify) and proves a missing
    # account gives the same generic error as a wrong password.
    async with _client() as client:
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": f"ghost+{uuid4().hex[:8]}@example.com", "password": "whatever123"},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "invalid_credentials"


async def test_otp_verification_is_rate_limited() -> None:
    # 10 guesses/min allowed; the 11th must be 429 (brute-force protection).
    email = f"bf+{uuid4().hex[:8]}@example.com"
    async with _client() as client:
        statuses = []
        for _ in range(11):
            r = await client.post(
                "/api/v1/auth/verify-email", json={"email": email, "otp": "000000"}
            )
            statuses.append(r.status_code)
        assert statuses[-1] == 429
        assert all(s == 400 for s in statuses[:10])
