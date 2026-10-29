from typing import Annotated
from uuid import UUID, uuid4

from botocore.exceptions import ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select, text

from app.ai import dedup, embeddings
from app.api.deps import CurrentUser, require_roles
from app.core.config import get_settings
from app.core.db import SessionDep
from app.core.queue import enqueue_analyze_media, enqueue_process_complaint
from app.core.ratelimit import enforce_daily_complaint_limit, similar_check_rate_limit
from app.models.complaint import Complaint, ComplaintMedia
from app.models.enums import ProcessingStatus, UserRole
from app.models.user import User
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintOut,
    MediaConfirmIn,
    MediaOut,
    MediaPresignIn,
    MediaPresignOut,
    SimilarCheckIn,
    SimilarCheckOut,
    SimilarIssueOut,
)
from app.schemas.geo import GeoPoint
from app.services import codes, geo, storage
from app.services.pipeline import analyze_media as run_analyze_media
from app.services.pipeline import run_pipeline

settings = get_settings()

router = APIRouter(prefix="/complaints", tags=["complaints"])

CitizenUser = Annotated[User, Depends(require_roles(UserRole.citizen))]


async def _load_for_user(db: SessionDep, complaint_id: UUID, user: User) -> Complaint:
    complaint = await db.get(Complaint, complaint_id)
    # Citizens may only see their own; hide others' existence behind a 404.
    if complaint is None or (user.role == UserRole.citizen and complaint.citizen_id != user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Complaint not found"},
        )
    return complaint


async def _media_out(db: SessionDep, complaint_id: UUID) -> list[MediaOut]:
    rows = (
        await db.execute(select(ComplaintMedia).where(ComplaintMedia.complaint_id == complaint_id))
    ).scalars()
    return [
        MediaOut(
            id=m.id,
            object_key=m.object_key,
            mime=m.mime,
            url=storage.presign_get(m.object_key),
            cv_status=m.cv_status,
            cv_result=m.cv_result,
            moderation=m.moderation,
        )
        for m in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ComplaintOut)
async def create_complaint(
    body: ComplaintCreate,
    user: CitizenUser,
    db: SessionDep,
    background: BackgroundTasks,
) -> ComplaintOut:
    await enforce_daily_complaint_limit(str(user.id))
    lng, lat = body.location.lng, body.location.lat
    ward_id = await geo.find_ward(db, lng, lat)

    complaint = Complaint(
        public_code=await codes.next_complaint_code(db),
        citizen_id=user.id,
        description=body.description,
        location=geo.point(lng, lat),
        address_text=body.address_text,
        ward_id=ward_id,
        declined_intercept=body.declined_intercept,
        processing_status=ProcessingStatus.queued,
    )
    db.add(complaint)
    await db.commit()
    await db.refresh(complaint)

    # Kick off the AI pipeline off the request path: inline (BackgroundTasks) in dev,
    # or enqueued to the arq worker when pipeline_inline is false.
    if settings.pipeline_inline:
        background.add_task(run_pipeline, str(complaint.id))
    else:
        await enqueue_process_complaint(str(complaint.id))

    return ComplaintOut(
        id=complaint.id,
        public_code=complaint.public_code,
        description=complaint.description,
        address_text=complaint.address_text,
        ward_id=complaint.ward_id,
        processing_status=complaint.processing_status,
        issue_id=complaint.issue_id,
        location=GeoPoint(coordinates=(lng, lat)),
        created_at=complaint.created_at,
        media=[],
    )


@router.post("/similar-check", response_model=SimilarCheckOut)
async def similar_check(
    body: SimilarCheckIn,
    user: CitizenUser,
    db: SessionDep,
    _: None = Depends(similar_check_rate_limit),
) -> SimilarCheckOut:
    """Pre-submit duplicate intercept: embed the draft and look for nearby open
    issues. Category-agnostic (the citizen hasn't picked one) — broader than the
    pipeline's auto-attach. Synchronous because the citizen is waiting (~30 ms embed)."""
    emb = await embeddings.aembed_query(body.description)
    found = await dedup.find_similar_issues(
        db,
        emb,
        body.location.lng,
        body.location.lat,
        radius_m=settings.dedup_radius_m,
        min_sim=settings.similar_check_min_sim,
        limit=3,
    )
    return SimilarCheckOut(
        candidates=[
            SimilarIssueOut(
                issue_id=s.issue_id,
                public_code=s.public_code,
                title=s.title,
                status=s.status,
                complaint_count=s.complaint_count,
                upvote_count=s.upvote_count,
                similarity=s.similarity,
                distance_m=s.distance_m,
            )
            for s in found
        ]
    )


