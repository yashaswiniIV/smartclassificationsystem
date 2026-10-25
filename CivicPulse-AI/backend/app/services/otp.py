from app.core.config import get_settings
from app.core.redis import redis_client
from app.core.security import new_otp

settings = get_settings()


def _key(email: str) -> str:
    return f"otp:{email.lower()}"


async def issue_otp(email: str) -> str:
    otp = new_otp()
    await redis_client.set(_key(email), otp, ex=settings.otp_ttl_min * 60)
    return otp


async def verify_otp(email: str, otp: str) -> bool:
    key = _key(email)
    stored = await redis_client.get(key)
    if stored is not None and stored == otp:
        await redis_client.delete(key)
        return True
    return False
