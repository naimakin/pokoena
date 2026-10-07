"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { CheckIcon, LockIcon, PencilIcon, UsersIcon, XIcon } from "@/components/icons";
import {
  PROJECT_ROLE_LABELS,
  type Invite,
  type InviteCreatePayload,
  type PasswordResetLink,
  type Project,
  type ProjectRole,
  type ProjectScope,
  type SubcontractorOrg,
  type TeamMember,
  type TeamMemberUpdate,
  type TenantRole,
  type User,
} from "@/lib/types";

// Company roles. A subcontractor never holds these — their only permission is
// whether they may update progress on their scopes (backend: services/team_roles.py).
const EMPLOYEE_ROLE_OPTIONS = Object.entries(PROJECT_ROLE_LABELS) as [ProjectRole, string][];
const SUB_UPDATER: ProjectRole = "activity_status_updater";

// What each role actually unlocks (backend: EDIT_CAPABLE_PROJECT_ROLES and
// USER_MANAGEMENT_CAPABLE_PROJECT_ROLES in models/user_tenant_role.py).
const ROLE_HELP: Record<ProjectRole, string> = {
  project_administrator: "Edit the programme, activities and progress on their projects.",
  all_access: "Edit everything on their projects except threshold settings.",
  execution: "Update activities and progress on their projects.",
  user_management: "Open Users: invite people and change their access.",
  activity_status_updater: "Update activity status and % complete only.",
};
// Only a company admin may hand these out (services/team_roles.py).
const ADMIN_GRANTED: ProjectRole[] = ["project_administrator", "user_management"];

const selectStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border-strong)",
  borderRadius: 6,
  padding: ".5rem .65rem",
  fontSize: ".8125rem",
};

type MemberType = "employee" | "subcontractor";

