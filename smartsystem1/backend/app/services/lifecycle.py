from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import IssueStatusHistory
from app.models.enums import IssueStatus
from app.models.issue import Issue
from app.services import notifications

# The issue state machine (docs/02-user-flows.md F5). Keys = current status,
# values = allowed next statuses. Anything not listed is rejected server-side.
ALLOWED: dict[IssueStatus, set[IssueStatus]] = {
    IssueStatus.open: {IssueStatus.acknowledged, IssueStatus.rejected},
    IssueStatus.acknowledged: {IssueStatus.assigned, IssueStatus.rejected},
    IssueStatus.assigned: {IssueStatus.in_progress},
    IssueStatus.in_progress: {IssueStatus.resolved},
    IssueStatus.resolved: {IssueStatus.closed, IssueStatus.reopened},
    IssueStatus.reopened: {IssueStatus.assigned},
    IssueStatus.closed: set(),
    IssueStatus.rejected: set(),
}

# Transitions that must carry an explanatory note.
NOTE_REQUIRED = {IssueStatus.resolved, IssueStatus.rejected}


class TransitionError(Exception):
    """Illegal state transition or missing required note."""


async def transition(
    db: AsyncSession,
    issue: Issue,
    to_status: IssueStatus,
    actor_id: UUID | None,
    note: str | None = None,
) -> None:
    frm = issue.status
    if to_status not in ALLOWED.get(frm, set()):
        raise TransitionError(f"Cannot move issue from {frm} to {to_status}")
    if to_status in NOTE_REQUIRED and not (note and note.strip()):
        raise TransitionError(f"A note is required to mark an issue {to_status}")

    now = datetime.now(UTC)
    issue.status = to_status
    if to_status == IssueStatus.resolved:
        issue.resolved_at = now
        issue.resolution_note = note
    elif to_status == IssueStatus.closed:
        issue.closed_at = now
    elif to_status == IssueStatus.reopened:
        issue.reopen_count += 1
        issue.resolved_at = None

    db.add(
        IssueStatusHistory(
            issue_id=issue.id,
            from_status=frm,
            to_status=to_status,
            actor_id=actor_id,
            note=note,
        )
    )
    await notifications.notify_issue_citizens(
        db,
        issue.id,
        kind="status_change",
        title=f"Update on {issue.public_code}",
        body=f"Status changed from {frm} to {to_status}.",
    )


async def assign(db: AsyncSession, issue: Issue, assignee_id: UUID, actor_id: UUID | None) -> None:
    """Set the assignee and, if the issue is waiting to be picked up, advance it to assigned."""
    issue.assigned_to = assignee_id
    if issue.status in (IssueStatus.acknowledged, IssueStatus.reopened):
        await transition(db, issue, IssueStatus.assigned, actor_id, note="Assigned to official")
