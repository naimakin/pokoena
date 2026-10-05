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
  // False while admin_email only reflects a still-pending invite — no User
  // row exists yet, so Reset password can't work; offer Resend invite instead.
  admin_accepted: boolean;
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

export interface TenantInviteLink {
  email: string;
  invite_url: string;
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
  // P6's TASK.phys_complete_pct. `percent_complete` is the % Poko shows:
  // labor units % when labor is assigned, else 100 / 0 / duration %
  // (backend/app/services/activity_progress.py).
  phys_complete_pct?: number | null;
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
  // The activity's own calendar day length (P6 CALENDAR.day_hr_cnt) — the
  // divisor for showing any *_hours field above in days. See lib/duration.ts.
  hours_per_day?: number;

  // Poko's own annotations — set from the Activity modal, never touched by
  // .xer import (see backend/app/models/activity.py).
  is_important?: boolean;
  tags?: string[];
  notes?: string | null;
  // Site / supply risk for the Criticality Score; null = not assessed
  // (scored as standard).
  site_risk?: SiteRisk | null;

  // Criticality Score (lib/criticality.ts) — null for completed work.
  criticality_score?: number | null;
  criticality_breakdown?: Record<string, number> | null;
}

export type SiteRisk = "high" | "standard" | "low";

/** One entry in the Activity modal's History tab. "change"/"comment" come from
 *  activity_events; "version" is derived from two consecutive import snapshots. */
export interface ActivityHistoryItem {
  kind: "change" | "comment" | "version";
  created_at: string;
  actor_name: string | null;
  field: string | null;
  old_value: string | null;
  new_value: string | null;
  body: string | null;
  revision_label: string | null;
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
  // What `pct` is a share of (backend/app/engine/quality/dcma.py): in-scope
  // activities, relationships (#3, #4) or activities planned to finish by the
  // data date (#14, BEI).
  denominator: number;
  basis: "activities" | "relationships" | "planned";
}

export interface DcmaReport {
  computed_at: string;
  total_activities: number;
  in_scope: number;
  overall_score: number;
  overall_status: "pass" | "warn" | "fail";
  checks: DcmaCheckResult[];
  // The targets the report was measured against (the project's own over
  // DCMA's), DCMA's defaults, and which keys the project changed.
  thresholds?: Record<string, number>;
  default_thresholds?: Record<string, number>;
  customized?: string[];
  can_edit_thresholds?: boolean;
}

export interface MonteCarloRequest {
  iterations?: number;
  spread?: number;
}

export interface MonteCarloHistogramBin {
  date: string;
  count: number;
  cumulative_pct: number;
}

export interface MonteCarloResult {
  iterations: number;
  project_finish_p10: string;
  project_finish_p50: string;
  project_finish_p80: string;
  project_finish_p90: string;
  mean_finish: string;
  histogram: MonteCarloHistogramBin[];
  critical_activities: string[];
}

export type LogicDiffChangeType = "ADDED" | "REMOVED" | "MODIFIED";

export interface LogicDiffChange {
  pred_external_id: string;
  pred_name: string;
  succ_external_id: string;
  succ_name: string;
  change_type: LogicDiffChangeType;
  changes: string[];
  old_link_type: LinkType | null;
  new_link_type: LinkType | null;
  old_lag_hours: number | null;
  new_lag_hours: number | null;
  pred_was_critical: boolean;
  succ_was_critical: boolean;
}

export interface LogicDiffSummary {
  added: number;
  removed: number;
  modified: number;
  total: number;
}

export interface LogicDiffReport {
  from_import_id: string;
  to_import_id: string;
  summary: LogicDiffSummary;
  changes: LogicDiffChange[];
}

// --- Execution → Changes: schedule comparison between two imports ---

export interface ChangeImportRef {
  id: string;
  filename: string;
  revision_label: string | null;
  data_date: string | null;
  imported_at: string;
}

export interface FieldChange {
  field: string;
  label: string;
  old: string | number | null;
  new: string | number | null;
  delta_days: number | null;
  delta_hours: number | null;
  /** Set on "logic": one line per relationship added/removed/retyped. */
  detail: string[] | null;
}

export interface ActivityChange {
  external_id: string;
  name: string | null;
  wbs_path: string | null;
  is_critical: boolean;
  fields: FieldChange[];
}

