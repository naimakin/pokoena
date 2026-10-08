"use client";

// Programme > Activity Workspace: the Activity Ledger and the Chart as one
// page. The left pane is the Ledger (saved + quick + advanced filters, WBS
// bands with their rollups, a row opens the Activity modal, Burned MH
// Loading); the right pane is the Gantt, switched on and off from the toolbar
// and remembered per browser. /progress, /chart and /gantt redirect here with
// their query string (?q=, ?filter=critical|overdue).

import { Suspense, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useSearchParams } from "next/navigation";
import { PageState } from "@/components/PageShell";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import { useCurrentUser } from "@/lib/user-context";
import { can } from "@/lib/permissions";
import { toDays } from "@/lib/duration";
import type { Activity, ActivityCodes, BaselineStatus, BaselineVariance, ScheduleImport, WbsNode } from "@/lib/types";
import { applyFilter, EMPTY_CRITERIA, type FilterCriteria } from "@/components/progress/filter";
import { FilterPanel } from "@/components/progress/FilterPanel";
import { ManhoursMode } from "@/components/progress/ManhoursMode";
import { ActivityModal } from "@/components/ActivityModal";
import { buildGridRows, groupByLeaf, UNGROUPED_KEY } from "@/lib/wbs-tree";
import { GanttIcon, MaximizeIcon, MinimizeIcon } from "@/components/icons";
import { NoProjectIllo } from "@/components/illustrations";
import { COLUMN_BY_KEY, DEFAULT_VISIBLE, parseVisible, type CellCtx, type ColKey } from "@/components/workspace/columns";
import { ColumnsMenu } from "@/components/workspace/ColumnsMenu";
import type { GanttViewToggles } from "@/components/workspace/gantt";
import {
  COLUMNS_PREF_KEY,
  earliestDate,
  fmtDate,
  fmtDateShort,
  GANTT_PREF_KEY,
  isGanttMilestone,
  readPref,
  writePref,
  type BaselineDates,
} from "@/components/workspace/model";
import { useSavedFilters } from "@/components/workspace/useSavedFilters";
import { WorkspacePanes } from "@/components/workspace/WorkspacePanes";

const TITLE = "Activity Workspace";
const SECTION = "Programme";

type Mode = "status" | "manhours";
type SortKey = "start" | "id" | "float";

const selectStyle: CSSProperties = {
  fontSize: ".75rem",
  height: 30,
  padding: "0 .5rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text-primary)",
};

const NO_TOGGLES: GanttViewToggles = { criticalOnly: false, wbsOnly: false, milestonesOnly: false };

/** ?filter= deep links (dashboard Project Health card) → risk indicators. */
function risksFor(preset: string | null): string[] {
  if (preset === "critical") return ["critical"];
  if (preset === "overdue") return ["overdue_finish"];
  return [];
}

export default function ActivityWorkspacePage() {
  // useSearchParams needs a Suspense boundary to prerender.
  return (
    <Suspense fallback={<PageState kind="loading" section={SECTION} title={TITLE} />}>
      <ActivityWorkspace />
    </Suspense>
  );
}

