"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { PageState } from "@/components/PageShell";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type {
  ActivityCodes,
  PriorityActivity,
  PriorityQuadrantKey,
  ProjectStatus,
  StatusCard,
  WbsNode,
} from "@/lib/types";
import { TrendLine } from "@/components/charts/TrendLine";
import { selectStyle } from "@/components/ScurveChart";
import { NoProjectIllo } from "@/components/illustrations";
import { BaselineVariancePanel } from "@/components/reporting/BaselineVariancePanel";

function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "2-digit", year: "numeric" });
}

type Tone = "good" | "warn" | "crit" | "muted";

const VERDICT_TONE: Record<string, Tone> = {
  "AHEAD": "good",
  "ON TRACK": "good",
  "BEHIND SCHEDULE": "crit",
  "NO DATA": "muted",
  "LOW": "good",
  "MEDIUM": "warn",
  "HIGH": "crit",
};

const TONE_VAR: Record<Tone, string> = {
  good: "var(--good)",
  warn: "var(--warn)",
  crit: "var(--crit)",
  muted: "var(--text-muted)",
};

// "LOW"/"MEDIUM"/"HIGH" mean opposite things for Quality vs Risk.
function toneFor(cardKey: "progress" | "risk" | "quality", verdict: string): Tone {
  if (cardKey === "quality") {
    if (verdict === "HIGH") return "good";
    if (verdict === "MEDIUM") return "warn";
    return "crit";
  }
  return VERDICT_TONE[verdict] ?? "muted";
}

const CARD_META: {
  key: "progress" | "risk" | "quality";
  title: string;
  color: string;
  format: (n: number) => string;
}[] = [
  { key: "progress", title: "Progress", color: "var(--dash-1)", format: (n) => n.toFixed(2) },
  { key: "risk", title: "Risk", color: "var(--dash-3)", format: (n) => `${n.toFixed(2)}×` },
  { key: "quality", title: "Quality", color: "var(--dash-2)", format: (n) => `${n.toFixed(0)}%` },
];

const QUADRANT_ORDER: PriorityQuadrantKey[] = ["focus", "watch", "delegate", "later"];

type PreviewChip = "all" | "overdue" | "delay" | "critical";

const PREVIEW_CHIPS: { key: PreviewChip; label: string; test: (a: PriorityActivity) => boolean }[] = [
  { key: "all", label: "All", test: () => true },
  { key: "overdue", label: "Overdue", test: (a) => a.is_overdue },
  { key: "delay", label: "Delay drivers", test: (a) => a.is_delay_driver },
  { key: "critical", label: "Critical path", test: (a) => a.is_critical },
];

