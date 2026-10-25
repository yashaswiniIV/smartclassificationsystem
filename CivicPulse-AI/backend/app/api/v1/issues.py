from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import aliased

from app.api.deps import StaffUser, require_roles
from app.core.db import SessionDep
from app.models.ai import IssueUpvote
from app.models.audit import IssueStatusHistory, IssueUpdate
from app.models.enums import IssueStatus, UserRole
from app.models.issue import Issue
from app.models.user import User
from app.schemas.complaint import MediaOut
from app.schemas.geo import GeoPoint
from app.schemas.issue import (
    AssignIn,
    IssueDetail,
    IssueListItem,
    IssuePage,
    IssueUpdateIn,
    ReopenIn,
    StatusTransitionIn,
    TimelineEntry,
)
from app.schemas.user import StaffOut
from app.services import lifecycle, priority, storage

router = APIRouter(prefix="/issues", tags=["issues"])

CitizenUser = Annotated[User, Depends(require_roles(UserRole.citizen))]
Assignee = aliased(User)
_CLOSED = (IssueStatus.closed, IssueStatus.rejected)


def _scope_to_user(stmt, user: User):
    """Officials and department heads see only their department; admins see all.
    (Ward-level narrowing for plain officials is a later refinement.)"""
    if user.role == UserRole.admin:
        return stmt
    return stmt.where(Issue.department_id == user.department_id)


async def _load_scoped(db: SessionDep, issue_id: UUID, user: User) -> Issue:
    issue = await db.get(Issue, issue_id)
    if issue is None or (user.role != UserRole.admin and issue.department_id != user.department_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Issue not found"},
        )
    return issue


def _to_list_item(issue: Issue, assignee_name: str | None) -> IssueListItem:
    return IssueListItem(
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
        assigned_to_name=assignee_name,
        created_at=issue.created_at,
    )


@router.get("", response_model=IssuePage)
async def list_issues(
    user: StaffUser,
    db: SessionDep,
    status_filter: Annotated[IssueStatus | None, Query(alias="status")] = None,
    ward_id: int | None = None,
    category_id: int | None = None,
    sla_breached: bool | None = None,
    assigned_to_me: bool = False,
    q: str | None = None,
    sort: str = "priority",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> IssuePage:
    stmt = select(Issue, Assignee.full_name).outerjoin(Assignee, Issue.assigned_to == Assignee.id)
    stmt = _scope_to_user(stmt, user)
    if status_filter is not None:
        stmt = stmt.where(Issue.status == status_filter)
    if ward_id is not None:
        stmt = stmt.where(Issue.ward_id == ward_id)
    if category_id is not None:
        stmt = stmt.where(Issue.category_id == category_id)
    if sla_breached is not None:
        stmt = stmt.where(Issue.sla_breached == sla_breached)
    if assigned_to_me:
        stmt = stmt.where(Issue.assigned_to == user.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Issue.title.ilike(like), Issue.public_code.ilike(like)))

    count_stmt = _scope_to_user(select(func.count()).select_from(Issue), user)
    total = (await db.execute(count_stmt)).scalar_one()

    order = Issue.created_at.desc() if sort == "created_at" else Issue.priority_score.desc()
    stmt = stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)

    rows = (await db.execute(stmt)).all()
    items = [_to_list_item(issue, name) for issue, name in rows]
    return IssuePage(items=items, total=total, page=page, page_size=page_size)


@router.get("/assignees", response_model=list[StaffOut])
async def list_assignees(
    user: StaffUser, db: SessionDep, department_id: int | None = None
) -> list[StaffOut]:
    """Officials who can be assigned issues. Scoped to the caller's department unless admin."""
    dept = user.department_id if user.role != UserRole.admin else department_id
    stmt = select(User).where(User.role == UserRole.official, User.is_active.is_(True))
    if dept is not None:
        stmt = stmt.where(User.department_id == dept)
    rows = (await db.execute(stmt.order_by(User.full_name))).scalars()
    return [StaffOut.model_validate(u, from_attributes=True) for u in rows]


@router.get("/{issue_id}", response_model=IssueDetail)
async def get_issue(issue_id: UUID, user: StaffUser, db: SessionDep) -> IssueDetail:
    issue = await _load_scoped(db, issue_id, user)
    name = None
    if issue.assigned_to:
        name = (
            await db.execute(select(User.full_name).where(User.id == issue.assigned_to))
        ).scalar_one_or_none()
    coords = (
        await db.execute(
            text(
                "SELECT ST_X(centroid::geometry), ST_Y(centroid::geometry) "
                "FROM issues WHERE id = :id"
            ),
            {"id": issue_id},
        )
    ).first()
    base = _to_list_item(issue, name)
    return IssueDetail(
        **base.model_dump(),
        location=GeoPoint(coordinates=(coords[0], coords[1])),
        first_reported_at=issue.first_reported_at,
        resolved_at=issue.resolved_at,
        resolution_note=issue.resolution_note,
    )


@router.get("/{issue_id}/media", response_model=list[MediaOut])
async def issue_media(issue_id: UUID, user: StaffUser, db: SessionDep) -> list[MediaOut]:
    """All photos across the complaints on this issue, with their CV detections."""
    await _load_scoped(db, issue_id, user)
    rows = (
        await db.execute(
            text(
                """
                SELECT cm.id, cm.object_key, cm.mime, cm.cv_status::text AS cv_status,
                       cm.cv_result, cm.moderation::text AS moderation
                FROM complaint_media cm
                JOIN complaints c ON c.id = cm.complaint_id
                WHERE c.issue_id = :iid
                ORDER BY cm.created_at
                """
            ),
            {"iid": issue_id},
        )
    ).mappings()
    return [
        MediaOut(
            id=r["id"],
            object_key=r["object_key"],
            mime=r["mime"],
            url=storage.presign_get(r["object_key"]),
            cv_status=r["cv_status"],
            cv_result=r["cv_result"],
            moderation=r["moderation"],
        )
        for r in rows
    ]


