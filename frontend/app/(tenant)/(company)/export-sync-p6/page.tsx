"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, SyncLogEntry } from "@/lib/types";
import { DownloadIcon } from "@/components/icons";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// P6 convention (DD-MMM-YYYY) — see CLAUDE.md.
function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()}`;
}

function fmtWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()} ${String(
    d.getUTCHours()
  ).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export default function ExportSyncP6Page() {
  const { project } = useProjectContext();
  const [activityCount, setActivityCount] = useState(0);
  const [log, setLog] = useState<SyncLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [editing, setEditing] = useState<SyncLogEntry | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [rowBusy, setRowBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!project) {
      setActivityCount(0);
      setLog([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [activities, syncLog] = await Promise.all([
        api.get<Activity[]>(`/activities?project_id=${project.id}`),
        api.get<SyncLogEntry[]>(`/projects/${project.id}/sync-log`),
      ]);
      setActivityCount(activities.length);
      setLog(syncLog);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the project.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  const lastExportNo = log
    .filter((e) => e.kind === "export")
    .reduce((max, e) => {
      const n = Number(e.label.replace(/\D/g, ""));
      return Number.isFinite(n) && n > max ? n : max;
    }, 0);
  const nextFilename = project ? `${project.code}-EXP-${lastExportNo + 1}.xer` : "";

  // Exports and imports live in different tables but read as one log, so each
  // row's actions route by `kind`. Imports already had these endpoints (they
  // guard the current schedule and any locked baseline); exports are log rows
  // with nothing derived from them — see routes/sync.py.
  function rowPath(entry: SyncLogEntry): string {
    return entry.kind === "export"
      ? `/projects/${project?.id}/exports/${entry.id}`
      : `/projects/${project?.id}/schedule-imports/${entry.id}`;
  }

  function startEdit(entry: SyncLogEntry) {
    setEditing(entry);
    setEditLabel(entry.label);
    setRowError(null);
  }

  async function saveLabel() {
    if (!editing || !project) return;
    const label = editLabel.trim();
    if (!label) return;
    setRowBusy(true);
    setRowError(null);
    try {
      await api.patch(rowPath(editing), { revision_label: label });
      setEditing(null);
      await load();
    } catch (err) {
      setRowError(err instanceof ApiError ? err.message : "Could not rename this entry.");
    } finally {
      setRowBusy(false);
    }
  }

  async function deleteEntry(entry: SyncLogEntry) {
    if (!project) return;
    const what = entry.kind === "export" ? "export" : "import";
    if (
      !window.confirm(
        `Delete ${entry.label} (${entry.filename}) from the sync log?\n\n` +
          (entry.kind === "import"
            ? "The schedule data this import brought in stays as it is — only its history entry is removed."
            : "This only removes the log entry; the file you already downloaded is unaffected.") +
          `\n\nThis can't be undone.`,
      )
    ) {
      return;
    }
    setRowBusy(true);
    setRowError(null);
    try {
      await api.delete(rowPath(entry));
      await load();
    } catch (err) {
      setRowError(err instanceof ApiError ? err.message : `Could not delete this ${what}.`);
    } finally {
      setRowBusy(false);
    }
  }

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
      await load();
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
            <div className="page-desc">
              Download the current schedule as a .xer file to update it back in Primavera P6. Every export
              and import is numbered per project — <span className="mono">EXP-n</span> going out,{" "}
              <span className="mono">UPD-n</span> coming back — so it&apos;s clear which file is which.
            </div>
          </div>
        </div>

        {!project ? (
          <div className="card">
            <p className="empty-state">No project yet — create one from the project switcher in the sidebar.</p>
          </div>
        ) : (
          <>
            <div className="card" style={{ padding: "1.25rem 1.1rem" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: 560 }}>
                <div>
                  <div style={{ fontSize: ".875rem", fontWeight: 700, marginBottom: ".4rem" }}>How this works</div>
                  <ol
                    style={{
                      fontSize: ".8125rem",
                      color: "var(--text-secondary)",
                      paddingLeft: "1.1rem",
                      lineHeight: 1.6,
                    }}
                  >
                    <li>Download the .xer file below — it reflects the current schedule and progress in Poko.</li>
                    <li>Open it in Primavera P6 and run F9 (schedule recalculation).</li>
                    <li>
                      Re-upload the F9 result via Program Library. Link it back to this export there so the sync
                      log shows the round-trip.
                    </li>
                  </ol>
                </div>

                <div className="banner">
                  <div>
                    <div style={{ fontWeight: 700, fontSize: ".8125rem" }}>{activityCount} activities included</div>
                    <div style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                      Calendars, resources, and activity codes from the last import are included automatically.
                    </div>
                  </div>
                </div>

                <button className="btn btn-primary" onClick={downloadXer} disabled={exporting || activityCount === 0}>
                  <DownloadIcon className="icon" /> {exporting ? "Preparing…" : "Export .xer"}
                </button>
                {activityCount > 0 && (
                  <p style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                    Next file: <span className="mono">{nextFilename}</span>
                  </p>
                )}
                {activityCount === 0 && (
                  <p style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                    Import a schedule from Program Library before exporting.
                  </p>
                )}
                {exportError && <p className="login-error">{exportError}</p>}
              </div>
            </div>

            <div className="card" style={{ marginTop: "1rem" }}>
              <div className="card-head">
                <div>
                  <div className="card-title">Sync log</div>
                  <div className="card-title-sub">Every .xer exported and imported for this project</div>
                </div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Rev</th>
                      <th>Direction</th>
                      <th>When</th>
                      <th>Data date</th>
                      <th>By</th>
                      <th>Activities</th>
                      <th>File</th>
                      <th style={{ width: 120 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {log.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="empty-state">
                          Nothing exported or imported yet.
                        </td>
                      </tr>
                    ) : (
                      log.map((e) => (
                        <tr key={`${e.kind}-${e.id}`}>
                          <td>
                            {editing && editing.kind === e.kind && editing.id === e.id ? (
                              <input
                                value={editLabel}
                                onChange={(ev) => setEditLabel(ev.target.value)}
                                onKeyDown={(ev) => {
                                  if (ev.key === "Enter") saveLabel();
                                  if (ev.key === "Escape") setEditing(null);
                                }}
                                maxLength={30}
                                autoFocus
                                aria-label="Revision label"
                                style={{
                                  width: "100%",
                                  minWidth: 110,
                                  background: "var(--surface)",
                                  border: "1px solid var(--accent)",
                                  borderRadius: 6,
                                  padding: ".3rem .4rem",
                                  fontSize: ".8125rem",
                                }}
                              />
                            ) : (
                              <>
                                <div className="subname">{e.label}</div>
                                {e.linked_export_label && (
                                  <div className="actid">from {e.linked_export_label}</div>
                                )}
                              </>
                            )}
                          </td>
                          <td>
                            <span className="chip chip-neutral">
                              {e.kind === "export" ? "Export → P6" : "Import ← P6"}
                            </span>
                          </td>
                          <td className="num">{fmtWhen(e.at)}</td>
                          <td className="num">{fmtDate(e.data_date)}</td>
                          <td>{e.user_name ?? "—"}</td>
                          <td className="num">{e.activity_count}</td>
                          <td className="mono" style={{ fontSize: ".6875rem" }}>
                            {e.filename}
                          </td>
                          <td>
                            <div style={{ display: "flex", gap: ".3rem", justifyContent: "flex-end" }}>
                              {editing && editing.kind === e.kind && editing.id === e.id ? (
                                <>
                                  <button
                                    className="btn btn-primary btn-sm"
                                    disabled={rowBusy || !editLabel.trim()}
                                    onClick={saveLabel}
                                  >
                                    Save
                                  </button>
                                  <button
                                    className="btn btn-ghost btn-sm"
                                    disabled={rowBusy}
                                    onClick={() => setEditing(null)}
                                  >
                                    Cancel
                                  </button>
                                </>
                              ) : (
                                <>
                                  <button
                                    className="btn btn-ghost btn-sm"
                                    disabled={rowBusy}
                                    onClick={() => startEdit(e)}
                                    title="Rename this entry"
                                  >
                                    Rename
                                  </button>
                                  <button
                                    className="btn btn-ghost btn-sm"
                                    disabled={rowBusy}
                                    onClick={() => deleteEntry(e)}
                                    title="Remove this entry from the log"
                                  >
                                    Delete
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              {rowError && (
                <p className="login-error" style={{ margin: ".75rem 1rem" }}>
                  {rowError}
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
