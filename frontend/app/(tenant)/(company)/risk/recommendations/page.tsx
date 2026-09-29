"use client";

// Risk > Recommendations — every rule-based recommendation in one prioritised
// list: the latest QSRA run's, the early warnings', and the resource
// productivity checks' (backend routes/risk.py::get_recommendations). Rules,
// not a model: each message says what triggered it, so it can be checked.

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { QsraRunSummary, RiskRecommendation } from "@/lib/types";
import { RecommendationList } from "@/components/risk/RecommendationList";
import { fmtDate } from "@/components/risk/RiskCharts";

export default function RiskRecommendationsPage() {
  const { project, loading: loadingProject } = useProjectContext();
  const [items, setItems] = useState<RiskRecommendation[]>([]);
  const [run, setRun] = useState<QsraRunSummary | null>(null);
  const [area, setArea] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!project) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<{ run: QsraRunSummary | null; items: RiskRecommendation[] }>(
        `/projects/${project.id}/risk/recommendations`,
      );
      setItems(res.items);
      setRun(res.run);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load recommendations.");
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    load();
  }, [load]);

  const areas = useMemo(() => Array.from(new Set(items.map((i) => i.area))).sort(), [items]);
  const shown = area ? items.filter((i) => i.area === area) : items;

  if (loadingProject || loading) {
    return (
      <div className="a-content">
        <p className="page-desc">Loading…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="a-content">
        <p className="login-error" style={{ maxWidth: 420 }}>{error}</p>
      </div>
    );
  }

  const red = items.filter((i) => i.severity === "red").length;
  const amber = items.filter((i) => i.severity === "amber").length;

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          {project?.name ?? "—"} / <b>Recommendations</b>
        </span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Recommendations</div>
            <div className="page-desc">
              {red} to act on, {amber} to watch — from{" "}
              {run ? `the QSRA run of ${fmtDate(run.created_at)}` : <Link href="/risk">no QSRA run yet</Link>}, the early
              warnings and the resource checks.
            </div>
          </div>
          {areas.length > 1 && (
            <div className="segmented">
              <button className={area === "" ? "active" : ""} onClick={() => setArea("")}>All</button>
              {areas.map((a) => (
                <button key={a} className={area === a ? "active" : ""} onClick={() => setArea(a)}>{a}</button>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <RecommendationList
            items={shown}
            empty="Nothing flagged. Run QSRA with quantified risks, and keep uploading schedule updates — the early warnings need at least two."
          />
        </div>
      </div>
    </>
  );
}
