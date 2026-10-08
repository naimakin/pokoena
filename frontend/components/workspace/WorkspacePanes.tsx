"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { ChevronDownIcon } from "@/components/icons";
import type { Activity } from "@/lib/types";
import type { GridRow } from "@/lib/wbs-tree";
import { COLUMNS, type CellCtx, type ColKey, type ColumnDef } from "./columns";
import { barColor, ChartRow, GanttScale, GanttToolbar, type GanttViewToggles, type LensKey } from "./gantt";
import { HEAD_H_GANTT, HEAD_H_GRID, ROW_H } from "./model";
import { useGanttTimeline } from "./useGanttTimeline";
import { GridHead, GridRowCells } from "./WorkspaceGrid";

// Split pane: the activity grid on the left and, when switched on, the
// time-scaled Gantt on the right. Each pane is its own scroll container, with
// vertical scroll mirrored between them (syncScroll). Horizontal scroll is
// deliberately NOT mirrored — the grid scrolls through its columns while the
// chart scrolls through time. Without the Gantt the grid has the card to
// itself and Activity absorbs the spare width.

const MIN_LEFT_W = 220;
// Until the divider is dragged the grid takes a share of the card, not a fixed width.
const DEFAULT_LEFT_SHARE = "55%";

const DEFAULT_WIDTHS = Object.fromEntries(COLUMNS.map((c) => [c.key, c.width])) as Record<ColKey, number>;

