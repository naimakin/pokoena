export type TenantRole = "company_admin" | "company_employee" | "subcontractor";

export type ProjectRole =
  | "project_administrator"
  | "all_access"
  | "execution"
  | "user_management"
  | "activity_status_updater";

export const PROJECT_ROLE_LABELS: Record<ProjectRole, string> = {
  project_administrator: "Project Administrator",
  all_access: "All Access (No Threshold Settings)",
  execution: "Execution",
  user_management: "User Management",
  activity_status_updater: "Activity Status Updater",
};

export interface User {
  id: string;
  email: string;
  full_name: string;
  title?: string | null;
  phone?: string | null;
  is_active: boolean;
  tenant_id: string;
  role: TenantRole;
  project_role?: ProjectRole | null;
  scope_ids: string[];
}

export interface PlatformAdmin {
  id: string;
  email: string;
  full_name: string;
  title?: string | null;
  phone?: string | null;
  is_active: boolean;
}

export interface PlatformAdminCreatePayload {
  email: string;
  password: string;
  full_name: string;
  title?: string;
  phone?: string;
}

export type TenantStatus = "active" | "suspended" | "deleted";

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  status: TenantStatus;
  created_at: string;
}

export interface UsageSummary {
  tenant_count: number;
  active_tenant_count: number;
  total_users: number;
  total_projects: number;
}

export interface Project {
  id: string;
  tenant_id: string;
  name: string;
  code: string;
}

export interface ProjectScope {
  id: string;
  tenant_id: string;
  project_id: string;
  subcontractor_org_id: string | null;
  name: string;
  discipline: string;
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
  tenant_id: string;
  project_id: string;
  project_scope_id: string | null;
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
  requested_by_org?: string | null;
  activity_name?: string | null;
  activity_external_id?: string | null;
}

export interface ScopeSubmissionStatus {
  subcontractor_org_id: string;
  org_name: string;
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
  orgs_total: number;
  orgs_submitted: number;
  flagged_pending: number;
  scope_status: ScopeSubmissionStatus[];
}

export interface InviteCreatePayload {
  email: string;
  full_name: string;
  title?: string;
  phone?: string;
  role: TenantRole;
  project_role?: ProjectRole;
  project_ids?: string[];
  project_scope_ids?: string[];
  subcontractor_org_id?: string | null;
}

export interface Invite {
  id: string;
  email: string;
  full_name: string;
  role: TenantRole;
  project_role?: ProjectRole | null;
  status: string;
  expires_at: string;
}

export interface InvitePreview {
  email: string;
  full_name: string;
  title?: string | null;
  role: TenantRole;
  project_role?: ProjectRole | null;
  tenant_name: string;
  expires_at: string;
}

export interface TeamMember {
  user_tenant_role_id: string;
  user_id: string;
  email: string;
  full_name: string;
  title?: string | null;
  phone?: string | null;
  role: TenantRole;
  project_role?: ProjectRole | null;
  is_active: boolean;
  created_at: string;
}

export interface SubcontractorOrg {
  id: string;
  tenant_id: string;
  name: string;
  discipline: string;
}
