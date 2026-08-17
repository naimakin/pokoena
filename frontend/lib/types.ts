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
  project_roles: ProjectRole[];
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
  admin_email: string | null;
}

export interface TenantCreateResult extends Tenant {
  // One-time invite link for the first company admin — no email provider is
  // wired up yet, so this is the only place it's ever recoverable.
  admin_invite_url: string;
}

export interface PasswordResetLink {
  email: string;
  reset_url: string;
}

export interface PasswordResetPreview {
  email: string;
  is_platform_admin: boolean;
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

export interface ProjectCreatePayload {
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

  // P6/CPM fields, populated by .xer import — null until a schedule has been
  // imported for this project. See ScheduleImport.
  wbs_path?: string | null;
  task_type?: string | null;
  status_code?: string | null;
  target_duration_hours?: number | null;
  remaining_duration_hours?: number | null;
  early_start?: string | null;
  early_finish?: string | null;
  late_start?: string | null;
  late_finish?: string | null;
  total_float_hours?: number | null;
  free_float_hours?: number | null;
  is_critical?: boolean;
  constraint_type?: string | null;
  constraint_date?: string | null;
  constraint_type_2?: string | null;
  constraint_date_2?: string | null;
  is_longest_path?: boolean;
}

export interface DcmaCheckResult {
  id: number;
  name: string;
  status: "pass" | "warn" | "fail" | "not_tracked";
  value: number;
  threshold: number;
  pct: number;
  unit: string;
  details: string[];
}

export interface DcmaReport {
  computed_at: string;
  total_activities: number;
  in_scope: number;
  overall_score: number;
  overall_status: "pass" | "warn" | "fail";
  checks: DcmaCheckResult[];
}

export interface ScheduleImport {
  id: string;
  project_id: string;
  filename: string;
  data_date: string | null;
  imported_by_user_id: string;
  imported_at: string;
  activity_count: number;
  critical_count: number;
  warnings: string[];
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
  project_roles?: ProjectRole[];
  project_ids?: string[];
  project_scope_ids?: string[];
  subcontractor_org_id?: string | null;
}

export interface Invite {
  id: string;
  email: string;
  full_name: string;
  role: TenantRole;
  project_roles: ProjectRole[];
  status: string;
  expires_at: string;
  // Only present on the response to creating this invite — see
  // TenantCreateResult for why.
  invite_url?: string | null;
}

export interface InvitePreview {
  email: string;
  full_name: string;
  title?: string | null;
  role: TenantRole;
  project_roles: ProjectRole[];
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
  project_roles: ProjectRole[];
  is_active: boolean;
  created_at: string;
}

export interface SubcontractorOrg {
  id: string;
  tenant_id: string;
  name: string;
  discipline: string;
}
