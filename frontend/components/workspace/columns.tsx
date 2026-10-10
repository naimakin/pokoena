// The Activity Workspace grid's columns: what each shows on an activity row
// and on a WBS band row. The Activity Ledger's columns (ID, Status, Start /
// Finish with P6's " A", Total Float badge, %, Criticality, Flags) plus the
// Chart's (Duration, Baseline Start / Finish, Finish variance).

import type { ReactNode } from "react";
import { AlertTriangleIcon, FlagIcon } from "@/components/icons";
import { floatClass } from "@/components/reporting/format";
import { criticalityChip } from "@/lib/criticality";
import { toDays } from "@/lib/duration";
import { displayFinish, displayStart, finishIsActual, startIsActual } from "@/lib/schedule-dates";
import type { Activity } from "@/lib/types";
import { bandFinishIsActual, bandStartIsActual, fmtUnitsPercent, type BandRow } from "@/lib/wbs-tree";
import { durationDays, earliestDate, fmtDate, milestoneDates, spanDays, type BaselineDates } from "./model";

export type ColKey =
  | "name"
  | "id"
  | "status"
  | "start"
  | "finish"
  | "duration"
  | "baseline_start"
  | "baseline_finish"
  | "finish_var"
  | "float"
  | "pct"
  | "criticality"
  | "flags";

export interface CellCtx {
  dataDate: string | null;
  baselineByActivity: Map<string, BaselineDates>;
  bandBaseline: Map<string, { start: string | null; finish: string | null }>;
}

export interface ColumnDef {
  key: ColKey;
  label: string;
  /** Header tooltip. */
  title?: string;
  width: number;
  align: "left" | "right";
  defaultOn: boolean;
  /** Always shown (Activity). */
  locked?: boolean;
  /** On a band row, folded into the WBS label cell (when it sits right after
   *  Activity), so the band's name and rollup have room. */
  mergeIntoLabel?: boolean;
  activity: (a: Activity, ctx: CellCtx) => ReactNode;
  band?: (row: BandRow, ctx: CellCtx) => ReactNode;
  /** What a header click sorts on; null (blank) always sorts last. */
  sortValue: (a: Activity, ctx: CellCtx) => string | number | null;
}

export type SortDir = "asc" | "desc";
export interface SortState {
  key: ColKey;
  dir: SortDir;
}
/** The page's starting order: by start date, as P6 opens a layout. */
export const DEFAULT_SORT: SortState = { key: "start", dir: "asc" };

const byId = (x: Activity, y: Activity) => x.external_id.localeCompare(y.external_id, undefined, { numeric: true });

/** Comparator for one column. Blanks stay at the bottom in both directions;
 *  ties fall back to Activity ID (ascending), so the order is stable. */
export function activityComparator(col: ColumnDef, dir: SortDir, ctx: CellCtx) {
  const sign = dir === "asc" ? 1 : -1;
  return (x: Activity, y: Activity) => {
    const a = col.sortValue(x, ctx);
    const b = col.sortValue(y, ctx);
    if (a === null || b === null) {
      if (a !== b) return a === null ? 1 : -1;
      return byId(x, y);
    }
    const c =
      typeof a === "number" && typeof b === "number"
        ? a - b
        : String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
    return c !== 0 ? c * sign : byId(x, y);
  };
}

const STATUS_ORDER: Record<string, number> = { not_started: 0, in_progress: 1, complete: 2 };

function baselineOf(a: Activity, ctx: CellCtx) {
  const bl = ctx.baselineByActivity.get(a.id);
  return milestoneDates(a, bl?.start ?? null, bl?.finish ?? null);
}

const STATUS_LABEL: Record<string, string> = {
  not_started: "Not Started",
  in_progress: "In Progress",
  complete: "Completed",
};
const STATUS_CHIP: Record<string, string> = {
  not_started: "chip-neutral",
  in_progress: "chip-active",
  complete: "chip-good",
};

// Total float is stored in hours; shown in the activity's own calendar days.
function fmtFloat(a: Activity): string {
  const days = toDays(a.total_float_hours, a);
  if (days === null) return "—";
  return `${days >= 0 ? "" : "-"}${Math.abs(days).toFixed(1)}d`;
}

