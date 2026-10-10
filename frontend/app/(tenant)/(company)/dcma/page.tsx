"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import Link from "next/link";
import { PageState } from "@/components/PageShell";
import { EmptyState } from "@/components/EmptyState";
import { UploadScheduleIllo } from "@/components/illustrations";
import { DcmaRing } from "@/components/dcma/DcmaRing";
import { DcmaTargetsModal } from "@/components/dcma/DcmaTargetsModal";
import {
  AlertTriangleIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  DownloadIcon,
  InfoIcon,
  SettingsIcon,
  XIcon,
} from "@/components/icons";
import { api, ApiError } from "@/lib/api";
import { findingsLabel, PokoFindings } from "@/components/dcma/PokoChecks";
import { FoldAllControls } from "@/components/reporting/collapse";
import {
  categoryLabel,
  checksCsv,
  countLabel,
  countShort,
  DCMA_CATEGORIES,
  factLabel,
  isCustom,
  isIndex,
  metaById,
  metaFor,
  resultLabel,
  scoreImpact,
  STATUS_CHIP,
  STATUS_LABEL,
  STATUS_STROKE,
  thresholdsOf,
  type DcmaCategory,
  type Thresholds,
} from "@/lib/dcma";
import { useProjectContext } from "@/lib/project-context";
import type { DcmaCheckResult, DcmaReport } from "@/lib/types";
import { can } from "@/lib/permissions";
import { useCurrentUser } from "@/lib/user-context";
import { HelpTip } from "@/components/HelpTip";

type Status = DcmaCheckResult["status"];
type StatusFilter = "all" | "fail" | "warn" | "pass";
type View = "cards" | "table";

const STATUS_FILTERS: { key: StatusFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "fail", label: "Failed" },
  { key: "warn", label: "Warnings" },
  { key: "pass", label: "Passed" },
];

function StatusIcon({ status }: { status: Status }) {
  if (status === "pass") return <CheckIcon className="icon" />;
  if (status === "warn") return <AlertTriangleIcon className="icon" />;
  if (status === "fail") return <XIcon className="icon" />;
  return <InfoIcon className="icon" />;
}

function StatusChip({ status }: { status: Status }) {
  return (
    <span className={`chip ${STATUS_CHIP[status]}`}>
      <StatusIcon status={status} />
      {STATUS_LABEL[status]}
    </span>
  );
}

function impactLabel(impact: number): string {
  return impact === 0 ? "—" : `−${Math.abs(impact).toFixed(1)}`;
}

// A card is at least this wide; the page fits as many columns as that allows
// (at most five, the largest category) and lets each row's sections share it.
const CARD_MIN = 300;
const GAP_PX = 16;
const FOLD_KEY = "poko.dcma.folded";

function tally(checks: DcmaCheckResult[]) {
  const c = { pass: 0, warn: 0, fail: 0, not_tracked: 0 };
  for (const check of checks) c[check.status] += 1;
  return c;
}

function ringLabel(check: DcmaCheckResult, t: Thresholds): string {
  const m = metaFor(check, t);
  return `${m.title}: ${resultLabel(check)} (${countLabel(check)}). Target ${m.target}. ${STATUS_LABEL[check.status]}.`;
}