@router.get("/mine", response_model=list[ComplaintOut])
async def my_complaints(user: CitizenUser, db: SessionDep) -> list[ComplaintOut]:
    rows = (
        await db.execute(
            text(
                """
                SELECT c.id, c.public_code, c.description, c.address_text, c.ward_id,
                       c.processing_status, c.issue_id, c.created_at,
                       ST_X(c.location::geometry) AS lng, ST_Y(c.location::geometry) AS lat,
                       i.status AS issue_status, i.public_code AS issue_public_code
                FROM complaints c
                LEFT JOIN issues i ON i.id = c.issue_id
                WHERE c.citizen_id = :uid
                ORDER BY c.created_at DESC
                LIMIT 100
                """
            ),
            {"uid": user.id},
        )
    ).mappings()
    return [
        ComplaintOut(
            id=r["id"],
            public_code=r["public_code"],
            description=r["description"],
            address_text=r["address_text"],
            ward_id=r["ward_id"],
            processing_status=r["processing_status"],
            issue_id=r["issue_id"],
            issue_status=r["issue_status"],
            issue_public_code=r["issue_public_code"],
            location=GeoPoint(coordinates=(r["lng"], r["lat"])),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/{complaint_id}", response_model=ComplaintOut)
async def get_complaint(complaint_id: UUID, user: CurrentUser, db: SessionDep) -> ComplaintOut:
    complaint = await _load_for_user(db, complaint_id, user)
    coords = (
        await db.execute(
            text(
                "SELECT ST_X(location::geometry), ST_Y(location::geometry) "
                "FROM complaints WHERE id = :id"
            ),
            {"id": complaint_id},
        )
    ).first()
    issue_status = issue_code = None
    if complaint.issue_id is not None:
        row = (
            await db.execute(
                text("SELECT status, public_code FROM issues WHERE id = :id"),
                {"id": complaint.issue_id},
            )
        ).first()
        if row is not None:
            issue_status, issue_code = row[0], row[1]
    return ComplaintOut(
        id=complaint.id,
        public_code=complaint.public_code,
        description=complaint.description,
        address_text=complaint.address_text,
        ward_id=complaint.ward_id,
        processing_status=complaint.processing_status,
        issue_id=complaint.issue_id,
        issue_status=issue_status,
        issue_public_code=issue_code,
        location=GeoPoint(coordinates=(coords[0], coords[1])),
        created_at=complaint.created_at,
        media=await _media_out(db, complaint_id),
    )


@router.post("/{complaint_id}/media/presign", response_model=MediaPresignOut)
async def presign_media(
    complaint_id: UUID, body: MediaPresignIn, user: CitizenUser, db: SessionDep
) -> MediaPresignOut:
    await _load_for_user(db, complaint_id, user)
    if body.mime not in storage.ALLOWED_MIME:
        raise HTTPException(
            status_code=422,
            detail={"code": "bad_mime", "message": "Only JPEG, PNG, or WebP images"},
        )
    if body.bytes > storage.MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail={"code": "too_large", "message": "Image exceeds 8 MB"},
        )
    existing = (
        await db.execute(
            select(func.count())
            .select_from(ComplaintMedia)
            .where(ComplaintMedia.complaint_id == complaint_id)
        )
    ).scalar_one()
    if existing >= 3:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "media_limit", "message": "Max 3 photos per complaint"},
        )
    ext = storage.ALLOWED_MIME[body.mime]
    object_key = f"complaints/{complaint_id}/{uuid4().hex}.{ext}"
    return MediaPresignOut(
        upload_url=storage.presign_put(object_key, body.mime), object_key=object_key
    )


@router.post("/{complaint_id}/media/confirm", response_model=MediaOut)
async def confirm_media(
    complaint_id: UUID,
    body: MediaConfirmIn,
    user: CitizenUser,
    db: SessionDep,
    background: BackgroundTasks,
) -> MediaOut:
    await _load_for_user(db, complaint_id, user)
    if not body.object_key.startswith(f"complaints/{complaint_id}/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "bad_key", "message": "object_key does not belong to this complaint"},
        )
    try:
        meta = await storage.head(body.object_key)
    except ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "upload_missing", "message": "Upload not found in storage"},
        ) from e
    size = int(meta["ContentLength"])
    if size > storage.MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "too_large", "message": "Uploaded file exceeds 8 MB"},
        )

    media = ComplaintMedia(
        complaint_id=complaint_id,
        object_key=body.object_key,
        mime=body.mime,
        bytes=size,
        width=body.width,
        height=body.height,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)

    # Run computer vision off the request path (inline in dev, arq worker in prod).
    if settings.pipeline_inline:
        background.add_task(run_analyze_media, str(media.id))
    else:
        await enqueue_analyze_media(str(media.id))

    return MediaOut(
        id=media.id,
        object_key=media.object_key,
        mime=media.mime,
        url=storage.presign_get(media.object_key),
        cv_status=media.cv_status,
        cv_result=media.cv_result,
        moderation=media.moderation,
    )
