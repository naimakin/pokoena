"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { BarChartIcon, BuildingIcon, CheckIcon, UsersIcon } from "@/components/icons";
import type { UsageSummary } from "@/lib/types";

export default function PlatformUsagePage() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<UsageSummary>("/platform/usage")
      .then(setUsage)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load usage data."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          <b>Usage</b>
        </span>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Aggregate usage</div>
            <div className="page-desc">
              Anonymized counts only — no tenant business data. Use support access on a tenant's page for anything more.
            </div>
          </div>
        </div>

        {loading && <p className="page-desc">Loading…</p>}
        {error && <p className="login-error">{error}</p>}

        {usage && (
          <div className="kpi-row">
            <div className="card kpi">
              <div className="kpi-top">
                <span className="kpi-label">Tenants</span>
                <div className="kpi-icon" style={{ background: "var(--info-soft)", color: "var(--info)" }}>
                  <BuildingIcon className="icon" />
                </div>
              </div>
              <div className="kpi-value">{usage.tenant_count}</div>
              <div className="kpi-sub">{usage.active_tenant_count} active</div>
            </div>

            <div className="card kpi">
              <div className="kpi-top">
                <span className="kpi-label">Users</span>
                <div className="kpi-icon" style={{ background: "var(--good-soft)", color: "var(--good)" }}>
                  <UsersIcon className="icon" />
                </div>
              </div>
              <div className="kpi-value">{usage.total_users}</div>
              <div className="kpi-sub">Across all tenants</div>
            </div>

            <div className="card kpi">
              <div className="kpi-top">
                <span className="kpi-label">Projects</span>
                <div className="kpi-icon" style={{ background: "var(--warn-soft)", color: "var(--warn)" }}>
                  <BarChartIcon className="icon" />
                </div>
              </div>
              <div className="kpi-value">{usage.total_projects}</div>
              <div className="kpi-sub">Across all tenants</div>
            </div>

            <div className="card kpi">
              <div className="kpi-top">
                <span className="kpi-label">Status</span>
                <div className="kpi-icon" style={{ background: "var(--good-soft)", color: "var(--good)" }}>
                  <CheckIcon className="icon" />
                </div>
              </div>
              <div className="kpi-value" style={{ fontSize: "1.1rem" }}>
                Computed live
              </div>
              <div className="kpi-sub">Per-tenant counts, not row content</div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
