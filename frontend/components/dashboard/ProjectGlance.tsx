"use client";

// Project Status's "At a glance" band: the Dashboard's KPI strip, gauges and
// behind-plan table for the whole project (the page's filters don't apply —
// it reads GET /dashboard/analytics, which is project-wide).

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ProjectAnalytics } from "@/lib/types";
import {
  AnalyticsState,
  BehindPlanLink,
  BehindPlanTable,
  CostGauge,
  HoursGauge,
  KpiStrip,
  TimeVsWork,
  type AnalyticsStatus,
} from "@/components/dashboard/AnalyticsWidgets";

function Panel({
  cell,
  title,
  sub,
  action,
  children,
}: {
  cell: string;
  title: string;
  sub: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className={`card dash-card ${cell}`}>
      <div className="card-head">
        <div>
          <div className="card-title">{title}</div>
          <div className="card-title-sub">{sub}</div>
        </div>
        {action}
      </div>
      <div className="dash-card-body">{children}</div>
    </section>
  );
}

export function ProjectGlance({ projectId }: { projectId: string }) {
  const [a, setA] = useState<ProjectAnalytics | null>(null);
  const [status, setStatus] = useState<AnalyticsStatus>("loading");

  useEffect(() => {
    let live = true;
    setA(null);
    setStatus("loading");
    api
      .get<ProjectAnalytics>(`/dashboard/analytics?project_id=${projectId}`)
      .then((res) => {
        if (!live) return;
        setA(res);
        setStatus("ready");
      })
      .catch((err) => {
        if (live) setStatus(err instanceof ApiError && err.status === 423 ? "locked" : "error");
      });
    return () => {
      live = false;
    };
  }, [projectId]);

  if (!a) {
    return status === "locked" ? null : (
      <div className="card">
        <AnalyticsState status={status} what="the project at a glance" />
      </div>
    );
  }

  const thirds = a.cost ? "dash-cell-third" : "dash-cell-half";
  return (
    <div className="dash-stack">
      <KpiStrip a={a} />
      <div className="dash-grid">
        <Panel cell={thirds} title="Labor hours" sub="Actual vs planned units %">
          <HoursGauge a={a} />
        </Panel>
        {a.cost && (
          <Panel cell={thirds} title="Cost" sub="Spent vs planned spend">
            <CostGauge a={a} />
          </Panel>
        )}
        <Panel cell={thirds} title="Time vs work" sub="Baseline span elapsed vs work done">
          <TimeVsWork a={a} />
        </Panel>
        <Panel
          cell="dash-cell-full"
          title={`Behind plan${a.behind_total ? ` · ${a.behind_total}` : ""}`}
          sub="Unfinished activities trailing the baseline's planned %"
          action={<BehindPlanLink />}
        >
          <BehindPlanTable a={a} />
        </Panel>
      </div>
    </div>
  );
}