export default function DcmaPage() {
  const { project } = useProjectContext();
  const user = useCurrentUser();
  const [report, setReport] = useState<DcmaReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [category, setCategory] = useState<DcmaCategory | "all">("all");
  const [view, setView] = useState<View>("cards");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  // The targets editor: closed (null), or open at one check (or none).
  const [targetsAt, setTargetsAt] = useState<number | "all" | null>(null);
  const [cols, setCols] = useState(5);
  const flowRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      if (!project) {
        setReport(null);
        setLoading(false);
        return;
      }
      if (!quiet) setLoading(true);
      setError(null);
      try {
        setReport(await api.get<DcmaReport>(`/projects/${project.id}/dcma`));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load the DCMA report.");
      } finally {
        setLoading(false);
      }
    },
    [project],
  );

  useEffect(() => {
    load();
  }, [load]);

  // How many card columns fit; re-measured as the page resizes.
  const measure = useCallback((el: HTMLDivElement | null) => {
    flowRef.current = el;
    if (el) setCols(Math.max(1, Math.min(5, Math.floor((el.clientWidth + GAP_PX) / (CARD_MIN + GAP_PX)))));
  }, []);
  useEffect(() => {
    const el = flowRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => measure(el));
    ro.observe(el);
    return () => ro.disconnect();
  }, [measure, view, report]);

  const t = useMemo(() => thresholdsOf(report), [report]);
  const canEdit = Boolean(report?.can_edit_thresholds);
  const customCount = useMemo(
    () => (report?.checks ?? []).filter((c) => isCustom(c.id, report)).length,
    [report],
  );

  // The score, the summary tallies and "Passing by category" are DCMA's 14;
  // POKO's own (unscored) checks are a section of their own, listed first.
  const allChecks = useMemo(() => report?.checks ?? [], [report]);
  const dcmaChecks = useMemo(() => allChecks.filter((c) => c.scored !== false), [allChecks]);
  const pokoChecks = useMemo(() => allChecks.filter((c) => c.scored === false), [allChecks]);

  const counts = useMemo(() => tally(dcmaChecks), [dcmaChecks]);
  // What each status filter would show, POKO checks included.
  const filterCounts = useMemo(() => tally(allChecks), [allChecks]);

  useEffect(() => {
    if (category === "poko" && pokoChecks.length === 0) setCategory("all");
  }, [category, pokoChecks.length]);

  const visible = useMemo(
    () =>
      allChecks.filter(
        (c) =>
          (statusFilter === "all" || c.status === statusFilter) &&
          (category === "all" || metaFor(c, t).category === category),
      ),
    [allChecks, statusFilter, category, t],
  );

  const byCategory = useMemo(
    () =>
      DCMA_CATEGORIES.map((cat) => {
        const all = dcmaChecks.filter((c) => metaFor(c, t).category === cat.key);
        const applicable = all.filter((c) => c.status !== "not_tracked");
        return {
          ...cat,
          total: applicable.length,
          passed: applicable.filter((c) => c.status === "pass").length,
          shown: visible.filter((c) => metaFor(c, t).category === cat.key),
        };
      }),
    [dcmaChecks, visible, t],
  );

  const pokoAttention = pokoChecks.filter((c) => c.status !== "pass").length;
  const sections = useMemo(() => {
    const dcma = byCategory.map((cat) => ({
      key: cat.key as DcmaCategory,
      label: cat.label,
      sub: `${cat.passed} of ${cat.total} passing`,
      shown: cat.shown,
    }));
    if (pokoChecks.length === 0) return dcma;
    const poko = {
      key: "poko" as DcmaCategory,
      label: categoryLabel("poko"),
      sub: `${pokoAttention > 0 ? `${pokoAttention} of ${pokoChecks.length} need attention` : "All clean"} · not scored`,
      shown: visible.filter((c) => c.scored === false),
    };
    return [poko, ...dcma];
  }, [byCategory, pokoChecks.length, pokoAttention, visible]);

  // Folded sections, remembered per browser; shared by Charts and Table.
  const [closed, setClosed] = useState<Set<string>>(new Set());
  useEffect(() => {
    try {
      const raw = localStorage.getItem(FOLD_KEY);
      if (raw) setClosed(new Set(JSON.parse(raw) as string[]));
    } catch {
      /* ignore */
    }
  }, []);
  const saveClosed = useCallback((next: Set<string>) => {
    setClosed(next);
    try {
      localStorage.setItem(FOLD_KEY, JSON.stringify([...next]));
    } catch {
      /* ignore */
    }
  }, []);
  const setSectionOpen = useCallback(
    (key: string, open: boolean) => {
      const next = new Set(closed);
      if (open) next.delete(key);
      else next.add(key);
      saveClosed(next);
    },
    [closed, saveClosed],
  );
  function pickCategory(key: DcmaCategory | "all") {
    setCategory(key);
    if (key !== "all" && closed.has(key)) setSectionOpen(key, true);
  }
  const shownSections = sections.filter((s) => s.shown.length > 0);

  function toggle(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function downloadCsv() {
    if (!report || !project) return;
    const blob = new Blob([checksCsv(report)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${project.code}-DCMA-14-point.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  if (loading) return <PageState kind="loading" section="Reports" title="Schedule Quality" />;
  if (error) return <PageState kind="error" section="Reports" title="Schedule Quality" message={error} />;

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">Reports</span>
      </div>
      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">
              Schedule Quality <HelpTip id="page.schedule-quality" />
            </div>
            <div className="page-desc">
              DCMA 14-Point assessment per DCMA EA PAM 200.1, plus POKO&apos;s own data and sequence checks
            </div>
          </div>
        </div>

        {!report || report.total_activities === 0 ? (
          <div className="card">
            <EmptyState
              art={<UploadScheduleIllo />}
              title="No schedule imported yet"
              body="Upload a Primavera P6 .xer from Programme Files to run the DCMA check."
              action={
                <Link className="btn btn-primary btn-sm" href="/project-files">
                  Go to Programme Files
                </Link>
              }
            />
          </div>
        ) : (
          <>
            {/* ---- Summary ---- */}
            <div className="card dcma-summary">
              <DcmaRing
                pct={report.overall_score}
                stroke={STATUS_STROKE[report.overall_status as Status]}
                size={148}
                thickness={12}
                label={`Overall schedule quality score ${report.overall_score.toFixed(0)} of 100`}
              >
                <span className="dcma-score-value">{report.overall_score.toFixed(0)}</span>
                <span className="dcma-ring-sub">of 100</span>
              </DcmaRing>

              <div style={{ minWidth: 0 }}>
                <div className="dcma-summary-title">
                  <span className="card-title">
                    Overall schedule quality <HelpTip id="dcma.overall" />
                  </span>
                  <StatusChip status={report.overall_status as Status} />
                </div>
                <div className="dcma-summary-meta">
                  {report.total_activities} activities · {report.in_scope} unfinished in scope · computed{" "}
                  {new Date(report.computed_at).toLocaleString()}
                  {customCount > 0 && (
                    <>
                      {" · "}
                      <span className="dcma-custom-note">
                        Project targets on {customCount} check{customCount === 1 ? "" : "s"}
                      </span>
                    </>
                  )}
                </div>
                <div className="dcma-tallies">
                  {(["pass", "warn", "fail"] as const).map((s) => (
                    <button
                      key={s}
                      type="button"
                      className={`dcma-tally${statusFilter === s ? " is-on" : ""}`}
                      onClick={() => setStatusFilter(statusFilter === s ? "all" : s)}
                      title={statusFilter === s ? "Show all checks" : `Show only ${STATUS_LABEL[s].toLowerCase()} checks`}
                    >
                      <span className="dcma-tally-label">
                        <span className="dcma-dot" style={{ background: STATUS_STROKE[s] }} />
                        {s === "pass" ? "Passed" : s === "warn" ? "Warnings" : "Failed"}
                      </span>
                      <span className="dcma-tally-value">{counts[s]}</span>
                    </button>
                  ))}
                  <div className="dcma-tally dcma-tally-static">
                    <span className="dcma-tally-label">
                      <span className="dcma-dot" style={{ background: STATUS_STROKE.not_tracked }} />
                      Not tracked
                    </span>
                    <span className="dcma-tally-value">{counts.not_tracked}</span>
                  </div>
                </div>
              </div>

              <div className="dcma-cats">
                <div className="dcma-cats-title">Passing by category</div>
                {byCategory.map((cat) => (
                  <button
                    key={cat.key}
                    type="button"
                    className={`dcma-cat-row${category === cat.key ? " is-on" : ""}`}
                    onClick={() => pickCategory(category === cat.key ? "all" : cat.key)}
                  >
                    <span>{cat.label}</span>
                    <span className="mono">
                      {cat.passed}/{cat.total}
                    </span>
                    <span className="progress" aria-hidden>
                      <span
                        style={{
                          display: "block",
                          height: "100%",
                          width: `${cat.total ? (cat.passed / cat.total) * 100 : 0}%`,
                          background: "var(--good)",
                          borderRadius: "inherit",
                        }}
                      />
                    </span>
                  </button>
                ))}
                {pokoChecks.length > 0 && (
                  <button
                    type="button"
                    className={`dcma-cat-row dcma-cats-poko${category === "poko" ? " is-on" : ""}`}
                    onClick={() => pickCategory(category === "poko" ? "all" : "poko")}
                  >
                    <span>
                      POKO checks
                      <span className="dcma-cats-poko-sub">Not in the score</span>
                    </span>
                    <span className={`mono${pokoAttention > 0 ? " dcma-cats-poko-warn" : ""}`}>
                      {pokoAttention > 0 ? `${pokoAttention} to review` : "Clean"}
                    </span>
                  </button>
                )}
              </div>
            </div>

            {/* ---- Filters ---- */}
            <div className="card dcma-toolbar">
              <div className="segmented" role="group" aria-label="Status">
                {STATUS_FILTERS.map((f) => (
                  <button
                    key={f.key}
                    className={statusFilter === f.key ? "active" : ""}
                    onClick={() => setStatusFilter(f.key)}
                  >
                    {f.label}{" "}
                    <span className="dcma-count">
                      {f.key === "all" ? allChecks.length : filterCounts[f.key]}
                    </span>
                  </button>
                ))}
              </div>
              <div className="segmented" role="group" aria-label="Category">
                <button className={category === "all" ? "active" : ""} onClick={() => pickCategory("all")}>
                  All categories
                </button>
                {DCMA_CATEGORIES.map((cat) => (
                  <button
                    key={cat.key}
                    className={category === cat.key ? "active" : ""}
                    onClick={() => pickCategory(cat.key)}
                  >
                    {cat.label}
                  </button>
                ))}
                {pokoChecks.length > 0 && (
                  <button className={category === "poko" ? "active" : ""} onClick={() => pickCategory("poko")}>
                    POKO checks
                  </button>
                )}
              </div>
              <span className="dcma-spacer" />
              <FoldAllControls
                onExpand={() => saveClosed(new Set())}
                onCollapse={() => saveClosed(new Set(shownSections.map((s) => s.key)))}
                canExpand={shownSections.some((s) => closed.has(s.key))}
                canCollapse={shownSections.some((s) => !closed.has(s.key))}
              />
              <div className="segmented" role="group" aria-label="View">
                <button className={view === "cards" ? "active" : ""} onClick={() => setView("cards")}>
                  Charts
                </button>
                <button className={view === "table" ? "active" : ""} onClick={() => setView("table")}>
                  Table
                </button>
              </div>
              {canEdit && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setTargetsAt("all")}
                  title="Set this project's own targets for the checks"
                >
                  <SettingsIcon className="icon" /> Targets
                </button>
              )}
              {can(user, "export") && (
                <button className="btn btn-secondary btn-sm" onClick={downloadCsv} title="Download the checks as CSV">
                  <DownloadIcon className="icon" /> CSV
                </button>
              )}
            </div>

            {visible.length === 0 ? (
              <div className="card">
                <p className="empty-state">No checks match this filter.</p>
              </div>
            ) : view === "cards" ? (
              // Categories sit side by side when they fit (Dates + Duration +
              // Performance share a row), and a row with room to spare widens
              // its cards rather than leaving a hole.
              <div className="dcma-flow" ref={measure}>
                {shownSections.map((cat) => {
                    const n = cat.shown.length;
                    const span = Math.min(n, cols);
                    const perRow = Math.ceil(n / Math.ceil(n / cols));
                    const style = {
                      flexGrow: span,
                      flexBasis: `calc((100% - ${(cols - 1) * GAP_PX}px) * ${span / cols} + ${(span - 1) * GAP_PX}px - 1px)`,
                      "--dcma-per": perRow,
                    } as CSSProperties;
                    const open = !closed.has(cat.key);
                    return (
                      <section
                        key={cat.key}
                        className={`dcma-section${cat.key === "poko" ? " is-poko" : ""}`}
                        style={style}
                      >
                        <SectionHead
                          id={`dcma-sec-${cat.key}`}
                          open={open}
                          onToggle={() => setSectionOpen(cat.key, !open)}
                          title={cat.label}
                          sub={cat.sub}
                          hint={`${n} check${n === 1 ? "" : "s"}`}
                        />
                        <div id={`dcma-sec-${cat.key}`} className={`dcma-grid fold-body${open ? "" : " is-folded"}`}>
                          {cat.shown.map((check) => (
                            <CheckCard
                              key={check.id}
                              check={check}
                              t={t}
                              custom={isCustom(check.id, report)}
                              onEditTarget={
                                canEdit && metaById(check.id).fields.length > 0 ? () => setTargetsAt(check.id) : undefined
                              }
                              impact={scoreImpact(check, report)}
                              open={expanded.has(check.id)}
                              onToggle={() => toggle(check.id)}
                            />
                          ))}
                        </div>
                      </section>
                    );
                  })}
              </div>
            ) : (
              <div className="card" style={{ marginTop: "1rem" }}>
                <div className="table-wrap">
                  <table className="dcma-table">
                    <thead>
                      <tr>
                        <th style={{ width: "2.5rem" }}>#</th>
                        <th>Check</th>
                        <th>Compliance</th>
                        <th style={{ textAlign: "right" }}>Result</th>
                        <th>Target</th>
                        <th>Affected</th>
                        <th style={{ textAlign: "right" }}>Score impact</th>
                        <th style={{ width: "2rem" }} />
                      </tr>
                    </thead>
                    {shownSections.map((cat) => {
                      const open = !closed.has(cat.key);
                      const folded = open ? undefined : "dcma-row-folded";
                      const n = cat.shown.length;
                      return (
                        <tbody key={cat.key} id={`dcma-tsec-${cat.key}`}>
                          <tr className="dcma-group-row">
                            <td colSpan={8}>
                              <SectionHead
                                id={`dcma-tsec-${cat.key}`}
                                open={open}
                                onToggle={() => setSectionOpen(cat.key, !open)}
                                title={cat.label}
                                sub={cat.sub}
                                hint={`${n} check${n === 1 ? "" : "s"}`}
                              />
                            </td>
                          </tr>
                          {cat.shown.map((check) => {
                            const m = metaFor(check, t);
                            const isOpen = expanded.has(check.id);
                            const hasDetails = check.details.length > 0;
                            const unscored = check.scored === false;
                            return (
                              <Fragment key={check.id}>
                                <tr
                                  className={folded}
                                  onClick={() => hasDetails && toggle(check.id)}
                                  style={{ cursor: hasDetails ? "pointer" : "default" }}
                                >
                                  <td className="mono" style={{ color: "var(--text-muted)" }}>
                                    {check.id}
                                  </td>
                                  <td>
                                    <div style={{ fontWeight: 500 }}>{m.title}</div>
                                    <div className="dcma-table-sub">{m.measures}</div>
                                  </td>
                                  <td>
                                    <StatusChip status={check.status} />
                                  </td>
                                  <td className="num" style={{ textAlign: "right" }}>
                                    {resultLabel(check)}
                                  </td>
                                  <td className="mono">
                                    {m.target}
                                    {isCustom(check.id, report) && <span className="dcma-custom-dot" title="Project target" />}
                                  </td>
                                  <td className="mono" style={{ color: "var(--text-secondary)" }}>
                                    {countLabel(check)}
                                  </td>
                                  <td className="num" style={{ textAlign: "right" }}>
                                    {unscored ? "Not scored" : impactLabel(scoreImpact(check, report))}
                                  </td>
                                  <td>
                                    {hasDetails &&
                                      (isOpen ? (
                                        <ChevronUpIcon className="icon" style={{ width: 14, height: 14 }} />
                                      ) : (
                                        <ChevronDownIcon className="icon" style={{ width: 14, height: 14 }} />
                                      ))}
                                  </td>
                                </tr>
                                {isOpen && hasDetails && (
                                  <tr className={folded}>
                                    <td />
                                    <td colSpan={7} style={{ paddingTop: 0 }}>
                                      {unscored ? <PokoFindings check={check} /> : <AffectedIds check={check} />}
                                    </td>
                                  </tr>
                                )}
                              </Fragment>
                            );
                          })}
                        </tbody>
                      );
                    })}
                  </table>
                </div>
              </div>
            )}

          </>
        )}
      </div>

      {targetsAt !== null && report && project && (
        <DcmaTargetsModal
          projectId={project.id}
          thresholds={t}
          defaults={report.default_thresholds ?? {}}
          focusCheck={targetsAt === "all" ? null : targetsAt}
          onClose={() => setTargetsAt(null)}
          onSaved={() => {
            setTargetsAt(null);
            void load(true);
          }}
        />
      )}
    </>
  );
}

