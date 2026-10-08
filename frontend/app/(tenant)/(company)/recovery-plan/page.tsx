"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { PageState } from "@/components/PageShell";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { RecoveryPlan, ScheduleImport, SlipReport, SlipRow, User, WbsNode } from "@/lib/types";
import { FoldAllControls, FoldCard, FoldKey, FoldProvider } from "@/components/reporting/collapse";
import { fmtP6Date } from "@/components/reporting/format";
import { AlertTriangleIcon, ArrowRightIcon, ChevronDownIcon, ChevronRightIcon, DownloadIcon } from "@/components/icons";
import { selectStyle } from "@/components/ScurveChart";
import { RecoveryPlanPanel } from "@/components/recovery/RecoveryPlanPanel";
import { can } from "@/lib/permissions";
import { NoProjectIllo } from "@/components/illustrations";

type Grouping = "contractor" | "wbs" | "flat";
const GROUP_KEY = "poko:recovery:grouping";
const BASELINE = "baseline";

const PLAN_CHIP: Record<string, string> = {
  none: "chip-neutral",
  draft: "chip-info",
  submitted: "chip-warn",
  accepted: "chip-good",
  needs_revision: "chip-crit",
};
const PLAN_LABEL: Record<string, string> = {
  none: "No plan",
  draft: "Draft",
  submitted: "Submitted",
  accepted: "Acknowledged",
  needs_revision: "Needs revision",
};

/** The From / To choice, as it sits in the URL (?from=<id>|baseline&to=<id>).
 *  Empty = the default comparison (latest update against the one before). */
interface Choice {
  from: string;
  to: string;
}

function readUrl(): Choice & { activity: string } {
  const q = new URLSearchParams(window.location.search);
  return { from: q.get("from") ?? "", to: q.get("to") ?? "", activity: q.get("activity") ?? "" };
}

function reportQuery(choice: Choice): string {
  const q = new URLSearchParams();
  if (choice.from === BASELINE) q.set("from_baseline", "true");
  else if (choice.from) q.set("from_import_id", choice.from);
  if (choice.to) q.set("to_import_id", choice.to);
  const s = q.toString();
  return s ? `?${s}` : "";
}

function statusText(status: string | null): string {
  const t = (status ?? "").replace(/_/g, " ");
  return t ? t[0].toUpperCase() + t.slice(1) : "—";
}

function importLabel(i: { revision_label: string | null; data_date: string | null; imported_at: string } | null | undefined): string {
  if (!i) return "—";
  return `${i.revision_label ?? "Program"} (${fmtP6Date(i.data_date ?? i.imported_at)})`;
}

