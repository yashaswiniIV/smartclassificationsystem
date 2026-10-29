from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.redis import redis_client

settings = get_settings()


async def rate_limit(request: Request, bucket: str, limit: int, window_s: int = 60) -> None:
    """Fixed-window limiter keyed by client IP. Raises 429 when exceeded."""
    ip = request.client.host if request.client else "unknown"
    key = f"rl:{bucket}:{ip}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_s)
    if count > limit:
        ttl = await redis_client.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many requests"},
            headers={"Retry-After": str(max(ttl, 1))},
        )


async def auth_rate_limit(request: Request) -> None:
    await rate_limit(request, "auth", settings.auth_rate_per_min)


async def otp_rate_limit(request: Request) -> None:
    # Caps OTP guesses so the 6-digit code can't be brute-forced inside its
    # 10-minute window (10/min → at most ~100 tries vs a 1,000,000 space).
    await rate_limit(request, "otp", 10)


async def similar_check_rate_limit(request: Request) -> None:
    # similar-check embeds text + runs a vector query on each keystroke-ish call.
    await rate_limit(request, "similar", 30)


async def enforce_daily_complaint_limit(user_id: str, limit: int = 10) -> None:
    """Per-citizen daily cap on complaint creation (keyed by user, not IP)."""
    key = f"rl:complaint:{user_id}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 86400)
    if count > limit:
        ttl = await redis_client.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "daily_limit_reached", "message": "Daily complaint limit reached"},
            headers={"Retry-After": str(max(ttl, 1))},
        )
