"use client";

import { useMemo, useState } from "react";
import { AlertTriangleIcon, CheckIcon } from "@/components/icons";
import { fmtP6Date } from "@/components/reporting/format";
import { findingFields, formatPct, metaFor, STATUS_CHIP, STATUS_LABEL } from "@/lib/dcma";
import type { DcmaCheckResult } from "@/lib/types";

type Column = { label: string; align?: "right"; mono?: boolean; render: (f: string[]) => string };

// How each POKO check reads: what its headline number counts, which finding
// field it breaks down by, and the columns of its findings table.
type Shape = {
  noun: string;
  count: (c: DcmaCheckResult) => number;
  of: string;
  breakdownField: number;
  columns: Column[];
};

const SHAPES: Record<number, Shape> = {
  15: {
    noun: "out-of-sequence links",
    count: (c) => c.details.length,
    of: "links",
    breakdownField: 1,
    columns: [
      { label: "Predecessor", mono: true, render: (f) => f[0] },
      { label: "Link", render: (f) => f[1] },
      { label: "Activity", mono: true, render: (f) => f[2] },
    ],
  },
  16: {
    noun: "activities with future actuals",
    count: (c) => c.value,
    of: "activities",
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
  noun: "findings",
  count: (c) => c.details.length,
  of: "items",
  breakdownField: -1,
  columns: [{ label: "Finding", mono: true, render: (f) => f.join(" / ") }],
};

export function PokoChecks({ checks }: { checks: DcmaCheckResult[] }) {
  const attention = checks.filter((c) => c.status !== "pass").length;
  return (
    <section className="poko">
      <div className="poko-head">
        <div>
          <div className="dcma-section-title">POKO checks</div>
          <div className="dcma-section-sub">
            Data and sequence checks beyond DCMA. Every finding is listed; none of them count toward the score.
          </div>
        </div>
        <span className={`chip ${attention > 0 ? "chip-warn" : "chip-good"}`}>
          {attention > 0 ? (
            <>
              <AlertTriangleIcon className="icon" /> {attention} of {checks.length} need attention
            </>
          ) : (
            <>
              <CheckIcon className="icon" /> All clean
            </>
          )}
        </span>
      </div>
      <div className="poko-grid">
        {checks.map((c) => (
          <PokoCard key={c.id} check={c} />
        ))}
      </div>
    </section>
  );
}

function PokoCard({ check }: { check: DcmaCheckResult }) {
  const m = metaFor(check);
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

  const count = shape.count(check);
  const clean = check.status === "pass";

  return (
    <div className={`card poko-card${clean ? " is-clean" : ""}`}>
      <div className="dcma-card-head">
        <span className="dcma-card-no mono">{String(check.id).padStart(2, "0")}</span>
        <span className="dcma-card-title">{m.title}</span>
        <span className={`chip ${STATUS_CHIP[check.status]}`}>
          {clean ? <CheckIcon className="icon" /> : <AlertTriangleIcon className="icon" />}
          {STATUS_LABEL[check.status]}
        </span>
      </div>

      <div className="poko-stat">
        <span className="poko-stat-value">{count.toLocaleString()}</span>
        <span className="poko-stat-label">
          {shape.noun}
          <span className="poko-stat-of">
            {count.toLocaleString()} of {check.denominator.toLocaleString()} {shape.of} · {formatPct(check.pct)}%
          </span>
        </span>
      </div>

      {breakdown.length > 0 && (
        <div className="poko-breakdown">
          {breakdown.map(([k, n]) => (
            <span key={k} className="chip chip-neutral">
              {k} <b className="num">{n.toLocaleString()}</b>
            </span>
          ))}
        </div>
      )}

      <p className="dcma-card-measures">{m.measures}</p>

      {rows.length === 0 ? (
        <div className="poko-clean">
          <CheckIcon className="icon" /> Nothing to report.
        </div>
      ) : (
        <div className="poko-findings">
          <div className="poko-findings-bar">
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search activity ID…"
              aria-label={`Search ${m.title} findings`}
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
      )}
    </div>
  );
}
