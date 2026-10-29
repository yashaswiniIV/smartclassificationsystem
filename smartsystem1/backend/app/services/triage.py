from datetime import timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import IssueStatusHistory
from app.models.complaint import Complaint
from app.models.enums import IssueStatus, ProcessingStatus
from app.models.issue import Issue
from app.models.org import Category
from app.services import codes, geo


class TriageError(Exception):
    """Complaint cannot be triaged into an issue."""


async def create_issue_from_complaint(
    db: AsyncSession,
    complaint: Complaint,
    category_id: int,
    actor_id: UUID | None,
    title: str | None = None,
) -> Issue:
    """Turn a single complaint into a new issue and attach it. actor_id is None when
    the AI pipeline creates the issue automatically; a UUID for manual triage."""
    if complaint.ward_id is None:
        raise TriageError("Complaint has no ward (outside city) — cannot create an issue")
    category = await db.get(Category, category_id)
    if category is None:
        raise TriageError("Unknown category")

    # Build the centroid as a WKT point from the complaint's coords. (Assigning the
    # loaded WKBElement directly would pull in geoalchemy2's shapely path, which we
    # don't ship — WKT insertion matches how complaints store their location.)
    coords = (
        await db.execute(
            text(
                "SELECT ST_X(location::geometry), ST_Y(location::geometry) "
                "FROM complaints WHERE id = :id"
            ),
            {"id": complaint.id},
        )
    ).first()

    issue = Issue(
        public_code=await codes.next_issue_code(db),
        title=title or f"{category.name} near {complaint.address_text or 'reported location'}",
        category_id=category.id,
        department_id=category.department_id,
        ward_id=complaint.ward_id,
        centroid=geo.point(coords[0], coords[1]),  # reporter's point as the issue centroid
        status=IssueStatus.open,
        first_reported_at=complaint.created_at,
        sla_due_at=complaint.created_at + timedelta(hours=category.sla_hours),
        complaint_count=1,
    )
    db.add(issue)
    await db.flush()  # get issue.id

    db.add(
        IssueStatusHistory(
            issue_id=issue.id,
            from_status=None,
            to_status=IssueStatus.open,
            actor_id=actor_id,
            note=f"Issue created from complaint {complaint.public_code}",
        )
    )

    complaint.issue_id = issue.id
    complaint.category_id = category.id
    complaint.processing_status = ProcessingStatus.triaged
    return issue
