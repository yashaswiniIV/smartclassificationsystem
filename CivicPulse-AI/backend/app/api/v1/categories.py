from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import StaffUser
from app.core.db import SessionDep
from app.models.org import Category
from app.schemas.category import CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(_: StaffUser, db: SessionDep) -> list[CategoryOut]:
    rows = (
        await db.execute(
            select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
        )
    ).scalars()
    return [CategoryOut.model_validate(c, from_attributes=True) for c in rows]
