from uuid import UUID

from sqlalchemy import select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import IssueUpvote
from app.models.complaint import Complaint
from app.models.notification import Notification


async def create(
    db: AsyncSession,
    user_id: UUID,
    kind: str,
    title: str,
    body: str | None = None,
    issue_id: UUID | None = None,
) -> Notification:
    n = Notification(user_id=user_id, kind=kind, title=title, body=body, issue_id=issue_id)
    db.add(n)
    return n


async def notify_issue_citizens(
    db: AsyncSession, issue_id: UUID, kind: str, title: str, body: str | None = None
) -> int:
    """Notify everyone subscribed to this issue: complaint reporters AND upvoters
    (from the duplicate intercept). This is how the dedup payoff reaches people —
    fix one issue, every linked reporter and 'me too' hears about it."""
    reporters = select(Complaint.citizen_id).where(Complaint.issue_id == issue_id)
    upvoters = select(IssueUpvote.user_id).where(IssueUpvote.issue_id == issue_id)
    user_ids = (await db.execute(union(reporters, upvoters))).scalars()
    count = 0
    for uid in user_ids:
        await create(db, uid, kind, title, body=body, issue_id=issue_id)
        count += 1
    # Day 5 enqueues email fan-out here for each notification.
    return count