function ActivityWorkspace() {
  const { project } = useProjectContext();
  const user = useCurrentUser();
  const searchParams = useSearchParams();
  const qParam = searchParams.get("q") ?? "";
  const filterParam = searchParams.get("filter");

  const [activities, setActivities] = useState<Activity[]>([]);
  const [wbsNodes, setWbsNodes] = useState<WbsNode[]>([]);
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);
  const [hasActiveBaseline, setHasActiveBaseline] = useState(false);
  const [codes, setCodes] = useState<ActivityCodes | null>(null);
  const [variance, setVariance] = useState<BaselineVariance | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [mode, setMode] = useState<Mode>("status");
  const [criteria, setCriteriaState] = useState<FilterCriteria>(EMPTY_CRITERIA);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  // WBS depth shown, from the Max level slider; null = all levels open.
  const [maxLevel, setMaxLevel] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("start");
  const [toggles, setToggles] = useState<GanttViewToggles>(NO_TOGGLES);
  const [ganttPref, setGanttPref] = useState(true);
  const [visibleCols, setVisibleCols] = useState<ColKey[]>(DEFAULT_VISIBLE);
  const [openActivity, setOpenActivity] = useState<Activity | null>(null);
  // Only Burned MH Loading holds unsaved page-level state: status/date edits
  // happen in the Activity modal, which saves on its own.
  const [manhoursDirty, setManhoursDirty] = useState(0);

  // Full screen covers the whole working area (filters + workspace), so
  // filtering still works from there.
  const contentRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const saved = useSavedFilters({ projectId: project?.id ?? null, criteria, setCriteriaState });
  const { clearSaved } = saved;

  // Per-browser view preferences, read after mount (the server render can't
  // see localStorage).
  useEffect(() => {
    setGanttPref(readPref(GANTT_PREF_KEY) !== "off");
    setVisibleCols(parseVisible(readPref(COLUMNS_PREF_KEY)));
  }, []);

  function setGantt(on: boolean) {
    setGanttPref(on);
    writePref(GANTT_PREF_KEY, on ? "on" : "off");
  }
  function setColumns(next: ColKey[]) {
    setVisibleCols(next);
    writePref(COLUMNS_PREF_KEY, JSON.stringify(next));
  }

  // ?q= (header search) prefills the ID/name search; ?filter=critical|overdue
  // (dashboard) sets that risk indicator and sorts by float. Re-applied when
  // the project or the link changes — a fresh search from the header while
  // already here lands on the new activity.
  const projectId = project?.id ?? null;
  useEffect(() => {
    const risks = risksFor(filterParam);
    setCriteriaState({ ...EMPTY_CRITERIA, search: qParam, risks });
    clearSaved();
    if (risks.length > 0) {
      setMode("status");
      setSortKey("float");
    }
  }, [projectId, qParam, filterParam, clearSaved]);

  const canRecordManhours = can(user, "edit_progress");
  useEffect(() => {
    if (!canRecordManhours) setMode("status");
  }, [canRecordManhours]);

  // --- data ------------------------------------------------------------------
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
      setError(err instanceof ApiError ? err.message : "Failed to load activities.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    loadImports();
  }, [loadImports]);

  // Project-level and best-effort: no codes, no locked baseline (423) or no
  // access just leaves out that filter / column / mode instead of failing the
  // page.
  useEffect(() => {
    if (!project) {
      setCodes(null);
      setVariance(null);
      setHasActiveBaseline(false);
      return;
    }
    api
      .get<ActivityCodes>(`/projects/${project.id}/activity-codes`)
      .then(setCodes)
      .catch(() => setCodes(null));
    api
      .get<BaselineVariance>(`/projects/${project.id}/evm/baseline/variance`)
      .then(setVariance)
      .catch(() => setVariance(null));
    api
      .get<BaselineStatus>(`/projects/${project.id}/evm/baseline`)
      .then((b) => setHasActiveBaseline(b.has_active))
      .catch(() => setHasActiveBaseline(false));
  }, [project]);

  const currentImportId = useMemo(() => (imports.find((i) => i.is_current) ?? imports[0])?.id ?? null, [imports]);
  const selectedImport = useMemo(() => imports.find((i) => i.id === selectedImportId) ?? null, [imports, selectedImportId]);
  const isViewingCurrent = selectedImportId !== null && selectedImportId === currentImportId;
  const dataDate = selectedImport?.data_date ?? null;
  // A number, not a Date: a fresh Date each render would recompute every memo.
  const dataDateMs = useMemo(() => (dataDate ? new Date(dataDate).getTime() : null), [dataDate]);

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
    setMaxLevel(null);
  }, [loadData]);

  // --- unsaved guard ---------------------------------------------------------
  useEffect(() => {
    if (manhoursDirty === 0) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [manhoursDirty]);

  function switchProgram(id: string) {
    if (
      manhoursDirty > 0 &&
      !window.confirm(`Discard ${manhoursDirty} unsaved change${manhoursDirty === 1 ? "" : "s"} and switch programs?`)
    ) {
      return;
    }
    setSelectedImportId(id);
  }

  // --- filtering + rows ------------------------------------------------------
  // The Gantt is never shown while loading burned hours: that mode is a data
  // entry table, and the chart would only squeeze its inputs.
  const ganttShown = ganttPref && mode === "status";
  // The three view toggles live in the Gantt's toolbar, so they only apply
  // while it's on screen — a hidden control never keeps rows hidden.
  const activeToggles = ganttShown ? toggles : NO_TOGGLES;

  const nodeByWbsId = useMemo(() => new Map(wbsNodes.map((n) => [n.wbs_id, n])), [wbsNodes]);
  const knownWbsIds = useMemo(() => new Set(wbsNodes.map((n) => n.wbs_id)), [wbsNodes]);
  const deepestLevel = useMemo(() => (wbsNodes.length ? Math.max(...wbsNodes.map((n) => n.depth)) + 1 : 1), [wbsNodes]);
  // Activity codes are keyed to live activity ids: they only filter the current update.
  const codeMembership = useMemo(() => {
    if (!codes || !isViewingCurrent) return null;
    const m = new Map<string, Set<string>>();
    for (const [codeValueId, ids] of Object.entries(codes.assignments)) m.set(codeValueId, new Set(ids));
    return m;
  }, [codes, isViewingCurrent]);
  const tagOptions = useMemo(
    () => [...new Set(activities.flatMap((a) => a.tags ?? []))].sort((a, b) => a.localeCompare(b)),
    [activities],
  );

  const filtered = useMemo(
    () => applyFilter(activities, nodeByWbsId, criteria, { dataDate, codeMembership }),
    [activities, nodeByWbsId, criteria, dataDate, codeMembership],
  );
  const shown = useMemo(() => {
    let list = filtered;
    if (activeToggles.criticalOnly) list = list.filter((a) => a.is_critical);
    if (activeToggles.milestonesOnly) list = list.filter(isGanttMilestone);
    return list;
  }, [filtered, activeToggles.criticalOnly, activeToggles.milestonesOnly]);

  const completedCount = useMemo(() => activities.filter((a) => a.status === "complete").length, [activities]);
  const remaining = useMemo(() => shown.filter((a) => a.status !== "complete").length, [shown]);
  const hasUngrouped = useMemo(() => shown.some((a) => !a.wbs_path || !knownWbsIds.has(a.wbs_path)), [shown, knownWbsIds]);

  const activitiesByLeaf = useMemo(() => {
    const byLeaf = groupByLeaf(shown, knownWbsIds); // Activity ID order
    if (sortKey === "start") {
      for (const list of byLeaf.values()) {
        list.sort((x, y) => {
          const as = earliestDate(x) ?? "";
          const bs = earliestDate(y) ?? "";
          if (as !== bs) return as < bs ? -1 : 1;
          return x.external_id.localeCompare(y.external_id, undefined, { numeric: true });
        });
      }
    } else if (sortKey === "float") {
      const tf = (a: Activity) => toDays(a.total_float_hours, a) ?? Number.POSITIVE_INFINITY;
      for (const list of byLeaf.values()) list.sort((x, y) => tf(x) - tf(y));
    }
    return byLeaf;
  }, [shown, knownWbsIds, sortKey]);

  const allRows = useMemo(() => buildGridRows(wbsNodes, activitiesByLeaf, collapsed), [wbsNodes, activitiesByLeaf, collapsed]);
  const rows = useMemo(
    () => (activeToggles.wbsOnly ? allRows.filter((r) => r.kind === "band") : allRows),
    [allRows, activeToggles.wbsOnly],
  );

  const baselineByActivity = useMemo(() => {
    const m = new Map<string, BaselineDates>();
    for (const r of variance?.rows ?? []) {
      m.set(r.activity_id, { start: r.baseline_start, finish: r.baseline_finish, finishVar: r.finish_variance_days });
    }
    return m;
  }, [variance]);

  // Baseline span per WBS band — the same subtree walk buildGridRows does,
  // over the baseline dates.
  const bandBaseline = useMemo(() => {
    const m = new Map<string, { start: string | null; finish: string | null }>();
    if (baselineByActivity.size === 0) return m;
    for (const n of wbsNodes) m.set(n.wbs_id, { start: null, finish: null });
    for (const n of wbsNodes) {
      for (const a of activitiesByLeaf.get(n.wbs_id) ?? []) {
        const b = baselineByActivity.get(a.id);
        if (!b) continue;
        for (const ancestorId of n.path_ids) {
          const bucket = m.get(ancestorId);
          if (!bucket) continue;
          if (b.start && (bucket.start === null || b.start < bucket.start)) bucket.start = b.start;
          if (b.finish && (bucket.finish === null || b.finish > bucket.finish)) bucket.finish = b.finish;
        }
      }
    }
    return m;
  }, [wbsNodes, activitiesByLeaf, baselineByActivity]);

  const ctx = useMemo<CellCtx>(() => ({ dataDate, baselineByActivity, bandBaseline }), [dataDate, baselineByActivity, bandBaseline]);
  const columns = useMemo(() => visibleCols.map((k) => COLUMN_BY_KEY.get(k)!).filter(Boolean), [visibleCols]);

  // --- collapse --------------------------------------------------------------
  const toggleBand = useCallback((wbsId: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(wbsId)) next.delete(wbsId);
      else next.add(wbsId);
      return next;
    });
  }, []);

  // Level L shows WBS levels 1..L with the bands at level L folded; past the
  // deepest level everything is open ("All").
  function applyMaxLevel(level: number) {
    if (level > deepestLevel) {
      setMaxLevel(null);
      setCollapsed(new Set());
      return;
    }
    setMaxLevel(level);
    setCollapsed(new Set(wbsNodes.filter((n) => n.depth + 1 >= level).map((n) => n.wbs_id)));
  }

  const onActivitiesUpdated = useCallback((updated: Activity) => {
    setActivities((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
  }, []);

  // --- full screen -----------------------------------------------------------
  // Driven by the browser: Esc and the window chrome can leave full screen
  // without asking, so `fullscreenchange` is what sets the state.
  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement === contentRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => undefined);
    else contentRef.current?.requestFullscreen().catch(() => undefined);
  }

  if (loading) return <PageState kind="loading" section={SECTION} title={TITLE} />;
  if (error) return <PageState kind="error" section={SECTION} title={TITLE} message={error} />;
  if (!project) {
    return (
      <PageState
        kind="empty"
        section={SECTION}
        title={TITLE}
        emptyTitle="No project selected"
        message="Create or pick a project from the project switcher in the top bar."
        art={<NoProjectIllo />}
      />
    );
  }

  // Editing only ever applies to the live schedule — an earlier program is
  // viewed read-only through its frozen snapshot. The backend checks the same
  // capability on every write.
  const canEdit = isViewingCurrent && can(user, "edit_progress");

  const summary = dataLoading
    ? "Loading…"
    : (filtered.length !== activities.length
        ? `${filtered.length} of ${activities.length} activities shown`
        : `${activities.length} activities`) +
      ` · ${completedCount} completed` +
      (dataDate ? ` · data date ${fmtDate(dataDate)}` : "") +
      (!isViewingCurrent ? " · read-only — showing an earlier program" : "");

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">{SECTION}</span>
        <div className="spacer" />
        {manhoursDirty > 0 && <span className="chip chip-warn">{manhoursDirty} unsaved</span>}
      </div>
      <div ref={contentRef} className={`a-content fill-viewport ws-content${isFullscreen ? " is-fullscreen" : ""}`}>
        <div className="page-head">
          <div>
            <div className="page-title">{TITLE}</div>
            <div className="page-desc">{summary}</div>
          </div>
          {imports.length > 0 && (
            <label className="ws-field">
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
              {dataLoading
                ? "Loading…"
                : isViewingCurrent
                  ? "No activities yet — import a schedule from Programme Files."
                  : "No activities recorded for this program."}
            </p>
          </div>
        ) : (
          <>
            <FilterPanel
              criteria={criteria}
              onChange={saved.setCriteria}
              nodes={wbsNodes}
              savedFilters={saved.savedFilters}
              activeSavedId={saved.activeSavedId}
              filterDirty={saved.filterDirty}
              onSelectSaved={saved.selectSaved}
              onClearSaved={saved.clearSaved}
              onSaveNew={saved.saveNew}
              onUpdateActive={saved.updateActive}
              onDeleteSaved={saved.deleteSaved}
              dataDate={dataDate}
              codes={isViewingCurrent ? codes : null}
              codeMembership={codeMembership}
              tagOptions={tagOptions}
            />

            <div className="card ws-card">
              <div className="card-head ws-head">
                <div className="ws-head-group">
                  {canRecordManhours ? (
                    <div className="segmented" role="group" aria-label="Mode">
                      <button
                        type="button"
                        className={mode === "status" ? "active" : ""}
                        aria-pressed={mode === "status"}
                        onClick={() => setMode("status")}
                      >
                        Status &amp; Dates
                      </button>
                      <button
                        type="button"
                        className={mode === "manhours" ? "active" : ""}
                        aria-pressed={mode === "manhours"}
                        onClick={() => setMode("manhours")}
                      >
                        Burned MH Loading
                      </button>
                    </div>
                  ) : (
                    <div className="card-title">Activities</div>
                  )}
                  <span className="ws-tally">
                    Remaining / total tasks:{" "}
                    <span className="mono">
                      {remaining.toLocaleString()} / {shown.length.toLocaleString()}
                    </span>
                  </span>
                </div>

                <div className="ws-head-group">
                  <label className="gantt-maxlevel" title="How many WBS levels to show">
                    Max level
                    <input
                      type="range"
                      min={1}
                      max={deepestLevel + 1}
                      value={maxLevel ?? deepestLevel + 1}
                      onChange={(e) => applyMaxLevel(Number(e.target.value))}
                      aria-valuetext={maxLevel === null ? "All levels" : `Level ${maxLevel}`}
                    />
                    <span className="mono">{maxLevel === null ? "All" : maxLevel}</span>
                  </label>
                  {mode === "status" && (
                    <>
                      <label className="ws-field" title="Order of activities within each WBS band">
                        Order
                        <select style={selectStyle} value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
                          <option value="start">Start date</option>
                          <option value="id">Activity ID</option>
                          <option value="float">Total float</option>
                        </select>
                      </label>
                      <ColumnsMenu visible={visibleCols} onChange={setColumns} />
                    </>
                  )}
                  <span className="ws-sep" aria-hidden="true" />
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm ws-gantt-btn"
                    aria-pressed={ganttShown}
                    disabled={mode !== "status"}
                    title={
                      mode !== "status"
                        ? "The Gantt is hidden while loading burned hours"
                        : ganttPref
                          ? "Hide the Gantt chart"
                          : "Show the Gantt chart"
                    }
                    onClick={() => setGantt(!ganttPref)}
                  >
                    <GanttIcon className="icon" /> Gantt
                  </button>
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

              <div className="ws-body" hidden={mode !== "status"}>
                <WorkspacePanes
                  rows={rows}
                  columns={columns}
                  ganttOn={ganttShown}
                  ganttActivities={shown}
                  dataDateMs={dataDateMs}
                  ctx={ctx}
                  toggles={toggles}
                  onToggles={(patch) => setToggles((prev) => ({ ...prev, ...patch }))}
                  onToggleBand={toggleBand}
                  onActivityClick={setOpenActivity}
                  emptyMessage="No activities match your filters."
                />
              </div>

              {canRecordManhours && (
                <div className="ws-body ws-scroll" hidden={mode !== "manhours"}>
                  <ManhoursMode
                    hidden={false}
                    nodes={wbsNodes}
                    activities={filtered}
                    projectId={project.id}
                    hasActiveBaseline={hasActiveBaseline && isViewingCurrent}
                    collapsed={collapsed}
                    onToggle={toggleBand}
                    onDirtyChange={setManhoursDirty}
                  />
                </div>
              )}
            </div>
          </>
        )}

        <ActivityModal
          key={openActivity?.id ?? "none"}
          activity={openActivity}
          canEdit={canEdit}
          snapshotOnly={!isViewingCurrent}
          wbsNodes={wbsNodes}
          onClose={() => setOpenActivity(null)}
          onSaved={(updated) => {
            onActivitiesUpdated(updated);
            setOpenActivity(updated);
          }}
        />
      </div>
    </>
  );
}
