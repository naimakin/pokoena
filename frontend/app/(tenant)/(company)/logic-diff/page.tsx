"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { api, ApiError } from "@/lib/api";
import type { LogicDiffChangeType, LogicDiffReport, Project, ScheduleImport } from "@/lib/types";
import { ArrowRightIcon, CompareIcon } from "@/components/icons";

const CHANGE_CHIP: Record<LogicDiffChangeType, string> = {
  ADDED: "chip-good",
  MODIFIED: "chip-warn",
  REMOVED: "chip-crit",
};

function importLabel(imp: ScheduleImport): string {
  const when = new Date(imp.imported_at).toLocaleString();
  return `${imp.filename} — ${when}`;
}

export default function LogicDiffPage() {
  const [project, setProject] = useState<Project | null>(null);
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [report, setReport] = useState<LogicDiffReport | null>(null);
  const [typeFilter, setTypeFilter] = useState<"all" | LogicDiffChangeType>("all");

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const projects = await api.get<Project[]>("/projects");
        const active = projects[0] ?? null;
        setProject(active);
        if (!active) return;
        const history = await api.get<ScheduleImport[]>(`/projects/${active.id}/schedule-imports`);
        setImports(history);
        // History is newest-first — default "To" to the latest import, "From" to the one before it.
        if (history.length > 0) setToId(history[0].id);
        if (history.length > 1) setFromId(history[1].id);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load schedule imports.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function compare() {
    if (!project || !fromId || !toId) return;
    setComparing(true);
    setCompareError(null);
    try {
      const res = await api.get<LogicDiffReport>(
        `/projects/${project.id}/logic-diff?from_import_id=${fromId}&to_import_id=${toId}`
      );
      setReport(res);
    } catch (err) {
      setCompareError(err instanceof ApiError ? err.message : "Failed to compute the diff.");
      setReport(null);
    } finally {
      setComparing(false);
    }
  }

  const filteredChanges = report ? report.changes.filter((c) => typeFilter === "all" || c.change_type === typeFilter) : [];

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
          {project?.name ?? "—"} / <b>Logic Diff</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Logic Diff</div>
            <div className="page-desc">Compare relationships (predecessors/successors) between two schedule imports</div>
          </div>
        </div>

        {imports.length < 2 ? (
          <div className="card">
            <p className="empty-state">Need at least two schedule imports for this project to compare.</p>
          </div>
        ) : (
          <>
            <div className="card" style={{ padding: "1rem 1.1rem" }}>
              <div className="form-row" style={{ alignItems: "flex-end" }}>
                <div className="field">
                  <label htmlFor="from-import">From</label>
                  <select id="from-import" style={selectStyle} value={fromId} onChange={(e) => setFromId(e.target.value)}>
                    {imports.map((imp) => (
                      <option key={imp.id} value={imp.id}>
                        {importLabel(imp)}
                      </option>
                    ))}
                  </select>
                </div>
                <ArrowRightIcon className="icon" style={{ marginBottom: ".6rem" }} />
                <div className="field">
                  <label htmlFor="to-import">To</label>
                  <select id="to-import" style={selectStyle} value={toId} onChange={(e) => setToId(e.target.value)}>
                    {imports.map((imp) => (
                      <option key={imp.id} value={imp.id}>
                        {importLabel(imp)}
                      </option>
                    ))}
                  </select>
                </div>
                <button className="btn btn-primary" onClick={compare} disabled={comparing || fromId === toId}>
                  <CompareIcon className="icon" /> {comparing ? "Comparing…" : "Compare"}
                </button>
              </div>
              {fromId === toId && (
                <p style={{ fontSize: ".75rem", color: "var(--text-muted)", marginTop: ".5rem" }}>
                  Pick two different imports to compare.
                </p>
              )}
              {compareError && (
                <p className="login-error" style={{ marginTop: ".75rem" }}>
                  {compareError}
                </p>
              )}
            </div>

            {report && (
              <div className="card" style={{ marginTop: "1rem" }}>
                <div className="card-head" style={{ flexWrap: "wrap", gap: ".6rem" }}>
                  <div style={{ display: "flex", gap: ".5rem", alignItems: "center" }}>
                    <span className="card-title">{report.summary.total} changes</span>
                    <span className="chip chip-good">{report.summary.added} added</span>
                    <span className="chip chip-crit">{report.summary.removed} removed</span>
                    <span className="chip chip-warn">{report.summary.modified} modified</span>
                  </div>
                  <select style={selectStyle} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as typeof typeFilter)}>
                    <option value="all">All types</option>
                    <option value="ADDED">Added</option>
                    <option value="REMOVED">Removed</option>
                    <option value="MODIFIED">Modified</option>
                  </select>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Predecessor</th>
                        <th>Successor</th>
                        <th>Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredChanges.length === 0 && (
                        <tr>
                          <td colSpan={4} className="empty-state">
                            No changes of this type.
                          </td>
                        </tr>
                      )}
                      {filteredChanges.map((c, i) => (
                        <tr key={i}>
                          <td>
                            <span className={`chip ${CHANGE_CHIP[c.change_type]}`}>{c.change_type}</span>
                          </td>
                          <td>
                            <div className="subname">{c.pred_name}</div>
                            <div className="actid">
                              {c.pred_external_id}
                              {c.pred_was_critical && (
                                <span className="chip chip-crit" style={{ marginLeft: ".35rem" }}>
                                  Critical
                                </span>
                              )}
                            </div>
                          </td>
                          <td>
                            <div className="subname">{c.succ_name}</div>
                            <div className="actid">
                              {c.succ_external_id}
                              {c.succ_was_critical && (
                                <span className="chip chip-crit" style={{ marginLeft: ".35rem" }}>
                                  Critical
                                </span>
                              )}
                            </div>
                          </td>
                          <td>
                            {c.changes.includes("TYPE_CHANGED") && (
                              <div className="diff-line">
                                <span className="diff-before">{c.old_link_type}</span>
                                <ArrowRightIcon className="icon" />
                                <span className="diff-after">{c.new_link_type}</span>
                              </div>
                            )}
                            {c.changes.includes("LAG_CHANGED") && (
                              <div className="diff-line">
                                <span className="diff-before">{c.old_lag_hours}h</span>
                                <ArrowRightIcon className="icon" />
                                <span className="diff-after">{c.new_lag_hours}h</span>
                              </div>
                            )}
                            {c.change_type === "ADDED" && (
                              <span className="mono">
                                {c.new_link_type} · {c.new_lag_hours}h lag
                              </span>
                            )}
                            {c.change_type === "REMOVED" && (
                              <span className="mono">
                                {c.old_link_type} · {c.old_lag_hours}h lag
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}

const selectStyle: CSSProperties = {
  fontSize: ".8125rem",
  height: 34,
  padding: "0 .5rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text-primary)",
  minWidth: 220,
};