function CheckCard({
  check,
  t,
  custom,
  onEditTarget,
  impact,
  open,
  onToggle,
}: {
  check: DcmaCheckResult;
  t: Thresholds;
  custom: boolean;
  onEditTarget?: () => void;
  impact: number;
  open: boolean;
  onToggle: () => void;
}) {
  const m = metaFor(check, t);
  const tracked = check.status !== "not_tracked";
  return (
    <div className="card dcma-card">
      <div className="dcma-card-head">
        <span className="dcma-card-no mono">{String(check.id).padStart(2, "0")}</span>
        <span className="dcma-card-title">{m.title}</span>
        <StatusChip status={check.status} />
      </div>

      <div className="dcma-card-body">
        <DcmaRing
          pct={tracked ? check.pct : 0}
          marks={tracked ? m.marks : []}
          stroke={STATUS_STROKE[check.status]}
          label={ringLabel(check, t)}
        >
          <span className="dcma-ring-value">{resultLabel(check)}</span>
          <span className="dcma-ring-sub">{isIndex(check) ? "index" : `of ${check.basis === "relationships" ? "links" : "activities"}`}</span>
        </DcmaRing>
        <dl className="dcma-facts">
          <div>
            <dt>Target</dt>
            <dd className="mono">
              {onEditTarget ? (
                <button
                  type="button"
                  className="dcma-target-btn"
                  onClick={onEditTarget}
                  title={custom ? "Project target — click to change" : "DCMA target — click to set this project's own"}
                >
                  {custom && <span className="dcma-custom-dot" aria-label="Project target" />}
                  {m.target}
                </button>
              ) : (
                <>
                  {custom && <span className="dcma-custom-dot" aria-label="Project target" />}
                  {m.target}
                </>
              )}
            </dd>
          </div>
          <div>
            <dt>{factLabel(check)}</dt>
            <dd className="mono">{countShort(check)}</dd>
          </div>
          <div>
            <dt>Score impact</dt>
            <dd className="mono">{check.scored === false ? "Not scored" : impactLabel(impact)}</dd>
          </div>
        </dl>
      </div>

      <p className="dcma-card-measures">{m.measures}</p>

      {check.details.length > 0 && (
        <>
          <button type="button" className="dcma-more" onClick={onToggle} aria-expanded={open}>
            {open ? (
              <ChevronUpIcon className="icon" style={{ width: 13, height: 13 }} />
            ) : (
              <ChevronDownIcon className="icon" style={{ width: 13, height: 13 }} />
            )}
            {open ? "Hide" : "Show"}{" "}
            {check.scored === false
              ? findingsLabel(check)
              : isIndex(check)
                ? "activities behind plan"
                : "affected activities"}
          </button>
          {open && (check.scored === false ? <PokoFindings check={check} /> : <AffectedIds check={check} />)}
        </>
      )}
    </div>
  );
}

