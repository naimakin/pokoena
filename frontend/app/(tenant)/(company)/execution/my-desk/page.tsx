"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import { toDays } from "@/lib/duration";
import { PageState } from "@/components/PageShell";
import { ActivityModal } from "@/components/ActivityModal";
import { NoteComposer, NoteList, type NoteDraft, type NotePatch } from "@/components/PersonalNotes";
import { FloatBadge, fmtDays, fmtP6Date } from "@/components/reporting/format";
import { useToast } from "@/components/Toast";
import { CheckIcon, LockIcon, PinIcon, XIcon } from "@/components/icons";
import { NoProjectIllo } from "@/components/illustrations";
import type { Activity, DeskInboxItem, DeskPin, DeskSuggestion, PersonalNote } from "@/lib/types";

// Execution → My Desk: the one personal, cross-project page. Every other page
// shows the shared programme of one project; this one shows what waits on the
// signed-in user, the activities they chose to watch (pinned from the Activity
// modal), and their private notes. POKO has no activity assignees — P6
// responsibility runs through WBS / codes / scope — so "mine" here is whatever
// the user pinned or wrote, never inferred.

type Scope = "project" | "all";
type PinFilter = "all" | "critical" | "slipped" | "noted";

const SCOPE_KEY = "poko:my-desk-scope";

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
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => setScope(readScope()), []);

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
      const [nextInbox, nextPins, nextNotes, nextSuggestions] = await Promise.all([
        api.get<DeskInboxItem[]>(`/my-desk/inbox${qs}`),
        api.get<DeskPin[]>(`/my-desk/pins${qs}`),
        api.get<PersonalNote[]>(`/my-desk/notes${qs}`),
        projectId ? api.get<DeskSuggestion[]>(`/my-desk/suggestions?project_id=${projectId}`) : Promise.resolve([]),
      ]);
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
  const dueReminders = notes.filter((n) => !n.done_at && n.remind_on && n.remind_on <= todayIso()).length;

  // ---------------------------------------------------------------- actions

  function openInboxItem(item: DeskInboxItem) {
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
    return <PageState kind="loading" section="Execution" title="My Desk" />;
  }
  if (projects.length === 0) {
    return (
      <PageState
        kind="empty"
        section="Execution"
        title="My Desk"
        emptyTitle="No project yet"
        message="Once you're on a project, what waits on you, what you pin and your private notes collect here."
        art={<NoProjectIllo />}
      />
    );
  }
  if (error) {
    return <PageState kind="error" section="Execution" title="My Desk" message={error} />;
  }

  const allMode = scope === "all";

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">Execution</span>
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
              ) : suggestions.length > 0 ? (
                <>
                  <p className="desk-suggest-intro">
                    Nothing pinned yet. These look worth watching on {project?.code} — or pin any activity from its
                    detail in <Link href="/progress">Project Activities</Link>.
                  </p>
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
                </>
              ) : (
                <div className="desk-quiet">
                  {allMode
                    ? "Nothing pinned on any project yet. Open an activity in Project Activities and press Pin."
                    : "Nothing pinned yet. Open an activity in Project Activities and press Pin to watch it here."}
                </div>
              )}
            </div>
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
          onClose={() => {
            setOpenActivity(null);
            load();
          }}
          onSaved={() => load()}
        />
      )}
    </>
  );
}
