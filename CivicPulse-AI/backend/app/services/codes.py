from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _nextval(db: AsyncSession, seq: str) -> int:
    return (await db.execute(text(f"SELECT nextval('{seq}')"))).scalar_one()


async def next_complaint_code(db: AsyncSession) -> str:
    return f"CP-{datetime.now(UTC).year}-{await _nextval(db, 'complaint_code_seq'):06d}"


async def next_issue_code(db: AsyncSession) -> str:
    return f"ISS-{datetime.now(UTC).year}-{await _nextval(db, 'issue_code_seq'):05d}"
