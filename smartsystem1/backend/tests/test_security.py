from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.api.deps import require_roles
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_otp,
    verify_password,
)
from app.models.enums import UserRole


def test_password_hash_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"  # not stored in plaintext
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_access_token_roundtrip() -> None:
    uid = uuid4()
    token = create_access_token(uid, "citizen")
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["role"] == "citizen"


def test_decode_rejects_refresh_shaped_token() -> None:
    # a token without type=access must be rejected. Sign with the configured secret
    # so the signature is valid and we're truly testing the type-claim check.
    from app.core.config import get_settings

    bad = jwt.encode({"sub": "x"}, get_settings().jwt_secret, algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(bad)


def test_refresh_hash_is_deterministic_and_opaque() -> None:
    raw = "some-high-entropy-token"
    assert hash_refresh_token(raw) == hash_refresh_token(raw)
    assert hash_refresh_token(raw) != raw


def test_otp_is_six_digits() -> None:
    for _ in range(20):
        otp = new_otp()
        assert len(otp) == 6 and otp.isdigit()


class _FakeUser:
    def __init__(self, role: UserRole) -> None:
        self.role = role


async def test_require_roles_allows_and_forbids() -> None:
    guard = require_roles(UserRole.admin)
    admin = _FakeUser(UserRole.admin)
    citizen = _FakeUser(UserRole.citizen)

    assert await guard(admin) is admin  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as exc:
        await guard(citizen)  # type: ignore[arg-type]
    assert exc.value.status_code == 403
