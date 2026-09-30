"use client";

import { useCallback, useEffect, useState } from "react";
import { PageState } from "@/components/PageShell";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import { useToast } from "@/components/Toast";
import { fmtP6Date } from "@/components/reporting/format";
import { BarChartIcon, CheckIcon, DownloadIcon, SettingsIcon } from "@/components/icons";
import { NoProjectIllo } from "@/components/illustrations";
import type {
  ReportBlockCatalogueEntry,
  ReportBlockConfig,
  ReportFormat,
  ReportHeader,
} from "@/lib/types";

const REQUIREMENT_LABEL: Record<string, string> = {
  baseline: "Needs a locked baseline",
  two_imports: "Needs two schedule updates",
  resources: "Needs resource-loaded activities",
};

export default function ReportsPage() {
  const { project } = useProjectContext();
  const { showToast } = useToast();

  const [catalogue, setCatalogue] = useState<ReportBlockCatalogueEntry[]>([]);
  const [formats, setFormats] = useState<ReportFormat[]>([]);
  const [header, setHeader] = useState<ReportHeader | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftBlocks, setDraftBlocks] = useState<ReportBlockConfig[]>([]);
  const [draftNarrative, setDraftNarrative] = useState("");
  const [draftName, setDraftName] = useState("");
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const load = useCallback(async () => {
    if (!project) {
      setFormats([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [blocks, saved, head] = await Promise.all([
        api.get<ReportBlockCatalogueEntry[]>(`/projects/${project.id}/report-blocks`),
        api.get<ReportFormat[]>(`/projects/${project.id}/report-formats`),
        api.get<ReportHeader>(`/projects/${project.id}/report-header`),
      ]);
      setCatalogue(blocks);
      setFormats(saved);
      setHeader(head);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the reports.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  function startEdit(format: ReportFormat) {
    setEditingId(format.id);
    setDraftBlocks(format.blocks.map((b) => ({ ...b })));
    setDraftNarrative(format.narrative ?? "");
    setDraftName(format.name);
  }

  function toggleBlock(key: string) {
    setDraftBlocks((prev) =>
      prev.map((b) => (b.key === key ? { ...b, enabled: !b.enabled } : b)),
    );
  }

  function moveBlock(key: string, direction: -1 | 1) {
    setDraftBlocks((prev) => {
      const sorted = [...prev].sort((a, b) => a.order - b.order);
      const index = sorted.findIndex((b) => b.key === key);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= sorted.length) return prev;
      [sorted[index], sorted[target]] = [sorted[target], sorted[index]];
      return sorted.map((b, i) => ({ ...b, order: i }));
    });
  }

  async function saveFormat() {
    if (!project || !editingId) return;
    setSaving(true);
    try {
      await api.patch(`/projects/${project.id}/report-formats/${editingId}`, {
        name: draftName.trim(),
        blocks: draftBlocks,
        narrative: draftNarrative,
      });
      showToast("Report format saved.");
      setEditingId(null);
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not save the format.", "error");
    } finally {
      setSaving(false);
    }
  }

  async function createFormat() {
    if (!project || !newName.trim()) return;
    setCreating(true);
    try {
      const created = await api.post<ReportFormat>(`/projects/${project.id}/report-formats`, {
        name: newName.trim(),
        blocks: [],
      });
      setNewName("");
      await load();
      startEdit(created);
      showToast("Format created — pick the blocks it should contain.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not create the format.", "error");
    } finally {
      setCreating(false);
    }
  }

  async function deleteFormat(format: ReportFormat) {
    if (!project) return;
    if (!window.confirm(`Delete the "${format.name}" format?\n\nThis can't be undone.`)) return;
    try {
      await api.delete(`/projects/${project.id}/report-formats/${format.id}`);
      if (editingId === format.id) setEditingId(null);
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not delete the format.", "error");
    }
  }

  if (loading) {
    return <PageState kind="loading" section="Reporting" title="Reports" />;
  }
  if (error) {
    return <PageState kind="error" section="Reporting" title="Reports" message={error} />;
  }
  if (!project) {
    return (
      <PageState
        kind="empty"
        section="Reporting"
        title="Reports"
        emptyTitle="No project selected"
        message="Create or pick a project from the project switcher in the top bar."
        art={<NoProjectIllo />}
      />
    );
  }

  const byKey = new Map(catalogue.map((c) => [c.key, c]));
  const editing = formats.find((f) => f.id === editingId) ?? null;
  const ordered = [...draftBlocks].sort((a, b) => a.order - b.order);

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Reporting
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Reports</div>
            <div className="page-desc">
              Pick the blocks a report contains, save it as a named format, then open it to read or
              print. Everything is generated from the current programme, so a report and the .xer it
              was built from can never disagree.
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: ".8rem 1.1rem" }}>
          <div style={{ display: "flex", gap: "1.4rem", flexWrap: "wrap", fontSize: ".75rem" }}>
            <span>
              <span style={{ color: "var(--text-muted)" }}>Data date </span>
              <b className="mono">{fmtP6Date(header?.data_date)}</b>
            </span>
            <span>
              <span style={{ color: "var(--text-muted)" }}>Revision </span>
              <b className="mono">{header?.schedule_revision ?? "—"}</b>
            </span>
            <span>
              <span style={{ color: "var(--text-muted)" }}>Baseline </span>
              <b className="mono">{header?.baseline_label ?? "None locked"}</b>
            </span>
          </div>
        </div>

        {!header?.data_date && (
          <div className="banner warn">
            <span className="banner-text">
              No schedule imported yet. Reports will render, but most blocks will have nothing to show
              until a .xer is uploaded from Program Library.
            </span>
          </div>
        )}

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Report formats</div>
              <div className="card-title-sub">
                The four standard ones are ready to use; add your own alongside them.
              </div>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Format</th>
                  <th>Blocks</th>
                  <th style={{ width: 260 }} />
                </tr>
              </thead>
              <tbody>
                {formats.map((f) => (
                  <tr key={f.id}>
                    <td>
                      <div className="subname">{f.name}</div>
                      <div className="actid">{f.description ?? "—"}</div>
                    </td>
                    <td className="num">{f.blocks.filter((b) => b.enabled).length}</td>
                    <td>
                      <div style={{ display: "flex", gap: ".3rem", justifyContent: "flex-end", flexWrap: "wrap" }}>
                        <Link className="btn btn-primary btn-sm" href={`/reporting/reports/${f.id}`}>
                          <BarChartIcon className="icon" /> Open
                        </Link>
                        <button className="btn btn-ghost btn-sm" onClick={() => startEdit(f)}>
                          <SettingsIcon className="icon" /> Edit
                        </button>
                        {!f.is_preset && (
                          <button className="btn btn-ghost btn-sm" onClick={() => deleteFormat(f)}>
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: ".5rem", padding: ".8rem 1.1rem", flexWrap: "wrap" }}>
            <input
              placeholder="New format name…"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") createFormat();
              }}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--radius-sm)",
                padding: ".35rem .5rem",
                fontSize: ".8125rem",
                minWidth: 200,
              }}
            />
            <button className="btn btn-secondary" onClick={createFormat} disabled={creating || !newName.trim()}>
              Add format
            </button>
          </div>
        </div>

        {editing && (
          <div className="card">
            <div className="card-head">
              <div>
                <div className="card-title">Editing &ldquo;{editing.name}&rdquo;</div>
                <div className="card-title-sub">
                  Tick the blocks this report contains and put them in the order they should print.
                </div>
              </div>
              <div style={{ display: "flex", gap: ".4rem", flexWrap: "wrap" }}>
                <button className="btn btn-primary" onClick={saveFormat} disabled={saving || !draftName.trim()}>
                  <CheckIcon className="icon" /> {saving ? "Saving…" : "Save"}
                </button>
                <button className="btn btn-ghost" onClick={() => setEditingId(null)} disabled={saving}>
                  Cancel
                </button>
              </div>
            </div>

            <div style={{ padding: "1rem 1.1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
              <label style={{ fontSize: ".6875rem", color: "var(--text-muted)", fontWeight: 600 }}>
                Format name
                <input
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  maxLength={120}
                  style={{
                    display: "block",
                    marginTop: ".2rem",
                    width: "100%",
                    maxWidth: 420,
                    background: "var(--surface)",
                    border: "1px solid var(--border-strong)",
                    borderRadius: "var(--radius-sm)",
                    padding: ".4rem .5rem",
                    fontSize: ".875rem",
                  }}
                />
              </label>

              <label style={{ fontSize: ".6875rem", color: "var(--text-muted)", fontWeight: 600 }}>
                Executive summary narrative
                <textarea
                  value={draftNarrative}
                  onChange={(e) => setDraftNarrative(e.target.value)}
                  rows={6}
                  placeholder="Are we ahead or behind, by how many days, on what, and what is being done about it. Blank lines start a new paragraph."
                  style={{
                    display: "block",
                    marginTop: ".2rem",
                    width: "100%",
                    background: "var(--surface)",
                    border: "1px solid var(--border-strong)",
                    borderRadius: "var(--radius-sm)",
                    padding: ".5rem",
                    fontSize: ".8125rem",
                    fontFamily: "inherit",
                    lineHeight: 1.6,
                    resize: "vertical",
                  }}
                />
              </label>

              <div className="report-picker">
                {ordered.map((b, i) => {
                  const meta = byKey.get(b.key);
                  if (!meta) return null;
                  return (
                    <div key={b.key} className={`report-picker-row${b.enabled ? " is-on" : ""}`}>
                      <label style={{ display: "flex", gap: ".5rem", alignItems: "flex-start", flex: 1 }}>
                        <input type="checkbox" checked={b.enabled} onChange={() => toggleBlock(b.key)} />
                        <span>
                          <span className="report-picker-title">{meta.title}</span>
                          <span className="report-picker-desc">{meta.description}</span>
                          {meta.requires && (
                            <span className="chip chip-neutral" style={{ marginTop: ".25rem" }}>
                              {REQUIREMENT_LABEL[meta.requires] ?? meta.requires}
                            </span>
                          )}
                        </span>
                      </label>
                      <div style={{ display: "flex", gap: ".2rem" }}>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => moveBlock(b.key, -1)}
                          disabled={i === 0}
                          aria-label={`Move ${meta.title} up`}
                        >
                          ↑
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => moveBlock(b.key, 1)}
                          disabled={i === ordered.length - 1}
                          aria-label={`Move ${meta.title} down`}
                        >
                          ↓
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Getting a PDF</div>
              <div className="card-title-sub">
                Open a report and press Print. Choose &ldquo;Save as PDF&rdquo; as the destination, and turn
                the browser&rsquo;s own headers and footers off so it doesn&rsquo;t stamp the URL over the
                page — the report prints its own data date and revision on every sheet.
              </div>
            </div>
            <DownloadIcon className="icon" />
          </div>
        </div>
      </div>
    </>
  );
}
