"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type RefObject,
} from "react";
import type { Activity } from "@/lib/types";
import { earliestDate, fmtDate, latestDate, MONTHS, MS_DAY } from "./model";

// The Gantt's time axis: zoom (fit / fixed levels / drag-zoom), the date range
// it spans, the two-tier timescale and the start / data date / end markers.
// Lifted out of the old Programme > Chart page unchanged in behaviour.

// In fit mode, room left on each side of the project span so the edge flags
// ("Project start" / "Project end", centred on their line) aren't clipped.
const FIT_PAD_PX = 56;

export const ZOOM_LEVELS = [
  { key: "day", pxPerDay: 32, label: "Day" },
  { key: "week", pxPerDay: 14, label: "Week" },
  { key: "month", pxPerDay: 5, label: "Month" },
  { key: "quarter", pxPerDay: 2, label: "Quarter" },
  { key: "year", pxPerDay: 0.6, label: "Year" },
] as const;

// "fit" = the whole project span fills the chart pane (the initial view, and
// re-fitted whenever the pane width changes); "custom" = drag-zoomed.
export type ZoomKey = (typeof ZOOM_LEVELS)[number]["key"] | "custom" | "fit";

/** One labelled band of the timescale, in chart pixels. */
export interface ScaleSeg {
  x: number;
  w: number;
  label: string;
}

export interface Marker {
  x: number;
  label: string;
  kind: "edge" | "data";
}

/** Months of empty timeline kept before the earliest and after the latest date
 *  at a fixed zoom, so the chart can be scrolled into the past and future. */
function padMonthsFor(pxPerDay: number): number {
  if (pxPerDay >= 20) return 1;
  if (pxPerDay >= 8) return 2;
  if (pxPerDay >= 2.5) return 3;
  if (pxPerDay >= 0.9) return 6;
  return 12;
}

