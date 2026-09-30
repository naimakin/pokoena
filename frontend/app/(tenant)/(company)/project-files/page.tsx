"use client";

import { useEffect, useRef, useState, type ChangeEvent, type CSSProperties, type DragEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { BaselineStatus, ScheduleImport, SyncLogEntry } from "@/lib/types";
import { CheckIcon, LockIcon, PencilIcon, UploadCloudIcon, XIcon } from "@/components/icons";

const selectStyle: CSSProperties = {
  fontSize: ".8125rem",
  height: 34,
  padding: "0 .5rem",
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  color: "var(--text-primary)",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// P6-style short date on this page: DD-MMM-YY (e.g. 30-Apr-26).
function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${String(d.getUTCFullYear()).slice(-2)}`;
}

const MONTH_INDEX: Record<string, number> = Object.fromEntries(MONTHS.map((m, i) => [m.toLowerCase(), i]));

// Reads what a user types into the Data date box: DD-MMM-YY (30-Apr-26), DD-MMM-YYYY
// or ISO (2026-04-30). Returns an ISO date, or null when it isn't a real calendar date.
function parseDateInput(text: string): string | null {
  const t = text.trim();
  let y: number, m: number, d: number;
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(t);
  const dmy = /^(\d{1,2})[-\s/]([A-Za-z]{3})[-\s/](\d{2}|\d{4})$/.exec(t);
  if (iso) {
    [y, m, d] = [Number(iso[1]), Number(iso[2]) - 1, Number(iso[3])];
  } else if (dmy) {
    const month = MONTH_INDEX[dmy[2].toLowerCase()];
    if (month === undefined) return null;
    [y, m, d] = [dmy[3].length === 2 ? 2000 + Number(dmy[3]) : Number(dmy[3]), month, Number(dmy[1])];
  } else {
    return null;
  }
  const check = new Date(Date.UTC(y, m, d));
  if (check.getUTCFullYear() !== y || check.getUTCMonth() !== m || check.getUTCDate() !== d) return null;
  return `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

// Same format plus a local HH:MM — for the moment an import happened.
function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const date = `${String(d.getDate()).padStart(2, "0")}-${MONTHS[d.getMonth()]}-${String(d.getFullYear()).slice(-2)}`;
  return `${date} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function ProgramLibraryPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  const [syncExports, setSyncExports] = useState<SyncLogEntry[]>([]);
  const [linkExportId, setLinkExportId] = useState("");
  const [baselineStatus, setBaselineStatus] = useState<BaselineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ScheduleImport | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // The row being edited: label / data date as typed, plus the roles it should hold once saved.
  const [edit, setEdit] = useState<{
    id: string;
    label: string;
    dataDate: string;
    baseline: boolean;
    current: boolean;
  } | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    if (!project) {
      setImports([]);
      setBaselineStatus(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [history, baseline, syncLog] = await Promise.all([
        api.get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`),
        api.get<BaselineStatus>(`/projects/${project.id}/evm/baseline`),
        api.get<SyncLogEntry[]>(`/projects/${project.id}/sync-log`),
      ]);
      setImports(history);
      setBaselineStatus(baseline);
      setSyncExports(syncLog.filter((e) => e.kind === "export"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load program library.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  async function upload(file: File, force = false) {
    if (!project) return;
    if (!file.name.toLowerCase().endsWith(".xer")) {
      showToast("Only .xer files are supported");
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (linkExportId) formData.append("roundtrip_from_export_id", linkExportId);
      if (force) formData.append("force", "true");
      const result = await api.postFile<ScheduleImport>(`/projects/${project.id}/schedule-imports`, formData);
      setLastResult(result);
      setLinkExportId("");
      showToast(`Imported ${result.activity_count} activities (${result.critical_count} critical)`);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && !force) {
        setUploading(false);
        if (window.confirm(`${err.message}\n\nImport it anyway?`)) await upload(file, true);
        return;
      }
      showToast(err instanceof ApiError ? err.message : "Failed to import schedule file.");
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) upload(file);
  }

  function handleFileInput(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) upload(file);
    e.target.value = "";
  }

  async function deleteImport(imp: ScheduleImport) {
    if (!project) return;
    if (!window.confirm(`Delete import "${imp.revision_label ?? imp.filename}"? This can't be undone.`)) return;
    setDeletingId(imp.id);
    try {
      await api.delete(`/projects/${project.id}/schedule-imports/${imp.id}`);
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not delete this import.");
    } finally {
      setDeletingId(null);
    }
  }

  function startEdit(imp: ScheduleImport) {
    setEdit({
      id: imp.id,
      label: imp.revision_label ?? "",
      dataDate: imp.data_date ? fmtDate(imp.data_date) : "",
      baseline: imp.id === baselineStatus?.active_baseline?.schedule_import_id,
      current: imp.is_current,
    });
  }

  async function saveEdit(imp: ScheduleImport) {
    if (!project || !edit) return;
    const label = edit.label.trim();
    if (!label) {
      showToast("Revision label can't be blank");
      return;
    }
    const wasBaseline = imp.id === baselineStatus?.active_baseline?.schedule_import_id;
    const labelChanged = label !== (imp.revision_label ?? "");
    const typedDate = edit.dataDate.trim();
    let newDate: string | null = null;
    if (typedDate && typedDate !== (imp.data_date ? fmtDate(imp.data_date) : "")) {
      newDate = parseDateInput(typedDate);
      if (!newDate) {
        showToast("Data date must look like 30-Apr-26");
        return;
      }
    }
    const becomeCurrent = edit.current && !imp.is_current;
    const becomeBaseline = edit.baseline && !wasBaseline;
    const unlocking = !edit.baseline && wasBaseline;

    // Say what the riskier changes do before making them, in one prompt.
    const notes: string[] = [];
    if (newDate) {
      notes.push(
        "Data date: EVM, DCMA and risk analysis use the new date straight away, but float and dates are NOT recomputed — re-upload the .xer for that.",
      );
    }
    if (becomeCurrent) {
      notes.push(
        `Current update: the live schedule (dates, float, critical path) is rebuilt from ${imp.filename}. Progress already entered on matching activities is kept.`,
      );
    }
    if (becomeBaseline) {
      const from = baselineStatus?.active_baseline?.version_label;
      notes.push(
        from
          ? `Baseline: replaces "${from}" — it stays in Baseline history and can be restored.`
          : "Baseline: this import becomes the frozen plan.",
      );
    }
    if (unlocking) {
      notes.push("Unlock: Execution, Reporting, EVM, Risk and AI stay locked until a baseline is set again. Tick Baseline again to restore it.");
    }
    if (notes.length > 0 && !window.confirm(`${notes.join("\n\n")}\n\nContinue?`)) return;

    setSavingEdit(true);
    try {
      if (labelChanged || newDate) {
        await api.patch(`/projects/${project.id}/schedule-imports/${imp.id}`, {
          ...(labelChanged ? { revision_label: label } : {}),
          ...(newDate ? { data_date: newDate } : {}),
        });
      }
      // Current first: a baseline taken from the current update keeps its P6 resources.
      if (becomeCurrent) await api.post(`/projects/${project.id}/schedule-imports/${imp.id}/set-current`);
      if (becomeBaseline) await api.post(`/projects/${project.id}/evm/baseline/from-import/${imp.id}`);
      if (unlocking && baselineStatus?.active_baseline) {
        await api.delete(`/projects/${project.id}/evm/baseline/${baselineStatus.active_baseline.id}`);
      }
      setEdit(null);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not save this import.");
    } finally {
      setSavingEdit(false);
      await load();
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
          {project?.name ?? "—"} / <b>Program Library</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Program Library</div>
            <div className="page-desc">
              Upload update / progress programmes (Primavera P6 .xer) to recompute the live schedule — dates,
              float, and critical path. Set the baseline by editing an import below and ticking <b>Baseline</b> (or on{" "}
              <b>Planning → Baselines</b>) — later uploads update the live schedule and are compared back to it.
            </div>
          </div>
        </div>

        {!project ? (
          <div className="card">
            <p className="empty-state">No project yet — create one from the project switcher in the top bar.</p>
          </div>
        ) : (
          <>
            {baselineStatus?.has_active ? (
              <div className="banner">
                <LockIcon className="icon" style={{ color: "var(--good)" }} />
                <div className="banner-text">
                  Baseline locked (<b>{baselineStatus.active_baseline?.version_label}</b>) — new uploads update the
                  live schedule; the baseline itself stays fixed for comparison.
                </div>
              </div>
            ) : (
              <div className="banner warn">
                <LockIcon className="icon" />
                <div className="banner-text">
                  No baseline programme yet — edit an import below and tick <b>Baseline</b>, or set one on{" "}
                  <b>Planning → Baselines</b>.
                </div>
              </div>
            )}

            <div
              className={`dropzone${dragOver ? " dragover" : ""}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              <UploadCloudIcon className="icon" />
              <div className="dropzone-title">{uploading ? "Importing…" : "Drop a .xer file here, or click to browse"}</div>
              <div className="dropzone-sub">Recomputes CPM dates, float, and critical path for this project.</div>
              <input ref={fileInputRef} type="file" accept=".xer" onChange={handleFileInput} disabled={uploading} />
            </div>

            {syncExports.length > 0 && (
              <div
                style={{
                  marginTop: ".75rem",
                  display: "flex",
                  alignItems: "center",
                  gap: ".6rem",
                  flexWrap: "wrap",
                  fontSize: ".75rem",
                  color: "var(--text-muted)",
                }}
              >
                <label htmlFor="link-export">Is this the F9 result of a Poko export?</label>
                <select
                  id="link-export"
                  style={selectStyle}
                  value={linkExportId}
                  onChange={(e) => setLinkExportId(e.target.value)}
                  disabled={uploading}
                >
                  <option value="">Not linked</option>
                  {syncExports.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.label} — {e.filename}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {lastResult && (
              <div className="banner" style={{ marginTop: "1rem" }}>
                <CheckIcon className="icon" style={{ color: "var(--good)" }} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: ".8125rem" }}>
                    {lastResult.filename}: {lastResult.activity_count} activities imported, {lastResult.critical_count}{" "}
                    on the critical path
                  </div>
                  {lastResult.warnings.filter((w) => w.startsWith("WARNING")).length > 0 && (
                    <div className="import-warnings">
                      {lastResult.warnings.filter((w) => w.startsWith("WARNING")).join("\n")}
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="card" style={{ marginTop: "1rem" }}>
              <div className="card-head">
                <div className="card-title">Import history</div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Rev</th>
                      <th>File</th>
                      <th>Data date</th>
                      <th>Activities</th>
                      <th>Critical</th>
                      <th>Imported</th>
                      <th>Role</th>
                      <th style={{ width: 84 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {imports.length === 0 && (
                      <tr>
                        <td colSpan={8} className="empty-state">
                          No schedule imported yet.
                        </td>
                      </tr>
                    )}
                    {imports.map((imp) => {
                      const isBaselineLinked = imp.id === baselineStatus?.active_baseline?.schedule_import_id;
                      const editing = edit?.id === imp.id ? edit : null;
                      const exportLabel = imp.roundtrip_from_export_id
                        ? syncExports.find((e) => e.id === imp.roundtrip_from_export_id)?.label
                        : undefined;
                      return (
                        <tr key={imp.id}>
                          <td>
                            {editing ? (
                              <input
                                type="text"
                                autoFocus
                                maxLength={30}
                                style={{ width: 170 }}
                                value={editing.label}
                                disabled={savingEdit}
                                aria-label="Revision label"
                                onChange={(e) => setEdit({ ...editing, label: e.target.value })}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") saveEdit(imp);
                                  if (e.key === "Escape") setEdit(null);
                                }}
                              />
                            ) : (
                              <span className="mono">{imp.revision_label ?? "—"}</span>
                            )}
                            {exportLabel && <div className="actid">from {exportLabel}</div>}
                          </td>
                          <td>{imp.filename}</td>
                          <td>
                            {editing ? (
                              <input
                                type="text"
                                className="mono"
                                style={{ width: 110 }}
                                placeholder="30-Apr-26"
                                value={editing.dataDate}
                                disabled={savingEdit}
                                aria-label="Data date"
                                onChange={(e) => setEdit({ ...editing, dataDate: e.target.value })}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") saveEdit(imp);
                                  if (e.key === "Escape") setEdit(null);
                                }}
                              />
                            ) : (
                              fmtDate(imp.data_date)
                            )}
                          </td>
                          <td className="num">{imp.activity_count}</td>
                          <td className="num">{imp.critical_count}</td>
                          <td className="mono">{fmtDateTime(imp.imported_at)}</td>
                          <td>
                            {editing ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: ".25rem", fontSize: ".75rem" }}>
                                <label className="checkbox-row">
                                  <input
                                    type="checkbox"
                                    checked={editing.baseline}
                                    disabled={savingEdit}
                                    onChange={(e) => setEdit({ ...editing, baseline: e.target.checked })}
                                  />
                                  Baseline
                                </label>
                                <label
                                  className="checkbox-row"
                                  title={
                                    imp.is_current
                                      ? "This is the current update — tick it on another import to change it"
                                      : !imp.has_source_file
                                        ? "Uploaded before file storage — upload the .xer again to make it current"
                                        : undefined
                                  }
                                >
                                  <input
                                    type="checkbox"
                                    checked={editing.current}
                                    disabled={savingEdit || imp.is_current || !imp.has_source_file}
                                    onChange={(e) => setEdit({ ...editing, current: e.target.checked })}
                                  />
                                  Current update
                                </label>
                              </div>
                            ) : isBaselineLinked || imp.is_current ? (
                              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: ".25rem" }}>
                                {isBaselineLinked && (
                                  <span className="chip chip-good">
                                    <LockIcon className="icon" /> Baseline
                                  </span>
                                )}
                                {imp.is_current && <span className="chip chip-info">Current update</span>}
                              </div>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td style={{ textAlign: "right" }}>
                            <div className="actions" style={{ justifyContent: "flex-end" }}>
                              {editing ? (
                                <>
                                  <button
                                    className="act-btn act-approve"
                                    title="Save changes"
                                    disabled={savingEdit}
                                    onClick={() => saveEdit(imp)}
                                  >
                                    <CheckIcon className="icon" />
                                  </button>
                                  <button
                                    className="act-btn"
                                    title="Cancel"
                                    disabled={savingEdit}
                                    onClick={() => setEdit(null)}
                                  >
                                    <XIcon className="icon" />
                                  </button>
                                </>
                              ) : (
                                <>
                                  <button
                                    className="act-btn act-edit"
                                    title="Edit label, data date and role"
                                    onClick={() => startEdit(imp)}
                                  >
                                    <PencilIcon className="icon" />
                                  </button>
                                  <button
                                    className="act-btn act-reject"
                                    title={
                                      imp.is_current
                                        ? "Can't delete the current schedule"
                                        : isBaselineLinked
                                          ? "Locked as a baseline — can't be deleted"
                                          : "Delete this import"
                                    }
                                    disabled={imp.is_current || isBaselineLinked || deletingId === imp.id}
                                    onClick={() => deleteImport(imp)}
                                  >
                                    <XIcon className="icon" />
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
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
