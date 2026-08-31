"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, ScheduleImport } from "@/lib/types";

// Ported from the reference app's GanttView.jsx: hand-rolled CSS-positioned
// bars (no charting library), sticky month axis, 3 zoom levels, a data-date
// line. Renders the full activity list directly — no virtualization yet
// (the reference notes the same "up to ~2000 rows, add virtual scroll later
// if needed" limitation).

const LEFT_W = 260;
const ROW_H = 28;
const MS_DAY = 86_400_000;
const MILESTONE_TYPES = new Set(["TT_Mile", "TT_FinMile", "TT_StartMile"]);

const ZOOM_LEVELS = [
  { key: "compact", pxPerDay: 2.5, label: "Compact" },
  { key: "standard", pxPerDay: 7, label: "Standard" },
  { key: "detailed", pxPerDay: 20, label: "Detailed" },
] as const;

type ZoomKey = (typeof ZOOM_LEVELS)[number]["key"];
type StatusFilter = "all" | Activity["status"];

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" });
}

function barColor(a: Activity): string {
  if (a.status === "complete") return "var(--good)";
  if (a.is_critical) return "var(--crit)";
  if (a.status === "in_progress") return "var(--warn)";
  return "var(--info)";
}

function isMilestone(a: Activity): boolean {
  return Boolean(a.task_type && MILESTONE_TYPES.has(a.task_type));
}

function earliestDate(a: Activity): string | null {
  return a.early_start ?? a.actual_start ?? a.planned_start ?? null;
}

function latestDate(a: Activity): string | null {
  return a.early_finish ?? a.actual_finish ?? a.planned_finish ?? null;
}