export default function RecoveryPlanPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();
  const router = useRouter();

  const [report, setReport] = useState<SlipReport | null>(null);
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  const [grouping, setGrouping] = useState<Grouping>("contractor");
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [minSlip, setMinSlip] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [plans, setPlans] = useState<Record<string, RecoveryPlan>>({});
  const [wbsNames, setWbsNames] = useState<Map<string, string>>(new Map());
  // Groups folded shut; every group starts open.
  const [closed, setClosed] = useState<Set<string>>(new Set());
  // ?activity=… (a My Desk mention): open that row once the report is in.
  const focusActivity = useRef<string>("");

  useEffect(() => {
    try {
      const g = localStorage.getItem(GROUP_KEY);
      if (g === "contractor" || g === "wbs" || g === "flat") setGrouping(g);
    } catch {
      /* ignore */
    }
    api.get<User>("/auth/me").then(setMe).catch(() => setMe(null));
    const url = readUrl();
    focusActivity.current = url.activity;
    setChoice({ from: url.from, to: url.to });
  }, []);

  useEffect(() => {
    if (!project) return;
    api
      .get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`)
      .then(setImports)
      .catch(() => setImports([]));
  }, [project]);

  const load = useCallback(async () => {
    if (!project || choice === null) {
      if (!project) {
        setReport(null);
        setLoading(false);
      }
      return;
    }
    setComparing(true);
    setError(null);
    setCompareError(null);
    try {
      setReport(await api.get<SlipReport>(`/projects/${project.id}/recovery-plan${reportQuery(choice)}`));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load the recovery plan.";
      // A bad From / To (a stale link, two equal programs) is a choice to fix,
      // not a broken page.
      if (choice.from || choice.to) {
        setCompareError(message);
        setReport(null);
      } else setError(message);
    } finally {
      setLoading(false);
      setComparing(false);
    }
  }, [project, choice]);

  useEffect(() => {
    load();
  }, [load]);

  // A row's wbs_path is the P6 wbs_id; the name comes from the WBS tree.
  useEffect(() => {
    if (!project) return;
    api
      .get<WbsNode[]>(`/projects/${project.id}/wbs-nodes`)
      .then((nodes) => setWbsNames(new Map(nodes.map((n) => [n.wbs_id, n.wbs_name]))))
      .catch(() => setWbsNames(new Map()));
  }, [project]);

  function pick(side: "from" | "to", value: string) {
    if (!choice) return;
    applyChoice({ ...choice, [side]: value });
  }

  function applyChoice(next: Choice) {
    setChoice(next);
    const url = new URL(window.location.href);
    for (const [key, v] of [["from", next.from], ["to", next.to]] as const) {
      if (v) url.searchParams.set(key, v);
      else url.searchParams.delete(key);
    }
    url.searchParams.delete("activity");
    // A history entry per comparison, so Back returns to the previous one.
    router.push(`${url.pathname}${url.search}`, { scroll: false });
  }

  // Back / Forward between comparisons.
  useEffect(() => {
    function onPop() {
      const url = readUrl();
      setChoice((prev) => (prev && prev.from === url.from && prev.to === url.to ? prev : { from: url.from, to: url.to }));
    }
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Acknowledging a plan: anyone who manages progress, but not on a plan they
  // wrote themselves (backend: recovery_plans.review_plan).
  const managesProgress = can(me, "edit_progress");

  const loadPlan = useCallback(
    async (id: string) => {
      if (!project) return;
      try {
        const p = await api.get<RecoveryPlan>(`/projects/${project.id}/recovery-plan/plans/${id}`);
        setPlans((prev) => ({ ...prev, [id]: p }));
      } catch {
        /* ignore */
      }
    },
    [project],
  );

  function toggle(row: SlipRow) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(row.external_id)) next.delete(row.external_id);
      else {
        next.add(row.external_id);
        if (row.plan) loadPlan(row.plan.id);
      }
      return next;
    });
  }

  // Open the row a link points at (?activity=…).
  useEffect(() => {
    const code = focusActivity.current;
    if (!report || !code) return;
    focusActivity.current = "";
    const row = report.slipped.find((r) => r.external_id === code);
    if (!row) {
      showToast(`${code} hasn't slipped in this comparison.`, "error");
      return;
    }
    setExpanded((prev) => new Set(prev).add(code));
    if (row.plan) loadPlan(row.plan.id);
    window.setTimeout(() => document.getElementById(`rp-row-${code}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
  }, [report, loadPlan, showToast]);

  async function startPlan(row: SlipRow) {
    if (!project || !choice) return;
    try {
      // Raised against the comparison on screen.
      const p = await api.post<RecoveryPlan>(`/projects/${project.id}/recovery-plan/plans`, {
        activity_external_id: row.external_id,
        from_import_id: choice.from && choice.from !== BASELINE ? choice.from : null,
        to_import_id: choice.to || null,
        from_baseline: choice.from === BASELINE,
      });
      setPlans((prev) => ({ ...prev, [p.id]: p }));
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not start the plan.", "error");
    }
  }

  const rows = useMemo(() => {
    let r = report?.slipped ?? [];
    if (criticalOnly) r = r.filter((x) => x.is_critical || x.is_longest_path);
    if (minSlip > 0) r = r.filter((x) => x.slip_days >= minSlip);
    return r;
  }, [report, criticalOnly, minSlip]);

  const groups = useMemo(() => {
    if (grouping === "flat") return [{ key: "all", label: `${rows.length} activities`, rows }];
    const map = new Map<string, SlipRow[]>();
    for (const row of rows) {
      const key =
        grouping === "contractor"
          ? row.scope_name ?? "Self-perform / unassigned"
          : row.wbs_path ?? "No WBS";
      map.set(key, [...(map.get(key) ?? []), row]);
    }
    return [...map.entries()].map(([key, rs]) => {
      const name = grouping === "wbs" ? wbsNames.get(key) : undefined;
      return { key, label: name ? `${key} · ${name}` : key, rows: rs };
    });
  }, [grouping, rows, wbsNames]);

  const setGroupOpen = useCallback((key: string, open: boolean) => {
    setClosed((prev) => {
      const next = new Set(prev);
      if (open) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const currentImportId = useMemo(() => (imports.find((i) => i.is_current) ?? imports[0])?.id ?? null, [imports]);

  if (loading) {
    return <PageState kind="loading" section="Programme" title="Recovery Plan" />;
  }
  if (error) {
    return <PageState kind="error" section="Programme" title="Recovery Plan" message={error} />;
  }
  if (!project) {
    return (
      <PageState
        kind="empty"
        section="Programme"
        title="Recovery Plan"
        emptyTitle="No project selected"
        message="Create or pick a project from the project switcher in the top bar."
        art={<NoProjectIllo />}
      />
    );
  }

  const summary = report?.summary;
  const chosen = Boolean(choice && (choice.from || choice.to));
  const fromValue = choice?.from || report?.from_import?.id || "";
  const toValue = choice?.to || report?.to_import?.id || "";
  const fromText = report?.from_baseline
    ? `the baseline ${report.baseline?.label ?? ""} (${fmtP6Date(report.from_import?.data_date ?? report.from_import?.imported_at)})`
    : importLabel(report?.from_import);
  const noSnapshot = report && report.from_import && report.to_import && !(report.coverage.from_snapshot && report.coverage.to_snapshot);

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">Programme</span>
      </div>
      <div className="a-content recovery-print rp-page">
        <div className="page-head">
          <div>
            <div className="page-title">Recovery Plan</div>
            <div className="page-desc">
              {!report || report.comparison_basis === "none"
                ? "Slippage tracking starts once two schedule updates carry an activity snapshot."
                : `Slippage between ${fromText} and ${importLabel(report.to_import)}`}
              {report && report.comparison_basis !== "none" ? "." : ""} A plan is needed for a slip of 5 days or more,
              or any slip on the critical path; once it&rsquo;s submitted, someone else on the team acknowledges it.
            </div>
          </div>
          <button className="btn btn-secondary no-print" onClick={() => window.print()}>
            <DownloadIcon className="icon" /> Print
          </button>
        </div>

        {imports.length >= 2 && choice && (
          <div className="card no-print chg-compare rp-compare" role="group" aria-label="Compare">
            <span className="rp-compare-title">Compare</span>
            <label className="chg-field">
              <span>From</span>
              <select value={fromValue} onChange={(e) => pick("from", e.target.value)} style={{ ...selectStyle, minWidth: 240 }}>
                {!fromValue && <option value="">Previous update</option>}
                {report?.baseline && (
                  <option value={BASELINE}>
                    Baseline · {report.baseline.label}
                    {report.baseline.data_date ? ` (${fmtP6Date(report.baseline.data_date)})` : ""}
                  </option>
                )}
                {imports.map((imp) => (
                  <option key={imp.id} value={imp.id}>
                    {imp.revision_label ?? imp.filename}
                    {imp.data_date ? ` (${fmtP6Date(imp.data_date)})` : ""}
                    {imp.id === currentImportId ? " — Current update" : ""}
                  </option>
                ))}
              </select>
            </label>
            <ArrowRightIcon className="icon chg-compare-arrow" />
            <label className="chg-field">
              <span>To</span>
              <select value={toValue} onChange={(e) => pick("to", e.target.value)} style={{ ...selectStyle, minWidth: 240 }}>
                {!toValue && <option value="">Latest update</option>}
                {imports.map((imp) => (
                  <option key={imp.id} value={imp.id}>
                    {imp.revision_label ?? imp.filename}
                    {imp.data_date ? ` (${fmtP6Date(imp.data_date)})` : ""}
                    {imp.id === currentImportId ? " — Current update" : ""}
                  </option>
                ))}
              </select>
            </label>
            {chosen && !report?.is_default && (
              <button type="button" className="btn btn-ghost btn-sm rp-compare-reset" onClick={() => applyChoice({ from: "", to: "" })}>
                Latest two updates
              </button>
            )}
            <span className="chg-compare-status" aria-live="polite">
              {comparing ? "Comparing…" : compareError ?? null}
            </span>
          </div>
        )}

        {!report ? (
          <div className="card">
            <p className="empty-state">{compareError ?? "Nothing to compare."}</p>
          </div>
        ) : report.comparison_basis === "none" || noSnapshot ? (
          <div className="card">
            <p className="empty-state">
              {noSnapshot
                ? "One of these programs has no activity snapshot, so slippage can't be measured. Pick another pair."
                : "Upload at least two schedule updates (UPD-1, UPD-2…) from Programs. The recovery plan compares the two most recent."}
            </p>
          </div>
        ) : report.slipped.length === 0 ? (
          <div className="card">
            <p className="empty-state">
              No activities slipped between {report.from_baseline ? "the baseline" : report.from_import?.revision_label} and{" "}
              {report.to_import?.revision_label}.
            </p>
          </div>
        ) : (
          <>
            <div className="card rp-summary">
              <b className="num rp-summary-count">
                {summary!.plans_submitted} of {summary!.plans_required} plans submitted
              </b>
              <span className="chip chip-good">{summary!.plans_accepted} acknowledged</span>
              {summary!.critical_slipped_count > 0 && (
                <span className="chip chip-crit">
                  <AlertTriangleIcon className="icon" />
                  {summary!.critical_slipped_count} critical
                </span>
              )}
              <span className="spacer" />
              <div className="segmented no-print">
                {(["contractor", "wbs", "flat"] as Grouping[]).map((g) => (
                  <button
                    key={g}
                    className={grouping === g ? "active" : ""}
                    onClick={() => {
                      setGrouping(g);
                      try {
                        localStorage.setItem(GROUP_KEY, g);
                      } catch {
                        /* ignore */
                      }
                    }}
                  >
                    {g === "contractor" ? "By contractor" : g === "wbs" ? "By WBS" : "Flat"}
                  </button>
                ))}
              </div>
              <label className="no-print rp-filter">
                <input type="checkbox" checked={criticalOnly} onChange={(e) => setCriticalOnly(e.target.checked)} />
                Critical only
              </label>
              <label className="no-print rp-filter">
                Slip ≥
                <input
                  type="number"
                  min={0}
                  value={minSlip}
                  onChange={(e) => setMinSlip(Math.max(0, Number(e.target.value) || 0))}
                  style={{ width: 56 }}
                />
                d
              </label>
              <FoldAllControls
                onExpand={() => setClosed(new Set())}
                onCollapse={() => setClosed(new Set(groups.map((g) => g.key)))}
                canExpand={closed.size > 0}
                canCollapse={groups.some((g) => !closed.has(g.key))}
              />
            </div>

            {rows.length === 0 ? (
              <div className="card">
                <p className="empty-state">No slipped activity matches these filters.</p>
              </div>
            ) : (
              <FoldProvider closed={closed} onChange={setGroupOpen}>
                {groups.map((group) => (
                  <FoldKey key={group.key} id={group.key}>
                    <FoldCard title={group.label} meta={`${group.rows.length} slipped`}>
                      <div className="table-wrap">
                        <table className="rp-table">
                          <thead>
                            <tr>
                              <th>Activity</th>
                              <th>Finish (prev → curr)</th>
                              <th style={{ textAlign: "right" }}>Slip</th>
                              <th>Plan</th>
                              <th aria-label="Open" />
                            </tr>
                          </thead>
                          <tbody>
                            {group.rows.map((row) => {
                              const open = expanded.has(row.external_id);
                              const plan = row.plan ? plans[row.plan.id] : null;
                              const planStatus = row.plan?.status ?? "none";
                              const canStart = !row.scope_id && managesProgress; // company self-perform
                              return (
                                <Fragment key={row.external_id}>
                                  <tr
                                    id={`rp-row-${row.external_id}`}
                                    className={`rp-row${row.is_critical ? " critical" : ""}${open ? " is-open" : ""}`}
                                    onClick={() => toggle(row)}
                                    tabIndex={0}
                                    aria-expanded={open}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter" || e.key === " ") {
                                        e.preventDefault();
                                        toggle(row);
                                      }
                                    }}
                                  >
                                    <td>
                                      <div className="subname">{row.name}</div>
                                      <div className="actid">{row.external_id}</div>
                                    </td>
                                    <td className="mono">
                                      {fmtP6Date(row.prev_finish)} → {fmtP6Date(row.curr_finish)}
                                    </td>
                                    <td className="num rp-slip">+{row.slip_days}d</td>
                                    <td>
                                      <span className="rp-chips">
                                        <span className={`chip ${PLAN_CHIP[planStatus]}`}>{PLAN_LABEL[planStatus]}</span>
                                        {(row.is_critical || row.is_longest_path) && <span className="chip chip-crit">Critical</span>}
                                        {row.needs_attention && <span className="chip chip-warn">Needs action</span>}
                                      </span>
                                    </td>
                                    <td className="rp-caret" aria-hidden="true">
                                      {open ? <ChevronDownIcon className="icon" /> : <ChevronRightIcon className="icon" />}
                                    </td>
                                  </tr>
                                  {open && (
                                    <tr className="rp-detail">
                                      <td colSpan={5}>
                                        {plan ? (
                                          <RecoveryPlanPanel
                                            projectId={project.id}
                                            plan={plan}
                                            context={
                                              <>
                                                <span>{statusText(row.status)} · {row.percent_complete}%</span>
                                                <span>WBS {row.wbs_path ? wbsNames.get(row.wbs_path) ?? row.wbs_path : "—"}</span>
                                              </>
                                            }
                                            canTrack={managesProgress}
                                            canAcknowledge={managesProgress}
                                            adminReview={me?.role === "company_admin"}
                                            meId={me?.id ?? null}
                                            onChanged={async (statusMoved) => {
                                              await loadPlan(plan.id);
                                              if (statusMoved) await load();
                                            }}
                                          />
                                        ) : row.plan ? (
                                          <p className="rp-empty rp-loading">Loading the plan…</p>
                                        ) : (
                                          <div className="rp-noplan">
                                            <p>
                                              {canStart
                                                ? "No recovery plan yet. Start one to record the root cause and the actions that win the time back."
                                                : row.scope_id
                                                  ? `Awaiting a recovery plan from ${row.scope_name}.`
                                                  : "No recovery plan yet."}
                                            </p>
                                            {canStart && (
                                              <button className="btn btn-primary btn-sm no-print" onClick={() => startPlan(row)}>
                                                Start plan
                                              </button>
                                            )}
                                          </div>
                                        )}
                                      </td>
                                    </tr>
                                  )}
                                </Fragment>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </FoldCard>
                  </FoldKey>
                ))}
              </FoldProvider>
            )}
          </>
        )}
      </div>
    </>
  );
}
