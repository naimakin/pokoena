"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { CheckIcon, LockIcon, UsersIcon, XIcon } from "@/components/icons";
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
  type TenantRole,
} from "@/lib/types";

const PROJECT_ROLE_OPTIONS = Object.entries(PROJECT_ROLE_LABELS) as [ProjectRole, string][];

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

export default function UserManagementPage() {
  const { showToast } = useToast();
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [orgs, setOrgs] = useState<SubcontractorOrg[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [lastLink, setLastLink] = useState<{ heading: string; url: string } | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [title, setTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [memberType, setMemberType] = useState<MemberType>("employee");
  const [projectRoles, setProjectRoles] = useState<ProjectRole[]>(["execution"]);
  const [projectIds, setProjectIds] = useState<string[]>([]);

  const [orgId, setOrgId] = useState<string>("");
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgDiscipline, setNewOrgDiscipline] = useState("");
  const [scopeProjectId, setScopeProjectId] = useState<string>("");
  const [scopesByProject, setScopesByProject] = useState<Record<string, ProjectScope[]>>({});
  const [scopeIds, setScopeIds] = useState<string[]>([]);

  const [memberSearch, setMemberSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | MemberType>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "removed">("all");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [members, projectList, orgList] = await Promise.all([
        api.get<TeamMember[]>("/team"),
        api.get<Project[]>("/projects"),
        api.get<SubcontractorOrg[]>("/subcontractor-organizations"),
      ]);
      setTeam(members);
      setProjects(projectList);
      setOrgs(orgList);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load your team.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!scopeProjectId || scopesByProject[scopeProjectId]) return;
    api
      .get<ProjectScope[]>(`/projects/${scopeProjectId}/scopes`)
      .then((scopes) => setScopesByProject((prev) => ({ ...prev, [scopeProjectId]: scopes })))
      .catch(() => showToast("Failed to load scopes for that project."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeProjectId]);

  function resetForm() {
    setEmail("");
    setFullName("");
    setTitle("");
    setPhone("");
    setMemberType("employee");
    setProjectRoles(["execution"]);
    setProjectIds([]);
    setOrgId("");
    setNewOrgName("");
    setNewOrgDiscipline("");
    setScopeProjectId("");
    setScopeIds([]);
  }

  function openModal() {
    resetForm();
    setModalOpen(true);
  }

  function toggleProjectRole(role: ProjectRole) {
    setProjectRoles((prev) => (prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]));
  }

  function toggleProjectId(id: string) {
    setProjectIds((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
  }

  function toggleScopeId(id: string) {
    setScopeIds((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
  }

  async function resolveOrgId(): Promise<string | undefined> {
    if (orgId && orgId !== "__new__") return orgId;
    if (orgId === "__new__" && newOrgName.trim()) {
      const created = await api.post<SubcontractorOrg>("/subcontractor-organizations", {
        name: newOrgName.trim(),
        discipline: newOrgDiscipline.trim() || "General",
      });
      setOrgs((prev) => [...prev, created]);
      return created.id;
    }
    return undefined;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const role: TenantRole = memberType === "subcontractor" ? "subcontractor" : "company_employee";
      const payload: InviteCreatePayload = {
        email,
        full_name: fullName,
        title: title || undefined,
        phone: phone || undefined,
        role,
        project_roles: projectRoles,
      };
      if (memberType === "employee") {
        payload.project_ids = projectIds;
      } else {
        payload.project_scope_ids = scopeIds;
        payload.subcontractor_org_id = await resolveOrgId();
      }
      const invite = await api.post<Invite>("/invites", payload);
      if (invite.invite_url) {
        setLastLink({ heading: `Invite link for ${fullName || email}`, url: invite.invite_url });
      }
      showToast(`Invite created for ${email}`);
      setModalOpen(false);
      resetForm();
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to send invite.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCopyLink(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      showToast("Link copied");
    } catch {
      showToast("Couldn't copy — select and copy the link manually.");
    }
  }

  async function handleRemove(member: TeamMember) {
    if (!window.confirm(`Remove ${member.full_name}'s access? They won't be able to sign in anymore.`)) return;
    try {
      await api.delete(`/team/${member.user_tenant_role_id}`);
      showToast(`Removed ${member.full_name}`);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to remove team member.");
    }
  }

  async function handleResetLink(member: TeamMember) {
    try {
      const result = await api.post<PasswordResetLink>(`/team/${member.user_tenant_role_id}/reset-password-link`);
      setLastLink({ heading: `Password reset link for ${result.email}`, url: result.reset_url });
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to generate a reset link.");
    }
  }

  const availableScopes = scopeProjectId ? (scopesByProject[scopeProjectId] ?? []) : [];
  const activeCount = team.filter((m) => m.is_active).length;

  const filteredTeam = useMemo(() => {
    const q = memberSearch.trim().toLowerCase();
    return team.filter((m) => {
      if (q && !m.full_name.toLowerCase().includes(q) && !m.email.toLowerCase().includes(q)) return false;
      const isSub = m.role === "subcontractor";
      if (typeFilter === "employee" && isSub) return false;
      if (typeFilter === "subcontractor" && !isSub) return false;
      if (statusFilter === "active" && !m.is_active) return false;
      if (statusFilter === "removed" && m.is_active) return false;
      return true;
    });
  }, [team, memberSearch, typeFilter, statusFilter]);

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          <b>User Management</b>
        </span>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">User Management</div>
            <div className="page-desc">
              Add employees and subcontractors, assign them to projects, and set what they&rsquo;re allowed to do.
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
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setLastLink(null)}>
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
            <button className="btn btn-primary btn-sm" onClick={openModal}>
              <UsersIcon className="icon" /> Add User
            </button>
          </div>

          <div className="card-toolbar" style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", padding: "0.85rem 1.1rem", borderBottom: "1px solid var(--border)" }}>
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
                    <th>Roles</th>
                    <th>Status</th>
                    <th style={{ width: 96 }}></th>
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
                  {filteredTeam.map((member) => {
                    const visibleRoles = member.project_roles.slice(0, 2);
                    const overflowCount = member.project_roles.length - visibleRoles.length;
                    return (
                      <tr key={member.user_tenant_role_id} style={member.is_active ? undefined : { opacity: 0.55 }}>
                        <td>
                          <div className="cell-flex">
                            <div className="subrow-avatar">{initialsOf(member.full_name)}</div>
                            <div>
                              <div className="subname">{member.full_name}</div>
                              <div className="cell-sub">{member.email}</div>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={`chip ${member.role === "subcontractor" ? "chip-info" : "chip-neutral"}`}>
                            {member.role === "subcontractor" ? "Subcontractor" : "Employee"}
                          </span>
                        </td>
                        <td>
                          {member.project_roles.length > 0 ? (
                            <div className="role-wrap">
                              {visibleRoles.map((r) => (
                                <span key={r} className="role-badge">
                                  {PROJECT_ROLE_LABELS[r]}
                                </span>
                              ))}
                              {overflowCount > 0 && (
                                <span
                                  className="role-badge overflow"
                                  title={member.project_roles.slice(2).map((r) => PROJECT_ROLE_LABELS[r]).join(", ")}
                                >
                                  +{overflowCount}
                                </span>
                              )}
                            </div>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          <span className={`chip ${member.is_active ? "chip-good" : "chip-neutral"}`}>
                            {member.is_active ? "Active" : "Removed"}
                          </span>
                        </td>
                        <td>
                          <div className="actions">
                            {member.is_active && (
                              <button className="act-btn" title="Reset password" onClick={() => handleResetLink(member)}>
                                <LockIcon className="icon" />
                              </button>
                            )}
                            {member.is_active && member.role !== "company_admin" && (
                              <button className="act-btn act-reject" title="Remove access" onClick={() => handleRemove(member)}>
                                <XIcon className="icon" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setModalOpen(false)}>
          <div className="modal" style={{ maxWidth: 560, maxHeight: "90vh" }}>
            <div className="modal-head">
              <UsersIcon className="icon-lg" style={{ color: "var(--accent-strong)" }} />
              <div>
                <div className="modal-title">Add team member</div>
                <div className="modal-desc">
                  No email provider is connected yet — you&rsquo;ll get a one-time invite link to copy and send them
                  yourself.
                </div>
              </div>
            </div>
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
              <div className="modal-body" style={{ overflowY: "auto" }}>
                <div className="form-row">
                  <div className="field">
                    <label htmlFor="add-email">Email</label>
                    <input id="add-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
                  </div>
                  <div className="field">
                    <label htmlFor="add-name">Full name</label>
                    <input id="add-name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="field">
                    <label htmlFor="add-title">Title</label>
                    <input id="add-title" value={title} onChange={(e) => setTitle(e.target.value)} />
                  </div>
                  <div className="field">
                    <label htmlFor="add-phone">Phone</label>
                    <input id="add-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
                  </div>
                </div>

                <div className="field">
                  <label>Type</label>
                  <div className="segmented" style={{ width: "fit-content" }}>
                    <button type="button" className={memberType === "employee" ? "active" : ""} onClick={() => setMemberType("employee")}>
                      Company employee
                    </button>
                    <button type="button" className={memberType === "subcontractor" ? "active" : ""} onClick={() => setMemberType("subcontractor")}>
                      Subcontractor
                    </button>
                  </div>
                </div>

                <div className="field">
                  <label>Role(s)</label>
                  <div className="pick-wrap">
                    {PROJECT_ROLE_OPTIONS.map(([value, label]) => (
                      <button
                        type="button"
                        key={value}
                        className={`pick-chip${projectRoles.includes(value) ? " selected" : ""}`}
                        onClick={() => toggleProjectRole(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {memberType === "employee" && (
                  <div className="field">
                    <label>Projects</label>
                    <div className="pick-wrap">
                      {projects.map((p) => (
                        <button
                          type="button"
                          key={p.id}
                          className={`pick-chip${projectIds.includes(p.id) ? " selected" : ""}`}
                          onClick={() => toggleProjectId(p.id)}
                        >
                          {p.name}
                        </button>
                      ))}
                      {projects.length === 0 && <span className="cell-sub">No projects yet.</span>}
                    </div>
                  </div>
                )}

                {memberType === "subcontractor" && (
                  <>
                    <div className="field">
                      <label htmlFor="add-org">Subcontractor organization</label>
                      <select id="add-org" value={orgId} onChange={(e) => setOrgId(e.target.value)} style={selectStyle}>
                        <option value="">Select an organization…</option>
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
                          <input id="new-org-name" value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)} />
                        </div>
                        <div className="field">
                          <label htmlFor="new-org-discipline">Discipline</label>
                          <input id="new-org-discipline" value={newOrgDiscipline} onChange={(e) => setNewOrgDiscipline(e.target.value)} />
                        </div>
                      </div>
                    )}
                    <div className="field">
                      <label htmlFor="scope-project">Project</label>
                      <select
                        id="scope-project"
                        value={scopeProjectId}
                        onChange={(e) => {
                          setScopeProjectId(e.target.value);
                          setScopeIds([]);
                        }}
                        style={selectStyle}
                      >
                        <option value="">Select a project…</option>
                        {projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} ({p.code})
                          </option>
                        ))}
                      </select>
                    </div>
                    {scopeProjectId && (
                      <div className="field">
                        <label>Scopes</label>
                        <div className="pick-wrap">
                          {availableScopes.map((s) => (
                            <button
                              type="button"
                              key={s.id}
                              className={`pick-chip${scopeIds.includes(s.id) ? " selected" : ""}`}
                              onClick={() => toggleScopeId(s.id)}
                            >
                              {s.name} — {s.discipline}
                            </button>
                          ))}
                          {availableScopes.length === 0 && <span className="cell-sub">No scopes on this project yet.</span>}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
              <div className="modal-foot">
                <button type="button" className="btn btn-ghost" onClick={() => setModalOpen(false)}>
                  Cancel
                </button>
                <button className="btn btn-primary" type="submit" disabled={submitting}>
                  {submitting ? "Sending…" : "Send invite"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
