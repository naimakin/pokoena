"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { ActivityCard } from "@/components/ActivityCard";
import { FlagReviewModal } from "@/components/FlagReviewModal";
import Link from "next/link";
import { ClockIcon, LogOutIcon } from "@/components/icons";
import { PokoGlyph } from "@/components/brand";
import type {
  Activity,
  ActivityRelationship,
  ActivityUpdatePayload,
  ChangeRequest,
  Project,
  SlipReport,
  UpdatePeriod,
  User,
} from "@/lib/types";

interface FlagTarget {
  activity: Activity;
  relationship: ActivityRelationship;
  fieldLabel: string;
  currentValueLabel: string;
}

function daysUntil(iso: string): number {
  const diffMs = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
}

export default function ScopePage() {
  const router = useRouter();
  const { showToast } = useToast();

  const [user, setUser] = useState<User | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [period, setPeriod] = useState<UpdatePeriod | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [relationships, setRelationships] = useState<Record<string, ActivityRelationship[]>>({});
  const [changeRequests, setChangeRequests] = useState<ChangeRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flagTarget, setFlagTarget] = useState<FlagTarget | null>(null);
  const [flagSubmitting, setFlagSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [slippedCount, setSlippedCount] = useState(0);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const me = await api.get<User>("/auth/me");
      setUser(me);

      // Scope-restricted by construction: /projects and /activities are
      // already filtered server-side to this subcontractor's assigned
      // scopes (require_scope_access) — there's no "mine" toggle to get
      // wrong here, the backend never returns anything else.
      const projects = await api.get<Project[]>("/projects");
      const active = projects[0] ?? null;
      setProject(active);
      if (!active) return;

      const periods = await api.get<UpdatePeriod[]>(`/update-periods?project_id=${active.id}`);
      const openPeriod = periods.find((p) => p.status === "open") ?? null;
      setPeriod(openPeriod);

      const myActivities = await api.get<Activity[]>(`/activities?project_id=${active.id}`);
      setActivities(myActivities);

      const relationshipEntries = await Promise.all(
        myActivities.map(async (activity) => {
          const rels = await api.get<ActivityRelationship[]>(`/activities/${activity.id}/relationships`);
          return [activity.id, rels] as const;
        })
      );
      setRelationships(Object.fromEntries(relationshipEntries));

      if (openPeriod) {
        const crs = await api.get<ChangeRequest[]>(`/change-requests?update_period_id=${openPeriod.id}`);
        setChangeRequests(crs);
      }

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

  async function handleSignOut() {
    await api.post("/auth/logout");
    router.push("/login");
    router.refresh();
  }

  async function handleCommit(activityId: string, patch: ActivityUpdatePayload) {
    try {
      const updated = await api.patch<Activity>(`/activities/${activityId}`, patch);
      setActivities((prev) => prev.map((a) => (a.id === activityId ? updated : a)));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to save that change.", "error");
    }
  }

  async function handleFlagSubmit(newValue: string, justification: string) {
    if (!flagTarget || !period) return;
    setFlagSubmitting(true);
    try {
      await api.post<ChangeRequest>("/change-requests", {
        update_period_id: period.id,
        activity_relationship_id: flagTarget.relationship.id,
        field_changed: flagTarget.fieldLabel,
        before_value: flagTarget.currentValueLabel,
        after_value: newValue,
        justification,
        risk_level: "medium",
      });
      showToast("Flagged for admin review — you'll be notified once it's decided");
      setFlagTarget(null);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to submit the flag.", "error");
    } finally {
      setFlagSubmitting(false);
    }
  }

  async function handleSubmitUpdates() {
    if (!period) return;
    try {
      await api.post(`/update-periods/${period.id}/submit`);
      setSubmitted(true);
      showToast("Updates submitted — visible to Project Controls immediately");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to submit updates.", "error");
    }
  }

  const pendingActivityIds = useMemo(() => {
    const ids = new Set<string>();
    for (const cr of changeRequests) {
      if (cr.status !== "pending") continue;
      if (cr.activity_id) ids.add(cr.activity_id);
      if (cr.activity_relationship_id) {
        for (const [activityId, rels] of Object.entries(relationships)) {
          if (rels.some((r) => r.id === cr.activity_relationship_id)) ids.add(activityId);
        }
      }
    }
    return ids;
  }, [changeRequests, relationships]);

  const updatedCount = activities.filter((a) => a.status !== "not_started").length;

  if (loading) {
    return (
      <div className="sub-page">
        <p className="page-desc">Loading…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sub-page">
        <p className="login-error">{error}</p>
      </div>
    );
  }

  const deadlineDays = period ? daysUntil(period.deadline_at) : null;

  return (
    <div className="sub-page">
      <div className="sub-frame">
        <div className="sub-header">
          <div className="sub-header-top">
            <div className="sub-id">
              <div className="mark" style={{ width: 24, height: 24, borderRadius: 6, background: "var(--accent)", color: "var(--accent-contrast)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <PokoGlyph width={13} height={13} />
              </div>
              <div>
                <div className="sub-company">{user?.full_name}</div>
                <div className="sub-project">{project?.name ?? "—"}</div>
              </div>
            </div>
            <button className="signout" onClick={handleSignOut} title="Sign out" aria-label="Sign out">
              <LogOutIcon className="icon" />
            </button>
          </div>

          {period ? (
            <div className={`deadline-banner${deadlineDays !== null && deadlineDays > 3 ? " good" : ""}`}>
              <ClockIcon className="icon" />
              {period.label} closes in
              <span className="d">{deadlineDays} days</span>
            </div>
          ) : (
            <div className="deadline-banner good">
              <ClockIcon className="icon" />
              No open update period right now
            </div>
          )}
        </div>

        <div className="sub-body">
          {slippedCount > 0 && (
            <Link href="/scope/recovery-plan" className="deadline-banner" style={{ textDecoration: "none", marginBottom: ".8rem" }}>
              <ClockIcon className="icon" />
              {slippedCount} of your activities slipped — submit a recovery plan
              <span className="d">Open ›</span>
            </Link>
          )}
          {activities.length === 0 && <p className="empty-state">No activities are assigned to your scope yet.</p>}
          {activities.map((activity) => (
            <ActivityCard
              key={activity.id}
              activity={activity}
              relationships={relationships[activity.id] ?? []}
              pendingFlag={pendingActivityIds.has(activity.id)}
              readOnly={!period}
              onCommit={(patch) => handleCommit(activity.id, patch)}
              onFlag={(relationship, fieldLabel, currentValueLabel) =>
                setFlagTarget({ activity, relationship, fieldLabel, currentValueLabel })
              }
            />
          ))}
        </div>

        <div className="sub-footer">
          <div>
            <div className="sub-footer-label">
              {updatedCount} of {activities.length} updated
            </div>
            <div className="progress" style={{ width: 120, marginTop: ".3rem" }}>
              <span
                style={{
                  width: activities.length ? `${Math.round((updatedCount / activities.length) * 100)}%` : "0%",
                  background: "var(--good)",
                }}
              />
            </div>
          </div>
          <div className="spacer" />
          <button className="btn btn-primary" onClick={handleSubmitUpdates} disabled={!period || submitted}>
            {submitted ? "Submitted" : "Submit My Updates"}
          </button>
        </div>
      </div>

      <FlagReviewModal
        open={flagTarget !== null}
        activityLabel={flagTarget ? `${flagTarget.activity.external_id} · ${flagTarget.activity.name}` : ""}
        fieldLabel={flagTarget?.fieldLabel ?? ""}
        currentValueLabel={flagTarget?.currentValueLabel ?? ""}
        submitting={flagSubmitting}
        onCancel={() => setFlagTarget(null)}
        onSubmit={handleFlagSubmit}
      />
    </div>
  );
}
