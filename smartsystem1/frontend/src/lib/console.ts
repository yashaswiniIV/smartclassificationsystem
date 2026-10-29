import { api } from "./api";

export type IssueStatus =
  | "open"
  | "acknowledged"
  | "assigned"
  | "in_progress"
  | "resolved"
  | "closed"
  | "reopened"
  | "rejected";

export type IssueListItem = {
  id: string;
  public_code: string;
  title: string;
  status: IssueStatus;
  priority_score: number;
  category_id: number;
  department_id: number;
  ward_id: number;
  complaint_count: number;
  sla_due_at: string;
  sla_breached: boolean;
  assigned_to: string | null;
  assigned_to_name: string | null;
  created_at: string;
};

export type IssueDetail = IssueListItem & {
  location: { type: "Point"; coordinates: [number, number] };
  first_reported_at: string;
  resolved_at: string | null;
  resolution_note: string | null;
};

export type IssuePage = {
  items: IssueListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type TriageItem = {
  id: string;
  public_code: string;
  description: string;
  address_text: string | null;
  ward_id: number | null;
  processing_status: string;
  location: { type: "Point"; coordinates: [number, number] };
  created_at: string;
};

export type TimelineEntry = {
  kind: "status" | "update";
  created_at: string;
  actor_id: string | null;
  text: string | null;
  from_status: IssueStatus | null;
  to_status: IssueStatus | null;
  is_internal: boolean;
};

export type Category = {
  id: number;
  name: string;
  department_id: number;
  severity_weight: number;
  sla_hours: number;
};

export type StaffMember = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  department_id: number | null;
  is_department_head: boolean;
};

// Allowed next statuses (mirrors backend lifecycle.ALLOWED) for building action buttons.
export const NEXT_STATUSES: Record<IssueStatus, IssueStatus[]> = {
  open: ["acknowledged", "rejected"],
  acknowledged: ["assigned", "rejected"],
  assigned: ["in_progress"],
  in_progress: ["resolved"],
  resolved: ["closed", "reopened"],
  reopened: ["assigned"],
  closed: [],
  rejected: [],
};

export type IssueMedia = {
  id: string;
  url: string;
  mime: string;
  cv_status: string;
  cv_result: { labels?: { label: string; conf: number }[]; severity?: number } | null;
  moderation: string | null;
};

export type ReportListItem = {
  id: string;
  period_start: string;
  period_end: string;
  scope: string;
  created_at: string;
};
export type Report = ReportListItem & {
  stats: Record<string, unknown>;
  content_md: string | null;
};

export const consoleApi = {
  listIssues: (qs = "") => api.get<IssuePage>(`/issues${qs}`),
  getIssue: (id: string) => api.get<IssueDetail>(`/issues/${id}`),
  issueMedia: (id: string) => api.get<IssueMedia[]>(`/issues/${id}/media`),
  timeline: (id: string) => api.get<TimelineEntry[]>(`/issues/${id}/timeline`),
  changeStatus: (id: string, to_status: IssueStatus, note?: string) =>
    api.patch<IssueDetail>(`/issues/${id}/status`, { to_status, note }),
  assign: (id: string, assignee_id: string) =>
    api.post<IssueDetail>(`/issues/${id}/assign`, { assignee_id }),
  addUpdate: (id: string, body: string, is_internal: boolean) =>
    api.post(`/issues/${id}/updates`, { body, is_internal }),
  assignees: (departmentId?: number) =>
    api.get<StaffMember[]>(`/issues/assignees${departmentId ? `?department_id=${departmentId}` : ""}`),
  triageQueue: () => api.get<TriageItem[]>("/triage/queue"),
  createIssue: (complaintId: string, category_id: number, title?: string) =>
    api.post<IssueDetail>(`/triage/${complaintId}/create-issue`, { category_id, title }),
  categories: () => api.get<Category[]>("/categories"),
  listReports: () => api.get<ReportListItem[]>("/reports"),
  getReport: (id: string) => api.get<Report>(`/reports/${id}`),
  generateReport: () => api.post<Report>("/reports/generate"),
  scanSla: () => api.post<{ breached: number }>("/admin/jobs/scan-sla"),
};