export function WorkspacePanes({
  rows,
  columns,
  ganttOn,
  ganttActivities,
  dataDateMs,
  ctx,
  toggles,
  onToggles,
  onToggleBand,
  onActivityClick,
  emptyMessage,
}: {
  rows: GridRow[];
  /** Visible columns, in display order (Activity first). */
  columns: ColumnDef[];
  ganttOn: boolean;
  /** The activities the timeline spans (the filtered set). */
  ganttActivities: Activity[];
  dataDateMs: number | null;
  ctx: CellCtx;
  toggles: GanttViewToggles;
  onToggles: (patch: Partial<GanttViewToggles>) => void;
  onToggleBand: (wbsId: string) => void;
  onActivityClick: (a: Activity) => void;
  emptyMessage: string;
}) {
  const [lens, setLens] = useState<LensKey>("progress");
  const [leftW, setLeftW] = useState<number | null>(null);
  const [colWidths, setColWidths] = useState<Record<ColKey, number>>(DEFAULT_WIDTHS);
  // Measured inner (scrollbar-excluded) widths of the two panes: Activity
  // stretches to fill the left one, and the timeline always spans at least
  // the right one (and exactly it in fit mode).
  const [leftPaneW, setLeftPaneW] = useState(0);
  const [chartPaneW, setChartPaneW] = useState(0);

  const leftPaneRef = useRef<HTMLDivElement>(null);
  const rightPaneRef = useRef<HTMLDivElement>(null);
  const paneWrapRef = useRef<HTMLDivElement>(null);
  const scrollLock = useRef<"left" | "right" | null>(null);
  const releaseRaf = useRef<number | null>(null);

  const timeline = useGanttTimeline({
    activities: ganttActivities,
    dataDateMs,
    chartPaneW: ganttOn ? chartPaneW : 0,
    paneRef: rightPaneRef,
  });

  const headH = ganttOn ? HEAD_H_GANTT : HEAD_H_GRID;

  // The grid fills its pane: Activity absorbs whatever width the other columns
  // leave; below their combined width the pane scrolls horizontally instead
  // of squashing them.
  const baseGridWidth = columns.reduce((sum, c) => sum + colWidths[c.key], 0);
  const nameExtra = Math.max(0, leftPaneW - baseGridWidth);
  const shownWidths = useMemo<Record<ColKey, number>>(
    () => (nameExtra > 0 ? { ...colWidths, name: colWidths.name + nameExtra } : colWidths),
    [colWidths, nameExtra],
  );
  const gridWidth = baseGridWidth + nameExtra;

  const startColResize = useCallback(
    (e: ReactMouseEvent, key: ColKey) => {
      e.preventDefault();
      e.stopPropagation();
      const startX = e.clientX;
      // Start from the width on screen (Activity may be stretched to fill).
      const startW = shownWidths[key];
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
    [shownWidths],
  );

  // Drag the divider to trade grid width for chart width.
  const startSplitDrag = useCallback((e: ReactMouseEvent) => {
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

  // Track both panes' inner widths (divider drag, window resize, full screen,
  // a vertical scrollbar appearing, the Gantt switched on or off).
  const panesMounted = rows.length > 0;
  useLayoutEffect(() => {
    if (!panesMounted) return;
    const left = leftPaneRef.current;
    const right = rightPaneRef.current;
    if (!left) return;
    const measure = () => {
      setLeftPaneW(left.clientWidth);
      setChartPaneW(right ? right.clientWidth : 0);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(left);
    if (right) ro.observe(right);
    return () => ro.disconnect();
  }, [panesMounted, ganttOn]);

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

  // A freshly shown Gantt starts at the grid's scroll position.
  useLayoutEffect(() => {
    if (ganttOn && leftPaneRef.current && rightPaneRef.current) {
      rightPaneRef.current.scrollTop = leftPaneRef.current.scrollTop;
    }
  }, [ganttOn]);

  useEffect(
    () => () => {
      if (releaseRaf.current !== null) cancelAnimationFrame(releaseRaf.current);
    },
    [],
  );

  const colorOf = useCallback((a: Activity) => barColor(lens, a, ctx.baselineByActivity), [lens, ctx.baselineByActivity]);
  const contentHeight = headH + rows.length * ROW_H;

  return (
    <>
      {ganttOn && (
        <GanttToolbar
          lens={lens}
          onLens={setLens}
          toggles={toggles}
          onToggles={onToggles}
          zoomKey={timeline.zoomKey}
          isFit={timeline.isFit}
          onZoom={timeline.zoomTo}
          onFit={timeline.fitToScreen}
        />
      )}

      {rows.length === 0 ? (
        <p className="empty-state">{emptyMessage}</p>
      ) : (
        <div className={`gantt-panes ws-panes${ganttOn ? "" : " is-grid-only"}`} ref={paneWrapRef}>
          {/* ---- left: activity grid ---- */}
          <div
            className="gantt-pane ws-grid"
            ref={leftPaneRef}
            onScroll={ganttOn ? () => syncScroll("left") : undefined}
            style={
              ganttOn
                ? { width: leftW ?? DEFAULT_LEFT_SHARE, minWidth: MIN_LEFT_W, maxWidth: "calc(100% - 247px)" }
                : { flex: 1, minWidth: 0 }
            }
          >
            <div style={{ width: gridWidth, position: "relative" }}>
              <GridHead columns={columns} widths={shownWidths} height={headH} onResizeStart={startColResize} />
              {rows.map((row, idx) => (
                <GridRowCells
                  key={row.key}
                  row={row}
                  idx={idx}
                  columns={columns}
                  widths={shownWidths}
                  ctx={ctx}
                  onToggleBand={onToggleBand}
                  onActivityClick={onActivityClick}
                />
              ))}
            </div>
          </div>

          {ganttOn && (
            <>
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
                <div style={{ width: timeline.chartWidth, position: "relative", minHeight: contentHeight }}>
                  <GanttScale
                    height={headH}
                    width={timeline.chartWidth}
                    tiers={timeline.tiers}
                    markers={timeline.markers}
                    onZoomDrag={timeline.startZoomDrag}
                  />

                  {rows.map((row, idx) => (
                    <ChartRow
                      key={row.key}
                      row={row}
                      idx={idx}
                      chartWidth={timeline.chartWidth}
                      xFor={timeline.xFor}
                      colorOf={colorOf}
                      baselineByActivity={ctx.baselineByActivity}
                      bandBaseline={ctx.bandBaseline}
                      showLabels={timeline.pxPerDay >= 10}
                      onActivityClick={onActivityClick}
                    />
                  ))}

                  {/* Gridlines and markers are drawn once over the whole scroll
                      height instead of per row. Two layers, because each is its
                      own stacking context: gridlines sit under the bars, markers
                      over them. */}
                  <div className="gantt-overlay is-grid" style={{ top: headH }}>
                    {timeline.tiers.grid.map((s, i) => (
                      <i key={`g${i}`} className="gantt-gridline" style={{ left: s.x }} />
                    ))}
                  </div>
                  <div className="gantt-overlay is-markers" style={{ top: headH }}>
                    {timeline.markers.map((m, i) => (
                      <i
                        key={`m${i}`}
                        className={m.kind === "data" ? "gantt-marker is-data" : "gantt-marker"}
                        style={{ left: m.x }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