export interface AddedActivity {
  external_id: string;
  name: string | null;
  wbs_path: string | null;
  planned_finish: string | null;
  is_critical: boolean;
}

export interface RemovedActivity {
  external_id: string;
  name: string | null;
  was_critical: boolean;
}

export interface RenamedActivity {
  old_external_id: string;
  new_external_id: string;
  name: string | null;
}

export interface ScheduleChangeReport {
  project_id: string;
  comparison_basis: "previous_upd" | "baseline_programme" | "baseline_frozen" | "none";
  from_import: ChangeImportRef | null;
  to_import: ChangeImportRef | null;
  coverage: { from_snapshot: boolean; to_snapshot: boolean };
  thresholds: Record<string, number>;
  summary: {
    activities_added: number;
    activities_removed: number;
    activities_renamed: number;
    activities_modified: number;
    date_changes: number;
    criticality_changes: number;
    relationships_added: number;
    relationships_removed: number;
    relationships_modified: number;
  };
  activities: {
    added: AddedActivity[];
    removed: RemovedActivity[];
    renamed: RenamedActivity[];
    modified: ActivityChange[];
  };
  relationships: { summary: LogicDiffSummary; changes: LogicDiffChange[] };
}

export interface ActivityEvm {
  activity_id: string;
  external_id: string;
  name: string;
  status_code: string | null;
  percent_complete: number;
  bac: number;
  pv: number | null;
  ev: number;
  ac: number;
  cpi: number | null;
  spi: number | null;
  sv: number | null;
  cv: number;
  eac_cpi: number | null;
  eac_pf: number | null;
  vac: number | null;
  remaining_manhour: number;
  remaining_qty: number;
}

export interface QuickEvmResult {
  data_date: string | null;
  bac: number;
  pv: number | null;
  ev: number;
  ac: number;
  cpi: number | null;
  spi: number | null;
  sv: number | null;
  cv: number;
  eac_cpi: number | null;
  eac_pf: number | null;
  vac: number | null;
  activity_results: ActivityEvm[];
}

export type BaselineStatusValue = "draft" | "active" | "superseded";

export interface Baseline {
  id: string;
  project_id: string;
  schedule_import_id: string;
  version_label: string;
  locked_at: string | null;
  locked_by_user_id: string | null;
  total_budget_manhours: number;
  target_start_date: string;
  target_end_date: string;
  distribution_method: string;
  status: BaselineStatusValue;
  activity_count: number;
  notes: string | null;
  created_at: string;
  source_filename?: string | null;
}

export interface BaselineProgramResult {
  mode: "created" | "overwritten";
  filename: string;
  activity_count: number;
  critical_count: number;
  warnings: string[];
  baseline: Baseline;
}

export interface BaselineResourceItem {
  rsrc_id: string;
  name: string;
  short_name: string | null;
  rsrc_type: string;
  unit_id: string | null;
  budgeted_qty: number;
  budgeted_cost: number;
  assignment_count: number;
}

export interface BaselineResourceSummary {
  project_id: string;
  baseline_id: string;
  version_label: string;
  resource_count: number;
  labor_count: number;
  material_count: number;
  equipment_count: number;
  total_budgeted_labor_hours: number;
  total_budgeted_cost: number;
  resources: BaselineResourceItem[];
}

export interface BaselineVarianceHistogramBin {
  label: string;
  count: number;
}

export interface BaselineVarianceRow {
  activity_id: string;
  external_id: string;
  name: string;
  wbs_code: string | null;
  baseline_start: string | null;
  baseline_finish: string | null;
  current_start: string | null;
  current_finish: string | null;
  start_variance_days: number | null;
  finish_variance_days: number | null;
  is_critical: boolean;
  status: string;
  percent_complete: number;
}

export interface BaselineVarianceSummary {
  activities_total: number;
  ahead: number;
  on_track: number;
  behind: number;
  baseline_finish: string | null;
  forecast_finish: string | null;
  project_finish_variance_days: number | null;
  worst_slip_days: number | null;
  critical_slip_count: number;
  finish_variance_histogram: BaselineVarianceHistogramBin[];
}

export interface BaselineVariance {
  project_id: string;
  baseline_id: string;
  version_label: string;
  summary: BaselineVarianceSummary;
  rows: BaselineVarianceRow[];
}

