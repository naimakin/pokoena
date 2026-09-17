"use client";

import { useEffect, useRef, useState, type ChangeEvent, type CSSProperties, type DragEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { BaselineStatus, ScheduleImport, SyncLogEntry } from "@/lib/types";
import { CheckIcon, LockIcon, UploadCloudIcon, XIcon } from "@/components/icons";

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

// P6 convention (DD-MMM-YYYY) — see CLAUDE.md.
function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()}`;
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
  const [baselineLabel, setBaselineLabel] = useState("Baseline");
  const [baselineBusy, setBaselineBusy] = useState(false);
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

  async function lockBaseline() {
    if (!project || !baselineLabel.trim()) return;
    setBaselineBusy(true);
    try {
      await api.post(`/projects/${project.id}/evm/baseline`, { version_label: baselineLabel.trim() });
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not lock the baseline.");
    } finally {
      setBaselineBusy(false);
    }
  }

  async function relockBaseline() {
    if (!project || !baselineStatus?.active_baseline || !baselineLabel.trim()) return;
    setBaselineBusy(true);
    try {
      await api.delete(`/projects/${project.id}/evm/baseline/${baselineStatus.active_baseline.id}`);
      await api.post(`/projects/${project.id}/evm/baseline`, { version_label: baselineLabel.trim() });
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not change the baseline.");
    } finally {
      setBaselineBusy(false);
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
              float, and critical path. Lock the current import as the baseline below (or manage it in more detail
              on <b>Planning → Baselines</b>) — later uploads update the live schedule and are compared back to it.
            </div>
          </div>
        </div>

        {!project ? (
          <div className="card">
            <p className="empty-state">No project yet — create one from the project switcher in the sidebar.</p>
          </div>
        ) : (
          <>
            {baselineStatus?.has_active ? (
              <div className="banner">
                <LockIcon className="icon" style={{ color: "var(--good)" }} />
                <div className="banner-text">
                  Baseline locked (<b>{baselineStatus.active_baseline?.version_label}</b>) — new uploads update the
                  live schedule; the baseline itself stays fixed for comparison.
                  {imports[0] && baselineStatus.active_baseline?.schedule_import_id !== imports[0].id && (
                    <span style={{ color: "var(--warn)" }}> A newer import exists — the baseline still reflects an older one.</span>
                  )}
                </div>
              </div>
            ) : (
              <div className="banner warn">
                <LockIcon className="icon" />
                <div className="banner-text">
                  No baseline programme yet — lock the current import as baseline below, or set one on{" "}
                  <b>Planning → Baselines</b>.
                </div>
              </div>
            )}

            {imports.length > 0 && (
              <div
                style={{
                  marginTop: ".6rem",
                  display: "flex",
                  alignItems: "center",
                  gap: ".5rem",
                  flexWrap: "wrap",
                  fontSize: ".75rem",
                }}
              >
                <label htmlFor="baseline-label" style={{ color: "var(--text-muted)" }}>
                  {baselineStatus?.has_active ? "New baseline label" : "Baseline label"}
                </label>
                <input
                  id="baseline-label"
                  type="text"
                  style={{ width: 160 }}
                  value={baselineLabel}
                  onChange={(e) => setBaselineLabel(e.target.value)}
                  disabled={baselineBusy}
                />
                {baselineStatus?.has_active ? (
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={
                      baselineBusy ||
                      !baselineLabel.trim() ||
                      imports[0]?.id === baselineStatus.active_baseline?.schedule_import_id
                    }
                    title={
                      imports[0]?.id === baselineStatus.active_baseline?.schedule_import_id
                        ? "The baseline already reflects the current import"
                        : undefined
                    }
                    onClick={relockBaseline}
                  >
                    {baselineBusy ? "Working…" : "Lock latest import as baseline"}
                  </button>
                ) : (
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={baselineBusy || !baselineLabel.trim()}
                    onClick={lockBaseline}
                  >
                    {baselineBusy ? "Locking…" : "Lock latest import as baseline"}
                  </button>
                )}
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
                      <th>Baseline</th>
                      <th style={{ width: 48 }} />
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
                    {imports.map((imp, i) => {
                      const isLatest = i === 0;
                      const isBaselineLinked = imp.id === baselineStatus?.active_baseline?.schedule_import_id;
                      return (
                        <tr key={imp.id}>
                          <td>
                            <span className="mono">{imp.revision_label ?? "—"}</span>
                            {imp.roundtrip_from_export_id && syncExports.find((e) => e.id === imp.roundtrip_from_export_id) && (
                              <div className="actid">
                                from {syncExports.find((e) => e.id === imp.roundtrip_from_export_id)!.label}
                              </div>
                            )}
                          </td>
                          <td>{imp.filename}</td>
                          <td>{fmtDate(imp.data_date)}</td>
                          <td className="num">{imp.activity_count}</td>
                          <td className="num">{imp.critical_count}</td>
                          <td>{new Date(imp.imported_at).toLocaleString()}</td>
                          <td>
                            {isBaselineLinked ? (
                              <span className="chip chip-good">
                                <LockIcon className="icon" /> Baseline
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td style={{ textAlign: "right" }}>
                            <div className="actions" style={{ justifyContent: "flex-end" }}>
                              <button
                                className="act-btn act-reject"
                                title={
                                  isLatest
                                    ? "Can't delete the current schedule"
                                    : isBaselineLinked
                                      ? "Locked as a baseline — can't be deleted"
                                      : "Delete this import"
                                }
                                disabled={isLatest || isBaselineLinked || deletingId === imp.id}
                                onClick={() => deleteImport(imp)}
                              >
                                <XIcon className="icon" />
                              </button>
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