export default function ProjectStatusPage() {
  const { project } = useProjectContext();

  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [wbsNodes, setWbsNodes] = useState<WbsNode[]>([]);
  const [codes, setCodes] = useState<ActivityCodes | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [wbsId, setWbsId] = useState("");
  const [codeIds, setCodeIds] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");

  const [focused, setFocused] = useState<PriorityQuadrantKey>("focus");
  const [chip, setChip] = useState<PreviewChip>("all");

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  // Filter metadata — loaded once per project.
  useEffect(() => {
    if (!project) return;
    setWbsId("");
    setCodeIds([]);
    setQ("");
    api.get<WbsNode[]>(`/projects/${project.id}/wbs-nodes`).then(setWbsNodes).catch(() => setWbsNodes([]));
    api.get<ActivityCodes>(`/projects/${project.id}/activity-codes`).then(setCodes).catch(() => setCodes(null));
  }, [project]);

  const load = useCallback(async () => {
    if (!project) {
      setStatus(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (wbsId) params.set("wbs_id", wbsId);
    for (const id of codeIds) params.append("code_value_id", id);
    if (qDebounced) params.set("q", qDebounced);
    const qs = params.toString();
    try {
      const res = await api.get<ProjectStatus>(`/projects/${project.id}/status${qs ? `?${qs}` : ""}`);
      setStatus(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load project status.");
    } finally {
      setLoading(false);
    }
  }, [project, wbsId, codeIds, qDebounced]);

  useEffect(() => {
    load();
  }, [load]);

  const wbsOptions = useMemo(() => {
    const byParent = new Map<string, WbsNode[]>();
    for (const n of wbsNodes) {
      const key = n.parent_wbs_id ?? "";
      byParent.set(key, [...(byParent.get(key) ?? []), n]);
    }
    const out: { id: string; label: string }[] = [];
    const walk = (parent: string, depth: number) => {
      for (const n of (byParent.get(parent) ?? []).sort((a, b) => (a.seq_num ?? 0) - (b.seq_num ?? 0))) {
        out.push({ id: n.wbs_id, label: `${"  ".repeat(depth)}${n.wbs_name}` });
        walk(n.wbs_id, depth + 1);
      }
    };
    // Roots = nodes whose parent isn't itself in the set.
    const ids = new Set(wbsNodes.map((n) => n.wbs_id));
    const rootParentKeys = new Set(
      wbsNodes.filter((n) => !n.parent_wbs_id || !ids.has(n.parent_wbs_id)).map((n) => n.parent_wbs_id ?? ""),
    );
    for (const key of rootParentKeys) walk(key, 0);
    // Fallback: if the walk above missed (odd parent tokens), just list flat.
    return out.length ? out : wbsNodes.map((n) => ({ id: n.wbs_id, label: n.wbs_name }));
  }, [wbsNodes]);

  const hasFilters = Boolean(wbsId || codeIds.length || q);

  if (loading && !status) {
    return <PageState kind="loading" section="Reports" title="Project Status" />;
  }
  if (error) {
    return <PageState kind="error" section="Reports" title="Project Status" message={error} />;
  }
  if (!project || !status) {
    return (
      <PageState
        kind="empty"
        section="Reports"
        title="Project Status"
        emptyTitle="No project selected"
        message="Create or pick a project from the project switcher in the top bar."
        art={<NoProjectIllo />}
      />
    );
  }

  const noSchedule = !status.latest_filename;

  const focusedQuadrant = status.priorities.quadrants.find((x) => x.key === focused);
  const previewRows = (status.priorities.activities[focused] ?? []).filter(
    (a) => PREVIEW_CHIPS.find((c) => c.key === chip)!.test(a),
  );

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Reports
        </span>
        <div className="spacer" />
        {status.latest_revision_label && (
          <span className="chip chip-neutral mono">{status.latest_revision_label}</span>
        )}
      </div>

      <div className="a-content" data-dash-theme="calm">
        <div className="page-head">
          <div>
            <div className="page-title">Project Status</div>
            <div className="page-desc">
              {noSchedule
                ? "No schedule imported yet — upload a .xer from Programs."
                : `${status.latest_filename} · data date ${fmtDate(status.data_date)}`}
            </div>
          </div>
        </div>

        {/* --- Filter bar --- */}
        <div className="card" style={{ padding: "0.9rem 1.1rem" }}>
          <div className="filter-bar">
            <label style={{ fontSize: ".6875rem", color: "var(--text-muted)", fontWeight: 500 }}>
              Activity
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search name or ID…"
                style={{ ...selectStyle, marginLeft: ".5rem", width: 200, textTransform: "none", fontWeight: 400 }}
              />
            </label>

            {codes && codes.code_types.length > 0 && (
              <details style={{ position: "relative" }}>
                <summary
                  style={{
                    ...selectStyle,
                    listStyle: "none",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: ".4rem",
                  }}
                >
                  Activity Codes{codeIds.length ? ` (${codeIds.length})` : ""}
                </summary>
                <div
                  className="card"
                  style={{
                    position: "absolute",
                    zIndex: 20,
                    marginTop: ".35rem",
                    padding: ".6rem .8rem",
                    maxHeight: 280,
                    overflowY: "auto",
                    minWidth: 240,
                  }}
                >
                  {codes.code_types.map((t) => (
                    <div key={t.id} style={{ marginBottom: ".5rem" }}>
                      <div style={{ fontSize: ".6875rem", color: "var(--text-muted)", fontWeight: 500, marginBottom: ".25rem" }}>
                        {t.name}
                      </div>
                      {codes.code_values
                        .filter((v) => v.code_type_id === t.id)
                        .map((v) => (
                          <label key={v.id} style={{ display: "flex", alignItems: "center", gap: ".4rem", fontSize: ".8125rem", padding: ".15rem 0" }}>
                            <input
                              type="checkbox"
                              checked={codeIds.includes(v.id)}
                              onChange={(e) =>
                                setCodeIds((prev) =>
                                  e.target.checked ? [...prev, v.id] : prev.filter((x) => x !== v.id),
                                )
                              }
                            />
                            {v.short_name ? `${v.short_name} — ` : ""}
                            {v.name}
                          </label>
                        ))}
                    </div>
                  ))}
                </div>
              </details>
            )}

            {wbsOptions.length > 0 && (
              <select value={wbsId} onChange={(e) => setWbsId(e.target.value)} style={selectStyle}>
                <option value="">All WBS</option>
                {wbsOptions.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}

            {hasFilters && (
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setWbsId("");
                  setCodeIds([]);
                  setQ("");
                }}
              >
                Clear Filters
              </button>
            )}
          </div>
        </div>

        {/* --- Project Summary --- */}
        <div className="card-head" style={{ border: "none", padding: 0 }}>
          <div className="card-title" style={{ fontFamily: "var(--font-display)", fontSize: "1rem", letterSpacing: "-.01em" }}>
            Project summary
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.25rem" }}>
          {CARD_META.map((meta) => {
            const card: StatusCard = status.summary[meta.key];
            const tone = toneFor(meta.key, card.verdict);
            return (
              <div key={meta.key} className="card" style={{ padding: "1.1rem 1.15rem" }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                  <span style={{ fontSize: ".75rem", color: "var(--text-muted)", fontWeight: 500 }}>
                    {meta.title}
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-display)",
                      fontWeight: 700,
                      fontSize: "1rem",
                      letterSpacing: "-.01em",
                      color: TONE_VAR[tone],
                    }}
                  >
                    {card.verdict}
                  </span>
                </div>
                <div style={{ margin: ".5rem 0 .1rem", display: "flex", alignItems: "baseline", gap: ".5rem" }}>
                  <span className="num" style={{ fontSize: "1.5rem", fontWeight: 700 }}>
                    {card.metric === null ? "—" : meta.format(card.metric)}
                  </span>
                  {card.delta !== null && (
                    <span className="mono" style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                      {card.delta >= 0 ? "▲" : "▼"} {Math.abs(card.delta).toFixed(2)}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: ".75rem", color: "var(--text-secondary)", marginBottom: ".5rem" }}>
                  {card.headline}
                </div>
                <TrendLine points={card.series} color={meta.color} format={meta.format} />
              </div>
            );
          })}
        </div>

        {/* --- Priorities Matrix --- */}
        <div className="card-head" style={{ border: "none", padding: 0 }}>
          <div className="card-title" style={{ fontFamily: "var(--font-display)", fontSize: "1rem", letterSpacing: "-.01em" }}>
            Priorities matrix
          </div>
          <div className="card-title-sub">
            {status.priorities.filtered_total} activities · Important × Urgent
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1fr)", gap: "1.25rem", alignItems: "start" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".9rem" }}>
            {QUADRANT_ORDER.map((key) => {
              const qd = status.priorities.quadrants.find((x) => x.key === key)!;
              const active = key === focused;
              return (
                <button
                  key={key}
                  onClick={() => {
                    setFocused(key);
                    setChip("all");
                  }}
                  className="card"
                  style={{
                    textAlign: "left",
                    padding: "0.9rem 1rem",
                    cursor: "pointer",
                    boxShadow: active ? "inset 3px 0 0 var(--accent)" : undefined,
                    background: active ? "var(--accent-soft)" : "var(--surface)",
                  }}
                >
                  <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, letterSpacing: "-.01em", marginBottom: ".5rem" }}>
                    {qd.label}
                  </div>
                  {(
                    [
                      ["Program activities", qd.program_count],
                      ["User activities", qd.user_count],
                      ["Recommendations", qd.recommendation_count],
                    ] as [string, number][]
                  ).map(([label, count]) => (
                    <div key={label} style={{ display: "flex", justifyContent: "space-between", fontSize: ".8125rem", padding: ".15rem 0" }}>
                      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
                      <span className="num" style={{ fontWeight: 700 }}>{count}</span>
                    </div>
                  ))}
                </button>
              );
            })}
          </div>

          {/* Preview panel */}
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">
                  {focusedQuadrant?.label} · {(focusedQuadrant?.program_count ?? 0) + (focusedQuadrant?.user_count ?? 0)} activities
                </div>
                <div className="card-title-sub">
                  <Link href="/progress" style={{ color: "var(--accent-strong)", fontWeight: 500 }}>
                    View in Activity Ledger →
                  </Link>
                </div>
              </div>
            </div>
            <div style={{ padding: ".7rem 1rem", display: "flex", gap: ".4rem", flexWrap: "wrap" }}>
              {PREVIEW_CHIPS.map((c) => (
                <button
                  key={c.key}
                  onClick={() => setChip(c.key)}
                  className={`chip ${chip === c.key ? "chip-good" : "chip-neutral"}`}
                  style={{ cursor: "pointer", border: "none" }}
                >
                  {c.label}
                </button>
              ))}
            </div>
            <div style={{ maxHeight: 460, overflowY: "auto" }}>
              {previewRows.length === 0 ? (
                <p className="empty-state">No activities in this view.</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Activity</th>
                      <th>Finish</th>
                      <th style={{ textAlign: "right" }}>TF (d)</th>
                      <th style={{ textAlign: "right" }}>%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((a) => (
                      <tr key={a.activity_id} className={a.is_critical ? "critical" : undefined}>
                        <td>
                          <div style={{ fontWeight: 500 }}>{a.name}</div>
                          <div className="mono" style={{ fontSize: ".6875rem", color: "var(--text-muted)" }}>
                            {a.external_id} · {a.discipline}
                          </div>
                        </td>
                        <td className="mono" style={{ color: a.is_overdue ? "var(--crit)" : undefined }}>
                          {fmtDate(a.planned_finish)}
                        </td>
                        <td className="num" style={{ textAlign: "right" }}>
                          {a.total_float_days === null ? "—" : a.total_float_days}
                        </td>
                        <td className="num" style={{ textAlign: "right" }}>{a.percent_complete}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>

        <BaselineVariancePanel projectId={project.id} />
      </div>
    </>
  );
}
