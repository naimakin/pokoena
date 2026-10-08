"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { PageState } from "@/components/PageShell";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import { selectStyle } from "@/components/ScurveChart";
import { AlertTriangleIcon, CompareIcon, DownloadIcon } from "@/components/icons";
import { FloatBadge, fmtDays, fmtP6Date } from "@/components/reporting/format";
import { FoldAllControls, FoldCard, FoldKey, FoldProvider } from "@/components/reporting/collapse";
import { NoProjectIllo } from "@/components/illustrations";
import { can } from "@/lib/permissions";
import { useCurrentUser } from "@/lib/user-context";
import type {
  FloatPath,
  FloatPathEndCandidate,
  FloatPathMethod,
  FloatPathReport,
} from "@/lib/types";

const PATH_COUNTS = [3, 5, 10];

// With ten paths of fifty activities each the page scrolls for ever, so only
// the first few open on a fresh calculation; the rest fold to their header
// line, which already carries the count and the float.
const OPEN_PATHS = 3;

const MILESTONE_TYPES = new Set(["TT_Mile", "TT_FinMile"]);

function linkLabel(type: string | null, lag: number | null): string {
  if (!type) return "—";
  if (!lag) return type;
  return `${type}${lag > 0 ? "+" : ""}${lag}d`;
}

