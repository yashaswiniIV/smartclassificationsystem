from pydantic import BaseModel


class HeatCell(BaseModel):
    lng: float
    lat: float
    weight: int


class TrendPoint(BaseModel):
    week: str
    new_issues: int
    resolved_issues: int


class DepartmentRow(BaseModel):
    department_id: int
    name: str
    open_count: int
    total: int
    sla_breach_pct: float
    reopened_pct: float
    median_resolution_hours: float | None


class CategoryCount(BaseModel):
    name: str
    count: int


class PublicStats(BaseModel):
    total_issues: int
    open_issues: int
    resolved_issues: int
    resolved_pct: float
    top_categories: list[CategoryCount]


class PublicIssue(BaseModel):
    public_code: str
    title: str
    status: str
    category: str
    ward: str
    lng: float
    lat: float
    created_at: str


class Hotspot(BaseModel):
    ward_id: int
    ward_name: str
    category_id: int
    category_name: str
    recent_per_week: float
    baseline_per_week: float
    ratio: float
    lng: float
    lat: float


class ForecastPoint(BaseModel):
    week: str
    mean: float
    lower: float
    upper: float


class HistoryPoint(BaseModel):
    week: str
    count: int


class ForecastOut(BaseModel):
    status: str
    model: str | None = None
    weeks_available: int | None = None
    history: list[HistoryPoint] = []
    forecast: list[ForecastPoint] = []


class WardRisk(BaseModel):
    ward_id: int
    ward_name: str
    risk_score: float
    open_count: int
    factors: dict[str, float]


class RootCauseOut(BaseModel):
    ward_id: int
    ward_name: str | None = None
    hypothesis: str
    stats: dict
