from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, StaffUser
from app.core.db import SessionDep
from app.schemas.analytics import (
    DepartmentRow,
    ForecastOut,
    HeatCell,
    Hotspot,
    RootCauseOut,
    TrendPoint,
    WardRisk,
)
from app.services import analytics, predictive

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/heatmap", response_model=list[HeatCell])
async def heatmap(
    _: StaffUser,
    db: SessionDep,
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
) -> list[HeatCell]:
    cells = await analytics.heatmap(
        db, date_from=date_from, date_to=date_to, category_id=category_id
    )
    return [HeatCell(**c) for c in cells]


@router.get("/trends", response_model=list[TrendPoint])
async def trends(
    _: StaffUser,
    db: SessionDep,
    ward_id: int | None = None,
    category_id: int | None = None,
    weeks: Annotated[int, Query(ge=1, le=104)] = 26,
) -> list[TrendPoint]:
    rows = await analytics.trends(db, ward_id=ward_id, category_id=category_id, weeks=weeks)
    return [TrendPoint(**r) for r in rows]


@router.get("/departments", response_model=list[DepartmentRow])
async def departments(_: AdminUser, db: SessionDep) -> list[DepartmentRow]:
    rows = await analytics.department_performance(db)
    return [DepartmentRow(**r) for r in rows]


@router.get("/hotspots", response_model=list[Hotspot])
async def hotspots(_: StaffUser, db: SessionDep) -> list[Hotspot]:
    """Emerging ward x category cells: recent rate >= 2x the trailing-8-week baseline."""
    return [Hotspot(**h) for h in await predictive.emerging_hotspots(db)]


@router.get("/forecast", response_model=ForecastOut)
async def forecast(
    _: StaffUser, db: SessionDep, category_id: int, ward_id: int | None = None
) -> ForecastOut:
    """4-week SARIMAX forecast (with 80% CI) for a category, optionally ward-scoped."""
    return ForecastOut(**await predictive.forecast(db, category_id, ward_id))


@router.get("/wards/risk", response_model=list[WardRisk])
async def wards_risk(_: AdminUser, db: SessionDep) -> list[WardRisk]:
    return [WardRisk(**r) for r in await predictive.ward_risk(db)]


@router.get("/wards/{ward_id}/root-cause", response_model=RootCauseOut)
async def root_cause(ward_id: int, _: AdminUser, db: SessionDep) -> RootCauseOut:
    return RootCauseOut(**await predictive.root_cause(db, ward_id))