const afterDataDate = (v: string | null | undefined, dataDate: string | null) =>
  Boolean(v && dataDate && v > dataDate.slice(0, 10));

/** A row is one line tall, so the Ledger's "after data date" note becomes a
 *  small marker with the full sentence on hover. */
function AfterDataDate({ what }: { what: string }) {
  return (
    <span className="ws-warn" title={`${what} is after the data date`} aria-label={`${what} is after the data date`}>
      <AlertTriangleIcon className="icon" />
    </span>
  );
}

function dateCell(date: string | null, actual: boolean, warn: ReactNode = null) {
  return (
    <span className="ws-date">
      <span className="mono">
        {fmtDate(date)}
        {actual && " A"}
      </span>
      {warn}
    </span>
  );
}

export const COLUMNS: ColumnDef[] = [
  {
    key: "name",
    sortValue: (a) => a.name,
    label: "Activity",
    width: 260,
    align: "left",
    defaultOn: true,
    locked: true,
    activity: (a) => (
      <span className="gantt-cell-text ws-name" title={a.name}>
        {a.name}
      </span>
    ),
  },
  {
    key: "id",
    sortValue: (a) => a.external_id,
    label: "Activity ID",
    width: 116,
    align: "left",
    defaultOn: true,
    mergeIntoLabel: true,
    activity: (a) => (
      <span className="mono gantt-cell-text ws-id" title={a.external_id}>
        {a.external_id}
      </span>
    ),
  },
  {
    key: "status",
    sortValue: (a) => STATUS_ORDER[a.status] ?? null,
    label: "Status",
    width: 100,
    align: "left",
    defaultOn: true,
    mergeIntoLabel: true,
    activity: (a) => <span className={`chip ${STATUS_CHIP[a.status]}`}>{STATUS_LABEL[a.status]}</span>,
  },
  {
    key: "start",
    sortValue: (a) => earliestDate(a),
    label: "Start",
    title: "A = actual date",
    width: 112,
    align: "left",
    defaultOn: true,
    activity: (a, { dataDate }) =>
      dateCell(
        displayStart(a),
        startIsActual(a, dataDate),
        a.status !== "not_started" && afterDataDate(a.actual_start, dataDate) ? <AfterDataDate what="Actual start" /> : null,
      ),
    band: (row, { dataDate }) => dateCell(row.spanStart, bandStartIsActual(row, dataDate)),
  },
  {
    key: "finish",
    sortValue: (a) => displayFinish(a),
    label: "Finish",
    title: "A = actual date",
    width: 112,
    align: "left",
    defaultOn: true,
    activity: (a, { dataDate }) =>
      dateCell(
        displayFinish(a),
        finishIsActual(a, dataDate),
        a.status === "complete" && afterDataDate(a.actual_finish, dataDate) ? <AfterDataDate what="Actual finish" /> : null,
      ),
    band: (row, { dataDate }) => dateCell(row.spanFinish, bandFinishIsActual(row, dataDate)),
  },
  {
    key: "duration",
    sortValue: (a) => durationDays(a),
    label: "Duration",
    title: "Original duration, in the activity's own calendar days",
    width: 84,
    align: "right",
    defaultOn: false,
    activity: (a) => {
      const d = durationDays(a);
      return <span className="mono">{d != null ? `${d} days` : "—"}</span>;
    },
    band: (row) => {
      const d = spanDays(row.spanStart, row.spanFinish);
      return <span className="mono">{d != null ? `${d} days` : "—"}</span>;
    },
  },
  {
    key: "baseline_start",
    sortValue: (a, ctx) => baselineOf(a, ctx).start,
    label: "Baseline Start",
    width: 108,
    align: "left",
    defaultOn: false,
    activity: (a, { baselineByActivity }) => {
      const bl = baselineByActivity.get(a.id);
      return <span className="mono">{fmtDate(milestoneDates(a, bl?.start ?? null, bl?.finish ?? null).start)}</span>;
    },
    band: (row, { bandBaseline }) => <span className="mono">{fmtDate(bandBaseline.get(row.wbsId)?.start ?? null)}</span>,
  },
  {
    key: "baseline_finish",
    sortValue: (a, ctx) => baselineOf(a, ctx).finish,
    label: "Baseline Finish",
    width: 108,
    align: "left",
    defaultOn: false,
    activity: (a, { baselineByActivity }) => {
      const bl = baselineByActivity.get(a.id);
      return <span className="mono">{fmtDate(milestoneDates(a, bl?.start ?? null, bl?.finish ?? null).finish)}</span>;
    },
    band: (row, { bandBaseline }) => <span className="mono">{fmtDate(bandBaseline.get(row.wbsId)?.finish ?? null)}</span>,
  },
  {
    key: "finish_var",
    sortValue: (a, { baselineByActivity }) => baselineByActivity.get(a.id)?.finishVar ?? null,
    label: "Finish Var",
    title: "Finish variance against the active baseline, in days (+ = later than baseline)",
    width: 84,
    align: "right",
    defaultOn: false,
    activity: (a, { baselineByActivity }) => {
      const v = baselineByActivity.get(a.id)?.finishVar;
      return <span className="mono">{v == null ? "—" : v > 0 ? `+${v}d` : `${v}d`}</span>;
    },
  },
  {
    key: "float",
    sortValue: (a) => toDays(a.total_float_hours, a),
    label: "Total Float",
    width: 90,
    align: "right",
    defaultOn: true,
    activity: (a) => <span className={`mono ${floatClass(toDays(a.total_float_hours, a))}`}>{fmtFloat(a)}</span>,
  },
  {
    key: "pct",
    sortValue: (a) => a.percent_complete ?? null,
    label: "%",
    title: "% complete; on a WBS row, units % (Σ actual / Σ budgeted labor hours of the activities shown)",
    width: 72,
    align: "right",
    defaultOn: true,
    activity: (a) => <span className="mono">{a.percent_complete}%</span>,
    band: (row) => (
      <span className="mono" title="Units % complete: Σ actual / Σ budgeted labor hours of the activities shown">
        {fmtUnitsPercent(row)}
      </span>
    ),
  },
  {
    key: "criticality",
    sortValue: (a) => a.criticality_score ?? null,
    label: "Criticality",
    title: "Criticality Score (0-100): total float, duration, free float and site risk",
    width: 86,
    align: "right",
    defaultOn: true,
    activity: (a) =>
      a.criticality_score != null ? (
        <span className={`chip ${criticalityChip(a)}`}>{a.criticality_score}</span>
      ) : (
        <span className="mono">—</span>
      ),
  },
  {
    key: "flags",
    sortValue: (a) => (a.is_important ? 1000 : 0) + (a.tags?.length ?? 0) + (a.percent_complete === 100 && !a.actual_finish ? 1 : 0),
    label: "Flags",
    width: 132,
    align: "left",
    defaultOn: true,
    activity: (a) => {
      const tagCount = a.tags?.length ?? 0;
      return (
        <span className="pg-flags ws-flags">
          {a.is_important && (
            <span className="chip chip-warn" title="Flagged as important">
              <FlagIcon className="icon" style={{ width: 10, height: 10 }} />
            </span>
          )}
          {tagCount > 0 && (
            <span className="chip chip-neutral" title={(a.tags ?? []).join(", ")}>
              {tagCount} tag{tagCount === 1 ? "" : "s"}
            </span>
          )}
          {a.percent_complete === 100 && !a.actual_finish && (
            <span className="pg-warn" title="100% complete but no actual finish">
              100% · no finish
            </span>
          )}
        </span>
      );
    },
  },
];

export const COLUMN_BY_KEY = new Map(COLUMNS.map((c) => [c.key, c]));
export const DEFAULT_VISIBLE: ColKey[] = COLUMNS.filter((c) => c.defaultOn).map((c) => c.key);

/** Parse the stored column choice, falling back to the default on anything odd. */
export function parseVisible(raw: string | null): ColKey[] {
  if (!raw) return DEFAULT_VISIBLE;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_VISIBLE;
    const keys = parsed.filter((k): k is ColKey => typeof k === "string" && COLUMN_BY_KEY.has(k as ColKey));
    // Canonical order, Activity always first, whatever order was stored.
    return COLUMNS.map((c) => c.key).filter((k) => k === "name" || keys.includes(k));
  } catch {
    return DEFAULT_VISIBLE;
  }
}
