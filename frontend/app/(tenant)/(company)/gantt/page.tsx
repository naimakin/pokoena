"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, ScheduleImport, WbsNode } from "@/lib/types";
import { ChevronDownIcon } from "@/components/icons";
import { buildGridRows, groupByLeaf, UNGROUPED_KEY } from "@/lib/wbs-tree";

// Hand-rolled CSS-positioned bars (no charting library — see the research note
// in the PR this shipped with for why: every open-source Gantt library that
// actually virtualizes past a few thousand rows gates collapsible task/WBS
// grouping behind a paid tier, which is the one thing this page most needs).
// WBS grouping/collapse reuses the exact same lib/wbs-tree.ts logic as
// Planning > Activities and Progress, so a band collapsing here hides its
// whole subtree in one step, same as everywhere else in the app. True row
// virtualization (for a project meaningfully past ~5-8k rows) is deferred —
// collapsing bands already keeps the rendered row count far below the
// project's real activity count for any reasonably-grouped WBS, and this
// project's own 5000+-activity Gantt already renders today without it.

const LEFT_W = 280;
const ROW_H = 28;
const MS_DAY = 86_400_000;
const MILESTONE_TYPES = new Set(["TT_Mile", "TT_FinMile", "TT_StartMile"]);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// P6-style zoom presets (Day/Week/Month/Quarter/Year), plus "Fit" — computed
// from the container width so the whole project date range shows with no
// horizontal scroll at all, exactly what P6's "Zoom to Fit" does.
const ZOOM_LEVELS = [
  { key: "day", pxPerDay: 32, label: "Day" },
  { key: "week", pxPerDay: 14, label: "Week" },
  { key: "month", pxPerDay: 5, label: "Month" },
  { key: "quarter", pxPerDay: 2, label: "Quarter" },
  { key: "year", pxPerDay: 0.6, label: "Year" },
] as const;

type ZoomKey = (typeof ZOOM_LEVELS)[number]["key"] | "fit";
type StatusFilter = "all" | Activity["status"];

