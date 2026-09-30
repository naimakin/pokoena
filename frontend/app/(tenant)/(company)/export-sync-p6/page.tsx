"use client";

import { type CSSProperties, useCallback, useEffect, useMemo, useState } from "react";
import { PageState } from "@/components/PageShell";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, ScheduleImport, SyncLogEntry } from "@/lib/types";
import { DownloadIcon } from "@/components/icons";
import { EmptyState } from "@/components/EmptyState";
import { NoProjectIllo } from "@/components/illustrations";

const selectStyle: CSSProperties = {
  fontSize: ".8125rem",
  height: 32,
  padding: "0 .5rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text-primary)",
};

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
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  const [selectedImportId, setSelectedImportId] = useState<string | null>(null);
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
      setImports([]);
      setSelectedImportId(null);
      setLog([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [activities, importList, syncLog] = await Promise.all([
        api.get<Activity[]>(`/activities?project_id=${project.id}`),
        api.get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`),
        api.get<SyncLogEntry[]>(`/projects/${project.id}/sync-log`),
      ]);
      setActivityCount(activities.length);
      setImports(importList);
      // Default to the current update — the schedule every other page shows —
      // and keep whatever the user picked across a reload.
      setSelectedImportId((prev) => {
        if (prev && importList.some((i) => i.id === prev)) return prev;
        return (importList.find((i) => i.is_current) ?? importList[0])?.id ?? null;
      });
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

  const currentImportId = useMemo(
    () => (imports.find((i) => i.is_current) ?? imports[0])?.id ?? null,
    [imports],
  );
  // A programme can only be exported from its own stored .xer — an upload made
  // before Poko kept source files can only go out while it IS the current
  // update, where the export falls back to building the file from the live
  // tables (see backend routes/export.py).
  const exportable = useMemo(
    () => imports.filter((i) => i.has_source_file || i.id === currentImportId),
    [imports, currentImportId],
  );
  const selectedImport = useMemo(
    () => exportable.find((i) => i.id === selectedImportId) ?? null,
    [exportable, selectedImportId],
  );
  const isCurrentSelected = selectedImport !== null && selectedImport.id === currentImportId;
  const exportCount = selectedImport ? selectedImport.activity_count : activityCount;

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
      const path = `/projects/${project.id}/export/xer${
        selectedImport && !isCurrentSelected ? `?import_id=${selectedImport.id}` : ""
      }`;
      const { blob, filename } = await api.getBlob(path);
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
    return <PageState kind="loading" section="Planning" title="Export / Sync to P6" />;
  }
  if (error) {
    return <PageState kind="error" section="Planning" title="Export / Sync to P6" message={error} />;
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Planning
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Export / Sync to P6</div>
            <div className="page-desc">
              Download a programme as a .xer file to update it back in Primavera P6. Every export
              and import is numbered per project — <span className="mono">EXP-n</span> going out,{" "}
              <span className="mono">UPD-n</span> coming back — so it&apos;s clear which file is which.
            </div>
          </div>
        </div>

        {!project ? (
          <div className="card">
            <EmptyState
              art={<NoProjectIllo />}
              title="No project selected"
              body="Create or pick a project from the project switcher in the top bar."
            />
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
                    <li>
                      Pick the programme to send back and download its .xer below — it carries the progress
                      recorded in Poko.
                    </li>
                    <li>Open it in Primavera P6 and run F9 (schedule recalculation).</li>
                    <li>
                      Re-upload the F9 result via Program Library. Link it back to this export there so the sync
                      log shows the round-trip.
                    </li>
                  </ol>
                </div>

                {exportable.length > 0 && (
                  <label
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: ".3rem",
                      fontSize: ".75rem",
                      color: "var(--text-muted)",
                    }}
                  >
                    Programme to export
                    <select
                      style={selectStyle}
                      value={selectedImportId ?? ""}
                      onChange={(e) => setSelectedImportId(e.target.value)}
                    >
                      {exportable.map((imp) => (
                        <option key={imp.id} value={imp.id}>
                          {imp.revision_label ?? imp.filename}
                          {imp.data_date ? ` · ${fmtDate(imp.data_date)}` : ""}
                          {imp.id === currentImportId ? " — Current update" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                <div className="banner">
                  <div>
                    <div style={{ fontWeight: 700, fontSize: ".8125rem" }}>{exportCount} activities included</div>
                    <div style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                      {selectedImport && !isCurrentSelected
                        ? `${selectedImport.revision_label ?? selectedImport.filename} goes out as the file it was uploaded as — its own calendars, resources, and activity codes — with the progress recorded in Poko written onto the activities it shares with the current schedule.`
                        : "Calendars, resources, and activity codes from the last import are included automatically."}
                    </div>
                  </div>
                </div>

                <button className="btn btn-primary" onClick={downloadXer} disabled={exporting || exportCount === 0}>
                  <DownloadIcon className="icon" /> {exporting ? "Preparing…" : "Export .xer"}
                </button>
                {exportCount > 0 && (
                  <p style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                    Next file: <span className="mono">{nextFilename}</span>
                  </p>
                )}
                {exportCount === 0 && (
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
                                {/* An import says which export it came back from; an export
                                    says which programme it was built from. */}
                                {(e.linked_export_label ?? e.source_import_label) && (
                                  <div className="actid">from {e.linked_export_label ?? e.source_import_label}</div>
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