export interface BaselineStatus {
  project_id: string;
  has_active: boolean;
  active_baseline: Baseline | null;
  all_baselines: Baseline[];
}

export interface LockBaselinePayload {
  version_label?: string;
  notes?: string | null;
}

export interface LockBaselineResult {
  status: string;
  baseline_id: string;
  version_label: string;
  bac: number;
  activity_count: number;
  target_start: string;
  target_end: string;
}

export interface ProgressEntryPayload {
  activity_id: string;
  entry_date: string;
  burned_manhours_daily: number;
  physical_pct_snapshot?: number | null;
  crew_size?: number | null;
  notes?: string | null;
}

export interface ProgressEntry {
  id: string;
  activity_id: string;
  entry_date: string;
  burned_manhours_daily: number;
  physical_pct_snapshot: number | null;
  entry_type: "actual" | "correction" | "forecast";
  crew_size: number | null;
  notes: string | null;
  created_by_user_id: string;
  created_at: string;
  is_out_of_sequence: boolean;
}

export interface EvmScurvePoint {
  date: string;
  pv: number;
  ev: number;
  ac: number;
  bac: number;
  spi: number | null;
  cpi: number | null;
  sv: number;
  cv: number;
  eac: number | null;
  etc: number | null;
  tcpi: number | null;
  pct_planned: number;
  pct_earned: number;
  tcpi_critical: boolean;
}

export interface EvmScurve {
  project_id: string;
  baseline_id: string;
  version_label: string;
  bac: number;
  granularity: string;
  points: number;
  series: EvmScurvePoint[];
}

export interface EvmSummary {
  project_id: string;
  baseline_id: string | null;
  version_label: string | null;
  status: string;
  message?: string | null;
  as_of_date?: string | null;
  bac: number;
  pv_cumulative: number;
  ev_cumulative: number;
  ac_cumulative: number;
  spi: number | null;
  cpi: number | null;
  sv: number;
  cv: number;
  eac: number | null;
  etc: number | null;
  tcpi: number | null;
  tcpi_critical: boolean;
  pct_planned: number;
  pct_earned: number;
  total_ac_raw: number;
  entry_count: number;
}

/** GET /projects/{id}/evm/progress-summary — planned vs actual at the data
 *  date plus the baseline vs latest version table. See
 *  backend/app/engine/evm/progress_engine.py. */
export interface ProgressVersion {
  kind: "baseline" | "latest";
  label: string | null;
  filename: string | null;
  data_date: string | null;
  start: string | null;
  finish: string | null;
  milestones_total: number;
  /** Baseline row: still open in the baseline plan at the CURRENT data date. */
  milestones_remaining: number;
  tasks_total: number;
  tasks_remaining: number;
  max_wbs_level: number;
}

export interface ProgressSummary {
  project_id: string;
  baseline_id: string;
  version_label: string;
  data_date: string;
  basis: string;
  planned_pct: number | null;
  actual_pct: number | null;
  spi: number | null;
  finish_variance_days: number | null;
  versions: ProgressVersion[];
}

export interface WbsNode {
  id: string;
  wbs_id: string;
  parent_wbs_id: string | null;
  wbs_short_name: string;
  wbs_name: string;
  seq_num: number | null;
  direct_activity_count: number;
  total_activity_count: number;
  // Computed by the route; nodes are returned in preorder.
  depth: number;
  path_ids: string[];
  outline_code: string;
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
  // "UPD-1", "UPD-2"… for status updates; "Baseline programme" (revision_no
  // null) for the frozen plan. Null on imports from before sync-log tracking.
  revision_no: number | null;
  revision_label: string | null;
  roundtrip_from_export_id: string | null;
  // The import that is the live schedule ("Current update"). Only an import that
  // still has its source .xer can be made current again.
  is_current: boolean;
  has_source_file: boolean;
}

export interface ScheduleExport {
  id: string;
  project_id: string;
  revision_no: number;
  revision_label: string;
  source_filename: string;
  data_date: string | null;
  // The programme (import) this file was built from. Null on exports made
  // before the programme picker, and on a project with no imports.
  source_import_id: string | null;
  activity_count: number;
  exported_by_user_id: string;
  exported_at: string;
}

