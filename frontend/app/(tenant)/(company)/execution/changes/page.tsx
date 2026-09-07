"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import { selectStyle } from "@/components/ScurveChart";
import { ArrowRightIcon, CompareIcon, DownloadIcon } from "@/components/icons";
import type { ActivityChange, ScheduleChangeReport, ScheduleImport } from "@/lib/types";

type SectionKey = "added" | "removed" | "renamed" | "modified" | "logic";

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function importOption(i: ScheduleImport): string {
  return `${i.revision_label ?? i.filename} — ${new Date(i.imported_at).toLocaleDateString()}`;
}

function deltaLabel(f: ActivityChange["fields"][number]): string {
  if (f.delta_days != null) return `${f.delta_days > 0 ? "+" : ""}${f.delta_days}d`;
  if (f.delta_hours != null) return `${f.delta_hours > 0 ? "+" : ""}${f.delta_hours}h`;
  return "";
}

export default function ScheduleChangesPage() {
  const { project } = useProjectContext();
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  const [report, setReport] = useState<ScheduleChangeReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [comparing, setComparing] = useState(false);
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [hidden, setHidden] = useState<Set<SectionKey>>(new Set());

  useEffect(() => {
    if (!project) return;
    api
      .get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`)
      .then(setImports)
      .catch(() => setImports([]));
  }, [project]);

  const runCompare = useCallback(
    async (from: string, to: string) => {
      if (!project) {
        setReport(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setComparing(true);
      setError(null);
      const params = new URLSearchParams();
      if (from) params.set("from_import_id", from);
      if (to) params.set("to_import_id", to);
      const qs = params.toString();
      try {
        setReport(await api.get<ScheduleChangeReport>(`/projects/${project.id}/schedule-changes${qs ? `?${qs}` : ""}`));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to compare the schedules.");
      } finally {
        setLoading(false);
        setComparing(false);
      }
    },
    [project],
  );

  // Initial view = the default (auto) comparison; the selectors + Compare button re-run it.
  useEffect(() => {
    if (project) {
      setFromId("");
      setToId("");
      runCompare("", "");
    }
  }, [project, runCompare]);

  const modifiedRows = useMemo(() => {
    const rows = report?.activities.modified ?? [];
    const q = search.trim().toLowerCase();
    return rows.filter(
      (r) =>
        (!criticalOnly || r.is_critical) &&
        (!q || r.external_id.toLowerCase().includes(q) || (r.name ?? "").toLowerCase().includes(q)),
    );
  }, [report, criticalOnly, search]);

  function toggleSection(k: SectionKey) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }

  if (loading && !report) {
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
  if (!project || !report) {
    return (
      <div className="a-content">
        <p className="page-desc">No project selected.</p>
      </div>
    );
  }

  const s = report.summary;
  const noData = report.comparison_basis === "none";

  const CHIPS: { key: SectionKey; label: string; count: number; chip: string }[] = [
    { key: "added", label: "added", count: s.activities_added, chip: "chip-good" },
    { key: "removed", label: "removed", count: s.activities_removed, chip: "chip-crit" },
    { key: "renamed", label: "renamed", count: s.activities_renamed, chip: "chip-neutral" },
    { key: "modified", label: "modified", count: s.activities_modified, chip: "chip-warn" },
    { key: "logic", label: "logic changes", count: s.relationships_added + s.relationships_removed + s.relationships_modified, chip: "chip-info" },
  ];

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project.name} / <b>Changes</b>
        </span>
      </div>
      <div className="a-content changes-print">
        <div className="page-head">
          <div>
            <div className="page-title">Changes</div>
            <div className="page-desc">
              {noData
                ? "Need at least two schedule updates with an activity snapshot."
                : `${report.from_import?.revision_label ?? report.from_import?.filename} (${fmt(
                    report.from_import?.data_date ?? report.from_import?.imported_at,
                  )}) → ${report.to_import?.revision_label ?? report.to_import?.filename} (${fmt(
                    report.to_import?.data_date ?? report.to_import?.imported_at,
                  )})`}
            </div>
          </div>
          <button className="btn btn-secondary no-print" onClick={() => window.print()}>
            <DownloadIcon className="icon" /> Print
          </button>
        </div>

        {imports.length >= 2 && (
          <div className="card no-print" style={{ padding: "0.8rem 1.1rem", display: "flex", alignItems: "flex-end", gap: ".6rem", flexWrap: "wrap" }}>
            <label style={{ fontSize: ".6875rem", color: "var(--text-muted)", fontWeight: 600 }}>
              From
              <select value={fromId} onChange={(e) => setFromId(e.target.value)} style={{ ...selectStyle, display: "block", marginTop: ".2rem" }}>
                <option value="">Previous update (auto)</option>
                {imports.map((i) => (
                  <option key={i.id} value={i.id}>{importOption(i)}</option>
                ))}
              </select>
            </label>
            <ArrowRightIcon className="icon" style={{ marginBottom: ".5rem" }} />
            <label style={{ fontSize: ".6875rem", color: "var(--text-muted)", fontWeight: 600 }}>
              To
              <select value={toId} onChange={(e) => setToId(e.target.value)} style={{ ...selectStyle, display: "block", marginTop: ".2rem" }}>
                <option value="">Latest update (auto)</option>
                {imports.map((i) => (
                  <option key={i.id} value={i.id}>{importOption(i)}</option>
                ))}
              </select>
            </label>
            <button
              className="btn btn-primary"
              disabled={comparing || (fromId !== "" && fromId === toId)}
              onClick={() => runCompare(fromId, toId)}
            >
              <CompareIcon className="icon" /> {comparing ? "Comparing…" : "Compare"}
            </button>
            {fromId !== "" && fromId === toId && (
              <span style={{ fontSize: ".7rem", color: "var(--text-muted)", marginBottom: ".5rem" }}>
                Pick two different updates.
              </span>
            )}
          </div>
        )}

        {noData ? (
          <div className="card">
            <p className="empty-state">
              {imports.length >= 2
                ? "The two updates being compared don't both carry an activity snapshot yet — snapshots are captured from now on, so upload one more .xer from Program Library and the comparison will work."
                : "Upload at least two schedule updates (.xer) from Program Library. Changes compares the two most recent, or pick a pair above."}
            </p>
          </div>
        ) : (
          <>
            <div className="card" style={{ padding: "0.9rem 1.1rem", display: "flex", gap: ".5rem", alignItems: "center", flexWrap: "wrap" }}>
              {CHIPS.map((c) => (
                <button
                  key={c.key}
                  className={`chip ${c.chip}`}
                  style={{ border: "none", cursor: "pointer", opacity: hidden.has(c.key) ? 0.4 : 1 }}
                  onClick={() => toggleSection(c.key)}
                >
                  {c.count} {c.label}
                </button>
              ))}
              <span style={{ flex: 1 }} />
              <label className="no-print" style={{ fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".3rem" }}>
                <input type="checkbox" checked={criticalOnly} onChange={(e) => setCriticalOnly(e.target.checked)} />
                Critical only
              </label>
              <input
                className="no-print"
                placeholder="Search activity…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ ...selectStyle, minWidth: 160 }}
              />
            </div>

            {!hidden.has("added") && report.activities.added.length > 0 && (
              <div className="card">
                <div className="card-head"><div className="card-title">Added activities ({report.activities.added.length})</div></div>
                <div className="table-wrap">
                  <table>
                    <tbody>
                      {report.activities.added.map((a) => (
                        <tr key={a.external_id} className={a.is_critical ? "critical" : undefined}>
                          <td className="mono">{a.external_id}</td>
                          <td>{a.name}</td>
                          <td className="mono">{fmt(a.planned_finish)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {!hidden.has("removed") && report.activities.removed.length > 0 && (
              <div className="card">
                <div className="card-head"><div className="card-title">Removed activities ({report.activities.removed.length})</div></div>
                <div className="table-wrap">
                  <table>
                    <tbody>
                      {report.activities.removed.map((a) => (
                        <tr key={a.external_id} className={a.was_critical ? "critical" : undefined}>
                          <td className="mono">{a.external_id}</td>
                          <td>{a.name}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {!hidden.has("renamed") && report.activities.renamed.length > 0 && (
              <div className="card">
                <div className="card-head"><div className="card-title">Renamed activities ({report.activities.renamed.length})</div></div>
                <div className="table-wrap">
                  <table>
                    <tbody>
                      {report.activities.renamed.map((a) => (
                        <tr key={a.new_external_id}>
                          <td className="mono">{a.old_external_id} → {a.new_external_id}</td>
                          <td>{a.name}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {!hidden.has("modified") && modifiedRows.length > 0 && (
              <div className="card">
                <div className="card-head"><div className="card-title">Modified activities ({modifiedRows.length})</div></div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Activity</th>
                        <th>Changes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {modifiedRows.map((r) => (
                        <tr key={r.external_id} className={r.is_critical ? "critical" : undefined}>
                          <td>
                            <div className="subname">{r.name}</div>
                            <div className="actid">{r.external_id}{r.wbs_path ? ` · ${r.wbs_path}` : ""}</div>
                          </td>
                          <td>
                            {r.fields.map((f, i) => (
                              <div key={i} style={{ display: "flex", alignItems: "center", gap: ".4rem", fontSize: ".8125rem", padding: ".1rem 0" }}>
                                <span className="chip chip-neutral" style={{ minWidth: 70, justifyContent: "center" }}>{f.label}</span>
                                <span style={{ color: "var(--text-muted)" }}>{String(f.old ?? "—")}</span>
                                <ArrowRightIcon className="icon" style={{ width: 11, height: 11 }} />
                                <span style={{ fontWeight: 600 }}>{String(f.new ?? "—")}</span>
                                {deltaLabel(f) && <span className="mono" style={{ color: "var(--crit)" }}>{deltaLabel(f)}</span>}
                              </div>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {!hidden.has("logic") && report.relationships.changes.length > 0 && (
              <div className="card">
                <div className="card-head">
                  <div>
                    <div className="card-title">
                      Logic changes — {report.relationships.summary.added} added · {report.relationships.summary.removed} removed · {report.relationships.summary.modified} modified
                    </div>
                    <div className="card-title-sub">
                      <Link href="/logic-diff" style={{ color: "var(--accent-strong)", fontWeight: 600 }}>Open in Logic Diff →</Link>
                    </div>
                  </div>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr><th>Type</th><th>Predecessor</th><th>Successor</th><th>Change</th></tr>
                    </thead>
                    <tbody>
                      {report.relationships.changes.slice(0, 15).map((c, i) => (
                        <tr key={i}>
                          <td>
                            <span className={`chip ${c.change_type === "ADDED" ? "chip-good" : c.change_type === "REMOVED" ? "chip-crit" : "chip-warn"}`}>
                              {c.change_type}
                            </span>
                          </td>
                          <td className="mono">{c.pred_external_id}</td>
                          <td className="mono">{c.succ_external_id}</td>
                          <td className="mono">
                            {c.change_type === "MODIFIED"
                              ? `${c.old_link_type ?? ""}${c.new_link_type ? ` → ${c.new_link_type}` : ""}${
                                  c.new_lag_hours != null ? ` lag ${c.old_lag_hours}h → ${c.new_lag_hours}h` : ""
                                }`
                              : `${c.new_link_type ?? c.old_link_type} · ${c.new_lag_hours ?? c.old_lag_hours}h`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {report.relationships.changes.length > 15 && (
                  <div style={{ padding: ".5rem 1rem", fontSize: ".75rem", color: "var(--text-muted)" }}>
                    +{report.relationships.changes.length - 15} more — see Logic Diff
                  </div>
                )}
              </div>
            )}

            {s.activities_added + s.activities_removed + s.activities_renamed + s.activities_modified + report.relationships.summary.total === 0 && (
              <div className="card">
                <p className="empty-state">
                  No changes between {report.from_import?.revision_label} and {report.to_import?.revision_label}.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
