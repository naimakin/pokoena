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

/** Floating tooltip box, positioned by the caller inside a relative parent. */
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
  rows: { swatch?: string; label: string; value: ReactNode }[];
}) {
  return (
    <div
      className="viz-tip"
      role="status"
      aria-live="polite"
      style={{ left: x, top: y, transform: flip ? "translateX(calc(-100% - 12px))" : "translateX(12px)" }}
    >
      <div className="viz-tip-title">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="viz-tip-row">
          {r.swatch && <i className={`viz-key is-${r.swatch}`} aria-hidden="true" />}
          {r.label}
          <b className="num">{r.value}</b>
        </div>
      ))}
    </div>
  );
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
