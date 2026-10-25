from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_refresh_token, new_refresh_token
from app.models.user import Session, User

settings = get_settings()


class RefreshError(Exception):
    """Refresh token invalid, expired, or reused (session revoked)."""


def _expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days)


async def issue_session(
    db: AsyncSession, user_id: UUID, *, user_agent: str | None, ip: str | None
) -> str:
    """Start a new session family and return the raw refresh token (only ever returned here)."""
    raw = new_refresh_token()
    db.add(
        Session(
            user_id=user_id,
            family_id=uuid4(),
            token_hash=hash_refresh_token(raw),
            user_agent=user_agent,
            ip=ip,
            expires_at=_expiry(),
        )
    )
    return raw


async def rotate_session(
    db: AsyncSession, raw_token: str, *, user_agent: str | None, ip: str | None
) -> tuple[User, str]:
    """Rotate a refresh token. Reuse of an already-rotated token revokes the whole
    family (standard rotation-replay defense). Returns (user, new_raw_token)."""
    now = datetime.now(UTC)
    token_hash = hash_refresh_token(raw_token)

    sess = (
        await db.execute(select(Session).where(Session.token_hash == token_hash))
    ).scalar_one_or_none()
    if sess is None:
        raise RefreshError("unknown refresh token")

    if sess.revoked_at is not None:
        # This token was already rotated — someone is replaying it. Burn the family.
        await db.execute(
            update(Session)
            .where(Session.family_id == sess.family_id, Session.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        raise RefreshError("refresh token reuse detected")

    if sess.expires_at < now:
        raise RefreshError("refresh token expired")

    sess.revoked_at = now
    new_raw = new_refresh_token()
    db.add(
        Session(
            user_id=sess.user_id,
            family_id=sess.family_id,  # same family across rotations
            token_hash=hash_refresh_token(new_raw),
            user_agent=user_agent,
            ip=ip,
            expires_at=_expiry(),
        )
    )
    user = await db.get(User, sess.user_id)
    assert user is not None
    return user, new_raw


async def revoke_session(db: AsyncSession, raw_token: str) -> None:
    await db.execute(
        update(Session)
        .where(
            Session.token_hash == hash_refresh_token(raw_token),
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
