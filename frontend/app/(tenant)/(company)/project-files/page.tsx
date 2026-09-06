"use client";

import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { BaselineStatus, ScheduleImport } from "@/lib/types";
import { CheckIcon, LockIcon, UploadCloudIcon } from "@/components/icons";

export default function ProgramLibraryPage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();
  const [imports, setImports] = useState<ScheduleImport[]>([]);
  const [baselineStatus, setBaselineStatus] = useState<BaselineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ScheduleImport | null>(null);
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
      const [history, baseline] = await Promise.all([
        api.get<ScheduleImport[]>(`/projects/${project.id}/schedule-imports`),
        api.get<BaselineStatus>(`/projects/${project.id}/evm/baseline`),
      ]);
      setImports(history);
      setBaselineStatus(baseline);
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

  async function upload(file: File) {
    if (!project) return;
    if (!file.name.toLowerCase().endsWith(".xer")) {
      showToast("Only .xer files are supported");
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await api.postFile<ScheduleImport>(`/projects/${project.id}/schedule-imports`, formData);
      setLastResult(result);
      showToast(`Imported ${result.activity_count} activities (${result.critical_count} critical)`);
      load();
    } catch (err) {
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
              float, and critical path. The baseline programme is managed on <b>Planning → Baselines</b>; uploads
              here update the live schedule and are compared back to that baseline.
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
                </div>
              </div>
            ) : (
              <div className="banner warn">
                <LockIcon className="icon" />
                <div className="banner-text">
                  No baseline programme yet — set one on <b>Planning → Baselines</b> before uploading updates here.
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
                      <th>File</th>
                      <th>Data date</th>
                      <th>Activities</th>
                      <th>Critical</th>
                      <th>Imported</th>
                      <th>Baseline</th>
                    </tr>
                  </thead>
                  <tbody>
                    {imports.length === 0 && (
                      <tr>
                        <td colSpan={6} className="empty-state">
                          No schedule imported yet.
                        </td>
                      </tr>
                    )}
                    {imports.map((imp) => (
                      <tr key={imp.id}>
                        <td>{imp.filename}</td>
                        <td>{imp.data_date ? new Date(imp.data_date).toLocaleDateString() : "—"}</td>
                        <td>{imp.activity_count}</td>
                        <td>{imp.critical_count}</td>
                        <td>{new Date(imp.imported_at).toLocaleString()}</td>
                        <td>
                          {imp.id === baselineStatus?.active_baseline?.schedule_import_id ? (
                            <span className="chip chip-good">
                              <LockIcon className="icon" /> Baseline
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
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
