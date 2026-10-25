"""Reset to a clean, coherent demo state.

Clears all transactional data + citizen accounts (test cruft accumulates during
development and muddies the hotspot/forecast story), keeps reference data and staff
accounts, then regenerates the synthetic history so the planted signals — the
monsoon water spike and the ward-1 pothole hotspot — are the clear story.

Run from backend/:  uv run python -m scripts.reset_demo
"""

import asyncio

from sqlalchemy import text

from app.core.db import session_factory
from scripts import generate_synthetic

_TRUNCATE = """
TRUNCATE complaints, issues, complaint_media, issue_status_history, issue_updates,
         issue_upvotes, notifications, ai_jobs, corrections, reports, daily_stats
RESTART IDENTITY CASCADE
"""


async def main() -> None:
    async with session_factory() as db:
        await db.execute(text(_TRUNCATE))
        # Drop citizen accounts (test + synthetic); keep admin/officials.
        await db.execute(text("DELETE FROM users WHERE role = 'citizen'"))
        await db.commit()
    print("cleared transactional data + citizen accounts (staff + reference kept)")

    # Regenerate the synthetic history and rebuild daily_stats.
    await generate_synthetic.main()


if __name__ == "__main__":
    asyncio.run(main())
