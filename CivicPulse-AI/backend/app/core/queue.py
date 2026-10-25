from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings

settings = get_settings()


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


_pool: ArqRedis | None = None


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def enqueue_process_complaint(complaint_id: str) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("process_complaint", str(complaint_id))


async def enqueue_analyze_media(media_id: str) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("analyze_media", str(media_id))