const selectStyle: CSSProperties = {
  fontSize: ".75rem",
  height: 30,
  padding: "0 .5rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text-primary)",
};

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${String(d.getUTCFullYear()).slice(-2)}`;
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
  const [nodes, setNodes] = useState<WbsNode[]>([]);
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [zoomKey, setZoomKey] = useState<ZoomKey>("month");
  const [fitPxPerDay, setFitPxPerDay] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const scrollRef = useRef<HTMLDivElement>(null);

  const loadImports = useCallback(async () => {
    if (!project) {
      setImports([]);
      setSelectedImportId(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await api.get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`);
      setImports(list);
      setSelectedImportId((prev) => {
        if (prev && list.some((i) => i.id === prev)) return prev;
        return (list.find((i) => i.is_current) ?? list[0])?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the schedule imports.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    loadImports();
  }, [loadImports]);

  const currentImportId = useMemo(() => (imports.find((i) => i.is_current) ?? imports[0])?.id ?? null, [imports]);
  const selectedImport = useMemo(() => imports.find((i) => i.id === selectedImportId) ?? null, [imports, selectedImportId]);
  const isViewingCurrent = selectedImportId !== null && selectedImportId === currentImportId;
  const dataDate = selectedImport?.data_date ? new Date(selectedImport.data_date) : null;

  const loadData = useCallback(async () => {
    if (!project || !selectedImportId) {
      setActivities([]);
      setNodes([]);
      return;
    }
    setDataLoading(true);
    try {
      const [acts, wbs] = await Promise.all([
        isViewingCurrent
          ? api.get<Activity[]>(`/activities?project_id=${project.id}`)
          : api.get<Activity[]>(`/projects/${project.id}/schedule-imports/${selectedImportId}/activities`),
        isViewingCurrent
          ? api.get<WbsNode[]>(`/projects/${project.id}/wbs-nodes`)
          : api.get<WbsNode[]>(`/projects/${project.id}/schedule-imports/${selectedImportId}/wbs-nodes`),
      ]);
      setActivities(acts);
      setNodes(wbs);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the Gantt chart.");
      setActivities([]);
      setNodes([]);
    } finally {
      setDataLoading(false);
    }
  }, [project, selectedImportId, isViewingCurrent]);

  useEffect(() => {
    loadData();
    setCollapsed(new Set());
  }, [loadData]);

  const knownWbsIds = useMemo(() => new Set(nodes.map((n) => n.wbs_id)), [nodes]);
  const maxLevel = useMemo(() => (nodes.length ? Math.max(...nodes.map((n) => n.depth)) + 1 : 1), [nodes]);

  function collapseToLevel(level: number) {
    setCollapsed(new Set(nodes.filter((n) => n.depth + 1 >= level).map((n) => n.wbs_id)));
  }

  const filteredActivities = useMemo(() => {
    let list = activities;
    if (statusFilter !== "all") list = list.filter((a) => a.status === statusFilter);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter((a) => a.name.toLowerCase().includes(q) || a.external_id.toLowerCase().includes(q));
    }
    return list;
  }, [activities, statusFilter, query]);

  const hasUngrouped = useMemo(
    () => filteredActivities.some((a) => !a.wbs_path || !knownWbsIds.has(a.wbs_path)),
    [filteredActivities, knownWbsIds],
  );

  const rows = useMemo(() => {
    const byLeaf = groupByLeaf(filteredActivities, knownWbsIds);
    for (const list of byLeaf.values()) {
      list.sort((x, y) => {
        const as = earliestDate(x) ?? "";
        const bs = earliestDate(y) ?? "";
        if (as !== bs) return as < bs ? -1 : 1;
        return x.external_id.localeCompare(y.external_id, undefined, { numeric: true });
      });
    }
    return buildGridRows(nodes, byLeaf, collapsed);
  }, [nodes, filteredActivities, collapsed]);

  const { projectStart, totalDays } = useMemo(() => {
    let minD: Date | null = null;
    let maxD: Date | null = null;
    for (const a of filteredActivities) {
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
  }, [filteredActivities]);

  // "Fit to screen": pxPerDay so the whole date range fills the visible
  // timeline width with no horizontal scroll — matches P6's Zoom-to-Fit.
  function fitToScreen() {
    const el = scrollRef.current;
    if (!el || !totalDays) return;
    const available = el.clientWidth - LEFT_W - 32;
    setFitPxPerDay(Math.max(available / totalDays, 0.15));
    setZoomKey("fit");
  }

  const pxPerDay = zoomKey === "fit" ? (fitPxPerDay ?? 1) : ZOOM_LEVELS.find((z) => z.key === zoomKey)!.pxPerDay;
  const totalWidth = totalDays * pxPerDay;

  const monthLabels = useMemo(() => {
    if (!projectStart || !totalDays) return [];
    const labels: { x: number; label: string }[] = [];
    const cur = new Date(projectStart);
    const end = new Date(projectStart.getTime() + totalDays * MS_DAY);
    // At low zoom (Quarter/Year/Fit over a long range) a per-month label for
    // every single month is unreadable clutter — step by quarter instead.
    const stepMonths = pxPerDay < 1.5 ? 3 : 1;
    while (cur < end) {
      labels.push({
        x: ((cur.getTime() - projectStart.getTime()) / MS_DAY) * pxPerDay,
        label: cur.toLocaleDateString("en-GB", { month: "short", year: "2-digit" }),
      });
      cur.setMonth(cur.getMonth() + stepMonths);
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

  function toggleBand(wbsId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(wbsId)) next.delete(wbsId);
      else next.add(wbsId);
      return next;
    });
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
            <div className="page-desc">
              {dataLoading
                ? "Loading…"
                : `${filteredActivities.length} activities` + (!isViewingCurrent ? " · read-only — showing an earlier program" : "")}
            </div>
          </div>
          <div style={{ display: "flex", gap: ".55rem", alignItems: "center", flexWrap: "wrap" }}>
            {imports.length > 0 && (
              <label style={{ display: "flex", alignItems: "center", gap: ".4rem", fontSize: ".75rem", color: "var(--text-muted)" }}>
                Program
                <select
                  style={{ ...selectStyle, minWidth: 220 }}
                  value={selectedImportId ?? ""}
                  onChange={(e) => setSelectedImportId(e.target.value)}
                >
                  {imports.map((imp) => (
                    <option key={imp.id} value={imp.id}>
                      {imp.revision_label ?? imp.filename}
                      {imp.data_date ? ` (${fmtDate(imp.data_date)})` : ""}
                      {imp.id === currentImportId ? " — Current update" : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {nodes.length > 0 && (
              <>
                <label style={{ display: "flex", alignItems: "center", gap: ".4rem", fontSize: ".75rem", color: "var(--text-muted)" }}>
                  Collapse to
                  <select
                    style={selectStyle}
                    defaultValue=""
                    onChange={(e) => {
                      if (e.target.value) collapseToLevel(Number(e.target.value));
                      e.target.value = "";
                    }}
                  >
                    <option value="" disabled>
                      Level…
                    </option>
                    {Array.from({ length: maxLevel }, (_, i) => i + 1).map((level) => (
                      <option key={level} value={level}>
                        Level {level}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="btn btn-secondary btn-sm" onClick={() => setCollapsed(new Set())}>
                  Expand all
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() =>
                    setCollapsed(new Set([...nodes.map((n) => n.wbs_id), ...(hasUngrouped ? [UNGROUPED_KEY] : [])]))
                  }
                >
                  Collapse all
                </button>
              </>
            )}
          </div>
        </div>

        {!isViewingCurrent && selectedImport && (
          <div className="banner">
            <div className="banner-text">
              Showing <b>{selectedImport.revision_label ?? selectedImport.filename}</b>, an earlier program — read-only.
            </div>
          </div>
        )}

        {rows.length === 0 ? (
          <div className="card">
            <p className="empty-state">
              {activities.length === 0
                ? isViewingCurrent
                  ? "No schedule imported yet — upload a .xer file from Program Library."
                  : "No activities recorded for this program."
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
                      padding: ".25rem .6rem",
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
              <button
                className="btn btn-secondary btn-sm"
                title="Zoom so the whole date range fits with no horizontal scroll"
                onClick={fitToScreen}
              >
                Fit to screen
              </button>
            </div>

            <div ref={scrollRef} style={{ overflow: "auto", maxHeight: "70vh" }}>
              <div style={{ minWidth: LEFT_W + totalWidth + 32 }}>
                <div style={{ display: "flex", height: 32, position: "sticky", top: 0, zIndex: 6 }}>
                  <div
                    style={{
                      position: "sticky",
                      left: 0,
                      zIndex: 2,
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
                      background: "var(--surface)",
                      borderRight: "1px solid var(--border)",
                      borderBottom: "2px solid var(--border-strong)",
                    }}
                  >
                    Activity
                  </div>
                  <div style={{ position: "relative", width: totalWidth, background: "var(--surface)", borderBottom: "2px solid var(--border-strong)" }}>
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

                {rows.map((row, idx) => {
                  if (row.kind === "band") {
                    // Opaque tiers only — this cell (and its timeline-row twin below)
                    // sit under a `position: sticky` left column, so anything less
                    // than fully opaque would let horizontally-scrolled bars show
                    // through the "frozen" Activity column.
                    const bandBg = ["var(--surface-3)", "var(--surface-2)", "var(--surface)"][Math.min(row.depth, 2)];
                    return (
                      <div key={row.key} style={{ display: "flex", height: ROW_H, borderBottom: "1px solid var(--border-strong)" }}>
                        <div
                          style={{
                            position: "sticky",
                            left: 0,
                            zIndex: 2,
                            width: LEFT_W,
                            minWidth: LEFT_W,
                            flexShrink: 0,
                            display: "flex",
                            alignItems: "center",
                            gap: ".4rem",
                            paddingLeft: `${.5 + row.depth * 1}rem`,
                            paddingRight: ".5rem",
                            borderRight: "1px solid var(--border)",
                            background: bandBg,
                            fontWeight: 700,
                            fontSize: ".75rem",
                            overflow: "hidden",
                          }}
                        >
                          <button
                            onClick={() => toggleBand(row.wbsId)}
                            aria-label={row.collapsed ? "Expand" : "Collapse"}
                            aria-expanded={!row.collapsed}
                            style={{
                              display: "flex",
                              flexShrink: 0,
                              color: "var(--text-muted)",
                              transform: row.collapsed ? "rotate(-90deg)" : "none",
                              transition: "transform var(--dur-1, 120ms) var(--ease, ease)",
                            }}
                          >
                            <ChevronDownIcon className="icon" style={{ width: 14, height: 14 }} />
                          </button>
                          {row.node && (
                            <span className="wbs-level-chip" title={`WBS level ${row.depth + 1}`}>
                              L{row.depth + 1}
                            </span>
                          )}
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.label}</span>
                        </div>
                        <div style={{ position: "relative", width: totalWidth, background: bandBg }}>
                          {dataDateX !== null && (
                            <div style={{ position: "absolute", top: 0, bottom: 0, left: dataDateX, borderLeft: "1px solid var(--accent)", opacity: 0.3 }} />
                          )}
                          <span
                            className="mono"
                            style={{ position: "absolute", left: 6, top: "50%", transform: "translateY(-50%)", fontSize: ".625rem", color: "var(--text-muted)" }}
                          >
                            Σ {row.total}
                            {row.completed > 0 ? ` · ${row.completed} done` : ""} · {row.avgPercent}%
                          </span>
                        </div>
                      </div>
                    );
                  }

                  const a = row.activity;
                  const geom = barGeom(a);
                  const milestone = isMilestone(a);
                  const color = barColor(a);
                  const even = idx % 2 === 0;
                  const rowBg = even ? "var(--surface)" : "var(--surface-2)";
                  const floatDays = a.total_float_hours != null ? (a.total_float_hours / 8).toFixed(1) : "—";
                  const title = `${a.external_id}: ${a.name}\nES: ${fmtDate(a.early_start)}  EF: ${fmtDate(a.early_finish)}\nTF: ${floatDays}d  Progress: ${a.percent_complete}%`;

                  return (
                    <div key={row.key} style={{ display: "flex", height: ROW_H, borderBottom: "1px solid var(--border)" }}>
                      <div
                        style={{
                          position: "sticky",
                          left: 0,
                          zIndex: 1,
                          width: LEFT_W,
                          minWidth: LEFT_W,
                          flexShrink: 0,
                          display: "flex",
                          alignItems: "center",
                          gap: ".5rem",
                          paddingLeft: `${0.75 + row.depth * 1}rem`,
                          paddingRight: ".6rem",
                          borderRight: "1px solid var(--border)",
                          background: rowBg,
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

                      <div style={{ position: "relative", overflow: "hidden", width: totalWidth, background: rowBg }} title={title}>
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
                              {(zoomKey === "day" || zoomKey === "week") && geom.w > 60 && (
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
