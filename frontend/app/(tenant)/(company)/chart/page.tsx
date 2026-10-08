"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { api, ApiError } from "@/lib/api";
import { PageState } from "@/components/PageShell";
import { hoursPerDay } from "@/lib/duration";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, ActivityCodes, BaselineVariance, ScheduleImport, WbsNode } from "@/lib/types";
import { ChevronDownIcon, ExpandIcon, MaximizeIcon, MinimizeIcon, XIcon } from "@/components/icons";
import { applyFilter, criteriaIsEmpty, EMPTY_CRITERIA, type FilterCriteria } from "@/components/progress/filter";
import { QuickFilters } from "@/components/progress/QuickFilters";
import { WbsTreeSelect } from "@/components/progress/WbsTreeSelect";
import { buildGridRows, groupByLeaf, UNGROUPED_KEY, type GridRow } from "@/lib/wbs-tree";

// Hand-rolled split-pane Gantt (no charting library — every open-source one
// that virtualizes past a few thousand rows gates collapsible WBS grouping
// behind a paid tier, which is the one thing this page most needs).
//
// Layout is the industry-standard one: a resizable data grid on the left and a
// time-scaled chart on the right, each its own scroll container, with vertical
// scroll mirrored between them (see syncScroll). Horizontal scroll is
// deliberately NOT mirrored — the grid scrolls through its columns while the
// chart scrolls through time.

const ROW_H = 28;
// Grid header height = timescale height: two date tiers (coarse over fine)
// plus a lane for the project start / data date / project end flags.
const HEAD_H = 54;
const MS_DAY = 86_400_000;
const MIN_LEFT_W = 220;
// In fit mode, room left on each side of the project span so the edge flags
// ("Project start" / "Project end", centred on their line) aren't clipped.
const FIT_PAD_PX = 56;
const MILESTONE_TYPES = new Set(["TT_Mile", "TT_FinMile", "TT_StartMile"]);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Months of empty timeline kept before the earliest and after the latest date
 *  at a fixed zoom, so the chart can be scrolled into the past and future. */
function padMonthsFor(pxPerDay: number): number {
  if (pxPerDay >= 20) return 1;
  if (pxPerDay >= 8) return 2;
  if (pxPerDay >= 2.5) return 3;
  if (pxPerDay >= 0.9) return 6;
  return 12;
}

const ZOOM_LEVELS = [
  { key: "day", pxPerDay: 32, label: "Day" },
  { key: "week", pxPerDay: 14, label: "Week" },
  { key: "month", pxPerDay: 5, label: "Month" },
  { key: "quarter", pxPerDay: 2, label: "Quarter" },
  { key: "year", pxPerDay: 0.6, label: "Year" },
] as const;

// "fit" = the whole project span fills the chart pane (the initial view, and
// re-fitted whenever the pane width changes); "custom" = drag-zoomed.
type ZoomKey = (typeof ZOOM_LEVELS)[number]["key"] | "custom" | "fit";

// Which lens the bars are coloured by, and which metric the last grid column
// shows. Each maps onto data Poko actually holds, rather than mirroring a
// competitor's column names for their own sake.
const LENSES = [
  { key: "progress", label: "Progress", column: "% Complete" },
  { key: "criticality", label: "Criticality", column: "Total Float" },
  { key: "variance", label: "Baseline Variance", column: "Finish Var" },
] as const;
type LensKey = (typeof LENSES)[number]["key"];

/** One labelled band of the timescale (e.g. a year or month on the top tier,
 *  a month / quarter / week / day on the bottom tier), in chart pixels. */
interface ScaleSeg {
  x: number;
  w: number;
  label: string;
}

type ColKey =
  | "name"
  | "current_start"
  | "current_finish"
  | "baseline_start"
  | "baseline_finish"
  | "duration"
  | "metric";

const DEFAULT_COL_WIDTHS: Record<ColKey, number> = {
  name: 250,
  current_start: 96,
  current_finish: 96,
  baseline_start: 96,
  baseline_finish: 96,
  duration: 80,
  metric: 92,
};

const COL_ORDER: ColKey[] = [
  "name",
  "current_start",
  "current_finish",
  "baseline_start",
  "baseline_finish",
  "duration",
  "metric",
];

const COL_LABELS: Record<Exclude<ColKey, "metric">, string> = {
  name: "Name",
  current_start: "Current Start",
  current_finish: "Current Finish",
  baseline_start: "Baseline Start",
  baseline_finish: "Baseline Finish",
  duration: "Duration",
};

const selectStyle: CSSProperties = {
  fontSize: ".75rem",
  height: 28,
  padding: "0 .45rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text-primary)",
};

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

function isMilestone(a: Activity): boolean {
  return Boolean(a.task_type && MILESTONE_TYPES.has(a.task_type));
}

// A milestone is a single point in time, and P6 shows it against the one date it
// actually has: a Start Milestone has a start and no finish, a Finish Milestone
// the other way round. The .xer stores both (equal to each other) on every
// activity, so blank the one that isn't real instead of printing the same date
// in both columns.
function milestoneDates(
  a: Activity,
  start: string | null,
  finish: string | null,
): { start: string | null; finish: string | null } {
  if (a.task_type === "TT_Mile" || a.task_type === "TT_StartMile") return { start, finish: null };
  if (a.task_type === "TT_FinMile") return { start: null, finish };
  return { start, finish };
}

function earliestDate(a: Activity): string | null {
  return a.early_start ?? a.actual_start ?? a.planned_start ?? null;
}

function latestDate(a: Activity): string | null {
  return a.early_finish ?? a.actual_finish ?? a.planned_finish ?? null;
}

function durationDays(a: Activity): number | null {
  if (a.target_duration_hours != null) return Math.round(a.target_duration_hours / hoursPerDay(a));
  const s = earliestDate(a);
  const f = latestDate(a);
  if (!s || !f) return null;
  return Math.max(Math.round((new Date(f).getTime() - new Date(s).getTime()) / MS_DAY), 0);
}

