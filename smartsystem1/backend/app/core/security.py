import contextlib
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

settings = get_settings()
_ph = PasswordHasher()


# ---------- passwords ----------
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# Precomputed once so login can run a verify of equal cost when the email doesn't
# exist — otherwise the missing argon2 call makes "no such user" measurably faster,
# leaking which emails are registered (timing-based enumeration).
_DUMMY_HASH = _ph.hash("timing-equalization-placeholder")


def dummy_verify() -> None:
    with contextlib.suppress(VerifyMismatchError):
        _ph.verify(_DUMMY_HASH, "x")


# ---------- access tokens (stateless JWT) ----------
def create_access_token(user_id: UUID, role: str) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_min),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError on invalid/expired tokens."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return payload


# ---------- refresh tokens (opaque, hashed at rest) ----------
def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256 is correct here: the token is already high-entropy, so a fast hash
    is fine and lets us look it up by hash. Argon2 is only for low-entropy passwords."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- OTP ----------
def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
