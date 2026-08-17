"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Activity, Project } from "@/lib/types";

const PAGE_SIZE = 25;

function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "2-digit", year: "numeric" });
}

function fmtFloat(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "—";
  const days = hours / 8;
  return `${days >= 0 ? "" : "-"}${Math.abs(days).toFixed(1)}d`;
}

export default function SchedulePage() {
  const [project, setProject] = useState<Project | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [page, setPage] = useState(1);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const projects = await api.get<Project[]>("/projects");
        const active = projects[0] ?? null;
        setProject(active);
        if (!active) return;
        const rows = await api.get<Activity[]>(`/activities?project_id=${active.id}`);
        setActivities(rows);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load the schedule.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return activities.filter((a) => {
      if (criticalOnly && !a.is_critical) return false;
      if (!q) return true;
      return a.external_id.toLowerCase().includes(q) || a.name.toLowerCase().includes(q);
    });
  }, [activities, query, criticalOnly]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const criticalCount = activities.filter((a) => a.is_critical).length;

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
          {project?.name ?? "—"} / <b>Schedule</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Schedule</div>
            <div className="page-desc">
              {activities.length} activities · {criticalCount} on the critical path
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head" style={{ gap: ".6rem", flexWrap: "wrap" }}>
            <input
              type="text"
              placeholder="Search by activity ID or name…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
              style={{
                flex: 1,
                minWidth: 220,
                background: "var(--surface)",
                border: "1px solid var(--border-strong)",
                borderRadius: 6,
                padding: ".5rem .65rem",
                fontSize: ".8125rem",
              }}
            />
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={criticalOnly}
                onChange={(e) => {
                  setCriticalOnly(e.target.checked);
                  setPage(1);
                }}
              />
              Critical path only
            </label>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Activity ID</th>
                  <th>Name</th>
                  <th>Early Start</th>
                  <th>Early Finish</th>
                  <th>Total Float</th>
                  <th>% Complete</th>
                  <th>Critical</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="empty-state">
                      {activities.length === 0
                        ? "No schedule imported yet — upload a .xer file from Project Files."
                        : "No activities match your filters."}
                    </td>
                  </tr>
                )}
                {pageRows.map((a) => (
                  <tr key={a.id}>
                    <td className="actid">{a.external_id}</td>
                    <td>{a.name}</td>
                    <td>{fmtDate(a.early_start)}</td>
                    <td>{fmtDate(a.early_finish)}</td>
                    <td>{fmtFloat(a.total_float_hours)}</td>
                    <td>{a.percent_complete}%</td>
                    <td>
                      {a.is_critical ? (
                        <span className="chip chip-crit">Critical</span>
                      ) : (
                        <span className="chip chip-neutral">Float</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {pageCount > 1 && (
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: ".5rem",
                padding: ".75rem 1.1rem",
                borderTop: "1px solid var(--border)",
              }}
            >
              <button
                className="btn btn-secondary btn-sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <span style={{ alignSelf: "center", fontSize: ".75rem", color: "var(--text-muted)" }}>
                Page {page} of {pageCount}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page >= pageCount}
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
