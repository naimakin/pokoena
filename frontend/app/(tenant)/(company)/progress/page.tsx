"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import type { Activity, BaselineStatus, ProgressEntryPayload, Project, WbsNode } from "@/lib/types";
import { ChevronDownIcon, ChevronUpIcon, ClockIcon } from "@/components/icons";

interface RowDraft {
  burnedHours: string;
  physicalPct: string;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ProgressInputPage() {
  const { showToast } = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [wbsNodes, setWbsNodes] = useState<WbsNode[]>([]);
  const [hasActiveBaseline, setHasActiveBaseline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [entryDate, setEntryDate] = useState(todayIso());
  const [drafts, setDrafts] = useState<Record<string, RowDraft>>({});
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const projects = await api.get<Project[]>("/projects");
        const active = projects[0] ?? null;
        setProject(active);
        if (!active) return;
        const [acts, wbs, baseline] = await Promise.all([
          api.get<Activity[]>(`/activities?project_id=${active.id}`),
          api.get<WbsNode[]>(`/projects/${active.id}/wbs-nodes`),
          api.get<BaselineStatus>(`/projects/${active.id}/evm/baseline`),
        ]);
        setActivities(acts);
        setWbsNodes(wbs);
        setHasActiveBaseline(baseline.has_active);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load activities.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const groups = useMemo(() => {
    const nodeByWbsId = new Map(wbsNodes.map((n) => [n.wbs_id, n]));
    const byGroup = new Map<string, Activity[]>();
    for (const a of activities) {
      const key = (a.wbs_path && nodeByWbsId.has(a.wbs_path) ? a.wbs_path : null) ?? "__ungrouped__";
      const list = byGroup.get(key) ?? [];
      list.push(a);
      byGroup.set(key, list);
    }
    return Array.from(byGroup.entries())
      .map(([wbsId, acts]) => ({
        wbsId,
        label: wbsId === "__ungrouped__" ? "Ungrouped" : nodeByWbsId.get(wbsId)?.wbs_name ?? wbsId,
        activities: acts.sort((a, b) => a.external_id.localeCompare(b.external_id)),
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [activities, wbsNodes]);

  function toggleGroup(wbsId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(wbsId)) next.delete(wbsId);
      else next.add(wbsId);
      return next;
    });
  }

  function setDraft(activityId: string, field: keyof RowDraft, value: string) {
    setDrafts((prev) => ({ ...prev, [activityId]: { ...prev[activityId], [field]: value } }));
  }

  const pendingCount = Object.values(drafts).filter((d) => d.burnedHours && Number(d.burnedHours) > 0).length;

  async function submitProgress() {
    if (!project) return;
    const entries: ProgressEntryPayload[] = Object.entries(drafts)
      .filter(([, d]) => d.burnedHours && Number(d.burnedHours) > 0)
      .map(([activityId, d]) => ({
        activity_id: activityId,
        entry_date: entryDate,
        burned_manhours_daily: Number(d.burnedHours),
        physical_pct_snapshot: d.physicalPct ? Number(d.physicalPct) : undefined,
      }));
    if (entries.length === 0) return;

    setSubmitting(true);
    try {
      const result = await api.post<{ written: number; out_of_sequence_count: number }>(
        `/projects/${project.id}/evm/progress`,
        { entries }
      );
      showToast(
        `${result.written} progress entr${result.written === 1 ? "y" : "ies"} recorded` +
          (result.out_of_sequence_count > 0 ? ` (${result.out_of_sequence_count} out of sequence)` : "")
      );
      setDrafts({});
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to submit progress.");
    } finally {
      setSubmitting(false);
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
          {project?.name ?? "—"} / <b>Progress Input</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Progress Input</div>
            <div className="page-desc">Log today&rsquo;s burned manhours per activity — feeds the EVM S-Curve</div>
          </div>
        </div>

        {!hasActiveBaseline && (
          <div className="banner" style={{ marginBottom: "1rem" }}>
            <ClockIcon className="icon" style={{ color: "var(--warn)" }} />
            <span style={{ fontSize: ".8125rem" }}>
              No baseline is locked yet — progress can be entered, but submission requires an active baseline
              (lock one from EVM / S-Curve first).
            </span>
          </div>
        )}

        {activities.length === 0 ? (
          <div className="card">
            <p className="empty-state">No activities yet — import a schedule from Project Files.</p>
          </div>
        ) : (
          <div className="card">
            <div className="card-head" style={{ flexWrap: "wrap", gap: ".6rem" }}>
              <div className="field" style={{ maxWidth: 200 }}>
                <label htmlFor="entry-date">Entry date</label>
                <input id="entry-date" type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
              </div>
              <button className="btn btn-primary" onClick={submitProgress} disabled={submitting || pendingCount === 0 || !hasActiveBaseline}>
                {submitting ? "Submitting…" : `Submit Progress (${pendingCount})`}
              </button>
            </div>

            {groups.map((group) => {
              const isCollapsed = collapsed.has(group.wbsId);
              return (
                <div key={group.wbsId}>
                  <button
                    onClick={() => toggleGroup(group.wbsId)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: ".4rem",
                      width: "100%",
                      padding: ".6rem 1.1rem",
                      background: "var(--surface-2)",
                      border: "none",
                      borderBottom: "1px solid var(--border)",
                      borderTop: "1px solid var(--border)",
                      cursor: "pointer",
                      fontSize: ".75rem",
                      fontWeight: 700,
                      textAlign: "left",
                    }}
                  >
                    {isCollapsed ? <ChevronDownIcon className="icon" style={{ width: 14, height: 14 }} /> : <ChevronUpIcon className="icon" style={{ width: 14, height: 14 }} />}
                    {group.label}
                    <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>({group.activities.length})</span>
                  </button>
                  {!isCollapsed && (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Activity</th>
                            <th>Status</th>
                            <th>% Complete</th>
                            <th style={{ width: 160 }}>Burned Hours Today</th>
                            <th style={{ width: 160 }}>New % Complete</th>
                          </tr>
                        </thead>
                        <tbody>
                          {group.activities.map((a) => (
                            <tr key={a.id}>
                              <td>
                                <div className="subname">{a.name}</div>
                                <div className="actid">{a.external_id}</div>
                              </td>
                              <td style={{ textTransform: "capitalize" }}>{a.status.replace("_", " ")}</td>
                              <td className="num">{a.percent_complete}%</td>
                              <td>
                                <input
                                  type="number"
                                  min={0}
                                  step="0.5"
                                  placeholder="0"
                                  value={drafts[a.id]?.burnedHours ?? ""}
                                  onChange={(e) => setDraft(a.id, "burnedHours", e.target.value)}
                                />
                              </td>
                              <td>
                                <input
                                  type="number"
                                  min={0}
                                  max={100}
                                  placeholder={String(a.percent_complete)}
                                  value={drafts[a.id]?.physicalPct ?? ""}
                                  onChange={(e) => setDraft(a.id, "physicalPct", e.target.value)}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
