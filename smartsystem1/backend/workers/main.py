"""arq worker: the async transport for the AI pipeline.

Run it (prod / async dev):  uv run arq workers.main.WorkerSettings
In default dev the pipeline runs inline (settings.pipeline_inline=True), so the
worker is optional — but this is the real path the architecture is built around,
and it's where retries + crash-recovery live.
"""

from typing import Any

from app.core.queue import redis_settings
from app.services.pipeline import analyze_media as _analyze_media
from app.services.pipeline import run_pipeline


async def process_complaint(ctx: dict[str, Any], complaint_id: str) -> dict:
    return await run_pipeline(complaint_id)


async def analyze_media(ctx: dict[str, Any], media_id: str) -> dict:
    return await _analyze_media(media_id)


class WorkerSettings:
    functions = [process_complaint, analyze_media]
    redis_settings = redis_settings()
    max_tries = 3  # then the pipeline parks the complaint in needs_manual_triage
