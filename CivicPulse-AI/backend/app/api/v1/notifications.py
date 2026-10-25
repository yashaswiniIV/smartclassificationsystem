from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select, update

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models.notification import Notification
from app.schemas.notification import MarkReadIn, NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    user: CurrentUser, db: SessionDep, unread_only: bool = False
) -> list[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(100)
    rows = (await db.execute(stmt)).scalars()
    return [NotificationOut.model_validate(n, from_attributes=True) for n in rows]


@router.post("/read")
async def mark_read(body: MarkReadIn, user: CurrentUser, db: SessionDep) -> dict[str, int]:
    stmt = (
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    if body.ids:
        stmt = stmt.where(Notification.id.in_(body.ids))
    result = await db.execute(stmt)
    await db.commit()
    return {"marked": result.rowcount or 0}
