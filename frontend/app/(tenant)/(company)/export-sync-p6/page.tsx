"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Activity, Project } from "@/lib/types";
import { DownloadIcon } from "@/components/icons";

export default function ExportSyncP6Page() {
  const [project, setProject] = useState<Project | null>(null);
  const [activityCount, setActivityCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const projects = await api.get<Project[]>("/projects");
        const active = projects[0] ?? null;
        setProject(active);
        if (!active) return;
        const activities = await api.get<Activity[]>(`/activities?project_id=${active.id}`);
        setActivityCount(activities.length);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load the project.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function downloadXer() {
    if (!project) return;
    setExporting(true);
    setExportError(null);
    try {
      const { blob, filename } = await api.getBlob(`/projects/${project.id}/export/xer`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename ?? `${project.code}.xer`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : "Failed to export the schedule.");
    } finally {
      setExporting(false);
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

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>Export / Sync to P6</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Export / Sync to P6</div>
            <div className="page-desc">Download the current schedule as a .xer file to update it back in Primavera P6</div>
          </div>
        </div>

        {!project ? (
          <div className="card">
            <p className="empty-state">No project yet.</p>
          </div>
        ) : (
          <div className="card" style={{ padding: "1.25rem 1.1rem" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: 560 }}>
              <div>
                <div style={{ fontSize: ".875rem", fontWeight: 700, marginBottom: ".4rem" }}>How this works</div>
                <ol style={{ fontSize: ".8125rem", color: "var(--text-secondary)", paddingLeft: "1.1rem", lineHeight: 1.6 }}>
                  <li>Download the .xer file below — it reflects the current schedule and progress in Poko.</li>
                  <li>Open it in Primavera P6 and run F9 (schedule recalculation).</li>
                  <li>Re-upload the F9 result via Project Files to bring the recalculated dates back into Poko.</li>
                </ol>
              </div>

              <div className="banner">
                <div>
                  <div style={{ fontWeight: 700, fontSize: ".8125rem" }}>{activityCount} activities included</div>
                  <div style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                    Resource and activity-code data isn&rsquo;t tracked in Poko yet, so those P6 tables export empty.
                  </div>
                </div>
              </div>

              <button className="btn btn-primary" onClick={downloadXer} disabled={exporting || activityCount === 0}>
                <DownloadIcon className="icon" /> {exporting ? "Preparing…" : "Export .xer"}
              </button>
              {activityCount === 0 && (
                <p style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                  Import a schedule from Project Files before exporting.
                </p>
              )}
              {exportError && <p className="login-error">{exportError}</p>}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