export function useGanttTimeline({
  activities,
  dataDateMs,
  chartPaneW,
  paneRef,
}: {
  activities: Activity[];
  dataDateMs: number | null;
  /** Inner width of the chart pane (0 while it isn't shown). */
  chartPaneW: number;
  paneRef: RefObject<HTMLDivElement>;
}) {
  const [zoomKey, setZoomKey] = useState<ZoomKey>("fit");
  const [customPxPerDay, setCustomPxPerDay] = useState<number | null>(null);
  const dragRef = useRef<{ startX: number; startPxPerDay: number } | null>(null);
  // A moment in time (epoch ms) and where it sat in the pane, kept in place
  // across a rescale: the instant under the pointer while the timescale is
  // dragged (sticky until mouseup — P6 behaves the same way), or the centre of
  // the view when a zoom button is pressed (applied once).
  const zoomAnchor = useRef<{ ms: number; offsetX: number; sticky: boolean } | null>(null);
  const latestClientX = useRef(0);
  const dragRaf = useRef<number | null>(null);

  const { projStartMs, projEndMs } = useMemo(() => {
    let minMs: number | null = null;
    let maxMs: number | null = null;
    for (const a of activities) {
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
  }, [activities]);

  // The span the timeline must show, widened to take in the data date.
  const spanStartMs =
    projStartMs === null ? null : dataDateMs !== null ? Math.min(projStartMs, dataDateMs) : projStartMs;
  const spanEndMs = projEndMs === null ? null : dataDateMs !== null ? Math.max(projEndMs, dataDateMs) : projEndMs;

  const isFit = zoomKey === "fit";
  const fitPxPerDay = useMemo(() => {
    if (spanStartMs === null || spanEndMs === null || chartPaneW <= 0) return null;
    const days = Math.max((spanEndMs - spanStartMs) / MS_DAY, 1);
    const usable = Math.max(chartPaneW - 2 * FIT_PAD_PX, chartPaneW * 0.5);
    return usable / days;
  }, [spanStartMs, spanEndMs, chartPaneW]);

  const pxPerDay = isFit
    ? (fitPxPerDay ?? 5)
    : zoomKey === "custom"
      ? (customPxPerDay ?? 5)
      : ZOOM_LEVELS.find((z) => z.key === zoomKey)!.pxPerDay;

  // Fit: exactly the pane's width, project span centred in it. Fixed / drag
  // zoom: month-aligned, padded into the past and the future, and stretched
  // further at the end if that still wouldn't fill the pane.
  const { rangeStartMs, totalDays } = useMemo(() => {
    if (spanStartMs === null || spanEndMs === null) {
      return { rangeStartMs: null as number | null, totalDays: 0 };
    }
    if (isFit && fitPxPerDay !== null) {
      const sideDays = (chartPaneW - ((spanEndMs - spanStartMs) / MS_DAY) * fitPxPerDay) / 2 / fitPxPerDay;
      return { rangeStartMs: spanStartMs - sideDays * MS_DAY, totalDays: chartPaneW / fitPxPerDay };
    }
    const pad = padMonthsFor(pxPerDay);
    const min = new Date(spanStartMs);
    const max = new Date(spanEndMs);
    const start = Date.UTC(min.getUTCFullYear(), min.getUTCMonth() - pad, 1);
    const end = Date.UTC(max.getUTCFullYear(), max.getUTCMonth() + 1 + pad, 1);
    const days = Math.max(Math.ceil((end - start) / MS_DAY), Math.ceil(chartPaneW / pxPerDay), 1);
    return { rangeStartMs: start, totalDays: days };
  }, [spanStartMs, spanEndMs, isFit, fitPxPerDay, chartPaneW, pxPerDay]);

  const chartWidth = isFit && chartPaneW > 0 ? chartPaneW : Math.max(totalDays * pxPerDay, chartPaneW, 200);

  const xFor = useCallback(
    (ms: number | null | undefined) =>
      ms == null || rangeStartMs === null ? null : ((ms - rangeStartMs) / MS_DAY) * pxPerDay,
    [rangeStartMs, pxPerDay],
  );

  function fitToScreen() {
    zoomAnchor.current = null;
    setZoomKey("fit");
    if (paneRef.current) paneRef.current.scrollLeft = 0;
  }

  /** Switch to a fixed zoom level, keeping the date at the centre of the view. */
  function zoomTo(key: ZoomKey) {
    if (key === zoomKey) return;
    const pane = paneRef.current;
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
    (e: ReactMouseEvent) => {
      e.preventDefault();
      dragRef.current = { startX: e.clientX, startPxPerDay: pxPerDay };
      latestClientX.current = e.clientX;
      const pane = paneRef.current;
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
    [pxPerDay, rangeStartMs, paneRef],
  );

  // Keep the anchored instant in place while the chart rescales. Layout
  // effect, so the scroll lands before the frame paints.
  useLayoutEffect(() => {
    const anchor = zoomAnchor.current;
    const pane = paneRef.current;
    if (!anchor || !pane || rangeStartMs === null) return;
    pane.scrollLeft = Math.max(((anchor.ms - rangeStartMs) / MS_DAY) * pxPerDay - anchor.offsetX, 0);
    if (!anchor.sticky) zoomAnchor.current = null;
  }, [pxPerDay, rangeStartMs, zoomKey, paneRef]);

  useEffect(
    () => () => {
      if (dragRaf.current !== null) cancelAnimationFrame(dragRaf.current);
    },
    [],
  );

  // Two tiers, coarse over fine, chosen by scale so every zoom carries real
  // dates: month+year over days or week-start dates when zoomed in, year over
  // months or quarters further out, decade over years at the widest drag-zoom.
  const tiers = useMemo<{ top: ScaleSeg[]; bottom: ScaleSeg[]; grid: ScaleSeg[] }>(() => {
    if (rangeStartMs === null || !totalDays) return { top: [], bottom: [], grid: [] };
    const startMs = rangeStartMs;
    const endMs = startMs + totalDays * MS_DAY;
    const toX = (ms: number) => ((ms - startMs) / MS_DAY) * pxPerDay;
    const first = new Date(startMs);

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
    const out: Marker[] = [];
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

  return {
    zoomKey,
    isFit,
    pxPerDay,
    chartWidth,
    xFor,
    tiers,
    markers,
    fitToScreen,
    zoomTo,
    startZoomDrag,
  };
}
