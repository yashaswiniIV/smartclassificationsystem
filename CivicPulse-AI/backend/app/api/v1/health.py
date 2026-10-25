from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.db import SessionDep
from app.core.redis import redis_client

router = APIRouter()


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health")
async def health(response: Response, session: SessionDep) -> dict[str, Any]:
    db_ok = False
    redis_ok = False
    extensions: list[str] = []

    try:
        result = await session.execute(
            text("SELECT extname FROM pg_extension WHERE extname IN ('postgis','vector','citext')")
        )
        extensions = sorted(row[0] for row in result)
        db_ok = True
    except Exception:
        db_ok = False

    try:
        redis_ok = bool(await redis_client.ping())
    except Exception:
        redis_ok = False

    healthy = db_ok and redis_ok and len(extensions) == 3
    if not healthy:
        response.status_code = 503

    return {
        "status": "ok" if healthy else "degraded",
        "db": db_ok,
        "redis": redis_ok,
        "extensions": extensions,
    }
