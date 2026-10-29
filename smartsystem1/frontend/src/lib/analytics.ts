import { api } from "./api";

export type HeatCell = { lng: number; lat: number; weight: number };
export type TrendPoint = { week: string; new_issues: number; resolved_issues: number };
export type DepartmentRow = {
  department_id: number;
  name: string;
  open_count: number;
  total: number;
  sla_breach_pct: number;
  reopened_pct: number;
  median_resolution_hours: number | null;
};
export type PublicStats = {
  total_issues: number;
  open_issues: number;
  resolved_issues: number;
  resolved_pct: number;
  top_categories: { name: string; count: number }[];
};
export type PublicIssue = {
  public_code: string;
  title: string;
  status: string;
  category: string;
  ward: string;
  lng: number;
  lat: number;
  created_at: string;
};

export type Hotspot = {
  ward_id: number;
  ward_name: string;
  category_id: number;
  category_name: string;
  recent_per_week: number;
  baseline_per_week: number;
  ratio: number;
  lng: number;
  lat: number;
};
export type ForecastOut = {
  status: "ok" | "insufficient_history";
  model?: string;
  weeks_available?: number;
  history: { week: string; count: number }[];
  forecast: { week: string; mean: number; lower: number; upper: number }[];
};
export type WardRisk = {
  ward_id: number;
  ward_name: string;
  risk_score: number;
  open_count: number;
  factors: Record<string, number>;
};
export type RootCause = {
  ward_id: number;
  ward_name: string | null;
  hypothesis: string;
  stats: Record<string, unknown>;
};
export type Category = { id: number; name: string };

export const analyticsApi = {
  heatmap: (categoryId?: number) =>
    api.get<HeatCell[]>(`/analytics/heatmap${categoryId ? `?category_id=${categoryId}` : ""}`),
  trends: (weeks = 26) => api.get<TrendPoint[]>(`/analytics/trends?weeks=${weeks}`),
  departments: () => api.get<DepartmentRow[]>("/analytics/departments"),
  hotspots: () => api.get<Hotspot[]>("/analytics/hotspots"),
  forecast: (categoryId: number, wardId?: number) =>
    api.get<ForecastOut>(
      `/analytics/forecast?category_id=${categoryId}${wardId ? `&ward_id=${wardId}` : ""}`,
    ),
  wardRisk: () => api.get<WardRisk[]>("/analytics/wards/risk"),
  rootCause: (wardId: number) => api.get<RootCause>(`/analytics/wards/${wardId}/root-cause`),
  categories: () => api.get<Category[]>("/categories"),
  publicStats: () => api.get<PublicStats>("/public/stats"),
  publicIssues: (limit = 200) => api.get<PublicIssue[]>(`/public/issues?limit=${limit}`),
};
