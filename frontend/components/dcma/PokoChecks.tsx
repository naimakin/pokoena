"use client";

import { useMemo, useState } from "react";
import { fmtP6Date } from "@/components/reporting/format";
import { findingFields } from "@/lib/dcma";
import type { DcmaCheckResult } from "@/lib/types";

// POKO's own checks (unscored) list every finding as " / "-separated fields;
// this is the panel a POKO check card opens: a breakdown, a search box and a
// table with labelled columns instead of a wall of ID chips.

type Column = { label: string; align?: "right"; mono?: boolean; render: (f: string[]) => string };

type Shape = { more: string; breakdownField: number; columns: Column[] };

const SHAPES: Record<number, Shape> = {
  15: {
    more: "out-of-sequence links",
    breakdownField: 1,
    columns: [
      { label: "Predecessor", mono: true, render: (f) => f[0] },
      { label: "Link", render: (f) => f[1] },
      { label: "Activity", mono: true, render: (f) => f[2] },
    ],
  },
  16: {
    more: "activities with future actuals",
    breakdownField: 1,
    columns: [
      { label: "Activity", mono: true, render: (f) => f[0] },
      { label: "Date", render: (f) => f[1] },
      { label: "Recorded as", mono: true, render: (f) => fmtP6Date(f[2]) },
      { label: "After data date", align: "right", mono: true, render: (f) => `+${f[3]}d` },
    ],
  },
};

const FALLBACK: Shape = {
  more: "findings",
  breakdownField: -1,
  columns: [{ label: "Finding", mono: true, render: (f) => f.join(" / ") }],
};

/** What a POKO card's "Show …" toggle names. */
export function findingsLabel(check: DcmaCheckResult): string {
  return (SHAPES[check.id] ?? FALLBACK).more;
}

export function PokoFindings({ check }: { check: DcmaCheckResult }) {
  const shape = SHAPES[check.id] ?? FALLBACK;
  const rows = useMemo(() => check.details.map(findingFields), [check.details]);
  const [q, setQ] = useState("");
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return needle ? rows.filter((f) => f.join(" ").toLowerCase().includes(needle)) : rows;
  }, [rows, q]);

  const breakdown = useMemo(() => {
    if (shape.breakdownField < 0) return [];
    const counts = new Map<string, number>();
    for (const f of rows) {
      const k = f[shape.breakdownField];
      counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows, shape.breakdownField]);

  return (
    <div className="poko-panel">
      {breakdown.length > 1 && (
        <div className="poko-breakdown">
          {breakdown.map(([k, n]) => (
            <span key={k} className="chip chip-neutral">
              {k} <b className="num">{n.toLocaleString()}</b>
            </span>
          ))}
        </div>
      )}
      <div className="poko-findings">
        <div className="poko-findings-bar">
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search activity ID…"
            aria-label="Search findings"
          />
          <span className="poko-findings-count">
            {shown.length === rows.length
              ? `${rows.length.toLocaleString()} rows`
              : `${shown.length.toLocaleString()} of ${rows.length.toLocaleString()}`}
          </span>
        </div>
        <div className="poko-table-wrap">
          <table className="poko-table">
            <thead>
              <tr>
                {shape.columns.map((col) => (
                  <th key={col.label} style={col.align ? { textAlign: col.align } : undefined}>
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 ? (
                <tr>
                  <td colSpan={shape.columns.length} className="empty-state">
                    No finding matches.
                  </td>
                </tr>
              ) : (
                shown.map((f, i) => (
                  <tr key={`${f.join("|")}-${i}`}>
                    {shape.columns.map((col) => (
                      <td
                        key={col.label}
                        className={col.mono ? "mono" : undefined}
                        style={col.align ? { textAlign: col.align } : undefined}
                      >
                        {col.render(f)}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
