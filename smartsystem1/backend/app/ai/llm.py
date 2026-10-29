"""LLM adapter. Everything goes through here so the rest of the app never imports a
provider directly. Two providers: 'mock' (deterministic, offline, no key) and
'gemini' (Flash via REST). Any Gemini error falls back to mock behavior — a bad
key, quota, or demo-day wifi outage must never break the pipeline.

Rules: the LLM never receives PII it doesn't need, and (for reports, later) never
invents numbers — it only narrates figures we compute and pass in.
"""

import json
from typing import Any

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger()
settings = get_settings()

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _use_gemini() -> bool:
    return not settings.mock_ai and bool(settings.gemini_api_key)


async def _generate_json(prompt: str) -> dict[str, Any] | None:
    """Call Gemini for a JSON object. Returns None on any failure (caller falls back)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _GEMINI_URL.format(model=settings.gemini_model),
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
    except Exception as e:  # noqa: BLE001 — any failure must degrade gracefully
        log.warning("gemini.call_failed", error=str(e))
        return None


async def classify(description: str, categories: list[tuple[int, str]]) -> tuple[int, float] | None:
    """Second-opinion classifier used only when embedding confidence is low.
    Returns (category_id, confidence) or None to keep the embedding's guess."""
    if not _use_gemini():
        return None
    options = "\n".join(f"{cid}: {name}" for cid, name in categories)
    prompt = (
        "You categorize civic complaints. Pick the single best category id.\n"
        f"Categories (id: name):\n{options}\n\n"
        f'Complaint: "{description}"\n\n'
        'Respond as JSON: {"category_id": <int>, "confidence": <0..1>}'
    )
    result = await _generate_json(prompt)
    if result and "category_id" in result:
        try:
            return int(result["category_id"]), float(result.get("confidence", 0.7))
        except (TypeError, ValueError):
            return None
    return None


async def hypothesize_causes(stats: dict) -> str:
    """A short, clearly-labeled root-cause HYPOTHESIS from cluster stats. The LLM only
    narrates numbers we pass in — it never invents figures. Mock/fallback builds a
    deterministic sentence so this works offline."""
    ward = stats.get("ward_name", "this ward")
    top = stats.get("top_category", "issues")
    ratio = stats.get("ratio", 1.0)
    recent = stats.get("recent_per_week", 0)
    fallback = (
        f"{ward} shows about a {ratio:.1f}x rise in '{top}' reports "
        f"(~{recent:.0f}/week recently vs its prior baseline). Likely drivers to check: "
        f"localized infrastructure stress, recent weather, or a single recurring source. "
        f"This is an AI hypothesis — verify on the ground before acting."
    )
    if not _use_gemini():
        return fallback
    prompt = (
        "You are assisting a city official. Given these ward statistics, write a 2-3 "
        "sentence root-cause HYPOTHESIS (label it as a hypothesis, do not invent numbers "
        "beyond those given).\n"
        f"Stats: {json.dumps(stats)}"
    )
    result = await _generate_json(prompt + '\n\nRespond as JSON: {"hypothesis": "<text>"}')
    if result and result.get("hypothesis"):
        return str(result["hypothesis"])
    return fallback


async def narrate_report(stats: dict) -> str:
    """Narrate a weekly report in Markdown. Critically: the model is GIVEN the
    numbers and only describes them — every figure in the prose traces to `stats`."""
    fallback = (
        f"## Weekly civic report ({stats.get('period_start')} → {stats.get('period_end')})\n\n"
        f"- **New issues:** {stats.get('new_issues', 0)}\n"
        f"- **Resolved:** {stats.get('resolved_issues', 0)} "
        f"({stats.get('resolved_pct', 0)}% of new)\n"
        f"- **SLA breaches:** {stats.get('sla_breaches', 0)}\n"
        f"- **Busiest category:** {stats.get('top_category', 'n/a')}\n"
        f"- **Emerging hotspots:** {stats.get('emerging_hotspots', 0)}\n\n"
        "_Generated from the figures above; review before circulating._"
    )
    if not _use_gemini():
        return fallback
    prompt = (
        "Write a concise weekly civic-governance report in Markdown for city leadership. "
        "Use ONLY these figures, do not invent any numbers:\n"
        f"{json.dumps(stats)}"
    )
    result = await _generate_json(prompt + '\n\nRespond as JSON: {"markdown": "<md>"}')
    if result and result.get("markdown"):
        return str(result["markdown"])
    return fallback


async def title(description: str, category_name: str, address: str | None) -> str:
    """A short issue title. Mock/fallback uses a clean template; Gemini sharpens it."""
    fallback = f"{category_name} near {address or 'reported location'}"
    if not _use_gemini():
        return fallback
    prompt = (
        "Write a concise (max 10 words) issue title for a city department queue.\n"
        f"Category: {category_name}\n"
        f'Complaint: "{description}"\n\n'
        'Respond as JSON: {"title": "<title>"}'
    )
    result = await _generate_json(prompt)
    if result and result.get("title"):
        return str(result["title"])[:200]
    return fallback