export default function GanttPage() {
  const { project } = useProjectContext();
  const [activities, setActivities] = useState<Activity[]>([]);
  const [dataDate, setDataDate] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [zoomKey, setZoomKey] = useState<ZoomKey>("standard");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");

  const pxPerDay = ZOOM_LEVELS.find((z) => z.key === zoomKey)!.pxPerDay;

  useEffect(() => {
    async function load() {
      if (!project) {
        setActivities([]);
        setDataDate(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const [rows, imports] = await Promise.all([
          api.get<Activity[]>(`/activities?project_id=${project.id}`),
          api.get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`),
        ]);
        setActivities(rows);
        setDataDate(imports[0]?.data_date ? new Date(imports[0].data_date) : null);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load the Gantt chart.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [project]);

  const rows = useMemo(() => {
    let list = activities;
    if (statusFilter !== "all") list = list.filter((a) => a.status === statusFilter);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter((a) => a.name.toLowerCase().includes(q) || a.external_id.toLowerCase().includes(q));
    }
    return [...list].sort((a, b) => {
      const as = earliestDate(a) ?? "";
      const bs = earliestDate(b) ?? "";
      if (as !== bs) return as < bs ? -1 : 1;
      return a.external_id.localeCompare(b.external_id);
    });
  }, [activities, statusFilter, query]);

  const { projectStart, totalDays } = useMemo(() => {
    let minD: Date | null = null;
    let maxD: Date | null = null;
    for (const a of rows) {
      const s = earliestDate(a);
      const e = latestDate(a);
      if (s) {
        const d = new Date(s);
        if (!minD || d < minD) minD = d;
      }
      if (e) {
        const d = new Date(e);
        if (!maxD || d > maxD) maxD = d;
      }
    }
    if (!minD || !maxD) return { projectStart: null as Date | null, totalDays: 0 };
    const start = new Date(minD);
    start.setDate(1);
    const end = new Date(maxD);
    end.setMonth(end.getMonth() + 1, 1);
    return { projectStart: start, totalDays: Math.ceil((end.getTime() - start.getTime()) / MS_DAY) };
  }, [rows]);

  const totalWidth = totalDays * pxPerDay;

  const monthLabels = useMemo(() => {
    if (!projectStart || !totalDays) return [];
    const labels: { x: number; label: string }[] = [];
    const cur = new Date(projectStart);
    const end = new Date(projectStart.getTime() + totalDays * MS_DAY);
    while (cur < end) {
      labels.push({
        x: ((cur.getTime() - projectStart.getTime()) / MS_DAY) * pxPerDay,
        label: cur.toLocaleDateString("en-GB", { month: "short", year: "2-digit" }),
      });
      cur.setMonth(cur.getMonth() + 1);
    }
    return labels;
  }, [projectStart, totalDays, pxPerDay]);

  const dataDateX =
    dataDate && projectStart ? ((dataDate.getTime() - projectStart.getTime()) / MS_DAY) * pxPerDay : null;

  function barGeom(a: Activity): { x: number; w: number } | null {
    const s = earliestDate(a);
    const e = latestDate(a);
    if (!s || !e || !projectStart) return null;
    const x = ((new Date(s).getTime() - projectStart.getTime()) / MS_DAY) * pxPerDay;
    const w = Math.max(((new Date(e).getTime() - new Date(s).getTime()) / MS_DAY) * pxPerDay, 2);
    return { x: Math.max(x, 0), w };
  }

  if (loading) {
    return (
      <div className="a-content">
        <p className="page-desc">Loading…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="a-content">
        <p className="login-error" style={{ maxWidth: 420 }}>
          {error}
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>Gantt</b>
        </span>
      </div>
      <div className="a-content" style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div className="page-head">
          <div>
            <div className="page-title">Gantt</div>
            <div className="page-desc">{rows.length} activities</div>
          </div>
        </div>

        {rows.length === 0 ? (
          <div className="card">
            <p className="empty-state">
              {activities.length === 0
                ? "No schedule imported yet — upload a .xer file from Program Library."
                : "No activities match your filters."}
            </p>
          </div>
        ) : (
          <div className="card" style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: ".6rem",
                flexWrap: "wrap",
                padding: ".75rem 1.1rem",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                style={selectStyle}
              >
                <option value="all">All statuses</option>
                <option value="not_started">Not Started</option>
                <option value="in_progress">In Progress</option>
                <option value="complete">Complete</option>
              </select>
              <input
                type="text"
                placeholder="Search…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={{ ...selectStyle, width: 180 }}
              />

              <div style={{ flex: 1 }} />

              <div style={{ display: "flex", alignItems: "center", gap: ".7rem", fontSize: ".6875rem", color: "var(--text-muted)" }}>
                {[
                  { color: "var(--crit)", label: "Critical" },
                  { color: "var(--warn)", label: "In Progress" },
                  { color: "var(--info)", label: "Normal" },
                  { color: "var(--good)", label: "Complete" },
                ].map(({ color, label }) => (
                  <span key={label} style={{ display: "flex", alignItems: "center", gap: ".3rem" }}>
                    <span style={{ display: "inline-block", width: 9, height: 9, borderRadius: 2, background: color }} />
                    {label}
                  </span>
                ))}
                {dataDateX !== null && (
                  <span style={{ display: "flex", alignItems: "center", gap: ".3rem" }}>
                    <span style={{ display: "inline-block", width: 16, height: 2, background: "var(--accent)" }} />
                    Data Date
                  </span>
                )}
              </div>

              <div style={{ display: "flex", borderRadius: 20, overflow: "hidden", border: "1px solid var(--border-strong)" }}>
                {ZOOM_LEVELS.map((z) => (
                  <button
                    key={z.key}
                    onClick={() => setZoomKey(z.key)}
                    style={{
                      fontSize: ".6875rem",
                      fontWeight: zoomKey === z.key ? 700 : 400,
                      padding: ".25rem .7rem",
                      border: "none",
                      cursor: "pointer",
                      background: zoomKey === z.key ? "var(--accent)" : "transparent",
                      color: zoomKey === z.key ? "var(--accent-contrast)" : "var(--text-muted)",
                    }}
                  >
                    {z.label}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ overflow: "auto", maxHeight: "70vh" }}>
              <div style={{ minWidth: LEFT_W + totalWidth + 32 }}>
                <div
                  style={{
                    position: "sticky",
                    top: 0,
                    zIndex: 5,
                    display: "flex",
                    height: 32,
                    background: "var(--surface)",
                    borderBottom: "2px solid var(--border-strong)",
                  }}
                >
                  <div
                    style={{
                      width: LEFT_W,
                      minWidth: LEFT_W,
                      flexShrink: 0,
                      display: "flex",
                      alignItems: "center",
                      paddingLeft: "1rem",
                      fontSize: ".625rem",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: ".08em",
                      color: "var(--text-muted)",
                      borderRight: "1px solid var(--border)",
                    }}
                  >
                    Activity
                  </div>
                  <div style={{ position: "relative", width: totalWidth }}>
                    {monthLabels.map((ml, i) => (
                      <div
                        key={i}
                        style={{
                          position: "absolute",
                          top: 0,
                          bottom: 0,
                          left: ml.x,
                          borderLeft: "1px solid var(--border)",
                          display: "flex",
                          alignItems: "center",
                        }}
                      >
                        <span style={{ fontSize: ".625rem", color: "var(--text-muted)", paddingLeft: 6, whiteSpace: "nowrap" }}>
                          {ml.label}
                        </span>
                      </div>
                    ))}
                    {dataDateX !== null && (
                      <div
                        style={{
                          position: "absolute",
                          top: 0,
                          bottom: 0,
                          left: dataDateX,
                          borderLeft: "2px solid var(--accent)",
                          zIndex: 4,
                          paddingTop: 2,
                        }}
                      >
                        <span style={{ paddingLeft: 3, fontSize: ".5625rem", fontWeight: 700, color: "var(--accent)" }}>DD</span>
                      </div>
                    )}
                  </div>
                </div>

                {rows.map((a, idx) => {
                  const geom = barGeom(a);
                  const milestone = isMilestone(a);
                  const color = barColor(a);
                  const even = idx % 2 === 0;
                  const floatDays = a.total_float_hours != null ? (a.total_float_hours / 8).toFixed(1) : "—";
                  const title = `${a.external_id}: ${a.name}\nES: ${fmtDate(a.early_start)}  EF: ${fmtDate(a.early_finish)}\nTF: ${floatDays}d  Progress: ${a.percent_complete}%`;

                  return (
                    <div
                      key={a.id}
                      style={{
                        display: "flex",
                        height: ROW_H,
                        borderBottom: "1px solid var(--border)",
                        background: even ? "var(--surface)" : "var(--surface-2)",
                      }}
                    >
                      <div
                        style={{
                          width: LEFT_W,
                          minWidth: LEFT_W,
                          flexShrink: 0,
                          display: "flex",
                          alignItems: "center",
                          gap: ".5rem",
                          paddingLeft: ".75rem",
                          paddingRight: ".6rem",
                          borderRight: "1px solid var(--border)",
                          overflow: "hidden",
                        }}
                      >
                        <span
                          className="mono"
                          style={{ fontSize: ".625rem", color: "var(--text-muted)", flexShrink: 0, width: "4.5rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                        >
                          {a.external_id}
                        </span>
                        <span style={{ fontSize: ".75rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                          {a.name}
                        </span>
                      </div>

                      <div style={{ position: "relative", overflow: "hidden", width: totalWidth }} title={title}>
                        {dataDateX !== null && (
                          <div style={{ position: "absolute", top: 0, bottom: 0, left: dataDateX, borderLeft: "1px solid var(--accent)", opacity: 0.3 }} />
                        )}
                        {geom &&
                          (milestone ? (
                            <div
                              style={{
                                position: "absolute",
                                left: geom.x - 6,
                                top: "50%",
                                transform: "translateY(-50%) rotate(45deg)",
                                width: 11,
                                height: 11,
                                background: color,
                              }}
                            />
                          ) : (
                            <div
                              style={{
                                position: "absolute",
                                left: geom.x,
                                width: geom.w,
                                top: "50%",
                                height: 14,
                                transform: "translateY(-50%)",
                                background: color,
                                borderRadius: 3,
                                opacity: a.status === "not_started" ? 0.65 : 1,
                                overflow: "hidden",
                              }}
                            >
                              {a.status === "in_progress" && a.percent_complete > 0 && (
                                <div
                                  style={{
                                    position: "absolute",
                                    left: 0,
                                    top: 0,
                                    height: "100%",
                                    width: `${Math.min(a.percent_complete, 100)}%`,
                                    background: "rgba(255,255,255,0.3)",
                                  }}
                                />
                              )}
                              {zoomKey === "detailed" && geom.w > 60 && (
                                <span
                                  style={{
                                    position: "absolute",
                                    inset: 0,
                                    display: "flex",
                                    alignItems: "center",
                                    paddingLeft: 5,
                                    fontSize: ".5625rem",
                                    whiteSpace: "nowrap",
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    color: "var(--accent-contrast)",
                                  }}
                                >
                                  {a.name}
                                </span>
                              )}
                            </div>
                          ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

const selectStyle: CSSProperties = {
  fontSize: ".8125rem",
  height: 30,
  padding: "0 .5rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text-primary)",
};
