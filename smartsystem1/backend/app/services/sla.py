"""SLA breach scan (docs/02-user-flows.md F6). Hourly in prod (arq cron); also
admin-triggerable. Flags overdue open issues and notifies the people who can act:
the assignee if there is one, otherwise the department's heads.
"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.user import User
from app.services import notifications


async def scan_sla(db: AsyncSession) -> int:
    breached = (
        (
            await db.execute(
                text(
                    """
                UPDATE issues SET sla_breached = true
                WHERE sla_breached = false
                  AND status IN ('open','acknowledged','assigned','in_progress','reopened')
                  AND now() > sla_due_at
                RETURNING id, assigned_to, department_id
                """
                )
            )
        )
        .mappings()
        .all()
    )
    if not breached:
        return 0

    # Department heads, looked up once, to notify breaches with no assignee.
    heads_by_dept: dict[int, list] = {}
    head_rows = (
        await db.execute(
            select(User.id, User.department_id).where(
                User.role == UserRole.official, User.is_department_head.is_(True)
            )
        )
    ).all()
    for uid, dept in head_rows:
        heads_by_dept.setdefault(dept, []).append(uid)

    for r in breached:
        title = "SLA breached"
        body = "An issue has passed its resolution deadline."
        if r["assigned_to"] is not None:
            await notifications.create(
                db, r["assigned_to"], "sla_breach", title, body=body, issue_id=r["id"]
            )
        else:
            for head_id in heads_by_dept.get(r["department_id"], []):
                await notifications.create(
                    db, head_id, "sla_breach", title, body=body, issue_id=r["id"]
                )
    await db.commit()
    return len(breached)
