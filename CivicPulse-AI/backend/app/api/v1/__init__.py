from fastapi import APIRouter

from app.api.v1 import (
    admin,
    analytics,
    auth,
    categories,
    complaints,
    health,
    issues,
    notifications,
    public,
    reports,
    triage,
    wards,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(complaints.router)
api_router.include_router(issues.router)
api_router.include_router(triage.router)
api_router.include_router(notifications.router)
api_router.include_router(categories.router)
api_router.include_router(analytics.router)
api_router.include_router(reports.router)
api_router.include_router(public.router)
api_router.include_router(wards.router)
api_router.include_router(admin.router)
