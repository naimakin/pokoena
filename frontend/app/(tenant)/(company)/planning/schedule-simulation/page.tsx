"use client";

// Planning > Schedule Simulation: edit activities the way Activity Ledger
// does (mark one complete, change its %, push its finish out three weeks) on a
// copy of the current programme at a chosen data date, and see what moves, by
// how much, and why. Runs are read-only on the server
// (backend/app/services/schedule_simulation.py); scenarios can be saved.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PageState } from "@/components/PageShell";
import { useToast } from "@/components/Toast";
import { AlertTriangleIcon, PencilIcon, TrashIcon } from "@/components/icons";
import { NoProjectIllo, UploadScheduleIllo } from "@/components/illustrations";
import { ProgrammeGrid } from "@/components/simulation/ProgrammeGrid";
import { RunBar, ScenarioSetup, type Change } from "@/components/simulation/ScenarioSetup";
import { SimActivityModal } from "@/components/simulation/SimActivityModal";
import { SimResults } from "@/components/simulation/SimResults";
import { api, ApiError } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { Activity, WbsNode } from "@/lib/types";
import {
  daysBetween,
  isSimErrorDetail,
  liveDraft,
  runKey,
  signedDays,
  SUMMARY_TYPES,
  toDraft,
  toEdit,
  validateDraft,
  type Draft,
  type SimContext,
  type SimEdit,
  type SimResult,
  type SimScenario,
} from "@/lib/simulation";

const SECTION = "Programme";
const TITLE = "Scenario Lab";

type Modal = { kind: "save" | "rename"; name: string } | { kind: "delete" } | null;

