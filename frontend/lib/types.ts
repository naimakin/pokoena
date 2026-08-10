export type UserRole = "admin" | "subcontractor" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  company_id: string | null;
  is_active: boolean;
}

export interface Project {
  id: string;
  name: string;
  code: string;
}

export type UpdatePeriodStatus = "open" | "closed";

export interface UpdatePeriod {
  id: string;
  project_id: string;
  period_number: number;
  label: string;
  opens_at: string;
  deadline_at: string;
  status: UpdatePeriodStatus;
  closed_at: string | null;
}

export type ActivityStatus = "not_started" | "in_progress" | "complete";

export interface Activity {
  id: string;
  project_id: string;
  company_id: string | null;
  external_id: string;
  name: string;
  discipline: string;
  planned_start: string | null;
  planned_finish: string | null;
  actual_start: string | null;
  actual_finish: string | null;
  percent_complete: number;
  remaining_duration_days: number;
  status: ActivityStatus;
}

export interface ActivityUpdatePayload {
  percent_complete?: number;
  actual_start?: string | null;
  actual_finish?: string | null;
  remaining_duration_days?: number;
}

export type LinkType = "FS" | "SS" | "FF" | "SF";

export interface ActivityRelationship {
  id: string;
  predecessor_id: string;
  successor_id: string;
  link_type: LinkType;
  lag_days: number;
  predecessor_external_id?: string | null;
  successor_external_id?: string | null;
}

export type RiskLevel = "low" | "medium" | "high";
export type ChangeRequestStatusValue = "pending" | "approved" | "rejected";

export interface ChangeRequest {
  id: string;
  update_period_id: string;
  activity_id: string | null;
  activity_relationship_id: string | null;
  requested_by_user_id: string;
  field_changed: string;
  before_value: string;
  after_value: string;
  justification: string;
  risk_level: RiskLevel;
  status: ChangeRequestStatusValue;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  requested_by_name?: string | null;
  requested_by_company?: string | null;
  activity_name?: string | null;
  activity_external_id?: string | null;
}

export interface ScopeSubmissionStatus {
  company_id: string;
  company_name: string;
  discipline: string;
  activity_count: number;
  avg_percent_complete: number;
  submitted: boolean;
}

export interface DashboardSummary {
  active_period_id: string | null;
  active_period_label: string | null;
  active_period_status: UpdatePeriodStatus | null;
  deadline_at: string | null;
  companies_total: number;
  companies_submitted: number;
  flagged_pending: number;
  scope_status: ScopeSubmissionStatus[];
}
