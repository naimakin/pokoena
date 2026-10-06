"use client";

import { useEffect, useMemo, useState } from "react";
import { PageState } from "@/components/PageShell";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useProjectContext } from "@/lib/project-context";
import type { ChangeRequest, DashboardSummary } from "@/lib/types";
import { ArrowRightIcon, CheckIcon, XIcon } from "@/components/icons";

export default function ReviewQueuePage() {
  const { showToast } = useToast();
  const { project } = useProjectContext();
  const [items, setItems] = useState<ChangeRequest[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!project) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const summary = await api.get<DashboardSummary>(`/dashboard/summary?project_id=${project.id}`);
      if (!summary.active_period_id) {
        setItems([]);
        return;
      }
      const changeRequests = await api.get<ChangeRequest[]>(
        `/change-requests?update_period_id=${summary.active_period_id}`
      );
      setItems(changeRequests);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the review queue.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  const selectableIds = useMemo(
    () => new Set(items.filter((item) => item.status === "pending").map((item) => item.id)),
    [items]
  );

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll(checked: boolean) {
    setSelected(checked ? new Set(selectableIds) : new Set());
  }

  async function approve(id: string) {
    try {
      await api.post<ChangeRequest>(`/change-requests/${id}/approve`);
      showToast("Change approved and queued for P6 export");
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to approve change.", "error");
    }
  }

  async function reject(id: string) {
    try {
      await api.post<ChangeRequest>(`/change-requests/${id}/reject`);
      showToast("Change rejected — subcontractor will be notified");
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to reject change.", "error");
    }
  }

  async function bulkApprove() {
    if (selected.size === 0) return;
    try {
      await api.post<ChangeRequest[]>("/change-requests/bulk-approve", { ids: Array.from(selected) });
      showToast(`${selected.size} change(s) approved and queued for P6 export`);
      setSelected(new Set());
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to bulk approve.", "error");
    }
  }

  if (loading) {
    return <PageState kind="loading" section="Delivery" title="Flag Reviews" />;
  }
  if (error) {
    return <PageState kind="error" section="Delivery" title="Flag Reviews" message={error} />;
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          Delivery
        </span>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Flag Reviews</div>
            <div className="page-desc">Logic, lag, and dependency changes flagged by scope owners</div>
          </div>
          <button className="btn btn-primary" onClick={bulkApprove} disabled={selected.size === 0}>
            <CheckIcon className="icon" /> Bulk Approve Selected ({selected.size})
          </button>
        </div>

        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: "2rem" }}>
                    <input
                      type="checkbox"
                      className="rowcheck"
                      checked={selectableIds.size > 0 && selected.size === selectableIds.size}
                      onChange={(e) => toggleAll(e.target.checked)}
                    />
                  </th>
                  <th>Requested by</th>
                  <th>Activity</th>
                  <th>Field changed</th>
                  <th>Before &rarr; After</th>
                  <th>Justification</th>
                  <th>Risk</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 && (
                  <tr>
                    <td colSpan={9} className="empty-state">
                      No flagged changes for this period.
                    </td>
                  </tr>
                )}
                {items.map((item) => {
                  const isPending = item.status === "pending";
                  const who = item.requested_by_org ?? item.requested_by_name ?? "Unknown";
                  return (
                    <tr key={item.id} className={isPending ? "" : "resolved"}>
                      <td>
                        <input
                          type="checkbox"
                          className="rowcheck"
                          disabled={!isPending}
                          checked={selected.has(item.id)}
                          onChange={() => toggle(item.id)}
                        />
                      </td>
                      <td>
                        <div className="who-cell">
                          <div className="subrow-avatar">{who.slice(0, 2).toUpperCase()}</div>
                          {who}
                        </div>
                      </td>
                      <td>
                        {item.activity_name && <div className="subname">{item.activity_name}</div>}
                        {item.activity_external_id && <div className="actid">{item.activity_external_id}</div>}
                      </td>
                      <td>{item.field_changed}</td>
                      <td>
                        <div className="diff-line">
                          <span className="diff-before">{item.before_value}</span>
                          <ArrowRightIcon className="icon" />
                          <span className="diff-after">{item.after_value}</span>
                        </div>
                      </td>
                      <td className="justif">{item.justification}</td>
                      <td className={`risk-${item.risk_level}`} style={{ textTransform: "capitalize" }}>
                        {item.risk_level}
                      </td>
                      <td>
                        {item.status === "pending" && <span className="chip chip-warn">Pending</span>}
                        {item.status === "approved" && <span className="chip chip-good">Approved</span>}
                        {item.status === "rejected" && <span className="chip chip-crit">Rejected</span>}
                      </td>
                      <td>
                        {isPending && (
                          <div className="actions">
                            <button className="act-btn act-approve" title="Approve" onClick={() => approve(item.id)}>
                              <CheckIcon className="icon" />
                            </button>
                            <button className="act-btn act-reject" title="Reject" onClick={() => reject(item.id)}>
                              <XIcon className="icon" />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