function PathTable({ path }: { path: FloatPath }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Activity</th>
            <th>Driven by</th>
            <th>Early start</th>
            <th>Early finish</th>
            <th>Total float</th>
          </tr>
        </thead>
        <tbody>
          {path.activities.map((a) => (
            <tr key={a.external_id} className={a.is_critical ? "critical" : undefined}>
              <td>
                <div className="subname">{a.name}</div>
                <div className="actid">
                  {a.external_id}
                  {a.wbs_path ? ` · ${a.wbs_path}` : ""}
                </div>
              </td>
              <td>
                {a.link_type ? (
                  <span className={`fp-link${a.link_gap_days === 0 ? " fp-link-driving" : ""}`}>
                    {linkLabel(a.link_type, a.lag_days)}
                    {a.link_gap_days != null && ` · ${fmtDays(a.link_gap_days)} slack`}
                  </span>
                ) : (
                  <span className="fp-link">start of path</span>
                )}
              </td>
              <td className="num">{fmtP6Date(a.early_start)}</td>
              <td className="num">{fmtP6Date(a.early_finish)}</td>
              <td className="num">
                <FloatBadge days={a.total_float_days} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function FloatPathPage() {
  const { project } = useProjectContext();
  const user = useCurrentUser();

  const [candidates, setCandidates] = useState<FloatPathEndCandidate[]>([]);
  const [report, setReport] = useState<FloatPathReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [endActivity, setEndActivity] = useState("");
  const [method, setMethod] = useState<FloatPathMethod>("free_float");
  const [pathCount, setPathCount] = useState(5);
  const [excludeCompleted, setExcludeCompleted] = useState(true);
  const [selected, setSelected] = useState<number | null>(null);
  const [closedPaths, setClosedPaths] = useState<ReadonlySet<string>>(() => new Set());

  const setPathOpen = useCallback((key: string, open: boolean) => {
    setClosedPaths((prev) => {
      const next = new Set(prev);
      if (open) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!project) {
      setCandidates([]);
      setReport(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setReport(null);
    setError(null);
    api
      .get<FloatPathEndCandidate[]>(`/projects/${project.id}/float-path/end-candidates`)
      .then((rows) => {
        setCandidates(rows);
        // Default to the last milestone in the programme — the completion
        // milestone is what a float path is run against, not whichever
        // activity happens to sit last in the file.
        const milestones = rows.filter((r) => MILESTONE_TYPES.has(r.task_type ?? ""));
        const pick = milestones[milestones.length - 1] ?? rows[rows.length - 1];
        setEndActivity(pick?.external_id ?? "");
      })
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false));
  }, [project]);

  const run = useCallback(async () => {
    if (!project || !endActivity) return;
    setRunning(true);
    setError(null);
    const params = new URLSearchParams({
      end_activity: endActivity,
      method,
      path_count: String(pathCount),
      exclude_completed: String(excludeCompleted),
    });
    try {
      const result = await api.get<FloatPathReport>(`/projects/${project.id}/float-path?${params}`);
      setReport(result);
      setSelected(null);
      setClosedPaths(new Set(result.paths.filter((p) => p.path_no > OPEN_PATHS).map((p) => String(p.path_no))));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not calculate the float paths.");
      setReport(null);
    } finally {
      setRunning(false);
    }
  }, [project, endActivity, method, pathCount, excludeCompleted]);

  const options = useMemo(() => {
    const milestones = candidates.filter((c) => MILESTONE_TYPES.has(c.task_type ?? ""));
    const rest = candidates.filter((c) => !MILESTONE_TYPES.has(c.task_type ?? ""));
    return { milestones, rest };
  }, [candidates]);

  function exportCsv() {
    if (!report) return;
    const rows = [
      ["Path", "Activity ID", "Name", "WBS", "Driven by", "Lag (d)", "Link slack (d)", "Early start", "Early finish", "Total float (d)"],
      ...report.paths.flatMap((p) =>
        p.activities.map((a) => [
          String(p.path_no),
          a.external_id,
          a.name ?? "",
          a.wbs_path ?? "",
          a.link_type ?? "",
          a.lag_days ?? "",
          a.link_gap_days ?? "",
          a.early_start ?? "",
          a.early_finish ?? "",
          a.total_float_days ?? "",
        ]),
      ),
    ];
    const csv = rows
      .map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
      .join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${project?.code ?? "project"}-float-paths-${report.end_activity_external_id}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return <PageState kind="loading" section="Reports" title="Float Path" />;
  }
  if (!project) {
    return (
      <PageState
        kind="empty"
        section="Reports"
        title="Float Path"
        emptyTitle="No project selected"
        message="Create or pick a project from the project switcher in the top bar."
        art={<NoProjectIllo />}
      />
    );
  }

  const shown = report?.paths.filter((p) => selected === null || p.path_no === selected) ?? [];

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Reports
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Float Path</div>
            <div className="page-desc">
              The chains of driving logic into one activity, ranked. Path 1 is what is holding the date
              today; the paths behind it are what will hold it next.
            </div>
          </div>
          {report && can(user, "export") && (
            <button className="btn btn-secondary" onClick={exportCsv}>
              <DownloadIcon className="icon" /> Export CSV
            </button>
          )}
        </div>

        {candidates.length === 0 ? (
          <div className="card">
            <p className="empty-state">
              Import a schedule from Programme Files first — float paths are read off the current
              programme&rsquo;s logic and dates.
            </p>
          </div>
        ) : (
          <>
            <div
              className="card"
              style={{ padding: ".8rem 1.1rem", display: "flex", alignItems: "flex-end", gap: ".7rem", flexWrap: "wrap" }}
            >
              <label style={{ fontSize: ".6875rem", color: "var(--text-muted)", fontWeight: 500 }}>
                Calculate to
                <select
                  value={endActivity}
                  onChange={(e) => setEndActivity(e.target.value)}
                  style={{ ...selectStyle, display: "block", marginTop: ".2rem", maxWidth: 340 }}
                >
                  {options.milestones.length > 0 && (
                    <optgroup label="Milestones">
                      {options.milestones.map((c) => (
                        <option key={c.external_id} value={c.external_id}>
                          {c.external_id} — {c.name}
                        </option>
                      ))}
                    </optgroup>
                  )}
                  <optgroup label="All activities">
                    {options.rest.map((c) => (
                      <option key={c.external_id} value={c.external_id}>
                        {c.external_id} — {c.name}
                      </option>
                    ))}
                  </optgroup>
                </select>
              </label>

              <label style={{ fontSize: ".6875rem", color: "var(--text-muted)", fontWeight: 500 }}>
                Method
                <select
                  value={method}
                  onChange={(e) => setMethod(e.target.value as FloatPathMethod)}
                  style={{ ...selectStyle, display: "block", marginTop: ".2rem" }}
                >
                  <option value="free_float">Free float — driving chains</option>
                  <option value="total_float">Total float — float bands</option>
                </select>
              </label>

              <label style={{ fontSize: ".6875rem", color: "var(--text-muted)", fontWeight: 500 }}>
                Paths
                <select
                  value={pathCount}
                  onChange={(e) => setPathCount(Number(e.target.value))}
                  style={{ ...selectStyle, display: "block", marginTop: ".2rem" }}
                >
                  {PATH_COUNTS.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem", marginBottom: ".45rem" }}>
                <input
                  type="checkbox"
                  checked={excludeCompleted}
                  onChange={(e) => setExcludeCompleted(e.target.checked)}
                />
                Exclude completed
              </label>

              <button
                className="btn btn-primary"
                onClick={run}
                disabled={running || !endActivity}
                style={{ marginBottom: ".05rem" }}
              >
                <CompareIcon className="icon" /> {running ? "Calculating…" : "Calculate"}
              </button>
            </div>

            <p className="page-desc" style={{ marginTop: "-.35rem" }}>
              {method === "free_float"
                ? "Free float follows the tightest driving relationship back from the chosen activity, so every path is a connected chain of logic. This is P6's default and the one to argue a delay with."
                : "Total float groups the activities feeding the chosen one by their float value. These are bands, not chains — members of a band need not be linked to each other, and with mixed calendars the values are not directly comparable."}
            </p>

            {error && <p className="login-error">{error}</p>}

            {report && (
              <>
                {report.acceleration_headroom_days != null && (
                  <div className="banner">
                    <span className="banner-text">
                      <b>Acceleration headroom: {fmtDays(report.acceleration_headroom_days)}.</b> Pull path 1
                      in by more than that and path {report.paths[1]?.path_no} becomes the critical one —
                      accelerating past it buys nothing.
                    </span>
                  </div>
                )}

                {report.truncated && (
                  <div className="banner warn">
                    <AlertTriangleIcon className="icon" />
                    <span className="banner-text">
                      More chains feed this activity than the {report.requested_paths} asked for. Raise the
                      path count to see the rest.
                    </span>
                  </div>
                )}

                <div className="fp-summary">
                  {report.paths.map((p) => (
                    <button
                      key={p.path_no}
                      className="fp-card"
                      aria-pressed={selected === p.path_no}
                      onClick={() => {
                        // Picking a path shows it open, even if it was folded.
                        if (selected !== p.path_no) setPathOpen(String(p.path_no), true);
                        setSelected(selected === p.path_no ? null : p.path_no);
                      }}
                      style={{ borderLeftColor: `var(${floatVar(p.total_float_days)})` }}
                    >
                      <div className="fp-card-no">
                        {method === "free_float" ? `Path ${p.path_no}` : `Band ${p.path_no}`}
                      </div>
                      <div className="fp-card-float" style={{ color: `var(${floatVar(p.total_float_days)})` }}>
                        {fmtDays(p.total_float_days)}
                      </div>
                      <div className="fp-card-meta">
                        {p.activities.length} activities
                        {p.joins_at_external_id &&
                          ` · joins ${p.joins_at_external_id} via ${linkLabel(p.join_link_type, p.join_lag_days)}`}
                      </div>
                    </button>
                  ))}
                </div>

                {shown.length > 1 && (
                  <div className="fold-toolbar">
                    <span className="fold-toolbar-note">
                      {shown.length - shown.filter((p) => closedPaths.has(String(p.path_no))).length} of {shown.length}{" "}
                      {method === "free_float" ? "paths" : "bands"} open
                    </span>
                    <FoldAllControls
                      onExpand={() => setClosedPaths(new Set())}
                      onCollapse={() => setClosedPaths(new Set(shown.map((p) => String(p.path_no))))}
                      canExpand={shown.some((p) => closedPaths.has(String(p.path_no)))}
                      canCollapse={shown.some((p) => !closedPaths.has(String(p.path_no)))}
                    />
                  </div>
                )}

                <FoldProvider closed={closedPaths} onChange={setPathOpen}>
                  {shown.map((p) => (
                    <FoldKey key={p.path_no} id={String(p.path_no)}>
                      <FoldCard
                        title={`${method === "free_float" ? `Path ${p.path_no}` : `Band ${p.path_no}`} — ${p.activities.length} activities at ${fmtDays(p.total_float_days)}`}
                        subtitle={
                          p.joins_at_external_id
                            ? `Feeds ${p.joins_at_external_id} via ${linkLabel(p.join_link_type, p.join_lag_days)}`
                            : `Ends at ${report.end_activity_external_id} — ${report.end_activity_name ?? ""}`
                        }
                      >
                        <PathTable path={p} />
                      </FoldCard>
                    </FoldKey>
                  ))}
                </FoldProvider>
              </>
            )}

            {!report && !error && (
              <div className="card">
                <p className="empty-state">
                  Pick the activity to calculate to and press Calculate. Most of the time that is the
                  completion milestone, not the last activity in the file.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}

function floatVar(days: number | null): string {
  if (days == null) return "--text-muted";
  if (days <= 0) return "--float-zero";
  if (days <= 5) return "--float-low";
  if (days <= 15) return "--float-medium";
  if (days <= 30) return "--float-adequate";
  return "--float-high";
}