export default function ScheduleSimulationPage() {
  const { project } = useProjectContext();
  const { showToast } = useToast();
  const router = useRouter();

  const [ctx, setCtx] = useState<SimContext | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [nodes, setNodes] = useState<WbsNode[]>([]);
  const [editing, setEditing] = useState<Activity | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<SimScenario[]>([]);

  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [simDate, setSimDate] = useState("");
  const [edits, setEdits] = useState<SimEdit[]>([]);
  const [savedKey, setSavedKey] = useState<string | null>(null);

  const [result, setResult] = useState<SimResult | null>(null);
  const [ranKey, setRanKey] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<{ code: string; message: string } | null>(null);
  const [serverErrors, setServerErrors] = useState<Map<string, string>>(new Map());
  const [modal, setModal] = useState<Modal>(null);
  const [busy, setBusy] = useState(false);
  const [announce, setAnnounce] = useState("");
  const loadedFromUrl = useRef(false);

  // --- load ---------------------------------------------------------------
  useEffect(() => {
    if (!project) {
      setCtx(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    setResult(null);
    setRunError(null);
    setScenarioId(null);
    setEdits([]);
    loadedFromUrl.current = false;
    Promise.all([
      api.get<SimContext>(`/projects/${project.id}/simulations/context?include_activities=false`),
      api.get<SimScenario[]>(`/projects/${project.id}/simulations/scenarios`),
      api.get<Activity[]>(`/activities?project_id=${project.id}`),
      api.get<WbsNode[]>(`/projects/${project.id}/wbs-nodes`),
    ])
      .then(([c, s, acts, wbs]) => {
        setCtx(c);
        setScenarios(s);
        // Summary / level-of-effort activities follow the others; they aren't edited here.
        setActivities(acts.filter((a) => !SUMMARY_TYPES.has(a.task_type ?? "")));
        setNodes(wbs);
        setSimDate(c.current_data_date ?? "");
        setSavedKey(runKey(c.current_data_date ?? "", []));
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Could not load the programme."))
      .finally(() => setLoading(false));
  }, [project]);

  const activitiesById = useMemo(() => new Map(activities.map((a) => [a.external_id, a])), [activities]);
  const currentDD = ctx?.current_data_date ?? "";
  const key = runKey(simDate, edits);
  const dirty = savedKey !== null && key !== savedKey;
  const scenario = scenarios.find((s) => s.id === scenarioId) ?? null;

  // The scenario as drafts: what each changed activity looks like in it.
  const drafts = useMemo(() => {
    const m = new Map<string, Draft>();
    for (const e of edits) {
      const a = activitiesById.get(e.external_id);
      if (a) m.set(e.external_id, toDraft(e, a, simDate));
    }
    return m;
  }, [edits, activitiesById, simDate]);

  const errors = useMemo(() => {
    const m = new Map<string, string>();
    for (const e of edits) {
      const a = activitiesById.get(e.external_id);
      const d = drafts.get(e.external_id);
      const msg = !a || !d ? "This activity isn't in the current programme any more." : validateDraft(a, d, simDate);
      if (msg) m.set(e.external_id, msg);
    }
    // A server-side rejection stands until that row is edited.
    serverErrors.forEach((msg, id) => {
      if (!m.has(id) && ranKey === key) m.set(id, msg);
    });
    return m;
  }, [edits, activitiesById, drafts, simDate, serverErrors, ranKey, key]);

  const changes: Change[] = edits.map((e) => ({
    external_id: e.external_id,
    activity: activitiesById.get(e.external_id),
    draft: drafts.get(e.external_id) ?? null,
    error: errors.get(e.external_id) ?? null,
  }));

  function applyDraft(a: Activity, d: Draft) {
    const edit = toEdit(a, d);
    setEdits((prev) =>
      prev.some((e) => e.external_id === a.external_id)
        ? prev.map((e) => (e.external_id === a.external_id ? edit : e))
        : [...prev, edit],
    );
    setEditing(null);
  }

  function removeEdit(externalId: string) {
    setEdits((prev) => prev.filter((e) => e.external_id !== externalId));
    setEditing(null);
  }

  const canRun = Boolean(ctx?.has_schedule && currentDD) && errors.size === 0 && (edits.length > 0 || simDate !== currentDD);

  // --- scenarios ------------------------------------------------------------
  const loadScenario = useCallback(
    (s: SimScenario | null) => {
      const dd = s?.simulation_data_date && s.simulation_data_date >= currentDD ? s.simulation_data_date : currentDD;
      const nextEdits = s?.edits ?? [];
      setScenarioId(s?.id ?? null);
      setSimDate(dd);
      setEdits(nextEdits);
      setSavedKey(runKey(dd, nextEdits));
      setResult(null);
      setRunError(null);
      setServerErrors(new Map());
      const url = new URL(window.location.href);
      if (s) url.searchParams.set("scenario", s.id);
      else url.searchParams.delete("scenario");
      router.replace(`${url.pathname}${url.search}`, { scroll: false });
    },
    [currentDD, router],
  );

  useEffect(() => {
    if (loadedFromUrl.current || !ctx) return;
    loadedFromUrl.current = true;
    // Read straight off the URL: useSearchParams would need a Suspense boundary.
    const id = new URLSearchParams(window.location.search).get("scenario");
    const s = id ? scenarios.find((x) => x.id === id) : null;
    if (s) loadScenario(s);
  }, [ctx, scenarios, loadScenario]);

  function pickScenario(id: string) {
    if (dirty && !window.confirm("Discard the unsaved changes to this scenario?")) return;
    loadScenario(scenarios.find((s) => s.id === id) ?? null);
  }

  async function refreshScenarios() {
    if (!project) return;
    setScenarios(await api.get<SimScenario[]>(`/projects/${project.id}/simulations/scenarios`));
  }

  async function saveScenario(asNew: boolean, name?: string) {
    if (!project) return;
    setBusy(true);
    const body = { name: name ?? scenario?.name ?? "Scenario", simulation_data_date: simDate || null, edits };
    try {
      const saved =
        !asNew && scenario
          ? await api.patch<SimScenario>(`/projects/${project.id}/simulations/scenarios/${scenario.id}`, body)
          : await api.post<SimScenario>(`/projects/${project.id}/simulations/scenarios`, body);
      await refreshScenarios();
      setScenarioId(saved.id);
      setSavedKey(key);
      const url = new URL(window.location.href);
      url.searchParams.set("scenario", saved.id);
      router.replace(`${url.pathname}${url.search}`, { scroll: false });
      showToast(asNew || !scenario ? `Saved “${saved.name}”` : "Scenario saved");
      setModal(null);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not save the scenario.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function renameScenario(name: string) {
    if (!project || !scenario) return;
    setBusy(true);
    try {
      await api.patch(`/projects/${project.id}/simulations/scenarios/${scenario.id}`, { name });
      await refreshScenarios();
      setModal(null);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not rename the scenario.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function deleteScenario() {
    if (!project || !scenario) return;
    setBusy(true);
    try {
      await api.delete(`/projects/${project.id}/simulations/scenarios/${scenario.id}`);
      await refreshScenarios();
      setModal(null);
      loadScenario(null);
      showToast("Scenario deleted");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not delete the scenario.", "error");
    } finally {
      setBusy(false);
    }
  }

  // --- run --------------------------------------------------------------------
  const run = useCallback(async () => {
    if (!project || !canRun || running) return;
    setRunning(true);
    setRunError(null);
    setAnnounce("Simulating…");
    const thisKey = runKey(simDate, edits);
    try {
      const res = await api.post<SimResult>(`/projects/${project.id}/simulations/run`, {
        data_date: simDate,
        edits,
        scenario_id: scenarioId && !dirty ? scenarioId : null,
      });
      setResult(res);
      setRanKey(thisKey);
      setServerErrors(new Map());
      const d = res.project_finish.delta_days;
      setAnnounce(
        `Done. ${res.counts.moved} activities moved; project finish ${d === 0 ? "unchanged" : `${signedDays(d)} ${d > 0 ? "later" : "earlier"}`}.`,
      );
      if (scenarioId && !dirty) void refreshScenarios();
      setTimeout(() => {
        const head = document.getElementById("sim-results-title");
        head?.scrollIntoView({ behavior: "smooth", block: "start" });
        head?.focus({ preventScroll: true });
      }, 50);
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : null;
      if (isSimErrorDetail(detail)) {
        if (detail.code === "invalid_edits" && detail.errors?.length) {
          setServerErrors(new Map(detail.errors.map((e) => [e.external_id, e.message])));
          setRanKey(thisKey);
        } else {
          setRunError({ code: detail.code, message: detail.message });
        }
      } else {
        showToast(err instanceof ApiError ? err.message : "The simulation failed.", "error");
      }
      setAnnounce("");
    } finally {
      setRunning(false);
    }
    // refreshScenarios is stable enough for this purpose (it only reads project)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project, canRun, running, simDate, edits, scenarioId, dirty, showToast]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        void run();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [run]);

  function reset() {
    if (dirty && edits.length > 0 && !window.confirm("Clear every change in this scenario?")) return;
    setEdits([]);
    setSimDate(currentDD);
    setServerErrors(new Map());
  }

  // --- states -------------------------------------------------------------------
  if (loading) return <PageState kind="loading" section={SECTION} title={TITLE} />;
  if (!project) {
    return (
      <PageState
        kind="empty"
        section={SECTION}
        title={TITLE}
        emptyTitle="No project selected"
        message="Create or pick a project from the project switcher in the top bar."
        art={<NoProjectIllo />}
      />
    );
  }
  if (loadError) return <PageState kind="error" section={SECTION} title={TITLE} message={loadError} />;
  if (!ctx?.has_schedule) {
    return (
      <PageState
        kind="empty"
        section={SECTION}
        title={TITLE}
        emptyTitle="Import a schedule first"
        message="Simulation runs on the current programme's logic and dates."
        art={<UploadScheduleIllo />}
        action={
          <Link className="btn btn-primary btn-sm" href="/project-files">
            Go to Programme Files
          </Link>
        }
      />
    );
  }

  const stale = result !== null && ranKey !== key;
  return (
    <>
      <div className="a-topbar">
        <span className="crumb">{SECTION}</span>
      </div>
      <div className="a-content sim-page">
        <div className="page-head">
          <div>
            <div className="page-title sim-title">
              {TITLE}
              <span className="chip chip-info">Beta</span>
            </div>
            <div className="page-desc">
              Try changes against a copy of the current programme and see what moves, by how much, and why. Nothing here
              touches the live schedule.
            </div>
          </div>
          <div className="page-actions sim-scenario">
            <select
              className="select"
              value={scenarioId ?? ""}
              onChange={(e) => pickScenario(e.target.value)}
              aria-label="Saved scenarios"
            >
              <option value="">{scenarios.length ? "Unsaved scenario" : "No saved scenarios"}</option>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.edits.length} change{s.edits.length === 1 ? "" : "s"}
                  {s.last_finish_delta_days != null ? ` · ${signedDays(s.last_finish_delta_days)}` : ""}
                  {!s.is_owner && s.created_by_name ? `, by ${s.created_by_name}` : ""}
                </option>
              ))}
            </select>
            {scenario && scenario.can_change && dirty && (
              <button type="button" className="btn btn-secondary" onClick={() => saveScenario(false)} disabled={busy}>
                Save changes
              </button>
            )}
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setModal({ kind: "save", name: scenario ? `${scenario.name} (copy)` : "" })}
              disabled={busy || (edits.length === 0 && simDate === currentDD)}
            >
              {scenario ? "Save as new…" : "Save…"}
            </button>
            {scenario?.can_change && (
              <>
                <button
                  type="button"
                  className="act-btn act-edit"
                  aria-label="Rename scenario"
                  title="Rename"
                  onClick={() => setModal({ kind: "rename", name: scenario.name })}
                >
                  <PencilIcon className="icon icon-sm" />
                </button>
                <button
                  type="button"
                  className="act-btn act-reject"
                  aria-label="Delete scenario"
                  title="Delete"
                  onClick={() => setModal({ kind: "delete" })}
                >
                  <TrashIcon className="icon icon-sm" />
                </button>
              </>
            )}
          </div>
        </div>

        {scenario?.stale && (
          <div className="banner warn" role="status">
            <AlertTriangleIcon className="icon" />
            <span className="banner-text">
              This scenario was last run on {scenario.revision_label ?? "an earlier import"}; the live schedule has been updated
              since. Changes on activities that no longer exist are flagged below.
            </span>
          </div>
        )}

        <ScenarioSetup
          currentDataDate={currentDD}
          revisionLabel={ctx.revision_label}
          simDate={simDate}
          onSimDate={setSimDate}
          changes={changes}
          dirty={dirty && (scenario !== null || edits.length > 0)}
          onEdit={setEditing}
          onRemove={removeEdit}
        />

        {runError && (
          <div className="banner crit" role="alert">
            <AlertTriangleIcon className="icon" />
            <span className="banner-text">{runError.message}</span>
          </div>
        )}

        <div className="sim-sr-only" aria-live="polite">
          {announce}
        </div>

        {running && !result && (
          <section className="sim-results" aria-busy="true">
            <div className="kpi-row">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="card kpi">
                  <div className="skeleton" />
                  <div className="skeleton" />
                </div>
              ))}
            </div>
            <div className="card">
              <div className="skeleton-stack">
                <div className="skeleton" />
                <div className="skeleton" />
                <div className="skeleton" />
              </div>
            </div>
          </section>
        )}

        {result && (
          <SimResults result={result} stale={stale} running={running} projectCode={project.code} onRerun={run} />
        )}

        <ProgrammeGrid
          activities={activities}
          nodes={nodes}
          drafts={drafts}
          result={result}
          stale={stale}
          onOpen={setEditing}
        />

        <RunBar
          changes={edits.length}
          shift={currentDD && simDate ? daysBetween(currentDD, simDate) : 0}
          running={running}
          canRun={canRun}
          onRun={run}
          onReset={reset}
        />
      </div>

      {editing && (
        <SimActivityModal
          key={editing.external_id}
          activity={editing}
          draft={drafts.get(editing.external_id) ?? liveDraft(editing)}
          simDate={simDate}
          inScenario={drafts.has(editing.external_id)}
          onApply={(d) => applyDraft(editing, d)}
          onRemove={() => removeEdit(editing.external_id)}
          onClose={() => setEditing(null)}
        />
      )}

      {modal && (
        <div className="modal-overlay" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && !busy && setModal(null)}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="sim-modal-title">
            {modal.kind === "delete" ? (
              <>
                <div className="modal-head">
                  <AlertTriangleIcon className="icon" />
                  <div>
                    <div className="modal-title" id="sim-modal-title">
                      Delete “{scenario?.name}”?
                    </div>
                    <div className="modal-desc">This removes the saved scenario for everyone. It can&apos;t be undone.</div>
                  </div>
                </div>
                <div className="modal-foot">
                  <button type="button" className="btn btn-ghost" onClick={() => setModal(null)} disabled={busy}>
                    Cancel
                  </button>
                  <button type="button" className="btn btn-danger" onClick={deleteScenario} disabled={busy}>
                    Delete
                  </button>
                </div>
              </>
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const name = modal.name.trim();
                  if (!name) return;
                  if (modal.kind === "rename") void renameScenario(name);
                  else void saveScenario(true, name);
                }}
              >
                <div className="modal-head">
                  <div>
                    <div className="modal-title" id="sim-modal-title">
                      {modal.kind === "rename" ? "Rename scenario" : "Save scenario"}
                    </div>
                    <div className="modal-desc">
                      {modal.kind === "rename"
                        ? "Everyone on the project sees scenarios by name."
                        : "Saves the data date and the changes. Results are worked out again on every run, against the live schedule."}
                    </div>
                  </div>
                </div>
                <div className="modal-body">
                  <div className="field">
                    <label htmlFor="sim-scenario-name">Name</label>
                    <input
                      id="sim-scenario-name"
                      type="text"
                      maxLength={120}
                      autoFocus
                      value={modal.name}
                      placeholder="e.g. Steel delivery 3 weeks late"
                      onChange={(e) => setModal({ ...modal, name: e.target.value })}
                    />
                  </div>
                </div>
                <div className="modal-foot">
                  <button type="button" className="btn btn-ghost" onClick={() => setModal(null)} disabled={busy}>
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary" disabled={busy || !modal.name.trim()}>
                    {modal.kind === "rename" ? "Rename" : "Save"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
