"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { MentionText } from "@/components/MentionText";
import { fmtP6Date } from "@/components/reporting/format";
import { PokoGlyph } from "@/components/brand";
import {
  AlertTriangleIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  EyeIcon,
  AtSignIcon,
  LockIcon,
  LogOutIcon,
} from "@/components/icons";
import { displayFinish, displayStart, isMilestone } from "@/lib/schedule-dates";
import type {
  Activity,
  ActivityRelationship,
  ActivityUpdatePayload,
  MyMention,
  Project,
  ProjectScope,
  SlipReport,
  UpdatePeriod,
  User,
} from "@/lib/types";

type Filter = "all" | "not_started" | "in_progress" | "complete";

const STATUS: Record<Activity["status"], { label: string; chip: string }> = {
  not_started: { label: "Not started", chip: "chip-neutral" },
  in_progress: { label: "In progress", chip: "chip-info" },
  complete: { label: "Complete", chip: "chip-good" },
};

function daysUntil(iso: string): number {
  return Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
}

/** The subcontractor's workspace: the activities of their scopes on one
 *  project, and — while the company has an update period open and they may
 *  update progress — the place to enter it. Everything here is already
 *  scope-filtered server-side (deps.require_scope_access). */
export default function ScopePage() {
  const router = useRouter();
  const { showToast } = useToast();

  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [scopes, setScopes] = useState<ProjectScope[]>([]);
  const [period, setPeriod] = useState<UpdatePeriod | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [relationships, setRelationships] = useState<Record<string, ActivityRelationship[]>>({});
  const [mentions, setMentions] = useState<MyMention[]>([]);
  const [slippedCount, setSlippedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  async function load(projectId?: string) {
    setLoading(true);
    setError(null);
    try {
      const me = await api.get<User>("/auth/me");
      setUser(me);
      const projectList = await api.get<Project[]>("/projects");
      setProjects(projectList);
      const active = projectList.find((p) => p.id === projectId) ?? projectList[0] ?? null;
      setProject(active);
      setSubmitted(false);
      setOpenId(null);
      setRelationships({});
      if (!active) {
        setActivities([]);
        setPeriod(null);
        setScopes([]);
        return;
      }
      const [periods, myActivities, myScopes] = await Promise.all([
        api.get<UpdatePeriod[]>(`/update-periods?project_id=${active.id}`),
        api.get<Activity[]>(`/activities?project_id=${active.id}`),
        api.get<ProjectScope[]>(`/projects/${active.id}/scopes`).catch(() => [] as ProjectScope[]),
      ]);
      const openPeriod = periods.find((p) => p.status === "open") ?? null;
      setPeriod(openPeriod);
      setActivities(myActivities);
      setScopes(myScopes);
      // People who @-tagged this subcontractor in an activity comment.
      setMentions(await api.get<MyMention[]>("/my-desk/mentions?unread=true").catch(() => [] as MyMention[]));
      try {
        const slip = await api.get<SlipReport>(`/projects/${active.id}/recovery-plan`);
        setSlippedCount(slip.slipped.length);
      } catch {
        setSlippedCount(0);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load your scope.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Logic is fetched per activity the first time its row is opened.
  useEffect(() => {
    if (!openId || relationships[openId]) return;
    api
      .get<ActivityRelationship[]>(`/activities/${openId}/relationships`)
      .then((rels) => setRelationships((prev) => ({ ...prev, [openId]: rels })))
      .catch(() => setRelationships((prev) => ({ ...prev, [openId]: [] })));
  }, [openId, relationships]);

  const canUpdate = Boolean(user?.project_roles?.includes("activity_status_updater"));
  const editable = Boolean(period) && canUpdate;

  const counts = useMemo(() => {
    const c = { not_started: 0, in_progress: 0, complete: 0 };
    for (const a of activities) c[a.status] += 1;
    return c;
  }, [activities]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return activities
      .filter((a) => filter === "all" || a.status === filter)
      .filter((a) => !q || a.external_id.toLowerCase().includes(q) || a.name.toLowerCase().includes(q))
      .sort((a, b) => (displayFinish(a) ?? "9999").localeCompare(displayFinish(b) ?? "9999"));
  }, [activities, filter, query]);

  async function handleSignOut() {
    await api.post("/auth/logout");
    router.push("/login");
    router.refresh();
  }

  async function handleSave(activityId: string, patch: ActivityUpdatePayload): Promise<boolean> {
    try {
      const updated = await api.patch<Activity>(`/activities/${activityId}`, patch);
      setActivities((prev) => prev.map((a) => (a.id === activityId ? updated : a)));
      showToast(`${updated.external_id} saved`);
      return true;
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to save that change.", "error");
      return false;
    }
  }

  async function markMentionRead(id: string) {
    setMentions((prev) => prev.filter((m) => m.id !== id));
    await api.post(`/my-desk/mentions/${id}/read`).catch(() => undefined);
  }

  async function handleSubmitUpdates() {
    if (!period) return;
    try {
      await api.post(`/update-periods/${period.id}/submit`);
      setSubmitted(true);
      showToast("Updates submitted — the project team can see them now");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to submit updates.", "error");
    }
  }

  const initials = (user?.full_name ?? "")
    .split(" ")
    .filter(Boolean)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  const deadlineDays = period ? daysUntil(period.deadline_at) : null;
  const started = counts.in_progress + counts.complete;

  return (
    <div className="sw">
      <header className="sw-bar">
        <div className="sw-brand">
          <span className="sw-mark">
            <PokoGlyph width={15} height={15} />
          </span>
          <span className="sw-brand-name">POKO</span>
        </div>
        {projects.length > 1 ? (
          <select
            className="sw-project"
            value={project?.id ?? ""}
            onChange={(e) => load(e.target.value)}
            aria-label="Project"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        ) : (
          project && <span className="sw-project is-static">{project.name}</span>
        )}
        <span className="sw-spacer" />
        <span className="sw-user">
          <span className="sw-avatar">{initials}</span>
          <span className="sw-user-name">{user?.full_name}</span>
        </span>
        <button className="sw-signout" onClick={handleSignOut} title="Sign out" aria-label="Sign out">
          <LogOutIcon className="icon" />
        </button>
      </header>

      <main className="sw-main">
        {loading && <p className="empty-state">Loading your scope…</p>}
        {error && <p className="login-error">{error}</p>}

        {!loading && !error && !project && (
          <div className="sw-empty card">
            <LockIcon className="icon-lg" />
            <div className="sw-empty-title">You haven&rsquo;t been given a scope yet</div>
            <p className="cell-sub">
              The project team decides which activities you see. Ask them to assign you a scope — this page fills in
              as soon as they do.
            </p>
          </div>
        )}

        {!loading && !error && project && (
          <>
            <section className="sw-hero">
              <div>
                <div className="sw-eyebrow">{project.code}</div>
                <h1 className="sw-title">My scope</h1>
                <div className="cell-sub">
                  {scopes.length > 0 ? scopes.map((s) => s.name).join(" · ") : project.name}
                  {" · "}
                  {activities.length} activities
                </div>
              </div>
              <div className={`sw-period${period ? " is-open" : ""}`}>
                <ClockIcon className="icon" />
                {period ? (
                  <div>
                    <div className="sw-period-title">{period.label} is open</div>
                    <div className="sw-period-sub">
                      {deadlineDays !== null && deadlineDays > 0
                        ? `${deadlineDays} day${deadlineDays === 1 ? "" : "s"} left · due ${fmtP6Date(period.deadline_at)}`
                        : `Was due ${fmtP6Date(period.deadline_at)}`}
                    </div>
                  </div>
                ) : (
                  <div>
                    <div className="sw-period-title">Progress entry closed</div>
                    <div className="sw-period-sub">Opens when the project team starts an update</div>
                  </div>
                )}
              </div>
            </section>

            <section className="sw-stats" aria-label="Summary">
              {(["not_started", "in_progress", "complete"] as const).map((key) => (
                <button
                  key={key}
                  type="button"
                  className={`sw-stat${filter === key ? " is-active" : ""}`}
                  onClick={() => setFilter(filter === key ? "all" : key)}
                  aria-pressed={filter === key}
                >
                  <span className="sw-stat-value mono">{counts[key]}</span>
                  <span className="sw-stat-label">{STATUS[key].label}</span>
                </button>
              ))}
              {slippedCount > 0 ? (
                <Link href="/scope/recovery-plan" className="sw-stat is-warn">
                  <span className="sw-stat-value mono">{slippedCount}</span>
                  <span className="sw-stat-label">Slipped — recovery plan ›</span>
                </Link>
              ) : (
                <div className="sw-stat is-static">
                  <span className="sw-stat-value mono">0</span>
                  <span className="sw-stat-label">Slipped</span>
                </div>
              )}
            </section>

            {!period && (
              <div className="banner">
                <EyeIcon className="icon" />
                <div className="banner-text">
                  You can review your activities and their logic. Entering progress opens when the project team starts
                  an update period.
                </div>
              </div>
            )}
            {period && !canUpdate && (
              <div className="banner">
                <EyeIcon className="icon" />
                <div className="banner-text">
                  You have view-only access. Ask the project team if you need to update progress.
                </div>
              </div>
            )}

            {mentions.length > 0 && (
              <section className="card sw-mentions" aria-label="Mentions">
                <div className="sw-mentions-head">
                  <AtSignIcon className="icon" /> {mentions.length === 1 ? "1 new mention" : `${mentions.length} new mentions`}
                </div>
                <ul className="mention-feed">
                  {mentions.map((m) => (
                    <li key={m.id} className="mention-item is-unread">
                      <div className="mention-open">
                        <span className="mention-meta">
                          <b>{m.author_name ?? "Someone"}</b> on <span className="mono">{m.activity_external_id}</span>
                          {m.activity_name ? ` · ${m.activity_name}` : ""}
                        </span>
                        <span className="mention-body">
                          <MentionText body={m.body} />
                        </span>
                      </div>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => markMentionRead(m.id)}>
                        Mark read
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="card sw-list-card">
              <div className="sw-toolbar">
                <div className="segmented" role="group" aria-label="Status filter">
                  {(["all", "not_started", "in_progress", "complete"] as const).map((f) => (
                    <button key={f} type="button" className={filter === f ? "active" : ""} onClick={() => setFilter(f)}>
                      {f === "all" ? `All · ${activities.length}` : `${STATUS[f].label} · ${counts[f]}`}
                    </button>
                  ))}
                </div>
                <div className="field sw-search">
                  <input
                    type="text"
                    placeholder="Search ID or name…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    aria-label="Search activities"
                  />
                </div>
              </div>

              <div className="sw-head" aria-hidden="true">
                <span>Activity</span>
                <span>Start</span>
                <span>Finish</span>
                <span>Progress</span>
                <span />
              </div>

              {visible.length === 0 && (
                <p className="empty-state">
                  {activities.length === 0 ? "No activities are in your scope on this project yet." : "Nothing matches."}
                </p>
              )}

              <ul className="sw-rows">
                {visible.map((a) => (
                  <ActivityRow
                    key={a.id}
                    activity={a}
                    open={openId === a.id}
                    onToggle={() => setOpenId(openId === a.id ? null : a.id)}
                    editable={editable}
                    relationships={relationships[a.id]}
                    onSave={(patch) => handleSave(a.id, patch)}
                  />
                ))}
              </ul>
            </section>
          </>
        )}
      </main>

      {project && period && canUpdate && (
        <footer className="sw-foot">
          <div className="sw-foot-progress">
            <div className="sw-foot-label">
              <b className="mono">{started}</b> of <b className="mono">{activities.length}</b> started or complete
            </div>
            <div className="progress" style={{ width: 180 }}>
              <span
                style={{
                  width: activities.length ? `${Math.round((started / activities.length) * 100)}%` : "0%",
                  background: "var(--good)",
                }}
              />
            </div>
          </div>
          <button className="btn btn-primary" onClick={handleSubmitUpdates} disabled={submitted}>
            {submitted ? (
              <>
                <CheckIcon className="icon" /> Submitted
              </>
            ) : (
              "Submit my updates"
            )}
          </button>
        </footer>
      )}

    </div>
  );
}

function ActivityRow({
  activity: a,
  open,
  onToggle,
  editable,
  relationships,
  onSave,
}: {
  activity: Activity;
  open: boolean;
  onToggle: () => void;
  editable: boolean;
  relationships: ActivityRelationship[] | undefined;
  onSave: (patch: ActivityUpdatePayload) => Promise<boolean>;
}) {
  const milestone = isMilestone(a);
  const [start, setStart] = useState(a.actual_start ?? "");
  const [finish, setFinish] = useState(a.actual_finish ?? "");
  const [pct, setPct] = useState(a.percent_complete);
  const [remaining, setRemaining] = useState(String(a.remaining_duration_days));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setStart(a.actual_start ?? "");
    setFinish(a.actual_finish ?? "");
    setPct(a.percent_complete);
    setRemaining(String(a.remaining_duration_days));
  }, [a]);

  const patch: ActivityUpdatePayload = {};
  if (start !== (a.actual_start ?? "")) patch.actual_start = start || null;
  if (finish !== (a.actual_finish ?? "")) patch.actual_finish = finish || null;
  if (!milestone && pct !== a.percent_complete) patch.percent_complete = pct;
  if (!milestone && remaining !== "" && Number(remaining) !== a.remaining_duration_days) {
    patch.remaining_duration_days = Number(remaining);
  }
  const dirty = Object.keys(patch).length > 0;

  async function save() {
    setSaving(true);
    await onSave(patch);
    setSaving(false);
  }

  const status = STATUS[a.status];

  return (
    <li className={`sw-row${open ? " is-open" : ""}${a.is_critical ? " is-critical" : ""}`}>
      <button type="button" className="sw-row-main" onClick={onToggle} aria-expanded={open}>
        <span className="sw-row-act">
          <span className="sw-row-name">
            {a.name}
          </span>
          <span className="sw-row-id mono">
            {a.external_id}
            {a.is_critical && <span className="sw-crit">Critical</span>}
          </span>
        </span>
        <span className="sw-row-date mono" data-label="Start">
          {milestone && a.task_type === "TT_FinMile" ? "—" : fmtP6Date(displayStart(a))}
        </span>
        <span className="sw-row-date mono" data-label="Finish">
          {milestone && a.task_type === "TT_Mile" ? "—" : fmtP6Date(displayFinish(a))}
        </span>
        <span className="sw-row-progress">
          <span className={`chip ${status.chip}`}>{status.label}</span>
          {!milestone && (
            <span className="sw-pct">
              <span className="progress">
                <span style={{ width: `${a.percent_complete}%`, background: "var(--good)" }} />
              </span>
              <span className="mono">{a.percent_complete}%</span>
            </span>
          )}
        </span>
        <span className="sw-row-caret" aria-hidden="true">
          {open ? <ChevronDownIcon className="icon" /> : <ChevronRightIcon className="icon" />}
        </span>
      </button>

      {open && (
        <div className="sw-detail">
          <div className="sw-detail-block">
            <div className="sw-detail-label">
              {editable ? (
                <>
                  <CheckIcon className="icon" /> Progress
                </>
              ) : (
                <>
                  <LockIcon className="icon" /> Progress — read only
                </>
              )}
            </div>
            {editable ? (
              <div className="sw-form">
                <div className="field">
                  <label htmlFor={`as-${a.id}`}>{milestone ? "Actual date" : "Actual start"}</label>
                  <input
                    id={`as-${a.id}`}
                    type="date"
                    value={milestone && a.task_type === "TT_FinMile" ? finish : start}
                    onChange={(e) =>
                      milestone && a.task_type === "TT_FinMile" ? setFinish(e.target.value) : setStart(e.target.value)
                    }
                  />
                </div>
                {!milestone && (
                  <div className="field">
                    <label htmlFor={`af-${a.id}`}>Actual finish</label>
                    <input id={`af-${a.id}`} type="date" value={finish} onChange={(e) => setFinish(e.target.value)} />
                  </div>
                )}
                {!milestone && (
                  <div className="field sw-pct-field">
                    <label htmlFor={`pc-${a.id}`}>% complete</label>
                    <div className="sw-pct-input">
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={pct}
                        onChange={(e) => setPct(Number(e.target.value))}
                        aria-label="% complete slider"
                      />
                      <input
                        id={`pc-${a.id}`}
                        type="number"
                        min={0}
                        max={100}
                        value={pct}
                        onChange={(e) => setPct(Math.max(0, Math.min(100, Number(e.target.value) || 0)))}
                      />
                    </div>
                  </div>
                )}
                {!milestone && (
                  <div className="field">
                    <label htmlFor={`rd-${a.id}`}>Remaining (days)</label>
                    <input
                      id={`rd-${a.id}`}
                      type="number"
                      min={0}
                      value={remaining}
                      onChange={(e) => setRemaining(e.target.value)}
                    />
                  </div>
                )}
                <div className="sw-form-actions">
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={!dirty || saving}
                    onClick={() => {
                      setStart(a.actual_start ?? "");
                      setFinish(a.actual_finish ?? "");
                      setPct(a.percent_complete);
                      setRemaining(String(a.remaining_duration_days));
                    }}
                  >
                    Reset
                  </button>
                  <button type="button" className="btn btn-primary btn-sm" disabled={!dirty || saving} onClick={save}>
                    {saving ? "Saving…" : "Save"}
                  </button>
                </div>
              </div>
            ) : (
              <dl className="sw-facts">
                <div>
                  <dt>Actual start</dt>
                  <dd className="mono">{fmtP6Date(a.actual_start)}</dd>
                </div>
                <div>
                  <dt>Actual finish</dt>
                  <dd className="mono">{fmtP6Date(a.actual_finish)}</dd>
                </div>
                {!milestone && (
                  <div>
                    <dt>% complete</dt>
                    <dd className="mono">{a.percent_complete}%</dd>
                  </div>
                )}
                {!milestone && (
                  <div>
                    <dt>Remaining</dt>
                    <dd className="mono">{a.remaining_duration_days}d</dd>
                  </div>
                )}
              </dl>
            )}
          </div>

          <div className="sw-detail-block">
            <div className="sw-detail-label">
              <LockIcon className="icon" /> Logic
              <span className="cell-sub"> — set by the project team</span>
            </div>
            {relationships === undefined && <p className="cell-sub">Loading…</p>}
            {relationships && relationships.length === 0 && <p className="cell-sub">No predecessors or successors.</p>}
            {relationships && relationships.length > 0 && (
              <ul className="sw-logic">
                {relationships.map((rel) => {
                  const isPred = rel.successor_id === a.id;
                  const other = isPred ? rel.predecessor_external_id : rel.successor_external_id;
                  return (
                    <li key={rel.id}>
                      <span className="sw-logic-kind">{isPred ? "Predecessor" : "Successor"}</span>
                      <span className="mono sw-logic-value">
                        {rel.link_type} {other ?? "?"}
                        {rel.lag_days ? ` · lag ${rel.lag_days}d` : ""}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
            {a.is_critical && (
              <p className="sw-crit-note">
                <AlertTriangleIcon className="icon" /> On the critical path — any delay moves the project finish.
              </p>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