/** A section's header that folds it: the whole row is the button. `hint`
 *  only shows while folded, to say what is hidden. */
function SectionHead({
  id,
  open,
  onToggle,
  title,
  sub,
  hint,
}: {
  id: string;
  open: boolean;
  onToggle: () => void;
  title: string;
  sub: string;
  hint: string;
}) {
  return (
    <h2 className="fold-heading">
      <button
        type="button"
        className="section-head dcma-section-head"
        aria-expanded={open}
        aria-controls={id}
        onClick={onToggle}
      >
        <ChevronDownIcon className="icon icon-sm section-caret" aria-hidden="true" />
        <span className="dcma-section-title">{title}</span>
        <span className="dcma-section-sub">{sub}</span>
        {!open && <span className="fold-hint dcma-section-hint">{hint}</span>}
      </button>
    </h2>
  );
}

function AffectedIds({ check }: { check: DcmaCheckResult }) {
  const total = isIndex(check) ? check.denominator - Math.round(check.value * check.denominator) : check.value;
  return (
    <div className="dcma-ids">
      {check.details.map((id, i) => (
        <span key={`${id}-${i}`} className="chip chip-neutral mono">
          {id}
        </span>
      ))}
      {total > check.details.length && (
        <span className="dcma-ids-more">
          first {check.details.length} of {total}
        </span>
      )}
    </div>
  );
}