export interface SyncLogEntry {
  kind: "export" | "import";
  id: string;
  label: string;
  at: string;
  user_id: string;
  user_name: string | null;
  activity_count: number;
  data_date: string | null;
  filename: string;
  // On an import the user linked back to a Poko export; on an export, the
  // programme (import) whose .xer it was built from.
  linked_export_label: string | null;
  source_import_label: string | null;
}

export interface ActivityUpdatePayload {
  percent_complete?: number;
  actual_start?: string | null;
  actual_finish?: string | null;
  remaining_duration_days?: number;
}

export type LinkType = "FS" | "SS" | "FF" | "SF";

/** One resource assignment (P6 TASKRSRC) of an activity — GET /activities/{id}/assignments.
 *  Budgeted / actual / remaining units all follow the activity's % for every resource type. */
export interface ActivityAssignment {
  id: string;
  rsrc_id: string;
  name: string;
  short_name: string | null;
  /** P6 RSRC.rsrc_type: RT_Labor | RT_Equip (nonlabor) | RT_Mat (material). */
  rsrc_type: string;
  unit_id: string | null;
  target_qty: number;
  act_reg_qty: number;
  remain_qty: number;
}

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

/** The latest schedule update — what the period KPI cards fall back to when
 *  no subcontractor update period is running (backend schemas/dashboard.py). */
export interface CurrentUpdate {
  revision_label: string | null;
  filename: string;
  data_date: string;
  imported_at: string;
  previous_label: string | null;
  previous_data_date: string | null;
  /** Typical gap between updates (median of the last three), days. */
  cadence_days: number | null;
  /** data_date + cadence_days — when the next update is expected. */
  next_data_date: string | null;
  activities_total: number;
  activities_complete: number;
  activities_in_progress: number;
  /** Actual starts/finishes since the previous update's data date; null on the first update. */
  started_this_update: number | null;
  finished_this_update: number | null;
  /** Against the locked baseline; null without one. */
  planned_pct: number | null;
  actual_pct: number | null;
  spi: number | null;
}

/** GET /projects/{id}/evm/progress-curve — duration-weighted % complete:
 *  planned (baseline, every point), actual (one point per schedule update),
 *  forecast (current schedule, from the data date on). */
export interface ProgressCurvePoint {
  date: string;
  planned: number | null;
  actual: number | null;
  forecast: number | null;
}

export interface ProgressCurve {
  project_id: string;
  baseline_id: string;
  version_label: string;
  data_date: string;
  points: ProgressCurvePoint[];
}

export interface DashboardSummary {
  active_period_id: string | null;
  active_period_label: string | null;
  active_period_status: UpdatePeriodStatus | null;
  deadline_at: string | null;
  orgs_total: number;
  orgs_submitted: number;
  flagged_pending: number;
  /** Pending change requests across every period. */
  open_change_requests: number;
  current_update: CurrentUpdate | null;
  scope_status: ScopeSubmissionStatus[];
}

// ---- configurable dashboard ----

export type DashboardWidgetKey =
  | "update-period"
  | "deadline"
  | "scopes-submitted"
  | "flagged"
  | "health-badge"
  | "s-curve"
  | "risk-top3"
  | "scope-table";

export type DashboardThemeKey = "calm" | "high-contrast" | "mono-amber";

export interface DashboardWidgetConfig {
  key: DashboardWidgetKey;
  order: number;
  enabled: boolean;
  options: Record<string, unknown>;
}

export interface DashboardLayout {
  project_id: string;
  user_id: string;
  theme_key: DashboardThemeKey;
  widgets: DashboardWidgetConfig[];
  is_default: boolean;
}

export interface DashboardLayoutUpdate {
  project_id: string;
  theme_key: DashboardThemeKey;
  widgets: DashboardWidgetConfig[];
}

export type HealthStatus = "good" | "warn" | "crit" | "unknown";

export type HealthFactorKey =
  | "scope_submissions"
  | "evm"
  | "critical_path"
  | "pending_reviews"
  | "overdue";

export interface HealthFactor {
  key: HealthFactorKey;
  label: string;
  status: HealthStatus;
  detail: string;
}

export interface ProjectHealth {
  score: number | null;
  grade: string;
  status: HealthStatus;
  factors: HealthFactor[];
}

