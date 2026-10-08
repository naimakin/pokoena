"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import { toDays } from "@/lib/duration";
import { PageState } from "@/components/PageShell";
import { ActivityModal } from "@/components/ActivityModal";
import { NoteComposer, NoteList, type NoteDraft, type NotePatch } from "@/components/PersonalNotes";
import { FloatBadge, fmtDays, fmtP6Date } from "@/components/reporting/format";
import { useToast } from "@/components/Toast";
import { AtSignIcon, CheckIcon, ChevronDownIcon, LockIcon, PinIcon, XIcon } from "@/components/icons";
import { MentionText } from "@/components/MentionText";
import { NoProjectIllo } from "@/components/illustrations";
import type { Activity, DeskInboxItem, DeskPin, DeskSuggestion, MyMention, PersonalNote } from "@/lib/types";

// Execution → My Desk: the one personal, cross-project page. Every other page
// shows the shared programme of one project; this one shows what waits on the
// signed-in user, the activities they chose to watch (pinned from the Activity
// modal), and their private notes. POKO has no activity assignees — P6
// responsibility runs through WBS / codes / scope — so "mine" here is whatever
// the user pinned or wrote, never inferred.

type Scope = "project" | "all";

/** "on A100" for a comment; the recovery plan kinds say what happened. */
function mentionVerb(m: MyMention): string {
  if (m.kind === "recovery_owner") return "made you owner of a recovery action on";
  if (m.kind === "recovery_action") return "mentioned you in a recovery action on";
  if (m.kind === "recovery_root_cause") return "mentioned you in the recovery plan for";
  return "on";
}
type PinFilter = "all" | "critical" | "slipped" | "noted";

const SCOPE_KEY = "poko:my-desk-scope";
const SUGGEST_KEY = "poko:my-desk-suggestions-open";

const PIN_FILTERS: { key: PinFilter; label: string; test: (p: DeskPin) => boolean }[] = [
  { key: "all", label: "All", test: () => true },
  { key: "critical", label: "Critical", test: (p) => Boolean(p.activity?.is_critical && p.activity.status !== "complete") },
  { key: "slipped", label: "Slipped since pinned", test: (p) => (p.drift_days ?? 0) > 0 },
  { key: "noted", label: "With notes", test: (p) => p.note_count > 0 },
];

function readScope(): Scope {
  try {
    return window.localStorage.getItem(SCOPE_KEY) === "all" ? "all" : "project";
  } catch {
    return "project";
  }
}

