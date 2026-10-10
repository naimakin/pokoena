"use client";

// Shared pieces of the dashboard charts (Gauge, rings, bars, monthly combo):
// container measuring, compact number / money formatting and the tone bands.
// Hand-rolled SVG like ProgressCurveChart — no chart library in this project.

import { useEffect, useRef, useState, type ReactNode } from "react";

export type VizTone = "good" | "warn" | "crit" | "neutral";

/** Width of a box, kept current with a ResizeObserver; 0 until measured. */
export function useMeasuredWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(Math.floor(el.clientWidth));
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Same bands as the dashboard's SPI tone, on actual ÷ planned. */
export function ratioTone(actual: number | null | undefined, planned: number | null | undefined): VizTone {
  if (actual == null || planned == null) return "neutral";
  if (planned <= 0) return actual > 0 ? "good" : "neutral";
  const r = actual / planned;
  if (r >= 0.95) return "good";
  if (r >= 0.85) return "warn";
  return "crit";
}

/** 1,234 · 12.3k · 1.2M — en-US whatever the browser locale. */
export function fmtCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}${trim(abs / 1e9)}B`;
  if (abs >= 1e6) return `${sign}${trim(abs / 1e6)}M`;
  if (abs >= 1e4) return `${sign}${trim(abs / 1e3)}k`;
  return `${sign}${Math.round(abs).toLocaleString("en-US")}`;
}

function trim(v: number): string {
  return (v >= 100 ? Math.round(v) : Math.round(v * 10) / 10).toString();
}

const CURRENCY_SYMBOL: Record<string, string> = { EUR: "€", USD: "$", GBP: "£", TRY: "₺" };

export function currencySymbol(code: string): string {
  return CURRENCY_SYMBOL[code] ?? `${code} `;
}

export function fmtMoney(value: number | null | undefined, currency: string): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value < 0 ? "-" : ""}${currencySymbol(currency)}${fmtCompact(Math.abs(value))}`;
}

export function fmtHours(value: number | null | undefined): string {
  return value == null ? "—" : `${fmtCompact(value)} h`;
}

export function pctOf(part: number, whole: number): number | null {
  return whole > 0 ? (part / whole) * 100 : null;
}

/** "-6.2 pts" / "+1.0 pts" */
export function fmtPts(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const r = Math.round(value * 10) / 10;
  return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toFixed(1)} pts`;
}

export interface VizTipRow {
  label: string;
  value: ReactNode;
  /** Series key ("planned", "actual", "cost", or a status tone) — drawn as a short line. */
  swatch?: string;
  /** A share in %: drawn as a mini bar under the row, filled in the swatch's colour. */
  pct?: number | null;
  /** A second share marked on that bar as a tick (the plan, against an actual). */
  markPct?: number | null;
  /** Colour the value text: "warn" / "crit" only for a genuinely bad gap. */
  tone?: VizTone;
}

/** Floating tooltip box, positioned by the caller inside a relative parent.
 *  Values lead (bold, ink), labels follow; a row with `pct` also draws its
 *  share as a mini bar, with `markPct` as a tick — so a % reads at a glance. */
export function VizTip({
  x,
  y,
  flip,
  title,
  rows,
}: {
  x: number;
  y: number;
  flip: boolean;
  title: ReactNode;
  rows: VizTipRow[];
}) {
  const clamp = (v: number) => Math.min(Math.max(v, 0), 100);
  return (
    <div
      className="viz-tip"
      role="status"
      aria-live="polite"
      style={{ left: x, top: y, transform: flip ? "translateX(calc(-100% - 12px))" : "translateX(12px)" }}
    >
      <div className="viz-tip-title">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className={`viz-tip-row${r.pct != null ? " has-bar" : ""}`}>
          <span className="viz-tip-line">
            {r.swatch && <i className={`viz-tip-key is-${r.swatch}`} aria-hidden="true" />}
            {r.label}
            <b className={`num${r.tone === "warn" || r.tone === "crit" ? ` tone-${r.tone}` : ""}`}>{r.value}</b>
          </span>
          {r.pct != null && (
            <span className="viz-tip-bar" aria-hidden="true">
              <span className={`viz-tip-fill is-${r.swatch ?? "actual"}`} style={{ width: `${clamp(r.pct)}%` }} />
              {r.markPct != null && <span className="viz-tip-mark" style={{ left: `${clamp(r.markPct)}%` }} />}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

/** Tooltip position inside `box` for a pointer event: beside the pointer,
 *  flipped to its left on the right half so it never runs off the card. */
export function tipAt(e: { clientX: number; clientY: number }, box: Element) {
  const r = box.getBoundingClientRect();
  const x = e.clientX - r.left;
  return { x, y: e.clientY - r.top + 12, flip: x > r.width / 2 };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-03" → "Mar 26" */
export function fmtMonthShort(key: string): string {
  return `${MONTHS[Number(key.slice(5, 7)) - 1]} ${key.slice(2, 4)}`;
}

/** "2026-03" → "Mar 2026" */
export function fmtMonthLong(key: string): string {
  return `${MONTHS[Number(key.slice(5, 7)) - 1]} ${key.slice(0, 4)}`;
}
