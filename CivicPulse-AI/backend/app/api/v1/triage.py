from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.api.deps import StaffUser
from app.core.db import SessionDep
from app.models.complaint import Complaint
from app.schemas.geo import GeoPoint
from app.schemas.issue import CreateIssueIn, IssueDetail, TriageQueueItem
from app.services import triage

router = APIRouter(prefix="/triage", tags=["triage"])


@router.get("/queue", response_model=list[TriageQueueItem])
async def triage_queue(user: StaffUser, db: SessionDep) -> list[TriageQueueItem]:
    """Complaints awaiting a human: not yet attached to an issue. Day 5's pipeline
    auto-attaches most of these; what's left is genuine manual triage."""
    rows = (
        await db.execute(
            text(
                """
                SELECT id, public_code, description, address_text, ward_id,
                       processing_status, created_at,
                       ST_X(location::geometry) AS lng, ST_Y(location::geometry) AS lat
                FROM complaints
                WHERE issue_id IS NULL
                  AND processing_status IN ('queued', 'processing', 'needs_manual_triage')
                ORDER BY created_at ASC
                LIMIT 100
                """
            )
        )
    ).mappings()
    return [
        TriageQueueItem(
            id=r["id"],
            public_code=r["public_code"],
            description=r["description"],
            address_text=r["address_text"],
            ward_id=r["ward_id"],
            processing_status=r["processing_status"],
            location=GeoPoint(coordinates=(r["lng"], r["lat"])),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.post("/{complaint_id}/create-issue", response_model=IssueDetail)
async def create_issue(
    complaint_id: UUID, body: CreateIssueIn, user: StaffUser, db: SessionDep
) -> IssueDetail:
    complaint = await db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Complaint not found"},
        )
    if complaint.issue_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "already_triaged", "message": "Complaint already has an issue"},
        )
    try:
        issue = await triage.create_issue_from_complaint(
            db, complaint, body.category_id, user.id, body.title
        )
    except triage.TriageError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "triage_failed", "message": str(e)},
        ) from e

    await db.commit()

    # Note: the issue lands in the category's department, which may differ from the
    # triaging official's — that's intentional (routing), even if they can't see it after.
    coords = (
        await db.execute(
            text(
                "SELECT ST_X(centroid::geometry), ST_Y(centroid::geometry) "
                "FROM issues WHERE id = :id"
            ),
            {"id": issue.id},
        )
    ).first()
    return IssueDetail(
        id=issue.id,
        public_code=issue.public_code,
        title=issue.title,
        status=issue.status,
        priority_score=issue.priority_score,
        category_id=issue.category_id,
        department_id=issue.department_id,
        ward_id=issue.ward_id,
        complaint_count=issue.complaint_count,
        sla_due_at=issue.sla_due_at,
        sla_breached=issue.sla_breached,
        assigned_to=issue.assigned_to,
        assigned_to_name=None,
        created_at=issue.created_at,
        location=GeoPoint(coordinates=(coords[0], coords[1])),
        first_reported_at=issue.first_reported_at,
        resolved_at=issue.resolved_at,
        resolution_note=issue.resolution_note,
    )