function dayDiff(later: string | null, earlier: string | null): number | null {
  if (!later || !earlier) return null;
  return Math.round((Date.parse(later) - Date.parse(earlier)) / 86_400_000);
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function DriftLine({ days, suffix }: { days: number | null; suffix: string }) {
  if (days == null) return null;
  if (days === 0) return <span className="desk-delta">No change {suffix}</span>;
  return <span className={`desk-delta ${days > 0 ? "later" : "earlier"}`}>{fmtDays(days)} {suffix}</span>;
}

export default function MyDeskPage() {
  const { project, projects, loading: projectsLoading, selectProject } = useProjectContext();
  const { showToast } = useToast();
  const router = useRouter();

  const [scope, setScope] = useState<Scope>("project");
  const [inbox, setInbox] = useState<DeskInboxItem[]>([]);
  const [pins, setPins] = useState<DeskPin[]>([]);
  const [suggestions, setSuggestions] = useState<DeskSuggestion[]>([]);
  const [notes, setNotes] = useState<PersonalNote[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pinFilter, setPinFilter] = useState<PinFilter>("all");
  const [openActivity, setOpenActivity] = useState<Activity | null>(null);
  const [openEventId, setOpenEventId] = useState<string | null>(null);
  const [mentions, setMentions] = useState<MyMention[]>([]);
  const [mentionView, setMentionView] = useState<"unread" | "all">("unread");
  const [busyId, setBusyId] = useState<string | null>(null);

  // Suggestions stay open by default; folding them is remembered per browser.
  const [suggestOpen, setSuggestOpen] = useState(true);

  useEffect(() => {
    setScope(readScope());
    try {
      setSuggestOpen(window.localStorage.getItem(SUGGEST_KEY) !== "closed");
    } catch {
      // per-viewer convenience only
    }
  }, []);

  function toggleSuggestions() {
    setSuggestOpen((open) => {
      try {
        window.localStorage.setItem(SUGGEST_KEY, open ? "closed" : "open");
      } catch {
        // per-viewer convenience only
      }
      return !open;
    });
  }

  function changeScope(next: Scope) {
    setScope(next);
    try {
      window.localStorage.setItem(SCOPE_KEY, next);
    } catch {
      // per-viewer convenience only
    }
  }

  const projectId = scope === "project" ? project?.id ?? null : null;

  const load = useCallback(async () => {
    if (scope === "project" && !projectId) return;
    setError(null);
    const qs = projectId ? `?project_id=${projectId}` : "";
    try {
      const [nextInbox, nextPins, nextNotes, nextSuggestions, nextMentions] = await Promise.all([
        api.get<DeskInboxItem[]>(`/my-desk/inbox${qs}`),
        api.get<DeskPin[]>(`/my-desk/pins${qs}`),
        api.get<PersonalNote[]>(`/my-desk/notes${qs}`),
        projectId ? api.get<DeskSuggestion[]>(`/my-desk/suggestions?project_id=${projectId}`) : Promise.resolve([]),
        api.get<MyMention[]>("/my-desk/mentions?limit=100"),
      ]);
      setMentions(nextMentions);
      setInbox(nextInbox);
      setPins(nextPins);
      setNotes(nextNotes);
      setSuggestions(nextSuggestions);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load your desk.");
    } finally {
      setLoaded(true);
    }
  }, [scope, projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const shownPins = useMemo(
    () => pins.filter(PIN_FILTERS.find((f) => f.key === pinFilter)!.test),
    [pins, pinFilter],
  );
  const shownMentions = mentions.filter(
    (m) => (mentionView === "all" || !m.read_at) && (scope === "all" || !projectId || m.project_id === projectId),
  );
  const unreadMentions = mentions.filter((m) => !m.read_at && (scope === "all" || !projectId || m.project_id === projectId)).length;
  const dueReminders = notes.filter((n) => !n.done_at && n.remind_on && n.remind_on <= todayIso()).length;

  // ---------------------------------------------------------------- actions

  async function openMention(m: MyMention) {
    if (m.href) {
      // A recovery plan mention opens the plan's row on Programme > Recovery Plan.
      if (!m.read_at) markRead(m.id);
      if (m.project_id !== project?.id) {
        selectProject(m.project_id);
        showToast(`Switched to ${m.project_code}`);
      }
      router.push(m.href);
      return;
    }
    if (!m.activity_id) {
      showToast(`${m.activity_external_id} is no longer in the programme.`, "error");
      return;
    }
    try {
      const activity = await api.get<Activity>(`/activities/${m.activity_id}`);
      setOpenEventId(m.event_id);
      setOpenActivity(activity);
      if (!m.read_at) markRead(m.id);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not open that activity.", "error");
    }
  }

  async function markRead(id: string) {
    const now = new Date().toISOString();
    setMentions((prev) => prev.map((m) => (m.id === id ? { ...m, read_at: m.read_at ?? now } : m)));
    await api.post(`/my-desk/mentions/${id}/read`).catch(() => undefined);
  }

  async function markAllRead() {
    const now = new Date().toISOString();
    setMentions((prev) => prev.map((m) => ({ ...m, read_at: m.read_at ?? now })));
    await api.post("/my-desk/mentions/read-all").catch(() => undefined);
    load();
  }

  function openInboxItem(item: DeskInboxItem) {
    if (item.kind === "mention") {
      document.getElementById("mentions")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (item.project_id !== project?.id) {
      selectProject(item.project_id);
      showToast(`Switched to ${item.project_code}`);
    }
    router.push(item.href);
  }

  async function pin(activity: Activity) {
    setBusyId(activity.id);
    try {
      await api.put(`/my-desk/activities/${activity.id}/pin`);
      showToast(`Pinned ${activity.external_id}`);
      await load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not pin this activity.", "error");
    } finally {
      setBusyId(null);
    }
  }

  async function unpin(p: DeskPin) {
    setBusyId(p.id);
    try {
      await api.delete(`/my-desk/pins/${p.id}`);
      setPins((prev) => prev.filter((x) => x.id !== p.id));
      showToast(`Unpinned ${p.activity_external_id}`);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not unpin this activity.", "error");
    } finally {
      setBusyId(null);
    }
  }

  async function createNote(draft: NoteDraft): Promise<boolean> {
    try {
      const created = await api.post<PersonalNote>("/my-desk/notes", { ...draft, project_id: projectId });
      setNotes((prev) => [created, ...prev]);
      return true;
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not save the note.", "error");
      return false;
    }
  }

  async function updateNote(id: string, patch: NotePatch): Promise<boolean> {
    try {
      const updated = await api.patch<PersonalNote>(`/my-desk/notes/${id}`, patch);
      setNotes((prev) => prev.map((n) => (n.id === id ? updated : n)));
      return true;
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not update the note.", "error");
      return false;
    }
  }

  async function deleteNote(id: string) {
    try {
      await api.delete(`/my-desk/notes/${id}`);
      setNotes((prev) => prev.filter((n) => n.id !== id));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not delete the note.", "error");
    }
  }

  /** A note's activity opens in the modal when it's one of the pins loaded here. */
  function openerFor(note: PersonalNote): (() => void) | undefined {
    const match = pins.find(
      (p) => p.project_id === note.project_id && p.activity_external_id === note.activity_external_id && p.activity,
    );
    return match?.activity ? () => setOpenActivity(match.activity) : undefined;
  }

  // ---------------------------------------------------------------- render

  if (projectsLoading || (!loaded && !error && (project || scope === "all"))) {
    return <PageState kind="loading" section="Programme" title="My Desk" />;
  }
  if (projects.length === 0) {
    return (
      <PageState
        kind="empty"
        section="Programme"
        title="My Desk"
        emptyTitle="No project yet"
        message="Once you're on a project, what waits on you, what you pin and your private notes collect here."
        art={<NoProjectIllo />}
      />
    );
  }
  if (error) {
    return <PageState kind="error" section="Programme" title="My Desk" message={error} />;
  }

  const allMode = scope === "all";

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">Programme</span>
        <div className="spacer" />
        <div className="segmented" role="tablist" aria-label="Scope">
          <button role="tab" aria-selected={!allMode} className={!allMode ? "active" : undefined} onClick={() => changeScope("project")}>
            {project ? project.code : "This project"}
          </button>
          <button role="tab" aria-selected={allMode} className={allMode ? "active" : undefined} onClick={() => changeScope("all")}>
            All projects
          </button>
        </div>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">My Desk</div>
            <div className="page-desc">
              {allMode ? "All your projects" : project?.name}
              {" · "}
              {inbox.length ? `${inbox.length} waiting on you` : "Nothing waiting on you"}
              {dueReminders > 0 && ` · ${dueReminders} reminder${dueReminders === 1 ? "" : "s"} due`}
            </div>
          </div>
        </div>

        <div className="desk-grid">
          <div className="desk-col">
            {/* ---------------- Waiting on you ---------------- */}
            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">Waiting on you</div>
                  <div className="card-title-sub">Reviews, revisions and update deadlines across the approval queues</div>
                </div>
              </div>
              {inbox.length === 0 ? (
                <div className="desk-quiet">
                  <CheckIcon className="icon" /> You&rsquo;re clear — nothing is waiting on you.
                </div>
              ) : (
                <div>
                  {inbox.map((item) => (
                    <button
                      key={`${item.kind}-${item.project_id}`}
                      type="button"
                      className="desk-inbox-item"
                      onClick={() => openInboxItem(item)}
                    >
                      <span className={`desk-inbox-dot ${item.tone}`} aria-hidden />
                      <span className="desk-inbox-main">
                        <span className="desk-inbox-title">{item.title}</span>
                        {item.detail && <span className="desk-inbox-detail">{item.detail}</span>}
                      </span>
                      <span className="desk-inbox-side">
                        {(allMode || item.project_id !== project?.id) && (
                          <span className="chip chip-neutral mono" title={item.project_name}>{item.project_code}</span>
                        )}
                        {item.due_at && <span className="desk-inbox-due mono">Closes {fmtP6Date(item.due_at)}</span>}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* ---------------- Mentions ---------------- */}
            <div className="card" id="mentions">
              <div className="card-head">
                <div>
                  <div className="card-title">
                    Mentions{unreadMentions ? <span className="mention-count">{unreadMentions} new</span> : null}
                  </div>
                  <div className="card-title-sub">Comments and recovery plans where someone tagged you with @</div>
                </div>
                <div style={{ display: "flex", gap: ".5rem", alignItems: "center" }}>
                  <div className="segmented" role="group" aria-label="Mentions shown">
                    <button type="button" className={mentionView === "unread" ? "active" : ""} onClick={() => setMentionView("unread")}>
                      Unread
                    </button>
                    <button type="button" className={mentionView === "all" ? "active" : ""} onClick={() => setMentionView("all")}>
                      All
                    </button>
                  </div>
                  {unreadMentions > 0 && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={markAllRead}>
                      Mark all read
                    </button>
                  )}
                </div>
              </div>
              {shownMentions.length === 0 ? (
                <div className="desk-quiet">
                  <AtSignIcon className="icon" />{" "}
                  {mentionView === "unread" ? "No new mentions." : "Nobody has tagged you yet."}
                </div>
              ) : (
                <ul className="mention-feed">
                  {shownMentions.map((m) => (
                    <li key={m.id} className={`mention-item${m.read_at ? "" : " is-unread"}`}>
                      <button type="button" className="mention-open" onClick={() => openMention(m)}>
                        <span className="mention-meta">
                          <b>{m.author_name ?? "Someone"}</b> {mentionVerb(m)} <span className="mono">{m.activity_external_id}</span>
                          {m.activity_name ? ` · ${m.activity_name}` : ""}
                          {(allMode || m.project_id !== project?.id) && (
                            <span className="chip chip-neutral mono">{m.project_code}</span>
                          )}
                          <span className="mention-when">{fmtP6Date(m.created_at)}</span>
                        </span>
                        <span className="mention-body">
                          <MentionText body={m.body} />
                        </span>
                      </button>
                      {!m.read_at && (
                        <button
                          type="button"
                          className="act-btn"
                          title="Mark read"
                          aria-label="Mark read"
                          onClick={() => markRead(m.id)}
                        >
                          <CheckIcon className="icon" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* ---------------- Pinned ---------------- */}
            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">Pinned activities{pins.length ? ` · ${pins.length}` : ""}</div>
                  <div className="card-title-sub">How each one moved since you pinned it, and since the previous update</div>
                </div>
              </div>

              {pins.length > 0 ? (
                <>
                  <div className="desk-filters">
                    {PIN_FILTERS.map((f) => (
                      <button
                        key={f.key}
                        type="button"
                        className={`pick-chip${pinFilter === f.key ? " selected" : ""}`}
                        onClick={() => setPinFilter(f.key)}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                  <div className="table-wrap">
                    <table className="desk-table">
                      <thead>
                        <tr>
                          <th>Activity</th>
                          <th>Finish</th>
                          <th>Total float</th>
                          <th>Notes</th>
                          <th aria-label="Unpin" />
                        </tr>
                      </thead>
                      <tbody>
                        {shownPins.length === 0 && (
                          <tr>
                            <td colSpan={5} className="empty-state">No pinned activity matches this filter.</td>
                          </tr>
                        )}
                        {shownPins.map((p) => {
                          const a = p.activity;
                          const critical = Boolean(a?.is_critical && a.status !== "complete");
                          const tfNow = a ? toDays(a.total_float_hours, a) : null;
                          const tfPrev = a ? toDays(p.previous_total_float_hours, a) : null;
                          return (
                            <tr
                              key={p.id}
                              className={[critical ? "critical" : "", a ? "" : "is-gone"].join(" ").trim() || undefined}
                              onClick={() => a && setOpenActivity(a)}
                            >
                              <td>
                                <div className="desk-act-name">{p.activity_name}</div>
                                <div className="cell-sub">
                                  <span className="mono">{p.activity_external_id}</span>
                                  {allMode && <> · <span className="mono">{p.project_code}</span></>}
                                  {!a && " · no longer in the current programme"}
                                </div>
                              </td>
                              <td className="mono">
                                {fmtP6Date(p.finish)}
                                <DriftLine days={p.drift_days} suffix="since pinned" />
                                {p.previous_revision_label && (
                                  <DriftLine days={dayDiff(p.finish, p.previous_finish)} suffix={`vs ${p.previous_revision_label}`} />
                                )}
                              </td>
                              <td>
                                {a ? <FloatBadge days={tfNow} /> : "—"}
                                {p.previous_revision_label && tfPrev != null && (
                                  <span className="desk-delta mono">
                                    {p.previous_revision_label}: {fmtDays(tfPrev)}
                                  </span>
                                )}
                              </td>
                              <td className="num">{p.note_count || "—"}</td>
                              <td>
                                <button
                                  type="button"
                                  className="act-btn act-edit"
                                  aria-label={`Unpin ${p.activity_external_id}`}
                                  title="Unpin"
                                  disabled={busyId === p.id}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    unpin(p);
                                  }}
                                >
                                  <XIcon className="icon icon-sm" />
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="desk-quiet">
                  {allMode
                    ? "Nothing pinned on any project yet. Open an activity in Activity Workspace and press Pin."
                    : "Nothing pinned yet. Pin a suggestion below, or open any activity in Activity Workspace and press Pin."}
                </div>
              )}
            </div>

            {/* ---------------- Suggestions ---------------- */}
            {!allMode && suggestions.length > 0 && (
              <div className="card">
                <button
                  type="button"
                  className="section-head"
                  aria-expanded={suggestOpen}
                  onClick={() => toggleSuggestions()}
                >
                  <ChevronDownIcon className="icon icon-sm section-caret" />
                  <span>
                    <span className="card-title">Worth watching on {project?.code}</span>
                    <span className="card-title-sub">
                      Negative float, critical or starting within 14 days — and not pinned yet
                    </span>
                  </span>
                  <span className="spacer" />
                  <span className="chip chip-neutral">{suggestions.length}</span>
                </button>
                {suggestOpen && (
                  <div className="table-wrap">
                    <table className="desk-table">
                      <thead>
                        <tr>
                          <th>Activity</th>
                          <th>Why</th>
                          <th>Total float</th>
                          <th aria-label="Pin" />
                        </tr>
                      </thead>
                      <tbody>
                        {suggestions.map(({ activity: a, reason }) => (
                          <tr key={a.id} onClick={() => setOpenActivity(a)}>
                            <td>
                              <div className="desk-act-name">{a.name}</div>
                              <div className="cell-sub mono">{a.external_id}</div>
                            </td>
                            <td className="desk-reason">{reason}</td>
                            <td>
                              <FloatBadge days={toDays(a.total_float_hours, a)} />
                            </td>
                            <td>
                              <button
                                type="button"
                                className="pin-btn"
                                disabled={busyId === a.id}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  pin(a);
                                }}
                              >
                                <PinIcon className="icon icon-sm" /> Pin
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ---------------- Private notes ---------------- */}
          <div className="desk-col">
            <div className="card">
              <div className="card-head">
                <div>
                  <div className="card-title">Private notes</div>
                  <div className="card-title-sub" style={{ display: "flex", alignItems: "center", gap: ".3rem" }}>
                    <LockIcon className="icon icon-xs" /> Only you can see these
                  </div>
                </div>
              </div>
              <div className="card-body">
                <NoteComposer
                  placeholder={
                    allMode
                      ? "A general note or reminder… (Ctrl+Enter to save)"
                      : `A note on ${project?.code ?? "this project"}… (Ctrl+Enter to save)`
                  }
                  onCreate={createNote}
                  showPrivacy={false}
                />
                <NoteList
                  notes={notes}
                  showProject={allMode}
                  emptyText="No notes yet. Notes you add on an activity show up here too."
                  onOpenActivity={openerFor}
                  onUpdate={updateNote}
                  onDelete={deleteNote}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {openActivity && (
        <ActivityModal
          key={openActivity.id}
          activity={openActivity}
          canEdit
          highlightEventId={openEventId}
          onClose={() => {
            setOpenActivity(null);
            setOpenEventId(null);
            load();
          }}
          onSaved={() => load()}
        />
      )}
    </>
  );
}
