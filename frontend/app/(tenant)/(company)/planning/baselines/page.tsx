"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { Baseline, BaselineStatus } from "@/lib/types";
import { LockIcon } from "@/components/icons";

const STATUS_CHIP: Record<Baseline["status"], string> = {
  active: "chip-good",
  draft: "chip-neutral",
  superseded: "chip-neutral",
};

export default function BaselinesPage() {
  const { project } = useProjectContext();
  const [status, setStatus] = useState<BaselineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      if (!project) {
        setStatus(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        setStatus(await api.get<BaselineStatus>(`/projects/${project.id}/evm/baseline`));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load baselines.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [project]);

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>Baselines</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Baselines</div>
            <div className="page-desc">
              Every Performance Measurement Baseline ever locked for this project — the first one locks
              automatically from Program Library&apos;s first upload; each later one is a manual lock from the EVM page.
            </div>
          </div>
        </div>

        {loading ? (
          <p className="page-desc">Loading…</p>
        ) : error ? (
          <p className="login-error" style={{ maxWidth: 420 }}>
            {error}
          </p>
        ) : !project ? (
          <div className="card">
            <p className="empty-state">No project yet — create one from the project switcher.</p>
          </div>
        ) : (
          <div className="card">
            <div className="card-head">
              <div className="card-title">Baseline history</div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Status</th>
                    <th>BAC (hrs)</th>
                    <th>Target start</th>
                    <th>Target end</th>
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
                          <span className={`chip ${STATUS_CHIP[b.status]}`}>{b.status}</span>
                        </td>
                        <td className="num">{b.total_budget_manhours.toFixed(1)}</td>
                        <td className="num">{b.target_start_date}</td>
                        <td className="num">{b.target_end_date}</td>
                        <td className="num">{b.activity_count}</td>
                        <td>{b.locked_at ? new Date(b.locked_at).toLocaleString() : "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
