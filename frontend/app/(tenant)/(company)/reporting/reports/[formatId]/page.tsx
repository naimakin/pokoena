"use client";

import { useCallback, useEffect, useState } from "react";
import { PageState } from "@/components/PageShell";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import { BLOCK_REGISTRY, HALF_WIDTH_BLOCKS, type BlockContext } from "@/components/reporting/ReportBlocks";
import { FoldAllControls, FoldKey, FoldProvider } from "@/components/reporting/collapse";
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
  // Folded block keys. Screen only — print opens every block regardless.
  const [closed, setClosed] = useState<ReadonlySet<string>>(() => new Set());

  const setBlockOpen = useCallback((key: string, open: boolean) => {
    setClosed((prev) => {
      const next = new Set(prev);
      if (open) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

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
    return <PageState kind="loading" section="Reports" title="Report" />;
  }
  if (error || !format || !project) {
    return <PageState kind="error" section="Reports" title="Report" message={error ?? "Report not found."} />;
  }

  const blocks = format.blocks
    .filter((b) => b.enabled && BLOCK_REGISTRY[b.key])
    .sort((a, b) => a.order - b.order);

  const landscape = format.page_setup?.orientation === "landscape";

  // The cover never folds, so it is not part of "collapse all".
  const foldable = blocks.filter((b) => b.key !== "cover").map((b) => b.key);

  // Two adjacent half-width blocks share a row; anything else takes the full
  // width. Only neighbours pair up, so the format's order is never changed.
  const rows: (typeof blocks)[] = [];
  for (let i = 0; i < blocks.length; i++) {
    const next = blocks[i + 1];
    if (HALF_WIDTH_BLOCKS.has(blocks[i].key) && next && HALF_WIDTH_BLOCKS.has(next.key)) {
      rows.push([blocks[i], next]);
      i++;
    } else {
      rows.push([blocks[i]]);
    }
  }

  function renderBlock(b: (typeof blocks)[number]) {
    if (!project || !format) return null;
    const Block = BLOCK_REGISTRY[b.key];
    const ctx: BlockContext = {
      project,
      header,
      narrative: format.narrative,
      options: b.options ?? {},
    };
    return (
      <FoldKey key={b.key} id={b.key}>
        <Block {...ctx} />
      </FoldKey>
    );
  }

  return (
    <>
      <div className="a-topbar no-print">
        <span className="crumb">
          Reports / <Link href="/reporting/reports">Reports</Link>
        </span>
      </div>
      <div className={`a-content report-sheet${landscape ? " is-landscape" : ""}`}>
        <div className="page-head no-print">
          <div>
            <div className="page-title">{format.name}</div>
            <div className="page-desc">{format.description ?? `${blocks.length} blocks`}</div>
          </div>
          <div className="report-actions">
            {foldable.length > 0 && (
              <FoldAllControls
                onExpand={() => setClosed(new Set())}
                onCollapse={() => setClosed(new Set(foldable))}
                canExpand={closed.size > 0}
                canCollapse={foldable.some((key) => !closed.has(key))}
              />
            )}
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
                  <FoldProvider closed={closed} onChange={setBlockOpen}>
                    {rows.map((row) =>
                      row.length === 2 ? (
                        <div className="report-pair" key={row.map((b) => b.key).join("+")}>
                          {row.map(renderBlock)}
                        </div>
                      ) : (
                        renderBlock(row[0])
                      ),
                    )}
                  </FoldProvider>
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