function initialsOf(name: string) {
  return name
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export default function UserManagementPage() {
  const { showToast } = useToast();
  const [me, setMe] = useState<User | null>(null);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [orgs, setOrgs] = useState<SubcontractorOrg[]>([]);
  const [scopesByProject, setScopesByProject] = useState<Record<string, ProjectScope[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [lastLink, setLastLink] = useState<{ heading: string; url: string } | null>(null);

  // The member being edited; null with modalOpen = adding a new one.
  const [editing, setEditing] = useState<TeamMember | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [title, setTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [memberType, setMemberType] = useState<MemberType>("employee");
  const [projectRoles, setProjectRoles] = useState<ProjectRole[]>(["execution"]);
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [canUpdate, setCanUpdate] = useState(true);

  const [orgId, setOrgId] = useState<string>("");
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgDiscipline, setNewOrgDiscipline] = useState("");
  const [scopeProjectId, setScopeProjectId] = useState<string>("");
  const [scopeIds, setScopeIds] = useState<string[]>([]);

  const [memberSearch, setMemberSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | MemberType>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "removed">("all");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [user, members, projectList, orgList] = await Promise.all([
        api.get<User>("/auth/me"),
        api.get<TeamMember[]>("/team"),
        api.get<Project[]>("/projects"),
        api.get<SubcontractorOrg[]>("/subcontractor-organizations"),
      ]);
      setMe(user);
      setTeam(members);
      setProjects(projectList);
      setOrgs(orgList);
      const scopeLists = await Promise.all(
        projectList.map((p) => api.get<ProjectScope[]>(`/projects/${p.id}/scopes`).catch(() => [] as ProjectScope[])),
      );
      setScopesByProject(Object.fromEntries(projectList.map((p, i) => [p.id, scopeLists[i]])));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load your team.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const scopeById = useMemo(() => {
    const map = new Map<string, ProjectScope>();
    for (const list of Object.values(scopesByProject)) for (const s of list) map.set(s.id, s);
    return map;
  }, [scopesByProject]);

  const projectById = useMemo(() => new Map(projects.map((p) => [p.id, p])), [projects]);

  function fillForm(member: TeamMember | null) {
    setEmail(member?.email ?? "");
    setFullName(member?.full_name ?? "");
    setTitle(member?.title ?? "");
    setPhone(member?.phone ?? "");
    setMemberType(member?.role === "subcontractor" ? "subcontractor" : "employee");
    setProjectRoles(member ? member.project_roles : ["execution"]);
    setProjectIds(member?.project_ids ?? []);
    setCanUpdate(member ? member.project_roles.includes(SUB_UPDATER) : true);
    setOrgId(member?.subcontractor_org_id ?? "");
    setNewOrgName("");
    setNewOrgDiscipline("");
    const ids = member?.scope_ids ?? [];
    setScopeIds(ids);
    const firstScope = ids.map((id) => scopeById.get(id)).find(Boolean);
    setScopeProjectId(firstScope?.project_id ?? (projects.length === 1 ? projects[0].id : ""));
  }

  function openAdd() {
    setEditing(null);
    fillForm(null);
    setModalOpen(true);
  }

  function openEdit(member: TeamMember) {
    setEditing(member);
    fillForm(member);
    setModalOpen(true);
  }

  async function resolveOrgId(): Promise<string | null> {
    if (orgId && orgId !== "__new__") return orgId;
    if (orgId === "__new__" && newOrgName.trim()) {
      const created = await api.post<SubcontractorOrg>("/subcontractor-organizations", {
        name: newOrgName.trim(),
        discipline: newOrgDiscipline.trim() || "General",
      });
      setOrgs((prev) => [...prev, created]);
      return created.id;
    }
    return null;
  }

  const isSub = memberType === "subcontractor";
  const editingAdmin = editing?.role === "company_admin";
  const editingSelf = editing !== null && editing.user_id === me?.id;
  const accessLocked = editingAdmin || editingSelf;
  const subRoles: ProjectRole[] = canUpdate ? [SUB_UPDATER] : [];

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      if (editing) {
        const patch: TeamMemberUpdate = { full_name: fullName, title: title || null, phone: phone || null };
        if (!accessLocked) {
          if (isSub) {
            patch.project_roles = subRoles;
            patch.scope_ids = scopeIds;
            patch.subcontractor_org_id = await resolveOrgId();
          } else {
            patch.project_roles = projectRoles;
            patch.project_ids = projectIds;
          }
        }
        await api.patch<TeamMember>(`/team/${editing.user_tenant_role_id}`, patch);
        showToast(`Saved ${fullName || editing.email}`);
      } else {
        const role: TenantRole = isSub ? "subcontractor" : "company_employee";
        const payload: InviteCreatePayload = {
          email,
          full_name: fullName,
          title: title || undefined,
          phone: phone || undefined,
          role,
          project_roles: isSub ? subRoles : projectRoles,
        };
        if (isSub) {
          payload.project_scope_ids = scopeIds;
          payload.subcontractor_org_id = (await resolveOrgId()) ?? undefined;
        } else {
          payload.project_ids = projectIds;
        }
        const invite = await api.post<Invite>("/invites", payload);
        if (invite.invite_url) {
          setLastLink({ heading: `Invite link for ${fullName || email}`, url: invite.invite_url });
        }
        showToast(`Invite created for ${email}`);
      }
      setModalOpen(false);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to save.", "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCopyLink(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      showToast("Link copied");
    } catch {
      showToast("Couldn't copy — select and copy the link manually.", "error");
    }
  }

  async function handleRemove(member: TeamMember) {
    if (!window.confirm(`Remove ${member.full_name}'s access? They won't be able to sign in anymore.`)) return;
    try {
      await api.delete(`/team/${member.user_tenant_role_id}`);
      showToast(`Removed ${member.full_name}`);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to remove team member.", "error");
    }
  }

  async function handleRestore(member: TeamMember) {
    try {
      await api.patch<TeamMember>(`/team/${member.user_tenant_role_id}`, { is_active: true });
      showToast(`Restored ${member.full_name}`);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to restore team member.", "error");
    }
  }

  async function handleResetLink(member: TeamMember) {
    try {
      const result = await api.post<PasswordResetLink>(`/team/${member.user_tenant_role_id}/reset-password-link`);
      setLastLink({ heading: `Password reset link for ${result.email}`, url: result.reset_url });
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to generate a reset link.", "error");
    }
  }

  const availableScopes = scopeProjectId ? (scopesByProject[scopeProjectId] ?? []) : [];
  const selectedScopes = scopeIds.map((id) => scopeById.get(id)).filter((s): s is ProjectScope => Boolean(s));
  const activeCount = team.filter((m) => m.is_active).length;

  const filteredTeam = useMemo(() => {
    const q = memberSearch.trim().toLowerCase();
    return team.filter((m) => {
      if (q && !m.full_name.toLowerCase().includes(q) && !m.email.toLowerCase().includes(q)) return false;
      const sub = m.role === "subcontractor";
      if (typeFilter === "employee" && sub) return false;
      if (typeFilter === "subcontractor" && !sub) return false;
      if (statusFilter === "active" && !m.is_active) return false;
      if (statusFilter === "removed" && m.is_active) return false;
      return true;
    });
  }, [team, memberSearch, typeFilter, statusFilter]);

  function renderAccess(member: TeamMember) {
    if (member.role === "company_admin") {
      return <span className="cell-sub">Full access to every project</span>;
    }
    if (member.role === "subcontractor") {
      const scopes = member.scope_ids.map((id) => scopeById.get(id)).filter((s): s is ProjectScope => Boolean(s));
      const activities = scopes.reduce((sum, s) => sum + s.activity_count, 0);
      return (
        <div className="role-wrap">
          <span className="role-badge">
            {member.project_roles.includes(SUB_UPDATER) ? "Updates progress" : "View only"}
          </span>
          {scopes.length === 0 ? (
            <span className="chip chip-warn" title="With no scope this subcontractor sees no activities">
              No scope
            </span>
          ) : (
            <span className="cell-sub" title={scopes.map((s) => s.name).join(", ")}>
              {scopes.length === 1 ? scopes[0].name : `${scopes.length} scopes`} · {activities} activities
            </span>
          )}
        </div>
      );
    }
    const visibleRoles = member.project_roles.slice(0, 2);
    const overflowCount = member.project_roles.length - visibleRoles.length;
    return (
      <div className="role-wrap">
        {visibleRoles.map((r) => (
          <span key={r} className="role-badge">
            {PROJECT_ROLE_LABELS[r]}
          </span>
        ))}
        {overflowCount > 0 && (
          <span className="role-badge overflow" title={member.project_roles.slice(2).map((r) => PROJECT_ROLE_LABELS[r]).join(", ")}>
            +{overflowCount}
          </span>
        )}
        <span className="cell-sub" title={member.project_ids.map((id) => projectById.get(id)?.name ?? "").join(", ")}>
          {member.project_ids.length === 1 ? "1 project" : `${member.project_ids.length} projects`}
        </span>
      </div>
    );
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">Administration</span>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Users</div>
            <div className="page-desc">
              Add employees and subcontractors, choose the projects or scopes they reach, and set what they&rsquo;re
              allowed to do.
            </div>
          </div>
        </div>

        {lastLink && (
          <div className="banner">
            <UsersIcon className="icon" />
            <div className="banner-text">
              <b>{lastLink.heading}</b> — no email provider is connected yet, so copy this link and send it to them
              yourself (it only works once).
              <div className="mono" style={{ marginTop: ".35rem", fontSize: ".75rem", wordBreak: "break-all" }}>
                {lastLink.url}
              </div>
            </div>
            <div className="banner-actions">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleCopyLink(lastLink.url)}>
                <CheckIcon className="icon" /> Copy
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setLastLink(null)} aria-label="Dismiss">
                <XIcon className="icon" />
              </button>
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Team</div>
              <div className="card-title-sub">{activeCount} active members</div>
            </div>
            <button className="btn btn-primary btn-sm" onClick={openAdd}>
              <UsersIcon className="icon" /> Add User
            </button>
          </div>

          <div
            className="card-toolbar"
            style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", padding: "0.85rem 1.1rem", borderBottom: "1px solid var(--border)" }}
          >
            <div className="field" style={{ minWidth: 220 }}>
              <input
                type="text"
                placeholder="Search by name or email…"
                value={memberSearch}
                onChange={(e) => setMemberSearch(e.target.value)}
              />
            </div>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as typeof typeFilter)} style={selectStyle}>
              <option value="all">All types</option>
              <option value="employee">Employees</option>
              <option value="subcontractor">Subcontractors</option>
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)} style={selectStyle}>
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="removed">Removed</option>
            </select>
          </div>

          {loading && <p className="empty-state">Loading…</p>}
          {error && (
            <p className="login-error" style={{ margin: "1rem 1.1rem" }}>
              {error}
            </p>
          )}
          {!loading && !error && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Member</th>
                    <th>Type</th>
                    <th>Access</th>
                    <th>Status</th>
                    <th style={{ width: 120 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTeam.length === 0 && (
                    <tr>
                      <td colSpan={5} className="empty-state">
                        {team.length === 0 ? "No team members yet." : "No members match your filters."}
                      </td>
                    </tr>
                  )}
                  {filteredTeam.map((member) => (
                    <tr key={member.user_tenant_role_id} style={member.is_active ? undefined : { opacity: 0.55 }}>
                      <td>
                        <div className="cell-flex">
                          <div className="subrow-avatar">{initialsOf(member.full_name)}</div>
                          <div>
                            <div className="subname">{member.full_name}</div>
                            <div className="cell-sub">
                              {member.email}
                              {member.subcontractor_org_name ? ` · ${member.subcontractor_org_name}` : ""}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span
                          className={`chip ${member.role === "subcontractor" ? "chip-info" : "chip-neutral"}`}
                        >
                          {member.role === "subcontractor"
                            ? "Subcontractor"
                            : member.role === "company_admin"
                              ? "Company admin"
                              : "Employee"}
                        </span>
                      </td>
                      <td>{renderAccess(member)}</td>
                      <td>
                        <span className={`chip ${member.is_active ? "chip-good" : "chip-neutral"}`}>
                          {member.is_active ? "Active" : "Removed"}
                        </span>
                      </td>
                      <td>
                        <div className="actions">
                          {member.is_active && (
                            <button className="act-btn" title="Edit" aria-label={`Edit ${member.full_name}`} onClick={() => openEdit(member)}>
                              <PencilIcon className="icon" />
                            </button>
                          )}
                          {member.is_active && (
                            <button className="act-btn" title="Reset password" aria-label={`Reset ${member.full_name}'s password`} onClick={() => handleResetLink(member)}>
                              <LockIcon className="icon" />
                            </button>
                          )}
                          {member.is_active && member.role !== "company_admin" && member.user_id !== me?.id && (
                            <button className="act-btn act-reject" title="Remove access" aria-label={`Remove ${member.full_name}`} onClick={() => handleRemove(member)}>
                              <XIcon className="icon" />
                            </button>
                          )}
                          {!member.is_active && (
                            <button className="btn btn-secondary btn-sm" onClick={() => handleRestore(member)}>
                              Restore
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setModalOpen(false)}>
          <div className="modal" style={{ maxWidth: 580, maxHeight: "90vh" }} role="dialog" aria-modal="true" aria-labelledby="member-modal-title">
            <div className="modal-head">
              {editing ? (
                <PencilIcon className="icon-lg" style={{ color: "var(--accent-strong)" }} />
              ) : (
                <UsersIcon className="icon-lg" style={{ color: "var(--accent-strong)" }} />
              )}
              <div>
                <div className="modal-title" id="member-modal-title">
                  {editing ? `Edit ${editing.full_name}` : "Add team member"}
                </div>
                <div className="modal-desc">
                  {editing
                    ? editingAdmin
                      ? "A company admin has full access to every project — only their details can change here."
                      : editingSelf
                        ? "You can update your details, but not your own access."
                        : "Changes apply on their next page load (a subcontractor's new scopes within 15 minutes)."
                    : "No email provider is connected yet — you’ll get a one-time invite link to copy and send them yourself."}
                </div>
              </div>
            </div>
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
              <div className="modal-body" style={{ overflowY: "auto" }}>
                <div className="form-row">
                  <div className="field">
                    <label htmlFor="add-email">Email</label>
                    <input
                      id="add-email"
                      type="email"
                      required
                      value={email}
                      disabled={editing !== null}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="add-name">Full name</label>
                    <input type="text" id="add-name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="field">
                    <label htmlFor="add-title">Title</label>
                    <input type="text" id="add-title" value={title} onChange={(e) => setTitle(e.target.value)} />
                  </div>
                  <div className="field">
                    <label htmlFor="add-phone">Phone</label>
                    <input type="text" id="add-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
                  </div>
                </div>

                {!editing && (
                  <div className="field">
                    <label>Type</label>
                    <div className="segmented" style={{ width: "fit-content" }}>
                      <button type="button" className={!isSub ? "active" : ""} onClick={() => setMemberType("employee")}>
                        Company employee
                      </button>
                      <button type="button" className={isSub ? "active" : ""} onClick={() => setMemberType("subcontractor")}>
                        Subcontractor
                      </button>
                    </div>
                  </div>
                )}

                {!accessLocked && !isSub && (
                  <>
                    <fieldset className="field role-options">
                      <legend>Roles</legend>
                      {EMPLOYEE_ROLE_OPTIONS.map(([value, label]) => {
                        const locked = ADMIN_GRANTED.includes(value) && me?.role !== "company_admin";
                        const on = projectRoles.includes(value);
                        return (
                          <label key={value} className={`role-option${on ? " is-on" : ""}${locked ? " is-locked" : ""}`}>
                            <input
                              type="checkbox"
                              checked={on}
                              disabled={locked}
                              onChange={() => setProjectRoles((prev) => toggle(prev, value))}
                            />
                            <span>
                              <span className="role-option-name">{label}</span>
                              <span className="role-option-help">
                                {locked ? "Only a company admin can grant this." : ROLE_HELP[value]}
                              </span>
                            </span>
                          </label>
                        );
                      })}
                      <span className="cell-sub">Without an editing role they can view their projects only.</span>
                    </fieldset>
                    <div className="field">
                      <label>Projects</label>
                      <div className="pick-wrap">
                        {projects.map((p) => (
                          <button
                            type="button"
                            key={p.id}
                            className={`pick-chip${projectIds.includes(p.id) ? " selected" : ""}`}
                            aria-pressed={projectIds.includes(p.id)}
                            onClick={() => setProjectIds((prev) => toggle(prev, p.id))}
                          >
                            {p.name}
                          </button>
                        ))}
                        {projects.length === 0 && <span className="cell-sub">No projects yet.</span>}
                      </div>
                    </div>
                  </>
                )}

                {!accessLocked && isSub && (
                  <>
                    <fieldset className="field role-options">
                      <legend>Permission</legend>
                      {[
                        { on: true, name: "Update progress", help: "Enter status, dates and % on their scope while an update period is open." },
                        { on: false, name: "View only", help: "See their scope and its logic; no edits." },
                      ].map((opt) => (
                        <label key={opt.name} className={`role-option${canUpdate === opt.on ? " is-on" : ""}`}>
                          <input
                            type="radio"
                            name="sub-permission"
                            checked={canUpdate === opt.on}
                            onChange={() => setCanUpdate(opt.on)}
                          />
                          <span>
                            <span className="role-option-name">{opt.name}</span>
                            <span className="role-option-help">{opt.help}</span>
                          </span>
                        </label>
                      ))}
                      <span className="cell-sub">
                        Subcontractors only ever see their own scopes; company roles don&rsquo;t apply to them.
                      </span>
                    </fieldset>
                    <div className="field">
                      <label htmlFor="add-org">Subcontractor organization</label>
                      <select id="add-org" value={orgId} onChange={(e) => setOrgId(e.target.value)} style={selectStyle}>
                        <option value="">No organization</option>
                        {orgs.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.name} — {o.discipline}
                          </option>
                        ))}
                        <option value="__new__">+ New organization…</option>
                      </select>
                    </div>
                    {orgId === "__new__" && (
                      <div className="form-row">
                        <div className="field">
                          <label htmlFor="new-org-name">New organization name</label>
                          <input type="text" id="new-org-name" value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)} />
                        </div>
                        <div className="field">
                          <label htmlFor="new-org-discipline">Discipline</label>
                          <input type="text" id="new-org-discipline" value={newOrgDiscipline} onChange={(e) => setNewOrgDiscipline(e.target.value)} />
                        </div>
                      </div>
                    )}
                    <div className="field">
                      <label htmlFor="scope-project">Scopes</label>
                      <select
                        id="scope-project"
                        value={scopeProjectId}
                        onChange={(e) => setScopeProjectId(e.target.value)}
                        style={selectStyle}
                      >
                        <option value="">Select a project…</option>
                        {projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} ({p.code})
                          </option>
                        ))}
                      </select>
                      {scopeProjectId && (
                        <div className="pick-wrap" style={{ marginTop: ".45rem" }}>
                          {availableScopes.map((s) => (
                            <button
                              type="button"
                              key={s.id}
                              className={`pick-chip${scopeIds.includes(s.id) ? " selected" : ""}`}
                              aria-pressed={scopeIds.includes(s.id)}
                              onClick={() => setScopeIds((prev) => toggle(prev, s.id))}
                              title={`${s.activity_count} activities`}
                            >
                              {s.name} · {s.activity_count}
                            </button>
                          ))}
                          {availableScopes.length === 0 && (
                            <span className="cell-sub">No scopes on this project yet.</span>
                          )}
                        </div>
                      )}
                      <span className="cell-sub">
                        {selectedScopes.length === 0
                          ? "No scope selected — they won't see any activities."
                          : `Selected: ${selectedScopes
                              .map((s) => `${s.name} (${projectById.get(s.project_id)?.code ?? "?"})`)
                              .join(", ")}`}
                        {" · "}
                        <Link href="/administration/scopes">Define scopes by WBS or activity code</Link>
                      </span>
                    </div>
                  </>
                )}
              </div>
              <div className="modal-foot">
                <button type="button" className="btn btn-ghost" onClick={() => setModalOpen(false)}>
                  Cancel
                </button>
                <button className="btn btn-primary" type="submit" disabled={submitting}>
                  {submitting ? "Saving…" : editing ? "Save changes" : "Send invite"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
