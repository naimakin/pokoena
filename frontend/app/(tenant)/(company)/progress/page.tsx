"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, BaselineStatus, SavedActivityFilter, ScheduleImport, WbsNode } from "@/lib/types";
import { applyFilter, EMPTY_CRITERIA, normalizeCriteria, type FilterCriteria } from "@/components/progress/filter";
import { FilterPanel } from "@/components/progress/FilterPanel";
import { StatusDatesMode } from "@/components/progress/StatusDatesMode";
import { ManhoursMode } from "@/components/progress/ManhoursMode";
import { UNGROUPED_KEY } from "@/lib/wbs-tree";
import { MaximizeIcon, MinimizeIcon } from "@/components/icons";

type Mode = "status" | "manhours";
const MODE_KEY = "poko:progress:mode";
const VIEW = "progress";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// P6 convention (DD-MMM-YYYY) — see CLAUDE.md.
function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()}`;
}

// Same short form as Program Library / Planning > WBS, for the Program picker.
function fmtDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${String(d.getUTCFullYear()).slice(-2)}`;
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

export default function ProgressPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();

  const [activities, setActivities] = useState<Activity[]>([]);
  const [wbsNodes, setWbsNodes] = useState<WbsNode[]>([]);
  const [savedFilters, setSavedFilters] = useState<SavedActivityFilter[]>([]);
  const [hasActiveBaseline, setHasActiveBaseline] = useState(false);
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  // Which uploaded program to show. Defaults to the current update once the
  // import list loads; null only while nothing has loaded yet.
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [mode, setMode] = useState<Mode>("status");
  const [criteria, setCriteriaState] = useState<FilterCriteria>(EMPTY_CRITERIA);
  const [activeSavedId, setActiveSavedId] = useState<string | null>(null);
  const [filterDirty, setFilterDirty] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  // Full screen, same as Planning > Schedule: the whole working area (controls,
  // filters and grid) goes full screen, so filtering still works from there.
  const contentRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Folded in from the old Planning > Activities view — CPM-side quick filters,
  // scoped to Status & Dates only (Burned MH Loading keeps its own filtered set).
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [floatAsc, setFloatAsc] = useState(false);

  // Only the manhours mode still holds unsaved page-level state: status/date
  // edits moved into the Activity modal, which saves on its own.
  const [manhoursDirty, setManhoursDirty] = useState(0);
  const totalDirty = manhoursDirty;

  useEffect(() => {
    try {
      const m = localStorage.getItem(MODE_KEY);
      if (m === "status" || m === "manhours") setMode(m);
    } catch {
      /* ignore */
    }
  }, []);

  // Deep links from the dashboard's Project Health card: /progress?filter=critical|overdue
  // (used to point at Planning > Activities before that view folded in here).
  useEffect(() => {
    const preset = new URLSearchParams(window.location.search).get("filter");
    if (preset === "critical") {
      setMode("status");
      setCriticalOnly(true);
      setFloatAsc(true);
    } else if (preset === "overdue") {
      setMode("status");
      setOverdueOnly(true);
      setFloatAsc(true);
    }
  }, []);

  useEffect(() => {
    if (totalDirty === 0) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [totalDirty]);

  const loadFilters = useCallback(async () => {
    if (!project) return;
    try {
      const rows = await api.get<SavedActivityFilter[]>(
        `/projects/${project.id}/saved-filters?view=${VIEW}`,
      );
      setSavedFilters(rows);
    } catch {
      setSavedFilters([]);
    }
  }, [project]);

  const loadImports = useCallback(async () => {
    if (!project) {
      setImports([]);
      setSelectedImportId(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    setCriteriaState(EMPTY_CRITERIA);
    setActiveSavedId(null);
    setFilterDirty(false);
    try {
      const [list, baseline] = await Promise.all([
        api.get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`),
        api.get<BaselineStatus>(`/projects/${project.id}/evm/baseline`),
      ]);
      setImports(list);
      setHasActiveBaseline(baseline.has_active);
      setSelectedImportId((prev) => {
        if (prev && list.some((i) => i.id === prev)) return prev;
        return (list.find((i) => i.is_current) ?? list[0])?.id ?? null;
      });
      loadFilters();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load activities.");
    } finally {
      setLoading(false);
    }
  }, [project, loadFilters]);

  useEffect(() => {
    loadImports();
  }, [loadImports]);

  const currentImportId = useMemo(() => (imports.find((i) => i.is_current) ?? imports[0])?.id ?? null, [imports]);
  const selectedImport = useMemo(() => imports.find((i) => i.id === selectedImportId) ?? null, [imports, selectedImportId]);
  const isViewingCurrent = selectedImportId !== null && selectedImportId === currentImportId;
  const dataDate = selectedImport?.data_date ?? null;

  const loadData = useCallback(async () => {
    if (!project || !selectedImportId) {
      setActivities([]);
      setWbsNodes([]);
      return;
    }
    setDataLoading(true);
    try {
      const [acts, nodes] = await Promise.all([
        isViewingCurrent
          ? api.get<Activity[]>(`/activities?project_id=${project.id}`)
          : api.get<Activity[]>(`/projects/${project.id}/schedule-imports/${selectedImportId}/activities`),
        isViewingCurrent
          ? api.get<WbsNode[]>(`/projects/${project.id}/wbs-nodes`)
          : api.get<WbsNode[]>(`/projects/${project.id}/schedule-imports/${selectedImportId}/wbs-nodes`),
      ]);
      setActivities(acts);
      setWbsNodes(nodes);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load activities.");
      setActivities([]);
      setWbsNodes([]);
    } finally {
      setDataLoading(false);
    }
  }, [project, selectedImportId, isViewingCurrent]);

  useEffect(() => {
    loadData();
    setCollapsed(new Set());
  }, [loadData]);

  function switchProgram(id: string) {
    if (totalDirty > 0 && !window.confirm(`Discard ${totalDirty} unsaved change${totalDirty === 1 ? "" : "s"} and switch programs?`)) {
      return;
    }
    setSelectedImportId(id);
  }

  const maxLevel = useMemo(() => (wbsNodes.length ? Math.max(...wbsNodes.map((n) => n.depth)) + 1 : 1), [wbsNodes]);

  function collapseToLevel(level: number) {
    setCollapsed(new Set(wbsNodes.filter((n) => n.depth + 1 >= level).map((n) => n.wbs_id)));
  }

  const nodeByWbsId = useMemo(() => new Map(wbsNodes.map((n) => [n.wbs_id, n])), [wbsNodes]);
  const filtered = useMemo(
    () => applyFilter(activities, nodeByWbsId, criteria),
    [activities, nodeByWbsId, criteria],
  );
  // Critical/overdue quick filters narrow the Status & Dates grid only —
  // Burned MH Loading keeps working off `filtered`, unchanged.
  const statusFiltered = useMemo(() => {
    if (!criticalOnly && !overdueOnly) return filtered;
    const today = new Date().toISOString().slice(0, 10);
    return filtered.filter((a) => {
      if (criticalOnly && !a.is_critical) return false;
      if (overdueOnly && (a.status === "complete" || !a.planned_finish || a.planned_finish.slice(0, 10) >= today)) {
        return false;
      }
      return true;
    });
  }, [filtered, criticalOnly, overdueOnly]);
  const completedCount = useMemo(() => activities.filter((a) => a.status === "complete").length, [activities]);
  const hasUngrouped = useMemo(
    () => filtered.some((a) => !a.wbs_path || !nodeByWbsId.has(a.wbs_path)),
    [filtered, nodeByWbsId],
  );

  function collapseAll() {
    setCollapsed(new Set([...wbsNodes.map((n) => n.wbs_id), ...(hasUngrouped ? [UNGROUPED_KEY] : [])]));
  }
  function expandAll() {
    setCollapsed(new Set());
  }

  const setCriteria = useCallback(
    (next: FilterCriteria) => {
      setCriteriaState(next);
      if (activeSavedId) setFilterDirty(true);
    },
    [activeSavedId],
  );

  function toggleCollapse(wbsId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(wbsId)) next.delete(wbsId);
      else next.add(wbsId);
      return next;
    });
  }

  function switchMode(m: Mode) {
    setMode(m);
    try {
      localStorage.setItem(MODE_KEY, m);
    } catch {
      /* ignore */
    }
  }

  const onActivitiesUpdated = useCallback((rows: Activity[]) => {
    setActivities((prev) => {
      const byId = new Map(rows.map((r) => [r.id, r]));
      return prev.map((a) => byId.get(a.id) ?? a);
    });
  }, []);

  function selectSaved(f: SavedActivityFilter) {
    setCriteriaState(normalizeCriteria(f.criteria));
    setActiveSavedId(f.id);
    setFilterDirty(false);
  }
  function clearSaved() {
    setActiveSavedId(null);
    setFilterDirty(false);
  }
  async function saveNewFilter(name: string) {
    if (!project) return;
    try {
      const created = await api.post<SavedActivityFilter>(
        `/projects/${project.id}/saved-filters?view=${VIEW}`,
        { name, criteria: criteria as unknown as Record<string, unknown>, filter_version: 1 },
      );
      await loadFilters();
      setActiveSavedId(created.id);
      setFilterDirty(false);
      showToast("Filter saved.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not save filter.");
    }
  }
  async function updateActiveFilter() {
    if (!project || !activeSavedId) return;
    try {
      await api.put<SavedActivityFilter>(`/projects/${project.id}/saved-filters/${activeSavedId}`, {
        criteria: criteria as unknown as Record<string, unknown>,
      });
      await loadFilters();
      setFilterDirty(false);
      showToast("Filter updated.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not update filter.");
    }
  }
  async function deleteSaved(f: SavedActivityFilter) {
    if (!project) return;
    try {
      await api.delete(`/projects/${project.id}/saved-filters/${f.id}`);
      if (activeSavedId === f.id) clearSaved();
      await loadFilters();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not delete filter.");
    }
  }

  // Driven by the browser, not by us: Esc and the window chrome can leave full
  // screen without asking, so `fullscreenchange` is what sets the state.
  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement === contentRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  function toggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => undefined);
    } else {
      contentRef.current?.requestFullscreen().catch(() => undefined);
    }
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
  if (!project) {
    return (
      <div className="a-content">
        <p className="page-desc">No project selected.</p>
      </div>
    );
  }

  // Editing (status/dates/manhours) only ever applies to the live schedule —
  // a historical program is viewed read-only via its frozen snapshot, same as
  // Planning > WBS/Gantt. Route-level role checks still apply on top.
  const canEdit = isViewingCurrent;

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>Project Activities</b>
        </span>
        <div className="spacer" />
        {totalDirty > 0 && <span className="chip chip-warn">{totalDirty} unsaved</span>}
      </div>
      <div ref={contentRef} className={`a-content fill-viewport${isFullscreen ? " is-fullscreen" : ""}`}>
        <div className="page-head">
          <div>
            <div className="page-title">Project Activities</div>
            <div className="page-desc">
              {dataLoading
                ? "Loading…"
                : (() => {
                    const shown = mode === "status" ? statusFiltered.length : filtered.length;
                    return shown !== activities.length
                      ? `${shown} of ${activities.length} activities shown`
                      : `${activities.length} activities`;
                  })() +
                  ` · ${completedCount} completed` +
                  (dataDate ? ` · data date ${fmtDate(dataDate)}` : "") +
                  (!isViewingCurrent ? " · read-only — showing an earlier program" : "")}
            </div>
          </div>
          <div style={{ display: "flex", gap: ".85rem", alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: ".55rem", alignItems: "center", flexWrap: "wrap" }}>
            {imports.length > 0 && (
              <label style={{ display: "flex", alignItems: "center", gap: ".4rem", fontSize: ".75rem", color: "var(--text-muted)" }}>
                Program
                <select
                  style={{ ...selectStyle, minWidth: 220 }}
                  value={selectedImportId ?? ""}
                  onChange={(e) => switchProgram(e.target.value)}
                >
                  {imports.map((imp) => (
                    <option key={imp.id} value={imp.id}>
                      {imp.revision_label ?? imp.filename}
                      {imp.data_date ? ` (${fmtDateShort(imp.data_date)})` : ""}
                      {imp.id === currentImportId ? " — Current update" : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {wbsNodes.length > 0 && (
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
                <button className="btn btn-secondary btn-sm" onClick={expandAll}>
                  Expand all
                </button>
                <button className="btn btn-secondary btn-sm" onClick={collapseAll}>
                  Collapse all
                </button>
              </>
            )}
            {mode === "status" && (
              <>
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
              </>
            )}
          </div>
          <div className="segmented">
            <button className={mode === "status" ? "active" : ""} onClick={() => switchMode("status")}>
              Status &amp; Dates
            </button>
            <button className={mode === "manhours" ? "active" : ""} onClick={() => switchMode("manhours")}>
              Burned MH Loading
            </button>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            title={isFullscreen ? "Exit full screen (Esc)" : "Full screen"}
            aria-label={isFullscreen ? "Exit full screen" : "Full screen"}
            onClick={toggleFullscreen}
          >
            {isFullscreen ? <MinimizeIcon className="icon" /> : <MaximizeIcon className="icon" />}
          </button>
          </div>
        </div>

        {!isViewingCurrent && selectedImport && (
          <div className="banner">
            <div className="banner-text">
              Showing <b>{selectedImport.revision_label ?? selectedImport.filename}</b>, an earlier program — read-only.
              Switch <b>Program</b> back to the current update to record progress.
            </div>
          </div>
        )}

        {activities.length === 0 ? (
          <div className="card">
            <p className="empty-state">
              {isViewingCurrent
                ? "No activities yet — import a schedule from Program Library."
                : "No activities recorded for this program."}
            </p>
          </div>
        ) : (
          <>
            <FilterPanel
              criteria={criteria}
              onChange={setCriteria}
              nodes={wbsNodes}
              savedFilters={savedFilters}
              activeSavedId={activeSavedId}
              filterDirty={filterDirty}
              onSelectSaved={selectSaved}
              onClearSaved={clearSaved}
              onSaveNew={saveNewFilter}
              onUpdateActive={updateActiveFilter}
              onDeleteSaved={deleteSaved}
            />

            <div className="card progress-card" style={{ padding: 0 }}>
              <StatusDatesMode
                hidden={mode !== "status"}
                nodes={wbsNodes}
                activities={statusFiltered}
                dataDate={dataDate}
                canEdit={canEdit}
                snapshotOnly={!isViewingCurrent}
                sortByFloat={floatAsc}
                collapsed={collapsed}
                onToggle={toggleCollapse}
                onActivitiesUpdated={onActivitiesUpdated}
              />
              <ManhoursMode
                hidden={mode !== "manhours"}
                nodes={wbsNodes}
                activities={filtered}
                projectId={project.id}
                hasActiveBaseline={hasActiveBaseline && isViewingCurrent}
                collapsed={collapsed}
                onToggle={toggleCollapse}
                onDirtyChange={setManhoursDirty}
              />
            </div>
          </>
        )}
      </div>
    </>
  );
}
