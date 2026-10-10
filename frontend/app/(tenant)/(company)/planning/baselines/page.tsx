"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type DragEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { api, ApiError } from "@/lib/api";
import { PageState } from "@/components/PageShell";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { BaselineProgramResult, BaselineResourceSummary, BaselineStatus, User } from "@/lib/types";
import { ChevronDownIcon, LockIcon, UploadCloudIcon } from "@/components/icons";
import { EmptyState } from "@/components/EmptyState";
import { NoProjectIllo } from "@/components/illustrations";
import { can } from "@/lib/permissions";
import { useCurrentUser } from "@/lib/user-context";
import { HelpTip } from "@/components/HelpTip";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// P6 convention (DD-MMM-YYYY) — see CLAUDE.md.
function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()}`;
}

const RSRC_TYPE_LABEL: Record<string, string> = {
  RT_Labor: "Labor",
  RT_Mat: "Material",
  RT_Equip: "Nonlabor",
};

// Card header that toggles its section open/closed. `children` sits on the right
// (chips, filters) and doesn't toggle when interacted with.
function SectionHead({
  open,
  onToggle,
  title,
  style,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  title: string;
  style?: CSSProperties;
  children?: ReactNode;
}) {
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onToggle();
    }
  }
  return (
    <div
      className="card-head"
      role="button"
      tabIndex={0}
      aria-expanded={open}
      onClick={onToggle}
      onKeyDown={onKeyDown}
      style={{ cursor: "pointer", userSelect: "none", ...(open ? {} : { borderBottom: "none" }), ...style }}
    >
      <div className="card-title cell-flex">
        <ChevronDownIcon
          className="icon"
          style={{ transform: open ? undefined : "rotate(-90deg)", transition: "transform var(--dur-1) var(--ease)" }}
        />
        {title}
      </div>
      {children}
    </div>
  );
}

// Hours read as a quantity, not a raw float: 153,128 rather than 153128.0.
function fmtHours(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: n >= 100 ? 0 : 1 });
}

export default function BaselinesPage() {
  const { showToast } = useToast();
  const { project, refreshBaseline } = useProjectContext();

  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<BaselineStatus | null>(null);
  const [resources, setResources] = useState<BaselineResourceSummary | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [replaceMode, setReplaceMode] = useState(false);
  // The long tables start collapsed so the page doesn't run off the bottom.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set(["resources"]));
  const isOpen = (key: string) => !collapsed.has(key);
  const toggle = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (!next.delete(key)) next.add(key);
      return next;
    });

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.get<User>("/auth/me").then(setUser).catch(() => setUser(null));
  }, []);

  const load = useCallback(async () => {
    if (!project) {
      setStatus(null);
      setResources(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const baseline = await api.get<BaselineStatus>(`/projects/${project.id}/evm/baseline`);
      setStatus(baseline);
      setResources(
        baseline.has_active
          ? await api.get<BaselineResourceSummary>(`/projects/${project.id}/evm/baseline/resources`)
          : null,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load baselines.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  async function upload(file: File, force = false) {
    if (!project) return;
    if (!file.name.toLowerCase().endsWith(".xer")) {
      showToast("Only .xer files are supported", "error");
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (force) formData.append("force", "true");
      const result = await api.postFile<BaselineProgramResult>(
        `/projects/${project.id}/evm/baseline/program`,
        formData
      );
      showToast(
        result.mode === "created"
          ? `Baseline locked — ${result.activity_count} activities`
          : `Baseline programme replaced — ${result.activity_count} activities`
      );
      setReplaceMode(false);
      await refreshBaseline();
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && !force) {
        setUploading(false);
        if (window.confirm(`${err.message}\n\nImport it anyway?`)) await upload(file, true);
        return;
      }
      showToast(err instanceof ApiError ? err.message : "Failed to upload the baseline programme.", "error");
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

  const isAdmin = can(user, "manage_baselines");
  const active = status?.active_baseline ?? null;

  const dropzone = (
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
      <div className="dropzone-title">
        {uploading ? "Uploading…" : "Drop the baseline programme (.xer) here, or click to browse"}
      </div>
      <div className="dropzone-sub">
        Reads the schedule and its P6 resources, runs CPM, and locks it as the Performance Measurement
        Baseline.
      </div>
      <input ref={fileInputRef} type="file" accept=".xer" onChange={handleFileInput} disabled={uploading} />
    </div>
  );

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Programme
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">
              Baselines <HelpTip id="page.baselines" />
            </div>
            <div className="page-desc">
              The baseline programme is the project&apos;s frozen plan. Every update programme uploaded to
              Programme Files is measured back against it — see Reports › Project Status for date variance and the
              S-curve.
            </div>
          </div>
        </div>

        {loading ? (
          <PageState kind="loading" />
        ) : error ? (
          <PageState kind="error" message={error} />
        ) : !project ? (
          <div className="card">
            <EmptyState
              art={<NoProjectIllo />}
              title="No project selected"
              body="Create or pick a project from the project switcher in the top bar."
            />
          </div>
        ) : (
          <>
            {/* 1. Baseline programme --------------------------------------- */}
            <div className="card">
              <div className="card-head">
                <div className="card-title">Baseline programme</div>
                <HelpTip id="baselines.programme" className="card-head-help" />
              </div>
              <div style={{ padding: "1rem 1.1rem" }}>
                {!active ? (
                  <>
                    <div className="banner warn" style={{ marginBottom: "1rem" }}>
                      <LockIcon className="icon" />
                      <div className="banner-text">
                        No baseline yet. Progress tracking, Reports, EVM, Risk and AI stay locked until one is set.
                      </div>
                    </div>
                    {isAdmin ? (
                      dropzone
                    ) : (
                      <p className="empty-state">
                        A Company Admin needs to upload the baseline programme.
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <div className="kpi-row" style={{ marginBottom: replaceMode ? "1rem" : 0 }}>
                      {[
                        { label: "Version", value: active.version_label, num: false },
                        { label: "BAC (hrs)", value: fmtHours(active.total_budget_manhours), num: true },
                        { label: "Target start", value: fmtDate(active.target_start_date), num: true },
                        { label: "Target finish", value: fmtDate(active.target_end_date), num: true },
                        { label: "Activities", value: String(active.activity_count), num: true },
                        {
                          label: "Locked",
                          value: active.locked_at ? fmtDate(active.locked_at) : "—",
                          num: true,
                        },
                      ].map((kpi) => (
                        <div className="card" key={kpi.label} style={{ padding: ".9rem 1rem" }}>
                          <div
                            style={{
                              fontSize: ".6875rem",
                              color: "var(--text-muted)",
                            }}
                          >
                            {kpi.label}
                          </div>
                          <div
                            className={kpi.num ? "num" : undefined}
                            style={{ fontSize: "1rem", fontWeight: 700, marginTop: ".3rem" }}
                          >
                            {kpi.value}
                          </div>
                        </div>
                      ))}
                    </div>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: ".75rem",
                        marginTop: "1rem",
                        flexWrap: "wrap",
                      }}
                    >
                      <span style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                        Locked from <span className="mono">{active.source_filename ?? "—"}</span>
                      </span>
                      {isAdmin && !replaceMode && (
                        <button className="btn btn-secondary btn-sm" onClick={() => setReplaceMode(true)}>
                          Replace baseline programme
                        </button>
                      )}
                    </div>
                    {isAdmin && replaceMode && (
                      <div style={{ marginTop: "1rem" }}>
                        <div className="banner warn" style={{ marginBottom: "1rem" }}>
                          <LockIcon className="icon" />
                          <div className="banner-text">
                            Replacing overwrites the frozen baseline in place (same version) and recomputes
                            EVM from existing progress. There is no undo.
                          </div>
                        </div>
                        {dropzone}
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ marginTop: ".6rem" }}
                          onClick={() => setReplaceMode(false)}
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* 2. Resources in this baseline ------------------------------- */}
            {active && resources && (
              <div className="card" style={{ marginTop: "1rem" }}>
                <SectionHead
                  open={isOpen("resources")}
                  onToggle={() => toggle("resources")}
                  title="Resources in this baseline"
                >
                  <div style={{ display: "flex", gap: ".4rem" }}>
                    <span className="chip chip-neutral">{resources.labor_count} Labor</span>
                    <span className="chip chip-neutral">{resources.material_count} Material</span>
                    <span className="chip chip-neutral">{resources.equipment_count} Equipment</span>
                  </div>
                </SectionHead>
                {isOpen("resources") && (
                  <>
                    {resources.resource_count === 0 ? (
                      <p className="empty-state">
                        The baseline programme carried no P6 resources (RSRC / TASKRSRC).
                      </p>
                    ) : (
                      <>
                        <div className="kpi-row" style={{ padding: "1rem 1.1rem 0" }}>
                          <div className="card" style={{ padding: ".9rem 1rem" }}>
                            <div style={{ fontSize: ".6875rem", color: "var(--text-muted)" }}>
                              Budgeted labor
                            </div>
                            <div className="num" style={{ fontSize: "1rem", fontWeight: 700, marginTop: ".3rem" }}>
                              {fmtHours(resources.total_budgeted_labor_hours)} h
                            </div>
                          </div>
                          <div className="card" style={{ padding: ".9rem 1rem" }}>
                            <div style={{ fontSize: ".6875rem", color: "var(--text-muted)" }}>
                              Budgeted cost
                            </div>
                            <div className="num" style={{ fontSize: "1rem", fontWeight: 700, marginTop: ".3rem" }}>
                              {resources.total_budgeted_cost.toLocaleString()}
                            </div>
                          </div>
                        </div>
                        <div className="table-wrap">
                          <table>
                            <thead>
                              <tr>
                                <th>Resource</th>
                                <th>Type</th>
                                <th>Unit</th>
                                <th>Budgeted qty</th>
                                <th>Budgeted cost</th>
                                <th>Activities</th>
                              </tr>
                            </thead>
                            <tbody>
                              {resources.resources.map((r) => (
                                <tr key={r.rsrc_id}>
                                  <td>
                                    <div className="subname">{r.name}</div>
                                    {r.short_name && <div className="actid">{r.short_name}</div>}
                                  </td>
                                  <td>{RSRC_TYPE_LABEL[r.rsrc_type] ?? r.rsrc_type}</td>
                                  <td>{r.unit_id ?? "—"}</td>
                                  <td className="num">{fmtHours(r.budgeted_qty)}</td>
                                  <td className="num">{r.budgeted_cost.toLocaleString()}</td>
                                  <td className="num">{r.assignment_count}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}
                  </>
                )}
              </div>
            )}

            {/* 3. Baseline history --------------------------------------- */}
            <div className="card" style={{ marginTop: "1rem" }}>
              <SectionHead
                open={isOpen("history")}
                onToggle={() => toggle("history")}
                title={`Baseline history${status ? ` (${status.all_baselines.length})` : ""}`}
              />
              {isOpen("history") && (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Version</th>
                        <th>Status</th>
                        <th>BAC (hrs)</th>
                        <th>Target start</th>
                        <th>Target finish</th>
                        <th>Activities</th>
                        <th>Locked</th>
                      </tr>
                    </thead>
                    <tbody>
                      {!status || status.all_baselines.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="empty-state">
                            No baseline locked yet.
                          </td>
                        </tr>
                      ) : (
                        status.all_baselines.map((b) => (
                          <tr key={b.id}>
                            <td className="cell-flex">
                              <LockIcon className="icon" />
                              {b.version_label}
                            </td>
                            <td>
                              <span
                                className={`chip ${b.status === "active" ? "chip-good" : "chip-neutral"}`}
                              >
                                {b.status}
                              </span>
                            </td>
                            <td className="num">{fmtHours(b.total_budget_manhours)}</td>
                            <td className="num">{fmtDate(b.target_start_date)}</td>
                            <td className="num">{fmtDate(b.target_end_date)}</td>
                            <td className="num">{b.activity_count}</td>
                            <td className="num">{b.locked_at ? fmtDate(b.locked_at) : "—"}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