export interface RiskHighlight {
  title: string;
  detail: string;
  severity: "low" | "medium" | "high";
  source: string;
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

export interface ActivityCodeType {
  id: string;
  actv_code_type_id: string;
  name: string;
}

export interface ActivityCodeValue {
  id: string;
  code_type_id: string;
  actv_code_id: string;
  name: string;
  short_name: string | null;
  parent_actv_code_id: string | null;
  seq_num: number | null;
}

export interface ActivityCodes {
  code_types: ActivityCodeType[];
  code_values: ActivityCodeValue[];
  // code_value_id -> activity ids carrying that code.
  assignments: Record<string, string[]>;
}

// --- Execution → Project / Program Status ---

export interface StatusTrendPoint {
  label: string;
  value: number;
}

export interface StatusCard {
  verdict: string;
  headline: string;
  metric: number | null;
  delta: number | null;
  series: StatusTrendPoint[];
}

export interface StatusSummary {
  progress: StatusCard;
  risk: StatusCard;
  quality: StatusCard;
}

export type PriorityQuadrantKey = "focus" | "watch" | "delegate" | "later";

export interface PriorityQuadrant {
  key: PriorityQuadrantKey;
  label: string;
  program_count: number;
  user_count: number;
  recommendation_count: number;
}

export interface PriorityActivity {
  activity_id: string;
  external_id: string;
  name: string;
  discipline: string;
  planned_start: string | null;
  planned_finish: string | null;
  total_float_days: number | null;
  percent_complete: number;
  is_critical: boolean;
  is_overdue: boolean;
  is_delay_driver: boolean;
}

export interface Priorities {
  quadrants: PriorityQuadrant[];
  activities: Record<PriorityQuadrantKey, PriorityActivity[]>;
  filtered_total: number;
}

export interface ProjectStatus {
  project_id: string;
  data_date: string | null;
  latest_revision_label: string | null;
  latest_filename: string | null;
  imported_at: string | null;
  has_snapshots: boolean;
  summary: StatusSummary;
  priorities: Priorities;
}

// --- Execution → Progress: saved filters + batch activity update ---

export interface SavedActivityFilter {
  id: string;
  project_id: string;
  user_id: string;
  view_key: string;
  name: string;
  criteria: Record<string, unknown>;
  is_shared: boolean;
  filter_version: number;
  is_owner: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavedFilterCreate {
  name: string;
  criteria: Record<string, unknown>;
  is_shared?: boolean;
  filter_version?: number;
}

export interface ActivityBatchItem {
  id: string;
  actual_start?: string | null;
  actual_finish?: string | null;
  percent_complete?: number | null;
}

export interface ActivityBatchResult {
  saved: Activity[];
  failed: { id: string; error: string }[];
}

// --- Execution → Recovery Plan ---

export type RecoveryPlanStatusValue = "draft" | "submitted" | "accepted" | "needs_revision";
export type RecoveryItemStatusValue = "open" | "in_progress" | "done" | "dropped";

export interface PlanLink {
  id: string;
  status: RecoveryPlanStatusValue;
  revision_no: number;
  item_count: number;
  submitted_at: string | null;
}

export interface SlipRow {
  external_id: string;
  p6_task_id: string | null;
  name: string | null;
  wbs_path: string | null;
  prev_finish: string | null;
  curr_finish: string | null;
  slip_days: number;
  is_critical: boolean;
  is_longest_path: boolean;
  status: string | null;
  percent_complete: number;
  activity_id: string | null;
  scope_id: string | null;
  scope_name: string | null;
  plan_required: boolean;
  needs_attention: boolean;
  plan: PlanLink | null;
}

export interface SlipImportRef {
  id: string;
  revision_label: string | null;
  data_date: string | null;
  imported_at: string;
}

export interface SlipReport {
  project_id: string;
  comparison_basis: "previous_upd" | "baseline_programme" | "none";
  from_import: SlipImportRef | null;
  to_import: SlipImportRef | null;
  threshold_days: number;
  coverage: { from_snapshot: boolean; to_snapshot: boolean };
  summary: {
    slipped_count: number;
    critical_slipped_count: number;
    worst_slip_days: number;
    total_added: number;
    total_removed: number;
    plans_required: number;
    plans_submitted: number;
    plans_accepted: number;
  };
  slipped: SlipRow[];
}

export interface RecoveryPlanItem {
  id: string;
  recovery_plan_id: string;
  order_index: number;
  action: string;
  owner_name: string | null;
  target_date: string | null;
  status: RecoveryItemStatusValue;
  completed_at: string | null;
}

// --- Risk register + mitigation plans ---

export type RiskStatusValue = "open" | "mitigating" | "closed" | "occurred";
export type MitigationStatusValue = "none" | "draft" | "submitted" | "accepted" | "needs_revision";
export type MitigationStrategyValue = "mitigate" | "avoid" | "transfer" | "accept";

export interface RiskActionItem {
  id: string;
  risk_item_id: string;
  order_index: number;
  action: string;
  owner_name: string | null;
  target_date: string | null;
  status: "open" | "in_progress" | "done" | "dropped";
  completed_at: string | null;
}

export interface RiskItem {
  id: string;
  project_id: string;
  code: string;
  title: string;
  description: string | null;
  cause: string | null;
  effect: string | null;
  category: string | null;
  probability: number;
  impact: number;
  score: number;
  status: RiskStatusValue;
  owner_name: string | null;
  wbs_path: string | null;
  activity_external_ids: string[];
  // QSRA quantification — see backend services/risk_analysis.py.
  qsra_enabled: boolean;
  risk_kind: "threat" | "opportunity";
  probability_pct: number | null; // null = derived from the 1–5 score
  impact_mode: "duration_pct" | "delay_days";
  impact_min: number | null;
  impact_ml: number | null;
  impact_max: number | null;
  impact_distribution: "triangular" | "pert" | "uniform";
  post_probability_pct: number | null;
  post_impact_min: number | null;
  post_impact_ml: number | null;
  post_impact_max: number | null;
  impact_in_schedule: boolean;
  apply_to_wbs: boolean;
  mitigation_strategy: MitigationStrategyValue | null;
  mitigation_status: MitigationStatusValue;
  mitigation_summary: string | null;
  revision_no: number;
  submitted_at: string | null;
  reviewed_at: string | null;
  reviewed_by_user_id: string | null;
  review_note: string | null;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
  action_item_count: number;
  created_by_name: string | null;
  items?: RiskActionItem[];
}

export interface RecoveryPlan {
  id: string;
  project_id: string;
  activity_external_id: string;
  activity_id: string | null;
  activity_name: string;
  wbs_path: string | null;
  project_scope_id: string | null;
  status: RecoveryPlanStatusValue;
  revision_no: number;
  summary: string | null;
  created_by_user_id: string;
  submitted_at: string | null;
  reviewed_at: string | null;
  reviewed_by_user_id: string | null;
  review_note: string | null;
  slip_days_at_creation: number | null;
  created_at: string;
  updated_at: string;
  author_name: string | null;
  scope_name: string | null;
  items?: RecoveryPlanItem[];
}

// --- Planning → Float Path: P6's multiple float paths ---

export type FloatPathMethod = "free_float" | "total_float";

export interface FloatPathActivity {
  external_id: string;
  name: string | null;
  wbs_path: string | null;
  status: string | null;
  percent_complete: number;
  early_start: string | null;
  early_finish: string | null;
  late_start: string | null;
  late_finish: string | null;
  total_float_days: number | null;
  free_float_days: number | null;
  is_critical: boolean;
  is_longest_path: boolean;
  /** The relationship driving this activity from the one above it on the path. */
  link_type: string | null;
  lag_days: number | null;
  link_gap_days: number | null;
}

export interface FloatPath {
  path_no: number;
  total_float_days: number | null;
  joins_at_external_id: string | null;
  join_link_type: string | null;
  join_lag_days: number | null;
  join_gap_days: number | null;
  activities: FloatPathActivity[];
}

export interface FloatPathEndCandidate {
  external_id: string;
  name: string;
  task_type: string | null;
  early_finish: string | null;
  total_float_days: number | null;
  is_critical: boolean;
}

export interface FloatPathReport {
  project_id: string;
  data_date: string | null;
  revision_label: string | null;
  end_activity_external_id: string;
  end_activity_name: string | null;
  method: FloatPathMethod;
  requested_paths: number;
  hours_per_day: number;
  truncated: boolean;
  acceleration_headroom_days: number | null;
  paths: FloatPath[];
}

// --- Reporting → Reports: saved report formats ---

export interface ReportBlockConfig {
  key: string;
  order: number;
  enabled: boolean;
  options: Record<string, unknown>;
}

export interface ReportBlockCatalogueEntry {
  key: string;
  title: string;
  description: string;
  requires: string | null;
  default_options: Record<string, unknown>;
}

export interface ReportFormat {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  blocks: ReportBlockConfig[];
  page_setup: { orientation?: string; paper?: string };
  is_preset: boolean;
  narrative: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportHeader {
  project_id: string;
  project_name: string;
  project_code: string | null;
  data_date: string | null;
  schedule_revision: string | null;
  schedule_filename: string | null;
  imported_at: string | null;
  baseline_label: string | null;
  baseline_changed_since: boolean;
  progress_basis: string;
  generated_at: string;
  generated_by: string | null;
}

// --- Risk: QSRA, early warnings, resources, recommendations ---
// Shapes mirror backend services/risk_analysis.py, risk_signals.py and
// risk_resources.py; dates are ISO strings.

export type QsraConfidence = "high" | "medium" | "low";

export interface QsraSettings {
  confidence: QsraConfidence;
  confidence_options: { value: QsraConfidence; label: string; range: [number, number, number] }[];
  iterations: number;
  seed: number;
  target_date: string | null;
  finish_activity_external_id: string | null;
  near_critical_days: number;
  correlate_by_wbs: boolean;
  baseline_finish?: string | null;
}

export interface QsraDistribution {
  p10: string;
  p50: string;
  p80: string;
  p90: string;
  p10_days: number;
  p50_days: number;
  p80_days: number;
  p90_days: number;
  min: string;
  max: string;
  mean: string;
  sd_days: number;
  prob_meet_cpm: number;
  prob_meet_target: number | null;
  contingency_p80_days: number;
  cdf: { date: string; pct: number }[];
  histogram: { date: string; count: number }[];
  bin: "day" | "week";
}

export interface QsraDriverRow {
  code: string;
  title: string;
  owner: string | null;
  kind: "threat" | "opportunity";
  mode: "duration_pct" | "delay_days";
  distribution: string;
  probability_pct: number;
  impact: [number, number, number];
  post_probability_pct: number;
  post_impact: [number, number, number];
  activity_count: number;
  status: string;
  mitigation_status: string;
  probability_derived: boolean;
  occurred_pct: number;
  delay_when_occurs_days: number;
  expected_delay_days: number;
  critical_hit_pct: number;
}

export interface QsraActivityRow {
  external_id: string;
  name: string;
  wbs_path: string | null;
  criticality_pct: number;
  ssi: number;
  cruciality: number;
  sd_days: number;
  total_float_days: number | null;
  p6_critical: boolean;
  hidden_driver: boolean;
}

export interface RiskRecommendation {
  id: string;
  severity: "red" | "amber" | "info";
  area: string;
  message: string;
  link: string;
}

export interface QsraResults {
  cpm_finish: string;
  target_date: string | null;
  target_source: "settings" | "baseline" | null;
  measured: { external_id: string; name: string } | null;
  pre: QsraDistribution;
  post: QsraDistribution | null;
  background: { p10: string; p50: string; p80: string; p90: string; p80_days: number };
  mitigation_benefit_p80_days: number | null;
  risk_exposure_p80_days: number;
  waterfall: { label: string; date: string; delta_days: number }[];
  drivers: QsraDriverRow[];
  activities: QsraActivityRow[];
  hidden_drivers: QsraActivityRow[];
  model_check: {
    calibration_finish: string;
    calibration_delta_days: number;
    calibration_ok: boolean;
    hard_constraints: string[];
    hard_constraint_count: number;
    open_end_count: number;
    open_ends: string[];
    summary_excluded: number;
    no_effect: { code: string; title: string; reason: string }[];
    warnings: string[];
    derived_probability: string[];
    network_size: number;
    uncertain_activities: number;
    groups: number;
    iterations_capped: boolean;
  };
  confidence: QsraConfidence;
  recommendations: RiskRecommendation[];
  ranking_meta?: { iterations: number; exposure_p80_days: number };
}

export interface QsraRunSummary {
  id: string;
  created_at: string | null;
  revision_label: string | null;
  data_date: string | null;
  cpm_finish: string | null;
  target_date: string | null;
  p10: string | null;
  p50: string | null;
  p80: string | null;
  p90: string | null;
  prob_meet_target: number | null;
  prob_meet_cpm: number | null;
  iterations: number;
}

export interface QsraRun extends QsraRunSummary {
  duration_ms: number;
  seed: number;
  settings: Record<string, unknown>;
  inputs: { risks?: unknown[] };
  results: QsraResults;
  ranking: { code: string; title: string; delta_p80_days: number; delta_p50_days: number; share_pct: number | null }[] | null;
}

export type SignalStatus = "good" | "amber" | "red" | "na";

export interface EarlyWarningIndicator {
  id: string;
  name: string;
  question: string;
  status: SignalStatus;
  value: string;
  detail: string;
  basis: string;
  series: { label: string; value: number | string | null }[];
  items: Record<string, string | number | boolean | null>[];
}

export interface EarlyWarnings {
  updates: { label: string; data_date: string }[];
  target_date: string | null;
  near_critical_days: number;
  indicators: EarlyWarningIndicator[];
}

export interface ResourceForecastSummary {
  budget: number;
  earned: number;
  actual: number;
  work_left: number;
  remaining_p6: number;
  demonstrated_rate: number | null;
  best_rate: number | null;
  planned_peak_rate: number | null;
  required_rate: number | null;
  rate_ratio: number | null;
  cumulative_productivity: number | null;
  finish_p10: string | null;
  finish_p50: string | null;
  finish_p90: string | null;
  capped: boolean;
  method: "demonstrated" | "insufficient" | "complete";
  notes: string[];
}

export interface ResourceAnalysis {
  data_date: string;
  target_date: string | null;
  types: { value: string; label: string }[];
  rsrc_type: string | null;
  resource_id: string | null;
  resources: { rsrc_id: string; name: string; type: string }[];
  unit: string | null;
  total: ResourceForecastSummary;
  weeks: { week: string; planned: number; earned: number; actual: number; remaining: number }[];
  periods: {
    label: string;
    start: string;
    end: string;
    weeks: number;
    earned: number;
    actual: number | null;
    rate: number;
    productivity: number | null;
  }[];
  per_resource: (ResourceForecastSummary & {
    rsrc_id: string;
    name: string;
    type: string;
    unit: string | null;
    last_productivity: (number | null)[];
  })[];
  snapshots_with_actuals: number;
  updates: number;
  qsra: { p10: string | null; p50: string | null; p90: string | null; cpm_finish: string | null; run_at: string | null } | null;
}

// ---------- My Desk (Execution → My Desk; backend routes/my_desk.py) ----------

export type DeskInboxKind =
  | "recovery_review"
  | "recovery_revision"
  | "flag_review"
  | "mitigation_review"
  | "mitigation_revision"
  | "update_period";

export interface DeskInboxItem {
  kind: DeskInboxKind;
  project_id: string;
  project_code: string;
  project_name: string;
  title: string;
  detail: string | null;
  count: number;
  due_at: string | null;
  tone: "crit" | "warn" | "info";
  href: string;
}

export interface DeskPin {
  id: string;
  project_id: string;
  project_code: string;
  project_name: string;
  activity_external_id: string;
  activity_name: string;
  pinned_at: string;
  pinned_finish: string | null;
  pinned_total_float_hours: number | null;
  pinned_hours_per_day: number | null;
  pinned_revision_label: string | null;
  /** The live activity; null once the current programme no longer carries it. */
  activity: Activity | null;
  finish: string | null;
  /** Shown finish now minus at pinning, calendar days (positive = later). */
  drift_days: number | null;
  previous_revision_label: string | null;
  previous_finish: string | null;
  previous_total_float_hours: number | null;
  note_count: number;
}

export interface DeskSuggestion {
  activity: Activity;
  reason: string;
}

export interface PersonalNoteContext {
  finish: string | null;
  total_float_hours: number | null;
  hours_per_day: number | null;
  revision_label: string | null;
}

export interface PersonalNote {
  id: string;
  project_id: string | null;
  project_code: string | null;
  activity_external_id: string | null;
  activity_name: string | null;
  body: string;
  remind_on: string | null;
  done_at: string | null;
  context: PersonalNoteContext | null;
  created_at: string;
  updated_at: string;
}

export interface ActivityDesk {
  pinned: boolean;
  notes: PersonalNote[];
}
