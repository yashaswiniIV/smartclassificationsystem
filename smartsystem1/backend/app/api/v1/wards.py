from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.models.org import Ward
from app.schemas.ward import WardOut

router = APIRouter(prefix="/wards", tags=["wards"])


@router.get("", response_model=list[WardOut])
async def list_wards(_: CurrentUser, db: SessionDep) -> list[WardOut]:
    rows = (
        await db.execute(select(Ward.id, Ward.ward_code, Ward.name, Ward.zone).order_by(Ward.name))
    ).all()
    return [WardOut(id=r.id, ward_code=r.ward_code, name=r.name, zone=r.zone) for r in rows]