function spanDays(start: string | null, finish: string | null): number | null {
  if (!start || !finish) return null;
  return Math.max(Math.round((new Date(finish).getTime() - new Date(start).getTime()) / MS_DAY), 0);
}

function Toggle({ label, on, onChange }: { label: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      className={`gantt-toggle${on ? " is-on" : ""}`}
      onClick={() => onChange(!on)}
    >
      <span className="gantt-toggle-track">
        <span className="gantt-toggle-knob" />
      </span>
      {label}
    </button>
  );
}

export default function GanttPage() {
  const { project } = useProjectContext();
  const [activities, setActivities] = useState<Activity[]>([]);
  const [nodes, setNodes] = useState<WbsNode[]>([]);
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  const [codes, setCodes] = useState<ActivityCodes | null>(null);
  const [variance, setVariance] = useState<BaselineVariance | null>(null);
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // --- filters ---
  // Same filters as Delivery > Activity Ledger (components/progress/filter.ts).
  const [criteria, setCriteria] = useState<FilterCriteria>(EMPTY_CRITERIA);
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [wbsOnly, setWbsOnly] = useState(false);
  const [milestonesOnly, setMilestonesOnly] = useState(false);

  // --- view ---
  const [lens, setLens] = useState<LensKey>("progress");
  const [zoomKey, setZoomKey] = useState<ZoomKey>("fit");
  const [customPxPerDay, setCustomPxPerDay] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [maxLevel, setMaxLevel] = useState(10);
  const [leftW, setLeftW] = useState(560);
  const [colWidths, setColWidths] = useState<Record<ColKey, number>>({ ...DEFAULT_COL_WIDTHS });
  const [isFullscreen, setIsFullscreen] = useState(false);
  // Measured inner (scrollbar-excluded) widths of the two panes: the grid's
  // Name column stretches to fill the left one, and the timeline always spans
  // at least the right one (and exactly it in fit mode).
  const [leftPaneW, setLeftPaneW] = useState(0);
  const [chartPaneW, setChartPaneW] = useState(0);

  const leftPaneRef = useRef<HTMLDivElement>(null);
  const rightPaneRef = useRef<HTMLDivElement>(null);
  const paneWrapRef = useRef<HTMLDivElement>(null);
  const scrollLock = useRef<"left" | "right" | null>(null);
  const releaseRaf = useRef<number | null>(null);
  const vizRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; startPxPerDay: number } | null>(null);
  // A moment in time (epoch ms) and where it sat in the pane, kept in place
  // across a rescale: the instant under the pointer while the timescale is
  // dragged (sticky until mouseup — P6 behaves the same way), or the centre of
  // the view when a zoom button is pressed (applied once). Absolute time, not
  // a day offset, because the timeline's start moves with the zoom padding.
  const zoomAnchor = useRef<{ ms: number; offsetX: number; sticky: boolean } | null>(null);
  const latestClientX = useRef(0);
  const dragRaf = useRef<number | null>(null);

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

  const currentImportId = useMemo(
    () => (imports.find((i) => i.is_current) ?? imports[0])?.id ?? null,
    [imports],
  );
  const selectedImport = useMemo(
    () => imports.find((i) => i.id === selectedImportId) ?? null,
    [imports, selectedImportId],
  );
  const isViewingCurrent = selectedImportId !== null && selectedImportId === currentImportId;
  // Kept as a number, not a Date: a fresh Date object every render would make
  // every memo that depends on the data date recompute on every render.
  const dataDateMs = useMemo(
    () => (selectedImport?.data_date ? new Date(selectedImport.data_date).getTime() : null),
    [selectedImport],
  );

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

  // Activity codes + baseline dates are project-level, not per-import: both are
  // best-effort, so a project with no codes or no locked baseline (423) just
  // renders without that column / filter rather than failing the whole page.
  useEffect(() => {
    if (!project) {
      setCodes(null);
      setVariance(null);
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
  }, [project]);

  const baselineByActivity = useMemo(() => {
    const m = new Map<string, { start: string | null; finish: string | null; finishVar: number | null }>();
    for (const r of variance?.rows ?? []) {
      m.set(r.activity_id, {
        start: r.baseline_start,
        finish: r.baseline_finish,
        finishVar: r.finish_variance_days,
      });
    }
    return m;
  }, [variance]);

  const nodeById = useMemo(() => {
    const m = new Map<string, WbsNode>();
    for (const n of nodes) m.set(n.wbs_id, n);
    return m;
  }, [nodes]);

  const knownWbsIds = useMemo(() => new Set(nodes.map((n) => n.wbs_id)), [nodes]);
  const deepestLevel = useMemo(
    () => (nodes.length ? Math.max(...nodes.map((n) => n.depth)) + 1 : 1),
    [nodes],
  );

  // code_value_id -> activity ids, as Sets for O(1) membership during filtering.
  const codeMembership = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const [codeValueId, ids] of Object.entries(codes?.assignments ?? {})) {
      m.set(codeValueId, new Set(ids));
    }
    return m;
  }, [codes]);

  const tagOptions = useMemo(
    () => [...new Set(activities.flatMap((a) => a.tags ?? []))].sort((a, b) => a.localeCompare(b)),
    [activities],
  );

  const filteredActivities = useMemo(() => {
    // Activity codes are keyed to live activity ids: they only filter the current update.
    let list = applyFilter(activities, nodeById, criteria, {
      dataDate: selectedImport?.data_date ?? null,
      codeMembership: isViewingCurrent ? codeMembership : null,
    });
    if (criticalOnly) list = list.filter((a) => a.is_critical);
    if (milestonesOnly) list = list.filter(isMilestone);
    return list;
  }, [activities, nodeById, criteria, selectedImport, isViewingCurrent, codeMembership, criticalOnly, milestonesOnly]);

  const hasUngrouped = useMemo(
    () => filteredActivities.some((a) => !a.wbs_path || !knownWbsIds.has(a.wbs_path)),
    [filteredActivities, knownWbsIds],
  );

  const activitiesByLeaf = useMemo(() => {
    const byLeaf = groupByLeaf(filteredActivities, knownWbsIds);
    for (const list of byLeaf.values()) {
      list.sort((x, y) => {
        const as = earliestDate(x) ?? "";
        const bs = earliestDate(y) ?? "";
        if (as !== bs) return as < bs ? -1 : 1;
        return x.external_id.localeCompare(y.external_id, undefined, { numeric: true });
      });
    }
    return byLeaf;
  }, [filteredActivities, knownWbsIds]);

  const allRows = useMemo(
    () => buildGridRows(nodes, activitiesByLeaf, collapsed),
    [nodes, activitiesByLeaf, collapsed],
  );
  const rows = useMemo(
    () => (wbsOnly ? allRows.filter((r) => r.kind === "band") : allRows),
    [allRows, wbsOnly],
  );

  // Baseline span per WBS band — same subtree walk buildGridRows does, but over
  // the baseline dates, which live outside the activity rows themselves.
  const bandBaseline = useMemo(() => {
    const m = new Map<string, { start: string | null; finish: string | null }>();
    if (baselineByActivity.size === 0) return m;
    for (const n of nodes) m.set(n.wbs_id, { start: null, finish: null });
    for (const n of nodes) {
      const direct = activitiesByLeaf.get(n.wbs_id) ?? [];
      if (direct.length === 0) continue;
      for (const a of direct) {
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
  }, [nodes, activitiesByLeaf, baselineByActivity]);

  const { projStartMs, projEndMs } = useMemo(() => {
    let minMs: number | null = null;
    let maxMs: number | null = null;
    for (const a of filteredActivities) {
      const s = earliestDate(a);
      const e = latestDate(a);
      if (s) {
        const t = new Date(s).getTime();
        if (minMs === null || t < minMs) minMs = t;
      }
      if (e) {
        const t = new Date(e).getTime();
        if (maxMs === null || t > maxMs) maxMs = t;
      }
    }
    if (minMs === null || maxMs === null) return { projStartMs: null, projEndMs: null };
    return { projStartMs: minMs as number | null, projEndMs: maxMs as number | null };
  }, [filteredActivities]);

  // The span the timeline must show: earliest start → latest finish (the
  // "Project end" flag), widened to take in the data date if it falls outside.
  const spanStartMs =
    projStartMs === null ? null : dataDateMs !== null ? Math.min(projStartMs, dataDateMs) : projStartMs;
  const spanEndMs =
    projEndMs === null ? null : dataDateMs !== null ? Math.max(projEndMs, dataDateMs) : projEndMs;

  const isFit = zoomKey === "fit";
  const fitPxPerDay = useMemo(() => {
    if (spanStartMs === null || spanEndMs === null || chartPaneW <= 0) return null;
    const spanDays = Math.max((spanEndMs - spanStartMs) / MS_DAY, 1);
    const usable = Math.max(chartPaneW - 2 * FIT_PAD_PX, chartPaneW * 0.5);
    return usable / spanDays;
  }, [spanStartMs, spanEndMs, chartPaneW]);

  const pxPerDay = isFit
    ? (fitPxPerDay ?? 5)
    : zoomKey === "custom"
      ? (customPxPerDay ?? 5)
      : ZOOM_LEVELS.find((z) => z.key === zoomKey)!.pxPerDay;

  // Timeline range. Fit: exactly the pane's width, project span centred in it.
  // Fixed / drag zoom: month-aligned, padded into the past and the future, and
  // stretched further at the end if that still wouldn't fill the pane.
  const { rangeStartMs, totalDays } = useMemo(() => {
    if (spanStartMs === null || spanEndMs === null) {
      return { rangeStartMs: null as number | null, totalDays: 0 };
    }
    if (isFit && fitPxPerDay !== null) {
      const sideDays = (chartPaneW - (spanEndMs - spanStartMs) / MS_DAY * fitPxPerDay) / 2 / fitPxPerDay;
      return {
        rangeStartMs: spanStartMs - sideDays * MS_DAY,
        totalDays: chartPaneW / fitPxPerDay,
      };
    }
    const pad = padMonthsFor(pxPerDay);
    const min = new Date(spanStartMs);
    const max = new Date(spanEndMs);
    const start = Date.UTC(min.getUTCFullYear(), min.getUTCMonth() - pad, 1);
    const end = Date.UTC(max.getUTCFullYear(), max.getUTCMonth() + 1 + pad, 1);
    const days = Math.max(Math.ceil((end - start) / MS_DAY), Math.ceil(chartPaneW / pxPerDay), 1);
    return { rangeStartMs: start, totalDays: days };
  }, [spanStartMs, spanEndMs, isFit, fitPxPerDay, chartPaneW, pxPerDay]);

  const chartWidth =
    isFit && chartPaneW > 0 ? chartPaneW : Math.max(totalDays * pxPerDay, chartPaneW, 200);

  const xFor = useCallback(
    (ms: number | null | undefined) =>
      ms == null || rangeStartMs === null ? null : ((ms - rangeStartMs) / MS_DAY) * pxPerDay,
    [rangeStartMs, pxPerDay],
  );

  function fitToScreen() {
    zoomAnchor.current = null;
    setZoomKey("fit");
    if (rightPaneRef.current) rightPaneRef.current.scrollLeft = 0;
  }

  /** Switch to a fixed zoom level, keeping the date at the centre of the view
   *  where it is (from fit, that's the middle of the project). */
  function zoomTo(key: ZoomKey) {
    if (key === zoomKey) return;
    const pane = rightPaneRef.current;
    if (pane && rangeStartMs !== null) {
      const offsetX = pane.clientWidth / 2;
      zoomAnchor.current = {
        ms: rangeStartMs + ((pane.scrollLeft + offsetX) / pxPerDay) * MS_DAY,
        offsetX,
        sticky: false,
      };
    }
    setZoomKey(key);
  }

  // Drag the timescale to zoom continuously (P6's "grab the scale and pull").
  const startZoomDrag = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragRef.current = { startX: e.clientX, startPxPerDay: pxPerDay };
      latestClientX.current = e.clientX;
      const pane = rightPaneRef.current;
      if (pane && rangeStartMs !== null) {
        const offsetX = e.clientX - pane.getBoundingClientRect().left;
        zoomAnchor.current = {
          ms: rangeStartMs + ((pane.scrollLeft + offsetX) / pxPerDay) * MS_DAY,
          offsetX,
          sticky: true,
        };
      }

      const onMove = (ev: MouseEvent) => {
        latestClientX.current = ev.clientX;
        if (dragRaf.current !== null) return;
        dragRaf.current = requestAnimationFrame(() => {
          dragRaf.current = null;
          const drag = dragRef.current;
          if (!drag) return;
          // P6 direction: pull the scale right to stretch it (zoom in), left
          // to compress it (zoom out).
          const dx = latestClientX.current - drag.startX;
          const next = Math.min(Math.max(drag.startPxPerDay * Math.pow(2, dx / 150), 0.15), 60);
          setCustomPxPerDay(next);
          setZoomKey("custom");
        });
      };
      const onUp = () => {
        dragRef.current = null;
        zoomAnchor.current = null;
        if (dragRaf.current !== null) {
          cancelAnimationFrame(dragRaf.current);
          dragRaf.current = null;
        }
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [pxPerDay, rangeStartMs],
  );

  // Keep the anchored instant in place while the chart rescales. Layout
  // effect, so the scroll lands before the frame paints.
  useLayoutEffect(() => {
    const anchor = zoomAnchor.current;
    const pane = rightPaneRef.current;
    if (!anchor || !pane || rangeStartMs === null) return;
    pane.scrollLeft = Math.max(((anchor.ms - rangeStartMs) / MS_DAY) * pxPerDay - anchor.offsetX, 0);
    if (!anchor.sticky) zoomAnchor.current = null;
  }, [pxPerDay, rangeStartMs, zoomKey]);

  // Drag the divider to trade grid width for chart width.
  const startSplitDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const wrap = paneWrapRef.current;
    if (!wrap) return;
    const wrapLeft = wrap.getBoundingClientRect().left;
    const onMove = (ev: MouseEvent) => {
      const next = ev.clientX - wrapLeft;
      setLeftW(Math.min(Math.max(next, MIN_LEFT_W), Math.max(wrap.clientWidth - 240, MIN_LEFT_W)));
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, []);

  // The grid fills its pane: Name (long activity names) absorbs whatever
  // width the other columns leave; below their combined width the pane
  // scrolls horizontally instead of squashing them.
  const baseGridWidth = COL_ORDER.reduce((sum, key) => sum + colWidths[key], 0);
  const nameExtra = Math.max(0, leftPaneW - baseGridWidth);
  const shownColWidths = useMemo<Record<ColKey, number>>(
    () => (nameExtra > 0 ? { ...colWidths, name: colWidths.name + nameExtra } : colWidths),
    [colWidths, nameExtra],
  );
  const gridWidth = baseGridWidth + nameExtra;

  const startColResize = useCallback(
    (e: React.MouseEvent, key: ColKey) => {
      e.preventDefault();
      e.stopPropagation();
      const startX = e.clientX;
      // Start from the width on screen (Name may be stretched to fill).
      const startW = shownColWidths[key];
      const onMove = (ev: MouseEvent) => {
        setColWidths((prev) => ({ ...prev, [key]: Math.max(startW + (ev.clientX - startX), 56) }));
      };
      const onUp = () => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [shownColWidths],
  );

  // Track both panes' inner widths (divider drag, window resize, full screen,
  // a vertical scrollbar appearing). Re-attached whenever the panes remount.
  const panesMounted = !loading && !error && rows.length > 0;
  useLayoutEffect(() => {
    if (!panesMounted) return;
    const left = leftPaneRef.current;
    const right = rightPaneRef.current;
    if (!left || !right) return;
    const measure = () => {
      setLeftPaneW(left.clientWidth);
      setChartPaneW(right.clientWidth);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(left);
    ro.observe(right);
    return () => ro.disconnect();
  }, [panesMounted]);

  // Mirror vertical scroll between the two panes. The lock stops the mirrored
  // assignment from bouncing straight back as a second scroll event.
  const syncScroll = useCallback((from: "left" | "right") => {
    if (scrollLock.current && scrollLock.current !== from) return;
    scrollLock.current = from;
    const src = from === "left" ? leftPaneRef.current : rightPaneRef.current;
    const dst = from === "left" ? rightPaneRef.current : leftPaneRef.current;
    if (src && dst && dst.scrollTop !== src.scrollTop) dst.scrollTop = src.scrollTop;
    if (releaseRaf.current !== null) cancelAnimationFrame(releaseRaf.current);
    releaseRaf.current = requestAnimationFrame(() => {
      scrollLock.current = null;
      releaseRaf.current = null;
    });
  }, []);

  useEffect(
    () => () => {
      if (releaseRaf.current !== null) cancelAnimationFrame(releaseRaf.current);
      if (dragRaf.current !== null) cancelAnimationFrame(dragRaf.current);
    },
    [],
  );

  // Fullscreen is driven by the browser, not by us: Esc and the window chrome
  // can both exit it without going through the button, so the button only ever
  // asks — `fullscreenchange` is what actually sets the state.
  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement === vizRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  function toggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => undefined);
    } else {
      vizRef.current?.requestFullscreen().catch(() => undefined);
    }
  }

  function applyMaxLevel(level: number) {
    setMaxLevel(level);
    if (level >= 10) {
      setCollapsed(new Set());
      return;
    }
    setCollapsed(new Set(nodes.filter((n) => n.depth + 1 >= level).map((n) => n.wbs_id)));
  }

  function toggleBand(wbsId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(wbsId)) next.delete(wbsId);
      else next.add(wbsId);
      return next;
    });
  }

  function clearFilters() {
    setCriteria(EMPTY_CRITERIA);
    setCriticalOnly(false);
    setWbsOnly(false);
    setMilestonesOnly(false);
  }

  const filtersActive = !criteriaIsEmpty(criteria) || criticalOnly || wbsOnly || milestonesOnly;
  const setCriteriaPatch = (patch: Partial<FilterCriteria>) => setCriteria((prev) => ({ ...prev, ...patch }));

  // --- timescale tiers -----------------------------------------------------
  // Two tiers, coarse over fine, chosen by scale so every zoom carries real
  // dates: month+year over days or week-start dates when zoomed in, year over
  // months or quarters further out, decade over years at the widest drag-zoom.
  const tiers = useMemo<{ top: ScaleSeg[]; bottom: ScaleSeg[]; grid: ScaleSeg[] }>(() => {
    if (rangeStartMs === null || !totalDays) return { top: [], bottom: [], grid: [] };
    const startMs = rangeStartMs;
    const endMs = startMs + totalDays * MS_DAY;
    const toX = (ms: number) => ((ms - startMs) / MS_DAY) * pxPerDay;
    const first = new Date(startMs);

    // Walk calendar units from `from`, `step(t)` giving the next boundary.
    function segs(from: number, step: (t: number) => number, label: (t: number) => string): ScaleSeg[] {
      const out: ScaleSeg[] = [];
      for (let t = from; t < endMs; ) {
        const next = step(t);
        const s = Math.max(t, startMs);
        const e = Math.min(next, endMs);
        if (e > s) out.push({ x: toX(s), w: toX(e) - toX(s), label: label(t) });
        t = next;
      }
      return out;
    }
    const ymd = (t: number) => new Date(t);
    const monthStart = Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), 1);
    const nextMonth = (n: number) => (t: number) => Date.UTC(ymd(t).getUTCFullYear(), ymd(t).getUTCMonth() + n, 1);
    const months = (label: (t: number) => string) => segs(monthStart, nextMonth(1), label);
    const years = (span: number) =>
      segs(
        Date.UTC(Math.floor(first.getUTCFullYear() / span) * span, 0, 1),
        (t) => Date.UTC(ymd(t).getUTCFullYear() + span, 0, 1),
        (t) => (span === 1 ? String(ymd(t).getUTCFullYear()) : `${ymd(t).getUTCFullYear()}s`),
      );
    const monthYear = (t: number) => `${MONTHS[ymd(t).getUTCMonth()]} ${ymd(t).getUTCFullYear()}`;

    let top: ScaleSeg[];
    let bottom: ScaleSeg[];
    if (pxPerDay >= 20) {
      top = months(monthYear);
      const dayStart = Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), first.getUTCDate());
      bottom = segs(dayStart, (t) => t + MS_DAY, (t) => String(ymd(t).getUTCDate()));
    } else if (pxPerDay >= 8) {
      // Weeks start Monday (ISO, as P6), labelled with that Monday's date.
      top = months(monthYear);
      const day0 = Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), first.getUTCDate());
      const monday = day0 - ((first.getUTCDay() + 6) % 7) * MS_DAY;
      const roomy = pxPerDay * 7 >= 48;
      bottom = segs(
        monday,
        (t) => t + 7 * MS_DAY,
        (t) => (roomy ? `${MONTHS[ymd(t).getUTCMonth()]} ${ymd(t).getUTCDate()}` : String(ymd(t).getUTCDate())),
      );
    } else if (pxPerDay >= 2.5) {
      top = years(1);
      bottom = months((t) => MONTHS[ymd(t).getUTCMonth()]);
    } else if (pxPerDay * 91 >= 20) {
      top = years(1);
      bottom = segs(
        Date.UTC(first.getUTCFullYear(), Math.floor(first.getUTCMonth() / 3) * 3, 1),
        nextMonth(3),
        (t) => `Q${Math.floor(ymd(t).getUTCMonth() / 3) + 1}`,
      );
    } else {
      top = years(10);
      bottom = years(1);
    }
    // Gridlines follow the fine tier unless its units are too narrow to be
    // anything but noise; then the coarse tier.
    const fineW = bottom.length > 2 ? bottom[1].w : 0;
    return { top, bottom, grid: fineW >= 40 ? bottom : top };
  }, [rangeStartMs, totalDays, pxPerDay]);

  const markers = useMemo(() => {
    const out: { x: number; label: string; kind: "edge" | "data" }[] = [];
    const startX = xFor(projStartMs);
    const endX = xFor(projEndMs);
    const ddX = xFor(dataDateMs);
    if (startX !== null) out.push({ x: startX, label: "Project start", kind: "edge" });
    if (ddX !== null && dataDateMs !== null) {
      out.push({ x: ddX, label: `Data date · ${fmtDate(new Date(dataDateMs).toISOString())}`, kind: "data" });
    }
    if (endX !== null) out.push({ x: endX, label: "Project end", kind: "edge" });
    return out;
  }, [xFor, projStartMs, projEndMs, dataDateMs]);

  // --- bar colour per lens -------------------------------------------------
  function barColor(a: Activity): string {
    if (lens === "criticality") {
      const tf = a.total_float_hours;
      if (a.is_critical || (tf != null && tf <= 0)) return "var(--crit)";
      if (tf == null) return "var(--info)";
      const days = tf / hoursPerDay(a);
      if (days <= 5) return "var(--warn)";
      if (days <= 20) return "var(--status-active)";
      return "var(--good)";
    }
    if (lens === "variance") {
      const v = baselineByActivity.get(a.id)?.finishVar;
      if (v == null) return "var(--info)";
      if (v > 0) return "var(--crit)";
      if (v < 0) return "var(--status-active)";
      return "var(--good)";
    }
    if (a.status === "complete") return "var(--good)";
    if (a.is_critical) return "var(--crit)";
    if (a.status === "in_progress") return "var(--status-active)";
    return "var(--info)";
  }

  function metricCell(a: Activity): string {
    if (lens === "criticality") {
      return a.total_float_hours != null ? `${(a.total_float_hours / hoursPerDay(a)).toFixed(1)}d` : "—";
    }
    if (lens === "variance") {
      const v = baselineByActivity.get(a.id)?.finishVar;
      return v == null ? "—" : v > 0 ? `+${v}d` : `${v}d`;
    }
    return `${a.percent_complete}%`;
  }

  const legend = useMemo(() => {
    if (lens === "criticality") {
      return [
        { color: "var(--crit)", label: "Critical (≤0d)" },
        { color: "var(--warn)", label: "≤5d float" },
        { color: "var(--status-active)", label: "≤20d float" },
        { color: "var(--good)", label: ">20d float" },
      ];
    }
    if (lens === "variance") {
      return [
        { color: "var(--crit)", label: "Late vs baseline" },
        { color: "var(--good)", label: "On baseline" },
        { color: "var(--status-active)", label: "Early" },
        { color: "var(--info)", label: "Not in baseline" },
      ];
    }
    return [
      { color: "var(--crit)", label: "Critical" },
      { color: "var(--status-active)", label: "In Progress" },
      { color: "var(--info)", label: "Not Started" },
      { color: "var(--good)", label: "Complete" },
    ];
  }, [lens]);

  const remaining = filteredActivities.filter((a) => a.status !== "complete").length;
  const metricLabel = LENSES.find((l) => l.key === lens)!.column;
  const contentHeight = HEAD_H + rows.length * ROW_H;

  if (loading) {
    return <PageState kind="loading" section="Programme" title="Gantt Chart" />;
  }
  if (error) {
    return <PageState kind="error" section="Programme" title="Gantt Chart" message={error} />;
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Programme
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Gantt Chart</div>
            <div className="page-desc">
              {dataLoading
                ? "Loading…"
                : `${filteredActivities.length} activities` +
                  (!isViewingCurrent ? " · read-only — showing an earlier program" : "")}
            </div>
          </div>
          {imports.length > 0 && (
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: ".4rem",
                fontSize: ".75rem",
                color: "var(--text-muted)",
              }}
            >
              Program
              <select
                style={{ ...selectStyle, minWidth: 220, height: 30 }}
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
        </div>

        {/* ---------------- filter bar ---------------- */}
        <div className="card">
          <QuickFilters
            criteria={criteria}
            set={setCriteriaPatch}
            dataDate={selectedImport?.data_date ?? null}
            codes={isViewingCurrent ? codes : null}
            codeMembership={isViewingCurrent ? codeMembership : null}
            tagOptions={tagOptions}
            lead={
              <>
                <input
                  className="qf-search"
                  value={criteria.search}
                  onChange={(e) => setCriteriaPatch({ search: e.target.value })}
                  placeholder="Search ID or name…"
                  aria-label="Search activity ID or name"
                />
                <WbsTreeSelect nodes={nodes} value={criteria.wbsId} onChange={(wbsId) => setCriteriaPatch({ wbsId })} />
              </>
            }
            tail={
              filtersActive && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={clearFilters}>
                  <XIcon className="icon" style={{ width: 13, height: 13 }} /> Clear all
                </button>
              )
            }
          />
        </div>

        {!isViewingCurrent && selectedImport && (
          <div className="banner">
            <div className="banner-text">
              Showing <b>{selectedImport.revision_label ?? selectedImport.filename}</b>, an earlier program —
              read-only.
            </div>
          </div>
        )}

        {/* ---------------- schedule visualization ---------------- */}
        <div
          ref={vizRef}
          className={`card gantt-viz${isFullscreen ? " is-fullscreen" : ""}`}
          style={{ overflow: "hidden" }}
        >
          <div className="card-head">
            <div>
              <div className="card-title">Schedule Visualization</div>
              <div className="card-title-sub">
                Remaining / total tasks: {remaining.toLocaleString()} / {filteredActivities.length.toLocaleString()}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
              <label className="gantt-maxlevel">
                Max Level
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={maxLevel}
                  onChange={(e) => applyMaxLevel(Number(e.target.value))}
                />
                <span className="mono">{maxLevel >= 10 ? "All" : maxLevel}</span>
              </label>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                title="Zoom so the whole date range fits the chart pane"
                aria-pressed={isFit}
                onClick={fitToScreen}
              >
                <ExpandIcon className="icon" /> Fit
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

          <div className="gantt-toolbar">
            <div className="gantt-radios">
              {LENSES.map((l) => (
                <label key={l.key} className="gantt-radio">
                  <input
                    type="radio"
                    name="gantt-lens"
                    checked={lens === l.key}
                    onChange={() => setLens(l.key)}
                  />
                  {l.label}
                </label>
              ))}
            </div>

            <select
              style={selectStyle}
              value=""
              onChange={(e) => {
                const v = e.target.value;
                if (v === "expand") {
                  setCollapsed(new Set());
                  setMaxLevel(10);
                } else if (v === "collapse") {
                  setCollapsed(
                    new Set([...nodes.map((n) => n.wbs_id), ...(hasUngrouped ? [UNGROUPED_KEY] : [])]),
                  );
                  setMaxLevel(1);
                } else if (v) {
                  applyMaxLevel(Number(v));
                }
                e.target.value = "";
              }}
            >
              <option value="">Expand / Collapse…</option>
              <option value="expand">Expand All</option>
              <option value="collapse">Collapse All</option>
              {Array.from({ length: deepestLevel }, (_, i) => i + 1).map((level) => (
                <option key={level} value={level}>
                  Collapse to level {level}
                </option>
              ))}
            </select>

            <Toggle label="Critical Path Only" on={criticalOnly} onChange={setCriticalOnly} />
            <Toggle label="WBS Only" on={wbsOnly} onChange={setWbsOnly} />
            <Toggle label="Milestones Only" on={milestonesOnly} onChange={setMilestonesOnly} />

            <div style={{ flex: 1 }} />

            <div className="gantt-legend">
              {legend.map(({ color, label }) => (
                <span key={label}>
                  <i style={{ background: color }} />
                  {label}
                </span>
              ))}
            </div>

            <div className="gantt-zoom">
              {ZOOM_LEVELS.map((z) => (
                <button
                  key={z.key}
                  type="button"
                  className={zoomKey === z.key ? "is-on" : undefined}
                  onClick={() => zoomTo(z.key)}
                >
                  {z.label}
                </button>
              ))}
            </div>
          </div>

          {rows.length === 0 ? (
            <p className="empty-state">
              {activities.length === 0
                ? isViewingCurrent
                  ? "No schedule imported yet — upload a .xer file from Programs."
                  : "No activities recorded for this program."
                : "No activities match your filters."}
            </p>
          ) : (
            <div className="gantt-panes" ref={paneWrapRef}>
              {/* ---- left: data grid ---- */}
              <div
                className="gantt-pane"
                ref={leftPaneRef}
                onScroll={() => syncScroll("left")}
                style={{ width: leftW, minWidth: MIN_LEFT_W }}
              >
                <div style={{ width: gridWidth, position: "relative" }}>
                  <div className="gantt-head" style={{ height: HEAD_H }}>
                    {COL_ORDER.map((key) => (
                      <div
                        key={key}
                        className={`gantt-head-cell${key === "name" ? "" : " is-num"}`}
                        style={{ width: shownColWidths[key] }}
                      >
                        <span>{key === "metric" ? metricLabel : COL_LABELS[key]}</span>
                        <span
                          className="gantt-col-resizer"
                          onMouseDown={(e) => startColResize(e, key)}
                          role="separator"
                          aria-label={`Resize ${key === "metric" ? metricLabel : COL_LABELS[key]} column`}
                        />
                      </div>
                    ))}
                  </div>

                  {rows.map((row, idx) => (
                    <GridRowCells
                      key={row.key}
                      row={row}
                      idx={idx}
                      colWidths={shownColWidths}
                      metricCell={metricCell}
                      baselineByActivity={baselineByActivity}
                      bandBaseline={bandBaseline}
                      onToggleBand={toggleBand}
                    />
                  ))}
                </div>
              </div>

              {/* ---- divider ---- */}
              <div
                className="gantt-split"
                onMouseDown={startSplitDrag}
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize the activity grid"
              >
                <span className="gantt-split-grip">
                  <ChevronDownIcon className="icon" style={{ width: 11, height: 11, transform: "rotate(90deg)" }} />
                  <ChevronDownIcon className="icon" style={{ width: 11, height: 11, transform: "rotate(-90deg)" }} />
                </span>
              </div>

              {/* ---- right: chart ---- */}
              <div className="gantt-pane gantt-pane-chart" ref={rightPaneRef} onScroll={() => syncScroll("right")}>
                <div style={{ width: chartWidth, position: "relative", minHeight: contentHeight }}>
                  <div
                    className="gantt-head gantt-scale"
                    style={{ height: HEAD_H, width: chartWidth }}
                    onMouseDown={startZoomDrag}
                    title="Drag the timescale to zoom"
                  >
                    {/* Coarse tier: the label sticks to the pane's left edge
                        so a long year/month stays named while scrolled into. */}
                    <div className="gantt-scale-tier is-upper">
                      {tiers.top.map((s, i) => (
                        <span key={`t${i}`} style={{ left: s.x, width: s.w }}>
                          {s.w >= 24 && <em className="gantt-scale-label">{s.label}</em>}
                        </span>
                      ))}
                    </div>
                    <div className="gantt-scale-tier is-lower">
                      {tiers.bottom.map((s, i) => (
                        <span key={`b${i}`} style={{ left: s.x, width: s.w }}>
                          {s.w >= s.label.length * 5.5 + 4 ? s.label : ""}
                        </span>
                      ))}
                    </div>
                    {/* Flag lane. The labels are pinned inside the sticky scale
                        so they stay visible while the rows scroll underneath. */}
                    <div className="gantt-scale-tier is-lane" />
                    <div className="gantt-marker-labels">
                      {markers.map((m, i) => (
                        <span
                          key={`ml${i}`}
                          className={m.kind === "data" ? "gantt-marker-pill is-data" : "gantt-marker-pill"}
                          style={{ left: m.x }}
                        >
                          {m.label}
                        </span>
                      ))}
                    </div>
                  </div>

                  {rows.map((row, idx) => (
                    <ChartRow
                      key={row.key}
                      row={row}
                      idx={idx}
                      chartWidth={chartWidth}
                      xFor={xFor}
                      barColor={barColor}
                      baselineByActivity={baselineByActivity}
                      bandBaseline={bandBaseline}
                      showLabels={pxPerDay >= 10}
                    />
                  ))}

                  {/* Gridlines and markers are drawn once over the whole scroll
                      height instead of per row. Two layers, because each is its
                      own stacking context: gridlines sit *under* the bars,
                      markers *over* them. */}
                  <div className="gantt-overlay is-grid" style={{ top: HEAD_H }}>
                    {tiers.grid.map((s, i) => (
                      <i key={`g${i}`} className="gantt-gridline" style={{ left: s.x }} />
                    ))}
                  </div>
                  <div className="gantt-overlay is-markers" style={{ top: HEAD_H }}>
                    {markers.map((m, i) => (
                      <i
                        key={`m${i}`}
                        className={m.kind === "data" ? "gantt-marker is-data" : "gantt-marker"}
                        style={{ left: m.x }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/** One row of the left-hand data grid. */
function GridRowCells({
  row,
  idx,
  colWidths,
  metricCell,
  baselineByActivity,
  bandBaseline,
  onToggleBand,
}: {
  row: GridRow;
  idx: number;
  colWidths: Record<ColKey, number>;
  metricCell: (a: Activity) => string;
  baselineByActivity: Map<string, { start: string | null; finish: string | null; finishVar: number | null }>;
  bandBaseline: Map<string, { start: string | null; finish: string | null }>;
  onToggleBand: (wbsId: string) => void;
}) {
  const even = idx % 2 === 0;

  if (row.kind === "band") {
    const bl = bandBaseline.get(row.wbsId);
    const cells: Record<ColKey, string> = {
      name: row.label,
      current_start: fmtDate(row.spanStart),
      current_finish: fmtDate(row.spanFinish),
      baseline_start: fmtDate(bl?.start ?? null),
      baseline_finish: fmtDate(bl?.finish ?? null),
      duration: spanDays(row.spanStart, row.spanFinish) != null ? `${spanDays(row.spanStart, row.spanFinish)} days` : "—",
      metric: `${row.avgPercent}%`,
    };
    return (
      <div className={`gantt-row is-band d${Math.min(row.depth, 4)}`} style={{ height: ROW_H }}>
        {COL_ORDER.map((key) => (
          <div key={key} className={`gantt-cell${key === "name" ? "" : " is-num"}`} style={{ width: colWidths[key] }}>
            {key === "name" ? (
              <span style={{ display: "flex", alignItems: "center", gap: ".35rem", paddingLeft: row.depth * 12 }}>
                <button
                  type="button"
                  className="gantt-caret"
                  onClick={() => onToggleBand(row.wbsId)}
                  aria-label={row.collapsed ? "Expand" : "Collapse"}
                  aria-expanded={!row.collapsed}
                  style={{ transform: row.collapsed ? "rotate(-90deg)" : "none" }}
                >
                  <ChevronDownIcon className="icon" style={{ width: 13, height: 13 }} />
                </button>
                <span className="gantt-cell-text" title={`${row.outlineCode} ${row.label}`}>
                  {row.label}
                </span>
              </span>
            ) : (
              <span className="mono">{cells[key]}</span>
            )}
          </div>
        ))}
      </div>
    );
  }

  const a = row.activity;
  const bl = baselineByActivity.get(a.id);
  const dur = durationDays(a);
  const current = milestoneDates(a, earliestDate(a), latestDate(a));
  const baseline = milestoneDates(a, bl?.start ?? null, bl?.finish ?? null);
  const cells: Record<ColKey, string> = {
    name: a.name,
    current_start: fmtDate(current.start),
    current_finish: fmtDate(current.finish),
    baseline_start: fmtDate(baseline.start),
    baseline_finish: fmtDate(baseline.finish),
    duration: dur != null ? `${dur} days` : "—",
    metric: metricCell(a),
  };

  return (
    <div className={`gantt-row${even ? "" : " is-odd"}`} style={{ height: ROW_H }}>
      {COL_ORDER.map((key) => (
        <div key={key} className={`gantt-cell${key === "name" ? "" : " is-num"}`} style={{ width: colWidths[key] }}>
          {key === "name" ? (
            <span style={{ display: "flex", alignItems: "center", gap: ".45rem", paddingLeft: row.depth * 12 + 17 }}>
              <span className="mono gantt-cell-id">{a.external_id}</span>
              <span className="gantt-cell-text" title={`${a.external_id} — ${a.name}`}>
                {a.name}
              </span>
            </span>
          ) : (
            <span className="mono">{cells[key]}</span>
          )}
        </div>
      ))}
    </div>
  );
}

/** One row of the right-hand chart: current bar, baseline ghost bar, milestone. */
function ChartRow({
  row,
  idx,
  chartWidth,
  xFor,
  barColor,
  baselineByActivity,
  bandBaseline,
  showLabels,
}: {
  row: GridRow;
  idx: number;
  chartWidth: number;
  xFor: (ms: number | null | undefined) => number | null;
  barColor: (a: Activity) => string;
  baselineByActivity: Map<string, { start: string | null; finish: string | null; finishVar: number | null }>;
  bandBaseline: Map<string, { start: string | null; finish: string | null }>;
  showLabels: boolean;
}) {
  function geom(start: string | null, finish: string | null) {
    const x = xFor(start ? new Date(start).getTime() : null);
    const xe = xFor(finish ? new Date(finish).getTime() : null);
    if (x === null || xe === null) return null;
    return { x: Math.max(x, 0), w: Math.max(xe - Math.max(x, 0), 2) };
  }

  if (row.kind === "band") {
    const cur = geom(row.spanStart, row.spanFinish);
    const bl = bandBaseline.get(row.wbsId);
    const base = bl ? geom(bl.start, bl.finish) : null;
    return (
      <div className={`gantt-row is-band d${Math.min(row.depth, 4)}`} style={{ height: ROW_H, width: chartWidth }}>
        {base && <div className="gantt-bar-baseline" style={{ left: base.x, width: base.w }} />}
        {cur && (
          <div className="gantt-bar-summary" style={{ left: cur.x, width: cur.w }}>
            <i style={{ left: 0 }} />
            <i style={{ right: 0 }} />
          </div>
        )}
      </div>
    );
  }

  const a = row.activity;
  const cur = geom(earliestDate(a), latestDate(a));
  const bl = baselineByActivity.get(a.id);
  const base = bl ? geom(bl.start, bl.finish) : null;
  const color = barColor(a);
  const milestone = isMilestone(a);
  const floatDays = a.total_float_hours != null ? (a.total_float_hours / hoursPerDay(a)).toFixed(1) : "—";
  const title =
    `${a.external_id}: ${a.name}\n` +
    `Current: ${fmtDate(earliestDate(a))} → ${fmtDate(latestDate(a))}\n` +
    (bl ? `Baseline: ${fmtDate(bl.start)} → ${fmtDate(bl.finish)}\n` : "") +
    `Total float: ${floatDays}d · Progress: ${a.percent_complete}%`;

  return (
    <div
      className={`gantt-row${idx % 2 === 0 ? "" : " is-odd"}`}
      style={{ height: ROW_H, width: chartWidth }}
      title={title}
    >
      {base && !milestone && <div className="gantt-bar-baseline" style={{ left: base.x, width: base.w }} />}
      {cur &&
        (milestone ? (
          <div className="gantt-milestone" style={{ left: cur.x - 6, background: color }} />
        ) : (
          <div
            className="gantt-bar"
            style={{
              left: cur.x,
              width: cur.w,
              background: color,
              opacity: a.status === "not_started" ? 0.72 : 1,
            }}
          >
            {a.status === "in_progress" && a.percent_complete > 0 && (
              <span className="gantt-bar-fill" style={{ width: `${Math.min(a.percent_complete, 100)}%` }} />
            )}
            {showLabels && cur.w > 60 && <span className="gantt-bar-label">{a.name}</span>}
          </div>
        ))}
    </div>
  );
}
