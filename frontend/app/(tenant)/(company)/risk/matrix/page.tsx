"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { RiskItem, RiskStatusValue } from "@/lib/types";

const STATUSES: RiskStatusValue[] = ["open", "mitigating", "closed", "occurred"];

function cellClass(score: number): string {
  if (score >= 15) return "rm-crit";
  if (score >= 10) return "rm-warn";
  if (score <= 4) return "rm-good";
  return "rm-mid";
}

export default function RiskMatrixPage() {
  const { project } = useProjectContext();
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<Set<RiskStatusValue>>(new Set());
  const [cell, setCell] = useState<{ p: number; i: number } | null>(null);

  useEffect(() => {
    async function load() {
      if (!project) {
        setRisks([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        setRisks(await api.get<RiskItem[]>(`/projects/${project.id}/risks`));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load risks.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [project]);

  const filtered = useMemo(
    () => (statusFilter.size === 0 ? risks : risks.filter((r) => statusFilter.has(r.status))),
    [risks, statusFilter],
  );

  const byCell = useMemo(() => {
    const m = new Map<string, RiskItem[]>();
    for (const r of filtered) {
      const k = `${r.probability}:${r.impact}`;
      m.set(k, [...(m.get(k) ?? []), r]);
    }
    return m;
  }, [filtered]);

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
        <p className="login-error" style={{ maxWidth: 420 }}>{error}</p>
      </div>
    );
  }

  const selected = cell ? (byCell.get(`${cell.p}:${cell.i}`) ?? []) : [];

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>Risk Matrix</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Risk Matrix</div>
            <div className="page-desc">Probability × Impact, {filtered.length} risks</div>
          </div>
        </div>

        <div className="filter-bar" style={{ padding: ".2rem 0" }}>
          {STATUSES.map((s) => (
            <button
              key={s}
              className={`pick-chip${statusFilter.has(s) ? " selected" : ""}`}
              onClick={() =>
                setStatusFilter((prev) => {
                  const next = new Set(prev);
                  if (next.has(s)) next.delete(s);
                  else next.add(s);
                  return next;
                })
              }
            >
              {s}
            </button>
          ))}
        </div>

        <div className="card" style={{ padding: "1rem" }}>
          <div className="risk-matrix">
            <div className="rm-corner" />
            {[1, 2, 3, 4, 5].map((p) => (
              <div key={`ph-${p}`} className="rm-axis">P{p}</div>
            ))}
            {[5, 4, 3, 2, 1].map((impact) => (
              <Fragment key={`row-${impact}`}>
                <div className="rm-axis">I{impact}</div>
                {[1, 2, 3, 4, 5].map((prob) => {
                  const cellRisks = byCell.get(`${prob}:${impact}`) ?? [];
                  const active = cell?.p === prob && cell?.i === impact;
                  return (
                    <button
                      key={`c-${prob}-${impact}`}
                      className={`rm-cell ${cellClass(prob * impact)}${active ? " active" : ""}`}
                      onClick={() => setCell(active ? null : { p: prob, i: impact })}
                    >
                      <span className="rm-count">{cellRisks.length || ""}</span>
                      <span className="rm-codes">{cellRisks.slice(0, 4).map((r) => r.code).join(" ")}</span>
                    </button>
                  );
                })}
              </Fragment>
            ))}
          </div>
          <div style={{ fontSize: ".6875rem", color: "var(--text-muted)", marginTop: ".6rem" }}>
            Rows = Impact (5 at top) · Columns = Probability · tint by score band
          </div>
        </div>

        {cell && (
          <div className="card">
            <div className="card-head">
              <div className="card-title">
                P{cell.p} × I{cell.i} — {selected.length} risk{selected.length === 1 ? "" : "s"}
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <tbody>
                  {selected.map((r) => (
                    <tr key={r.id}>
                      <td className="mono">{r.code}</td>
                      <td>{r.title}</td>
                      <td>{r.status}</td>
                      <td>
                        <Link href="/risk/register" style={{ color: "var(--accent-strong)" }}>Open →</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
