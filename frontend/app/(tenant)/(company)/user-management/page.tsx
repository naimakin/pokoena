"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { CheckIcon, UsersIcon, XIcon } from "@/components/icons";
import {
  PROJECT_ROLE_LABELS,
  type Invite,
  type InviteCreatePayload,
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

export default function UserManagementPage() {
  const { showToast } = useToast();
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [orgs, setOrgs] = useState<SubcontractorOrg[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [lastInvite, setLastInvite] = useState<{ name: string; url: string } | null>(null);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [title, setTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [memberType, setMemberType] = useState<MemberType>("employee");
  const [projectRole, setProjectRole] = useState<ProjectRole>("execution");
  const [projectIds, setProjectIds] = useState<string[]>([]);

  const [orgId, setOrgId] = useState<string>("");
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgDiscipline, setNewOrgDiscipline] = useState("");
  const [scopeProjectId, setScopeProjectId] = useState<string>("");
  const [scopesByProject, setScopesByProject] = useState<Record<string, ProjectScope[]>>({});
  const [scopeIds, setScopeIds] = useState<string[]>([]);

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
    setProjectRole("execution");
    setProjectIds([]);
    setOrgId("");
    setNewOrgName("");
    setNewOrgDiscipline("");
    setScopeProjectId("");
    setScopeIds([]);
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
        project_role: projectRole,
      };
      if (memberType === "employee") {
        payload.project_ids = projectIds;
      } else {
        payload.project_scope_ids = scopeIds;
        payload.subcontractor_org_id = await resolveOrgId();
      }
      const invite = await api.post<Invite>("/invites", payload);
      if (invite.invite_url) {
        setLastInvite({ name: fullName || email, url: invite.invite_url });
      }
      showToast(`Invite created for ${email}`);
      resetForm();
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to send invite.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCopyInvite(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      showToast("Invite link copied");
    } catch {
      showToast("Couldn't copy — select and copy the link manually.");
    }
  }

  async function handleRemove(member: TeamMember) {
    try {
      await api.delete(`/team/${member.user_tenant_role_id}`);
      showToast(`Removed ${member.full_name}`);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to remove team member.");
    }
  }

  const availableScopes = scopeProjectId ? (scopesByProject[scopeProjectId] ?? []) : [];

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

        {lastInvite && (
          <div className="card">
            <div className="card-head">
              <div className="card-title">Invite link for {lastInvite.name}</div>
            </div>
            <div style={{ padding: "1rem 1.1rem" }}>
              <p className="page-desc" style={{ marginBottom: ".6rem" }}>
                No email provider is connected yet — copy this link and send it to them yourself (it only
                works once and only shows here, right now).
              </p>
              <div className="form-row" style={{ alignItems: "center" }}>
                <div className="field">
                  <input
                    type="text"
                    readOnly
                    value={lastInvite.url}
                    onFocus={(e) => e.target.select()}
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => handleCopyInvite(lastInvite.url)}
                >
                  <CheckIcon className="icon" /> Copy
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-head">
            <div className="card-title">Add user</div>
          </div>
          <form className="form-grid" style={{ padding: "1rem 1.1rem" }} onSubmit={handleSubmit}>
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

            <div className="form-row">
              <div className="field">
                <label htmlFor="add-type">Type</label>
                <select
                  id="add-type"
                  value={memberType}
                  onChange={(e) => setMemberType(e.target.value as MemberType)}
                  style={selectStyle}
                >
                  <option value="employee">Company employee</option>
                  <option value="subcontractor">Subcontractor</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="add-role">Role</label>
                <select
                  id="add-role"
                  value={projectRole}
                  onChange={(e) => setProjectRole(e.target.value as ProjectRole)}
                  style={selectStyle}
                >
                  {PROJECT_ROLE_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {memberType === "employee" && (
              <div className="field">
                <label htmlFor="add-projects">Projects</label>
                <select
                  id="add-projects"
                  multiple
                  value={projectIds}
                  onChange={(e) => setProjectIds(Array.from(e.target.selectedOptions, (o) => o.value))}
                  style={{ ...selectStyle, minHeight: 96 }}
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.code})
                    </option>
                  ))}
                </select>
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
                      <input
                        id="new-org-name"
                        value={newOrgName}
                        onChange={(e) => setNewOrgName(e.target.value)}
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="new-org-discipline">Discipline</label>
                      <input
                        id="new-org-discipline"
                        value={newOrgDiscipline}
                        onChange={(e) => setNewOrgDiscipline(e.target.value)}
                      />
                    </div>
                  </div>
                )}
                <div className="form-row">
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
                  <div className="field">
                    <label htmlFor="scope-ids">Scopes</label>
                    <select
                      id="scope-ids"
                      multiple
                      disabled={!scopeProjectId}
                      value={scopeIds}
                      onChange={(e) => setScopeIds(Array.from(e.target.selectedOptions, (o) => o.value))}
                      style={{ ...selectStyle, minHeight: 96 }}
                    >
                      {availableScopes.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} — {s.discipline}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </>
            )}

            <div className="form-actions">
              <button className="btn btn-primary" type="submit" disabled={submitting}>
                <UsersIcon className="icon" /> {submitting ? "Sending…" : "Add user & send invite"}
              </button>
            </div>
          </form>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Members</div>
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
                    <th>Name</th>
                    <th>Email</th>
                    <th>Title</th>
                    <th>Phone</th>
                    <th>Type</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {team.length === 0 && (
                    <tr>
                      <td colSpan={8} className="empty-state">
                        No team members yet.
                      </td>
                    </tr>
                  )}
                  {team.map((member) => (
                    <tr key={member.user_tenant_role_id}>
                      <td className="subname">{member.full_name}</td>
                      <td>{member.email}</td>
                      <td>{member.title ?? "—"}</td>
                      <td>{member.phone ?? "—"}</td>
                      <td>
                        <span className="role-badge">{member.role.replace("_", " ")}</span>
                      </td>
                      <td>{member.project_role ? PROJECT_ROLE_LABELS[member.project_role] : "—"}</td>
                      <td>
                        <span className={`chip ${member.is_active ? "chip-good" : "chip-neutral"}`}>
                          {member.is_active ? "Active" : "Removed"}
                        </span>
                      </td>
                      <td>
                        {member.is_active && member.role !== "company_admin" && (
                          <button
                            className="act-btn act-reject"
                            title="Remove access"
                            onClick={() => handleRemove(member)}
                          >
                            <XIcon className="icon" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
