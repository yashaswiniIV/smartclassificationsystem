"""The async AI pipeline (docs/02-user-flows.md F8), as a plain service so it's
testable without a running worker. The arq task and the inline BackgroundTask both
just call run_pipeline(complaint_id).

Flow: language → embed → categorize → dedup → (auto-attach | create issue) →
priority → telemetry. Idempotent: a complaint already triaged is a no-op. Any
failure parks the complaint in needs_manual_triage — AI failure never loses it.
"""

import time
from datetime import UTC, datetime
from uuid import UUID

import structlog
from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException
from sqlalchemy import text

from app.ai import categorize as categorize_mod
from app.ai import dedup, embeddings, llm, vision
from app.core.config import get_settings
from app.core.db import session_factory
from app.models.ai import AiJob
from app.models.complaint import Complaint, ComplaintMedia
from app.models.enums import AiJobStatus, CvStatus, ProcessingStatus
from app.models.issue import Issue
from app.models.org import Category
from app.services import priority, storage, triage

DetectorFactory.seed = 0  # deterministic language detection
log = structlog.get_logger()
settings = get_settings()


def _detect_language(text_value: str) -> str | None:
    try:
        return detect(text_value)[:2]
    except LangDetectException:
        return None


async def _coords(db, complaint_id: UUID) -> tuple[float, float]:
    row = (
        await db.execute(
            text(
                "SELECT ST_X(location::geometry), ST_Y(location::geometry) "
                "FROM complaints WHERE id = :id"
            ),
            {"id": complaint_id},
        )
    ).first()
    return float(row[0]), float(row[1])


async def _attach(db, complaint: Complaint, issue_id: UUID) -> None:
    complaint.issue_id = issue_id
    complaint.processing_status = ProcessingStatus.triaged
    issue = await db.get(Issue, issue_id)
    if issue is not None:
        issue.complaint_count += 1
        await priority.recompute(db, issue)


async def analyze_media(media_id: str | UUID) -> dict:
    """CV step: classify a complaint photo, store the result, and let its severity
    feed the issue's priority. Idempotent; failure marks the media cv_status=failed
    but never touches the complaint (CV verifies, never gates)."""
    mid = UUID(str(media_id))
    async with session_factory() as db:
        media = await db.get(ComplaintMedia, mid)
        if media is None or media.cv_status == CvStatus.done:
            return {"action": "skip"}
        complaint = await db.get(Complaint, media.complaint_id)
        hint = None
        if complaint is not None and complaint.category_id is not None:
            cat = await db.get(Category, complaint.category_id)
            hint = cat.name if cat else None
        try:
            image_bytes = None
            if not settings.mock_ai:
                image_bytes = await storage.get_bytes(media.object_key)
            result = await vision.analyze_image(image_bytes, media.mime, hint)
            media.cv_result = result
            media.cv_status = CvStatus.done
            media.moderation = result.get("moderation", "approved")
            if complaint is not None and complaint.issue_id is not None:
                issue = await db.get(Issue, complaint.issue_id)
                if issue is not None:
                    await priority.recompute(db, issue)
            await db.commit()
            return {"action": "done", "labels": result["labels"]}
        except Exception:
            log.exception("analyze_media.failed", media_id=str(mid))
            await db.rollback()
            failed = await db.get(ComplaintMedia, mid)
            if failed is not None:
                failed.cv_status = CvStatus.failed
            await db.commit()
            raise


async def run_pipeline(complaint_id: str | UUID) -> dict:
    """Process one complaint. Returns a small summary (handy for tests/telemetry)."""
    cid = UUID(str(complaint_id))
    async with session_factory() as db:
        complaint = await db.get(Complaint, cid)
        if complaint is None:
            return {"action": "missing"}
        if complaint.processing_status == ProcessingStatus.triaged:
            return {"action": "already_triaged"}  # idempotent

        started = time.monotonic()
        complaint.processing_status = ProcessingStatus.processing
        await db.flush()

        try:
            complaint.language = _detect_language(complaint.description)
            emb = await embeddings.aembed_query(complaint.description)
            complaint.embedding = emb
            lng, lat = await _coords(db, cid)

            cat_id, conf = await categorize_mod.categorize(db, emb, complaint.description)
            complaint.ai_category_id = cat_id
            complaint.ai_category_confidence = conf
            complaint.category_id = cat_id
            await db.flush()

            action: str
            attached_to: str | None = None
            best_sim: float | None = None

            if complaint.ward_id is None:
                # Outside the city → can't auto-create an issue (needs a ward).
                complaint.processing_status = ProcessingStatus.needs_manual_triage
                action = "needs_manual_triage"
            else:
                candidates = await dedup.find_similar_issues(
                    db,
                    emb,
                    lng,
                    lat,
                    radius_m=settings.dedup_radius_m,
                    min_sim=settings.auto_attach_min_sim,
                    category_id=cat_id,
                    exclude_complaint_id=str(cid),
                    limit=1,
                )
                if candidates:
                    best = candidates[0]
                    best_sim = best.similarity
                    await _attach(db, complaint, UUID(best.issue_id))
                    action = "attached"
                    attached_to = best.public_code
                else:
                    new_title = None
                    if not settings.mock_ai and cat_id is not None:
                        cat = await db.get(Category, cat_id)
                        if cat is not None:
                            new_title = await llm.title(
                                complaint.description, cat.name, complaint.address_text
                            )
                    issue = await triage.create_issue_from_complaint(
                        db, complaint, cat_id, actor_id=None, title=new_title
                    )
                    await priority.recompute(db, issue)
                    action = "created"
                    attached_to = issue.public_code

            db.add(
                AiJob(
                    job_type="process_complaint",
                    complaint_id=cid,
                    status=AiJobStatus.succeeded,
                    model=settings.embedding_model,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    confidence=conf,
                    payload={
                        "action": action,
                        "category_id": cat_id,
                        "attached_to": attached_to,
                        "similarity": best_sim,
                        "language": complaint.language,
                    },
                    finished_at=datetime.now(UTC),
                )
            )
            await db.commit()
            return {"action": action, "category_id": cat_id, "attached_to": attached_to}

        except Exception as e:
            log.exception("pipeline.failed", complaint_id=str(cid))
            await db.rollback()
            parked = await db.get(Complaint, cid)
            if parked is not None:
                parked.processing_status = ProcessingStatus.needs_manual_triage
            db.add(
                AiJob(
                    job_type="process_complaint",
                    complaint_id=cid,
                    status=AiJobStatus.failed,
                    error=str(e)[:500],
                    finished_at=datetime.now(UTC),
                )
            )
            await db.commit()
            raise
