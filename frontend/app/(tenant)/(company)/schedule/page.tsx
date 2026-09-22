"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, ScheduleImport, WbsNode } from "@/lib/types";
import { ChevronDownIcon } from "@/components/icons";
import { buildGridRows, groupByLeaf, UNGROUPED_KEY } from "@/lib/wbs-tree";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// P6-style short date: DD-MMM-YY (e.g. 30-Apr-26) — consistent with Program
// Library / Planning > WBS.
function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${String(d.getUTCFullYear()).slice(-2)}`;
}

function fmtFloat(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "—";
  const days = hours / 8;
  return `${days >= 0 ? "" : "-"}${Math.abs(days).toFixed(1)}d`;
}

const selectStyle: CSSProperties = {
  fontSize: ".75rem",
  height: 30,
  padding: "0 .5rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text-primary)",
};

export default function SchedulePage() {
  const { project } = useProjectContext();
  const [activities, setActivities] = useState<Activity[]>([]);
  const [nodes, setNodes] = useState<WbsNode[]>([]);
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  // Which uploaded program to show. Defaults to the current update once the
  // import list loads; null only while nothing has loaded yet.
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [overdueOnly, setOverdueOnly] = useState(false);
  // Lowest float first, within each WBS band, puts the most schedule-critical
  // activities on top.
  const [floatAsc, setFloatAsc] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  // Deep links from the dashboard's Project Health card: /schedule?filter=critical|overdue
  useEffect(() => {
    const preset = new URLSearchParams(window.location.search).get("filter");
    if (preset === "critical") {
      setCriticalOnly(true);
      setFloatAsc(true);
    } else if (preset === "overdue") {
      setOverdueOnly(true);
      setFloatAsc(true);
    }
  }, []);

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
      setError(err instanceof ApiError ? err.message : "Failed to load activities.");
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

  const maxLevel = useMemo(() => (nodes.length ? Math.max(...nodes.map((n) => n.depth)) + 1 : 1), [nodes]);
  const knownWbsIds = useMemo(() => new Set(nodes.map((n) => n.wbs_id)), [nodes]);

  // "Collapse to Level N" (matches P6's Group and Sort dialog): levels 1..N stay
  // expanded, everything at level N and deeper collapses under its level-N band.
  function collapseToLevel(level: number) {
    setCollapsed(new Set(nodes.filter((n) => n.depth + 1 >= level).map((n) => n.wbs_id)));
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const today = new Date().toISOString().slice(0, 10);
    return activities.filter((a) => {
      if (criticalOnly && !a.is_critical) return false;
      // Same definition as the dashboard's "Overdue activities": unfinished and past planned finish.
      if (overdueOnly && (a.status === "complete" || !a.planned_finish || a.planned_finish.slice(0, 10) >= today)) {
        return false;
      }
      if (!q) return true;
      return a.external_id.toLowerCase().includes(q) || a.name.toLowerCase().includes(q);
    });
  }, [activities, query, criticalOnly, overdueOnly]);

  const hasUngrouped = useMemo(
    () => filtered.some((a) => !a.wbs_path || !knownWbsIds.has(a.wbs_path)),
    [filtered, knownWbsIds],
  );

  const rows = useMemo(() => {
    const byLeaf = groupByLeaf(filtered, knownWbsIds);
    if (floatAsc) {
      for (const list of byLeaf.values()) {
        list.sort((x, y) => (x.total_float_hours ?? Number.POSITIVE_INFINITY) - (y.total_float_hours ?? Number.POSITIVE_INFINITY));
      }
    }
    return buildGridRows(nodes, byLeaf, collapsed);
  }, [nodes, filtered, collapsed, floatAsc]);

  const criticalCount = activities.filter((a) => a.is_critical).length;

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
          {project?.name ?? "—"} / <b>Schedule</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Schedule</div>
            <div className="page-desc">
              {dataLoading
                ? "Loading…"
                : `${activities.length} activities · ${criticalCount} on the critical path` +
                  (!isViewingCurrent ? " · read-only — showing an earlier program" : "")}
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
              Switch <b>Program</b> back to the current update to see live progress.
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-head" style={{ gap: ".6rem", flexWrap: "wrap" }}>
            <input
              type="text"
              placeholder="Search by activity ID or name…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{
                flex: 1,
                minWidth: 220,
                background: "var(--surface)",
                border: "1px solid var(--border-strong)",
                borderRadius: 6,
                padding: ".5rem .65rem",
                fontSize: ".8125rem",
              }}
            />
            <label className="checkbox-row">
              <input type="checkbox" checked={criticalOnly} onChange={(e) => setCriticalOnly(e.target.checked)} />
              Critical path only
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} />
              Overdue only
            </label>
            <label className="checkbox-row" title="Sort activities within each WBS band by total float, lowest first">
              <input type="checkbox" checked={floatAsc} onChange={(e) => setFloatAsc(e.target.checked)} />
              Sort by float
            </label>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Activity ID</th>
                  <th>Name</th>
                  <th>Early Start</th>
                  <th>Early Finish</th>
                  <th>Total Float</th>
                  <th>% Complete</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="empty-state">
                      {activities.length === 0
                        ? isViewingCurrent
                          ? "No schedule imported yet — upload a .xer file from Program Library."
                          : "No activities recorded for this program."
                        : "No activities match your filters."}
                    </td>
                  </tr>
                )}
                {rows.map((row) => {
                  if (row.kind === "band") {
                    const bandClass = `wbs-band d${Math.min(row.depth, 4)}`;
                    return (
                      <tr key={row.key} className={bandClass}>
                        <td colSpan={7}>
                          <div className="cell-flex" style={{ paddingLeft: `${row.depth * 1.25}rem`, gap: ".4rem" }}>
                            <button
                              onClick={() =>
                                setCollapsed((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(row.wbsId)) next.delete(row.wbsId);
                                  else next.add(row.wbsId);
                                  return next;
                                })
                              }
                              aria-label={row.collapsed ? "Expand" : "Collapse"}
                              aria-expanded={!row.collapsed}
                              style={{
                                display: "flex",
                                color: "var(--text-muted)",
                                transform: row.collapsed ? "rotate(-90deg)" : "none",
                                transition: "transform var(--dur-1, 120ms) var(--ease, ease)",
                              }}
                            >
                              <ChevronDownIcon className="icon" />
                            </button>
                            {row.node && (
                              <span className="wbs-level-chip" title={`WBS level ${row.depth + 1}`}>
                                L{row.depth + 1}
                              </span>
                            )}
                            <span className="wbs-band-code">{row.node?.wbs_short_name ?? "—"}</span>
                            <span>{row.label}</span>
                            <span className="wbs-band-roll" style={{ marginLeft: "auto" }}>
                              Σ {row.total}
                              {row.inProgress > 0 ? ` · ${row.inProgress} IP` : ""}
                              {row.completed > 0 ? ` · ${row.completed} done` : ""}
                              {` · ${row.avgPercent}%`}
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  }
                  const a = row.activity;
                  // Finished work is never "critical" regardless of its total float —
                  // matches P6's own convention (see services/xer_import.py::_is_critical).
                  const isFinished = a.status === "complete" || !!a.actual_finish;
                  return (
                    <tr key={row.key} className={!isFinished && a.is_critical ? "critical" : undefined}>
                      <td className="actid" style={{ paddingLeft: `${row.depth * 1.25}rem` }}>
                        {a.external_id}
                      </td>
                      <td>{a.name}</td>
                      <td>{fmtDate(a.early_start)}</td>
                      <td>{fmtDate(a.early_finish)}</td>
                      <td className="num">{fmtFloat(a.total_float_hours)}</td>
                      <td className="num">{a.percent_complete}%</td>
                      <td>
                        {isFinished ? (
                          <span className="chip chip-good">Completed</span>
                        ) : a.is_critical ? (
                          <span className="chip chip-crit">Critical</span>
                        ) : (
                          <span className="chip chip-neutral">Float</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