@router.get("/{issue_id}/timeline", response_model=list[TimelineEntry])
async def get_timeline(issue_id: UUID, user: StaffUser, db: SessionDep) -> list[TimelineEntry]:
    await _load_scoped(db, issue_id, user)
    history = (
        await db.execute(select(IssueStatusHistory).where(IssueStatusHistory.issue_id == issue_id))
    ).scalars()
    updates = (
        await db.execute(select(IssueUpdate).where(IssueUpdate.issue_id == issue_id))
    ).scalars()

    entries: list[TimelineEntry] = []
    for h in history:
        entries.append(
            TimelineEntry(
                kind="status",
                created_at=h.created_at,
                actor_id=h.actor_id,
                text=h.note,
                from_status=h.from_status,
                to_status=h.to_status,
            )
        )
    for u in updates:
        entries.append(
            TimelineEntry(
                kind="update",
                created_at=u.created_at,
                actor_id=u.author_id,
                text=u.body,
                is_internal=u.is_internal,
            )
        )
    entries.sort(key=lambda e: e.created_at)
    return entries


@router.patch("/{issue_id}/status", response_model=IssueDetail)
async def change_status(
    issue_id: UUID, body: StatusTransitionIn, user: StaffUser, db: SessionDep
) -> IssueDetail:
    issue = await _load_scoped(db, issue_id, user)
    try:
        await lifecycle.transition(db, issue, body.to_status, user.id, body.note)
    except lifecycle.TransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_transition", "message": str(e)},
        ) from e
    await db.commit()
    return await get_issue(issue_id, user, db)


@router.post("/{issue_id}/assign", response_model=IssueDetail)
async def assign_issue(
    issue_id: UUID, body: AssignIn, user: StaffUser, db: SessionDep
) -> IssueDetail:
    # Only department heads and admins may assign.
    if user.role != UserRole.admin and not user.is_department_head:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": "Only department heads can assign"},
        )
    issue = await _load_scoped(db, issue_id, user)
    assignee = await db.get(User, body.assignee_id)
    if assignee is None or assignee.role != UserRole.official:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "bad_assignee", "message": "Assignee must be an official"},
        )
    await lifecycle.assign(db, issue, body.assignee_id, user.id)
    await db.commit()
    return await get_issue(issue_id, user, db)


async def _is_linked(db: SessionDep, issue_id: UUID, user_id: UUID) -> bool:
    """A citizen is 'linked' to an issue if they reported it or upvoted it."""
    row = (
        await db.execute(
            text(
                "SELECT 1 FROM complaints WHERE issue_id = :i AND citizen_id = :u "
                "UNION SELECT 1 FROM issue_upvotes WHERE issue_id = :i AND user_id = :u LIMIT 1"
            ),
            {"i": issue_id, "u": user_id},
        )
    ).first()
    return row is not None


async def _citizen_transition(
    issue_id: UUID, user: User, db: SessionDep, to: IssueStatus, note: str | None
) -> dict[str, str]:
    issue = await db.get(Issue, issue_id)
    if issue is None or not await _is_linked(db, issue_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Issue not found"},
        )
    try:
        await lifecycle.transition(db, issue, to, actor_id=user.id, note=note)
    except lifecycle.TransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_transition", "message": str(e)},
        ) from e
    await db.commit()
    return {"status": issue.status.value}


@router.post("/{issue_id}/confirm-resolution")
async def confirm_resolution(issue_id: UUID, user: CitizenUser, db: SessionDep) -> dict[str, str]:
    """Citizen confirms a resolved issue is actually fixed → closed."""
    return await _citizen_transition(
        issue_id, user, db, IssueStatus.closed, note="Citizen confirmed resolution"
    )


@router.post("/{issue_id}/reopen")
async def reopen(
    issue_id: UUID, body: ReopenIn, user: CitizenUser, db: SessionDep
) -> dict[str, str]:
    """Citizen disputes a resolution → reopened, back into the official queue."""
    return await _citizen_transition(
        issue_id, user, db, IssueStatus.reopened, note=f"Reopened by citizen: {body.reason}"
    )


@router.post("/{issue_id}/upvote")
async def upvote_issue(issue_id: UUID, user: CitizenUser, db: SessionDep) -> dict[str, int]:
    """Citizen 'me too' from the duplicate intercept: subscribe + boost priority.
    Idempotent — upvoting twice is a no-op."""
    issue = await db.get(Issue, issue_id)
    if issue is None or issue.status in _CLOSED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Issue not available"},
        )
    existing = await db.get(IssueUpvote, {"issue_id": issue_id, "user_id": user.id})
    if existing is None:
        db.add(IssueUpvote(issue_id=issue_id, user_id=user.id))
        issue.upvote_count += 1
        await priority.recompute(db, issue)
        await db.commit()
    return {"upvotes": issue.upvote_count}


@router.post("/{issue_id}/updates", status_code=status.HTTP_201_CREATED)
async def add_update(
    issue_id: UUID, body: IssueUpdateIn, user: StaffUser, db: SessionDep
) -> dict[str, str]:
    await _load_scoped(db, issue_id, user)
    db.add(
        IssueUpdate(
            issue_id=issue_id, author_id=user.id, body=body.body, is_internal=body.is_internal
        )
    )
    await db.commit()
    return {"status": "added"}
