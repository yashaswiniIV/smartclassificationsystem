from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser
from app.core.db import SessionDep
from app.core.security import hash_password
from app.models.user import OfficialWard, User
from app.schemas.user import InviteIn, StaffOut
from app.schemas.ward import WardImportRequest, WardImportResult
from app.services import sla
from app.services import wards as ward_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/jobs/scan-sla")
async def scan_sla_job(_: AdminUser, db: SessionDep) -> dict[str, int]:
    """Trigger the SLA breach scan (runs hourly via the worker cron in prod)."""
    return {"breached": await sla.scan_sla(db)}


@router.post("/wards/import", response_model=WardImportResult)
async def import_wards(body: WardImportRequest, _: AdminUser, db: SessionDep) -> WardImportResult:
    n = await ward_service.import_feature_collection(
        db,
        body.feature_collection,
        code_prop=body.code_prop,
        name_prop=body.name_prop,
        zone_prop=body.zone_prop,
    )
    return WardImportResult(imported=n)


@router.post("/users/invite", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def invite_user(body: InviteIn, _: AdminUser, db: SessionDep) -> StaffOut:
    """Create an official or admin. Admin-created accounts are pre-verified (no OTP).
    A real invite flow would email a set-password link; here the admin sets an initial one."""
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "email_taken", "message": "Email already registered"},
        )
    user = User(
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        password_hash=hash_password(body.password),
        department_id=body.department_id,
        is_department_head=body.is_department_head,
        email_verified_at=datetime.now(UTC),  # admin-created → already verified
    )
    db.add(user)
    await db.flush()
    for ward_id in body.ward_ids:
        db.add(OfficialWard(user_id=user.id, ward_id=ward_id))
    await db.commit()
    return StaffOut.model_validate(user, from_attributes=True)
