"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import { BLOCK_REGISTRY, type BlockContext } from "@/components/reporting/ReportBlocks";
import { fmtP6Date, fmtP6DateTime } from "@/components/reporting/format";
import { ArrowRightIcon, DownloadIcon } from "@/components/icons";
import type { ReportFormat, ReportHeader } from "@/lib/types";

export default function ReportPage() {
  const { project } = useProjectContext();
  const params = useParams<{ formatId: string }>();
  const formatId = params?.formatId;

  const [format, setFormat] = useState<ReportFormat | null>(null);
  const [header, setHeader] = useState<ReportHeader | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!project || !formatId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [f, h] = await Promise.all([
        api.get<ReportFormat>(`/projects/${project.id}/report-formats/${formatId}`),
        api.get<ReportHeader>(`/projects/${project.id}/report-header`),
      ]);
      setFormat(f);
      setHeader(h);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load the report.");
    } finally {
      setLoading(false);
    }
  }, [project, formatId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="a-content">
        <p className="page-desc">Loading…</p>
      </div>
    );
  }
  if (error || !format || !project) {
    return (
      <div className="a-content">
        <p className="login-error" style={{ maxWidth: 420 }}>{error ?? "Report not found."}</p>
      </div>
    );
  }

  const blocks = format.blocks
    .filter((b) => b.enabled && BLOCK_REGISTRY[b.key])
    .sort((a, b) => a.order - b.order);

  const landscape = format.page_setup?.orientation === "landscape";

  return (
    <>
      <div className="a-topbar no-print">
        <span className="crumb">
          {project.name} / <Link href="/reporting/reports">Reports</Link> / <b>{format.name}</b>
        </span>
      </div>
      <div className={`a-content report-sheet${landscape ? " is-landscape" : ""}`}>
        <div className="page-head no-print">
          <div>
            <div className="page-title">{format.name}</div>
            <div className="page-desc">{format.description ?? `${blocks.length} blocks`}</div>
          </div>
          <div style={{ display: "flex", gap: ".4rem", flexWrap: "wrap" }}>
            <Link className="btn btn-ghost" href="/reporting/reports">
              Back to formats
            </Link>
            <button className="btn btn-primary" onClick={() => window.print()}>
              <DownloadIcon className="icon" /> Print / Save as PDF
            </button>
          </div>
        </div>

        {/* The running header. Chrome has no support for CSS @page margin
            boxes, but it does repeat a <thead> on every printed page — which
            is the only reliable way to get the data date and revision onto
            sheet 2 onwards, and a report missing those gets rejected. */}
        <table className="report-running">
          <thead>
            <tr>
              <th>
                <div className="report-runhead">
                  <span>
                    <b>{header?.project_name ?? project.name}</b>
                    <span className="mono"> · {header?.project_code ?? project.code}</span>
                  </span>
                  <span className="report-runhead-right mono">
                    {format.name} · Data date {fmtP6Date(header?.data_date)} ·{" "}
                    {header?.schedule_revision ?? "no revision"}
                  </span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                {blocks.length === 0 ? (
                  <div className="card">
                    <p className="empty-state">
                      This format has no blocks selected yet.{" "}
                      <Link href="/reporting/reports">Edit the format</Link> to pick some.
                    </p>
                  </div>
                ) : (
                  blocks.map((b) => {
                    const Block = BLOCK_REGISTRY[b.key];
                    const ctx: BlockContext = {
                      project,
                      header,
                      narrative: format.narrative,
                      options: b.options ?? {},
                    };
                    return <Block key={b.key} {...ctx} />;
                  })
                )}

                <div className="report-footer">
                  <span>
                    Generated {fmtP6DateTime(header?.generated_at)} by {header?.generated_by ?? "—"} from{" "}
                    <span className="mono">{header?.schedule_filename ?? "no import"}</span>
                    {header?.imported_at && ` (imported ${fmtP6Date(header.imported_at)})`}.
                  </span>
                  <span>{header?.progress_basis}</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <div className="no-print" style={{ display: "flex", justifyContent: "flex-end" }}>
          <Link className="btn btn-ghost btn-sm" href="/reporting/reports">
            Back to formats <ArrowRightIcon className="icon" />
          </Link>
        </div>
      </div>
    </>
  );
}
