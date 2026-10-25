from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, StaffUser
from app.core.db import SessionDep
from app.models.report import Report
from app.schemas.report import ReportListItem, ReportOut
from app.services import reports as report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=list[ReportListItem])
async def list_reports(_: StaffUser, db: SessionDep) -> list[ReportListItem]:
    rows = (await db.execute(select(Report).order_by(Report.created_at.desc()).limit(50))).scalars()
    return [ReportListItem.model_validate(r, from_attributes=True) for r in rows]


@router.post("/generate", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def generate(_: AdminUser, db: SessionDep) -> ReportOut:
    report = await report_service.generate_report(db)
    return ReportOut.model_validate(report, from_attributes=True)


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: UUID, _: StaffUser, db: SessionDep) -> ReportOut:
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Report not found"},
        )
    return ReportOut.model_validate(report, from_attributes=True)
