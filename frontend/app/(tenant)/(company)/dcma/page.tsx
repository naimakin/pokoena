"use client";

import { Fragment, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { DcmaCheckResult, DcmaReport } from "@/lib/types";
import { ChevronDownIcon, ChevronUpIcon } from "@/components/icons";

const STATUS_CHIP: Record<DcmaCheckResult["status"], string> = {
  pass: "chip-good",
  warn: "chip-warn",
  fail: "chip-crit",
  not_tracked: "chip-neutral",
};

const STATUS_LABEL: Record<DcmaCheckResult["status"], string> = {
  pass: "Pass",
  warn: "Warn",
  fail: "Fail",
  not_tracked: "Not Tracked",
};

function scoreColor(status: DcmaReport["overall_status"]): string {
  if (status === "pass") return "var(--good)";
  if (status === "warn") return "var(--warn)";
  return "var(--crit)";
}

function formatValue(check: DcmaCheckResult): string {
  if (check.status === "not_tracked") return "—";
  if (check.unit === "index") return check.value.toFixed(2);
  if (check.unit === "%") return `${check.pct}%`;
  return `${check.value}`;
}

export default function DcmaPage() {
  const { project } = useProjectContext();
  const [report, setReport] = useState<DcmaReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    async function load() {
      if (!project) {
        setReport(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const dcmaReport = await api.get<DcmaReport>(`/projects/${project.id}/dcma`);
        setReport(dcmaReport);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load the DCMA report.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [project]);

  function toggle(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>DCMA 14-Point</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">DCMA 14-Point Check</div>
            <div className="page-desc">Schedule quality assessment per DCMA EA PAM 200.1</div>
          </div>
        </div>

        {!report || report.total_activities === 0 ? (
          <div className="card">
            <p className="empty-state">
              No schedule imported yet — upload a .xer file from Program Library to run the DCMA check.
            </p>
          </div>
        ) : (
          <>
            <div className="card" style={{ padding: "1.25rem 1.1rem", display: "flex", alignItems: "center", gap: "1.5rem" }}>
              <div
                style={{
                  width: 84,
                  height: 84,
                  borderRadius: "50%",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  border: `3px solid ${scoreColor(report.overall_status)}`,
                  flexShrink: 0,
                }}
              >
                <span className="num" style={{ fontSize: "1.375rem", fontWeight: 700, color: scoreColor(report.overall_status) }}>
                  {report.overall_score.toFixed(0)}
                </span>
                <span style={{ fontSize: ".5625rem", color: "var(--text-muted)", letterSpacing: ".05em" }}>
                  Score
                </span>
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: ".5rem", marginBottom: ".3rem" }}>
                  <span className={`chip ${STATUS_CHIP[report.overall_status]}`}>{STATUS_LABEL[report.overall_status]}</span>
                  <span style={{ fontSize: ".8125rem", fontWeight: 700 }}>Overall Schedule Health</span>
                </div>
                <div style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                  {report.total_activities} activities · {report.in_scope} in scope · computed{" "}
                  {new Date(report.computed_at).toLocaleString()}
                </div>
              </div>
            </div>

            <div className="card" style={{ marginTop: "1rem" }}>
              <div className="card-head">
                <div className="card-title">14 Checks</div>
                <div className="card-title-sub">Click a row to see affected activities</div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: "2rem" }}>#</th>
                      <th>Check</th>
                      <th>Status</th>
                      <th>Value</th>
                      <th style={{ width: "2rem" }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.checks.map((check) => {
                      const isOpen = expanded.has(check.id);
                      const hasDetails = check.details.length > 0;
                      return (
                        <Fragment key={check.id}>
                          <tr
                            onClick={() => hasDetails && toggle(check.id)}
                            style={{ cursor: hasDetails ? "pointer" : "default" }}
                          >
                            <td className="mono" style={{ color: "var(--text-muted)" }}>
                              {check.id}
                            </td>
                            <td>{check.name}</td>
                            <td>
                              <span className={`chip ${STATUS_CHIP[check.status]}`}>{STATUS_LABEL[check.status]}</span>
                            </td>
                            <td className="num">{formatValue(check)}</td>
                            <td>
                              {hasDetails &&
                                (isOpen ? (
                                  <ChevronUpIcon className="icon" style={{ width: 14, height: 14 }} />
                                ) : (
                                  <ChevronDownIcon className="icon" style={{ width: 14, height: 14 }} />
                                ))}
                            </td>
                          </tr>
                          {isOpen && hasDetails && (
                            <tr>
                              <td></td>
                              <td colSpan={4} style={{ paddingTop: 0 }}>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: ".35rem", paddingBottom: ".4rem" }}>
                                  {check.details.map((id) => (
                                    <span key={id} className="chip chip-neutral mono">
                                      {id}
                                    </span>
                                  ))}
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
