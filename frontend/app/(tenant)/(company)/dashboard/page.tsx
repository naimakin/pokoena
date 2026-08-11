"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import type { DashboardSummary, Project } from "@/lib/types";
import { AlertTriangleIcon, BellIcon, CheckIcon, ClockIcon, FlagIcon, UsersIcon } from "@/components/icons";

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const diffMs = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
}

export default function DashboardPage() {
  const { showToast } = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCloseWarning, setShowCloseWarning] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const projects = await api.get<Project[]>("/projects");
      const active = projects[0] ?? null;
      setProject(active);
      if (active) {
        const dashboardSummary = await api.get<DashboardSummary>(`/dashboard/summary?project_id=${active.id}`);
        setSummary(dashboardSummary);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the dashboard.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleRemind() {
    const periodId = summary?.active_period_id;
    if (!periodId) return;
    try {
      const result = await api.post<{ reminded: number }>(`/update-periods/${periodId}/remind`);
      showToast(`Reminder sent to ${result.reminded} non-responding subcontractor(s)`);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to send reminders.");
    }
  }

  async function handleConfirmClose() {
    const periodId = summary?.active_period_id;
    if (!periodId) return;
    try {
      await api.post(`/update-periods/${periodId}/close`);
      showToast("Period closed. S-curve, EVM and Monte Carlo analysis ship in Phase 2.");
      setShowCloseWarning(false);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to close the period.");
    }
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
  if (!project) {
    return (
      <div className="a-content">
        <p className="page-desc">No projects yet — seed one with backend/scripts/seed_demo.py.</p>
      </div>
    );
  }

  const pendingCount = summary ? summary.orgs_total - summary.orgs_submitted : 0;
  const deadlineAt = summary?.deadline_at ?? null;
  const deadlineDays = daysUntil(deadlineAt);
  const deadlineDateLabel = deadlineAt ? `Deadline ${new Date(deadlineAt).toLocaleDateString()}` : "No deadline set";
  const submittedPct =
    summary && summary.orgs_total > 0 ? Math.round((summary.orgs_submitted / summary.orgs_total) * 100) : 0;

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project.name} / <b>Dashboard</b>
        </span>
        <div className="spacer" />
        {summary?.active_period_status && (
          <span className={`chip ${summary?.active_period_status === "open" ? "chip-good" : "chip-neutral"}`}>
            {summary?.active_period_label} {summary?.active_period_status === "open" ? "Open" : "Closed"}
          </span>
        )}
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Dashboard</div>
            <div className="page-desc">{summary?.active_period_label ?? "No open update period"}</div>
          </div>
          <div style={{ display: "flex", gap: ".55rem" }}>
            <button className="btn btn-secondary" onClick={handleRemind} disabled={!summary?.active_period_id}>
              <BellIcon className="icon" /> Send Reminder
            </button>
            <button
              className="btn btn-primary"
              onClick={() => setShowCloseWarning(true)}
              disabled={!summary?.active_period_id || summary?.active_period_status !== "open"}
            >
              <CheckIcon className="icon" /> Close &amp; Run Analysis
            </button>
          </div>
        </div>

        {showCloseWarning && (
          <div className="banner warn">
            <AlertTriangleIcon className="icon" />
            <span className="banner-text">
              <b>
                {pendingCount} of {summary?.orgs_total} scopes
              </b>{" "}
              haven&rsquo;t submitted yet. Closing now will freeze their activities at last-saved values.
            </span>
            <div className="banner-actions">
              <button className="btn btn-ghost btn-sm" onClick={() => setShowCloseWarning(false)}>
                Cancel
              </button>
              <button className="btn btn-danger btn-sm" onClick={handleConfirmClose}>
                Close anyway
              </button>
            </div>
          </div>
        )}

        <div className="kpi-row">
          <div className="card kpi">
            <div className="kpi-top">
              <span className="kpi-label">Update Period</span>
              <div className="kpi-icon" style={{ background: "var(--good-soft)", color: "var(--good)" }}>
                <CheckIcon className="icon" />
              </div>
            </div>
            <div className="kpi-value" style={{ fontSize: "1.4rem" }}>
              {summary?.active_period_status === "open" ? "Open" : summary?.active_period_status === "closed" ? "Closed" : "—"}
            </div>
            <div className="kpi-sub">
              {deadlineDateLabel}
            </div>
          </div>

          <div className="card kpi">
            <div className="kpi-top">
              <span className="kpi-label">Deadline Countdown</span>
              <div className="kpi-icon" style={{ background: "var(--warn-soft)", color: "var(--warn)" }}>
                <ClockIcon className="icon" />
              </div>
            </div>
            <div className="kpi-value">
              {deadlineDays ?? "—"}
              {deadlineDays !== null && (
                <span style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-secondary)" }}> days</span>
              )}
            </div>
            <div className="kpi-sub">Until this period closes</div>
          </div>

          <div className="card kpi">
            <div className="kpi-top">
              <span className="kpi-label">Scopes Submitted</span>
              <div className="kpi-icon" style={{ background: "var(--info-soft)", color: "var(--info)" }}>
                <UsersIcon className="icon" />
              </div>
            </div>
            <div className="kpi-value">
              {summary?.orgs_submitted ?? 0}
              <span style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                {" "}
                / {summary?.orgs_total ?? 0}
              </span>
            </div>
            <div className="progress">
              <span style={{ width: `${submittedPct}%`, background: "var(--info)" }} />
            </div>
          </div>

          <div className="card kpi">
            <div className="kpi-top">
              <span className="kpi-label">Flagged for Review</span>
              <div className="kpi-icon" style={{ background: "var(--crit-soft)", color: "var(--crit)" }}>
                <FlagIcon className="icon" />
              </div>
            </div>
            <div className="kpi-value">{summary?.flagged_pending ?? 0}</div>
            <div className="kpi-sub">Awaiting admin decision</div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Scope submission status</div>
              <div className="card-title-sub">
                {summary?.orgs_total ?? 0} subcontractors &middot; {summary?.active_period_label ?? "—"}
              </div>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Subcontractor</th>
                  <th>Discipline</th>
                  <th>Status</th>
                  <th>Activities</th>
                  <th>Avg % Complete</th>
                </tr>
              </thead>
              <tbody>
                {summary && summary.scope_status.length > 0 ? (
                  summary.scope_status.map((row) => (
                    <tr key={row.subcontractor_org_id}>
                      <td>
                        <div className="cell-flex">
                          <div className="subrow-avatar">{row.org_name.slice(0, 2).toUpperCase()}</div>
                          <span className="subname">{row.org_name}</span>
                        </div>
                      </td>
                      <td>{row.discipline}</td>
                      <td>
                        <span className={`chip ${row.submitted ? "chip-good" : "chip-neutral"}`}>
                          {row.submitted ? "Submitted" : "Pending"}
                        </span>
                      </td>
                      <td className="num">{row.activity_count}</td>
                      <td className="num">{row.avg_percent_complete}%</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="empty-state">
                      No subcontractor scopes on this project yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
