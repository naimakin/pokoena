"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, BaselineStatus, SavedActivityFilter, ScheduleImport, WbsNode } from "@/lib/types";
import { applyFilter, EMPTY_CRITERIA, normalizeCriteria, type FilterCriteria } from "@/components/progress/filter";
import { FilterPanel } from "@/components/progress/FilterPanel";
import { StatusDatesMode } from "@/components/progress/StatusDatesMode";
import { ManhoursMode } from "@/components/progress/ManhoursMode";

type Mode = "status" | "manhours";
const MODE_KEY = "poko:progress:mode";
const VIEW = "progress";

export default function ProgressPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();

  const [activities, setActivities] = useState<Activity[]>([]);
  const [wbsNodes, setWbsNodes] = useState<WbsNode[]>([]);
  const [savedFilters, setSavedFilters] = useState<SavedActivityFilter[]>([]);
  const [hasActiveBaseline, setHasActiveBaseline] = useState(false);
  const [dataDate, setDataDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [mode, setMode] = useState<Mode>("status");
  const [criteria, setCriteriaState] = useState<FilterCriteria>(EMPTY_CRITERIA);
  const [activeSavedId, setActiveSavedId] = useState<string | null>(null);
  const [filterDirty, setFilterDirty] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const [statusDirty, setStatusDirty] = useState(0);
  const [manhoursDirty, setManhoursDirty] = useState(0);
  const totalDirty = statusDirty + manhoursDirty;

  useEffect(() => {
    try {
      const m = localStorage.getItem(MODE_KEY);
      if (m === "status" || m === "manhours") setMode(m);
    } catch {
      /* ignore */
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

  useEffect(() => {
    async function load() {
      if (!project) {
        setActivities([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      setCriteriaState(EMPTY_CRITERIA);
      setActiveSavedId(null);
      setFilterDirty(false);
      try {
        const [acts, nodes, baseline, imports] = await Promise.all([
          api.get<Activity[]>(`/activities?project_id=${project.id}`),
          api.get<WbsNode[]>(`/projects/${project.id}/wbs-nodes`),
          api.get<BaselineStatus>(`/projects/${project.id}/evm/baseline`),
          api.get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`),
        ]);
        setActivities(acts);
        setWbsNodes(nodes);
        setHasActiveBaseline(baseline.has_active);
        setDataDate(imports[0]?.data_date ?? null);
        loadFilters();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load activities.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [project, loadFilters]);

  const nodeByWbsId = useMemo(() => new Map(wbsNodes.map((n) => [n.wbs_id, n])), [wbsNodes]);
  const filtered = useMemo(
    () => applyFilter(activities, nodeByWbsId, criteria),
    [activities, nodeByWbsId, criteria],
  );

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

  const canEdit = true; // route enforces per-role; company_employee without edit gets 403 on save

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>Progress</b>
        </span>
        <div className="spacer" />
        {totalDirty > 0 && <span className="chip chip-warn">{totalDirty} unsaved</span>}
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Progress</div>
            <div className="page-desc">
              {filtered.length} of {activities.length} activities
              {dataDate ? ` · data date ${new Date(dataDate).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })}` : ""}
            </div>
          </div>
          <div className="segmented">
            <button className={mode === "status" ? "active" : ""} onClick={() => switchMode("status")}>
              Status &amp; Dates
            </button>
            <button className={mode === "manhours" ? "active" : ""} onClick={() => switchMode("manhours")}>
              Manhours (EVM)
            </button>
          </div>
        </div>

        {activities.length === 0 ? (
          <div className="card">
            <p className="empty-state">No activities yet — import a schedule from Program Library.</p>
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

            <div className="card" style={{ padding: 0 }}>
              <StatusDatesMode
                hidden={mode !== "status"}
                nodes={wbsNodes}
                activities={filtered}
                allActivities={activities}
                dataDate={dataDate}
                projectId={project.id}
                canEdit={canEdit}
                collapsed={collapsed}
                onToggle={toggleCollapse}
                onActivitiesUpdated={onActivitiesUpdated}
                onDirtyChange={setStatusDirty}
              />
              <ManhoursMode
                hidden={mode !== "manhours"}
                nodes={wbsNodes}
                activities={filtered}
                projectId={project.id}
                hasActiveBaseline={hasActiveBaseline}
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
