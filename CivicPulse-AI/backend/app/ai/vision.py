"""Computer vision on complaint photos. Zero-shot via Gemini Vision (no training
data needed) classifying the civic-defect type, a rough severity, and a moderation
verdict. Offline/mock returns a deterministic result derived from the complaint's
category so the demo works without a key.

CV here VERIFIES and ENRICHES — it never gates a complaint (ADR-09). "Water leakage"
isn't visually separable from a wet road, so the detectable class is *waterlogging*.
The honest, on-prem fine-tuned YOLO detector is the named post-sprint stretch.
"""

import base64

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger()
settings = get_settings()

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# the civic-defect classes the demo recognizes
CLASSES = ["pothole", "garbage", "waterlogging", "other"]

# map a complaint category -> the CV label we'd expect (used for the offline mock)
_CATEGORY_HINT = {
    "Pothole": "pothole",
    "Road cracking / damage": "pothole",
    "Garbage dump / missed pickup": "garbage",
    "Dead animal": "garbage",
    "Waterlogging / flooding": "waterlogging",
    "Water pipe leakage": "waterlogging",
}


def _use_gemini() -> bool:
    return not settings.mock_ai and bool(settings.gemini_api_key)


def _mock_result(hint_category: str | None) -> dict:
    label = _CATEGORY_HINT.get(hint_category or "", "other")
    conf = 0.84 if label != "other" else 0.3
    return {
        "labels": [{"label": label, "conf": conf}],
        "severity": round(0.6 if label != "other" else 0.2, 2),
        "moderation": "approved",
        "model": "mock",
    }


async def analyze_image(image_bytes: bytes | None, mime: str, hint_category: str | None) -> dict:
    """Return {labels:[{label,conf}], severity 0..1, moderation, model}.
    Falls back to the deterministic mock on no-key or any Gemini error."""
    if not _use_gemini() or image_bytes is None:
        return _mock_result(hint_category)
    try:
        b64 = base64.b64encode(image_bytes).decode()
        prompt = (
            "You are inspecting a citizen-submitted civic complaint photo. Classify the "
            f"main defect as one of {CLASSES}. Give a severity 0..1 and flag obvious spam "
            "or non-civic images.\n"
            'Respond as JSON: {"label": "<one of the classes>", "confidence": <0..1>, '
            '"severity": <0..1>, "is_spam": <bool>}'
        )
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                _GEMINI_URL.format(model=settings.gemini_model),
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt},
                                {"inline_data": {"mime_type": mime, "data": b64}},
                            ]
                        }
                    ],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
            )
            resp.raise_for_status()
            import json

            data = json.loads(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
        label = data.get("label", "other")
        return {
            "labels": [{"label": label, "conf": float(data.get("confidence", 0.5))}],
            "severity": float(data.get("severity", 0.3)),
            "moderation": "flagged" if data.get("is_spam") else "approved",
            "model": settings.gemini_model,
        }
    except Exception as e:  # noqa: BLE001 — CV never blocks; degrade to mock
        log.warning("vision.failed", error=str(e))
        return _mock_result(hint_category)
