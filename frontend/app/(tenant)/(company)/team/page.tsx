"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { UsersIcon, XIcon } from "@/components/icons";
import type { InviteCreatePayload, TeamMember, TenantRole } from "@/lib/types";

export default function TeamPage() {
  const { showToast } = useToast();
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<TenantRole>("company_employee");
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const members = await api.get<TeamMember[]>("/team");
      setTeam(members);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load your team.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleInvite(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const payload: InviteCreatePayload = { email, role };
      await api.post("/invites", payload);
      showToast(`Invite sent to ${email}`);
      setEmail("");
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to send invite.");
    } finally {
      setSubmitting(false);
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

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          <b>Team</b>
        </span>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Team</div>
            <div className="page-desc">
              Invite employees and subcontractors, and manage who has access to your projects.
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Invite someone</div>
          </div>
          <form className="form-grid" style={{ padding: "1rem 1.1rem" }} onSubmit={handleInvite}>
            <div className="form-row">
              <div className="field">
                <label htmlFor="invite-email">Email</label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="invite-role">Role</label>
                <select
                  id="invite-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as TenantRole)}
                  style={{
                    background: "var(--surface)",
                    border: "1px solid var(--border-strong)",
                    borderRadius: 6,
                    padding: ".5rem .65rem",
                    fontSize: ".8125rem",
                  }}
                >
                  <option value="company_employee">Company employee</option>
                  <option value="subcontractor">Subcontractor</option>
                </select>
              </div>
            </div>
            <div className="form-actions">
              <button className="btn btn-primary" type="submit" disabled={submitting}>
                <UsersIcon className="icon" /> {submitting ? "Sending…" : "Send invite"}
              </button>
            </div>
            <p className="page-desc">
              Project and scope assignment for the invited person can be adjusted after they accept — this
              form sends the invite with default (unassigned) access.
            </p>
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
                    <th>Role</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {team.length === 0 && (
                    <tr>
                      <td colSpan={5} className="empty-state">
                        No team members yet.
                      </td>
                    </tr>
                  )}
                  {team.map((member) => (
                    <tr key={member.user_tenant_role_id}>
                      <td className="subname">{member.full_name}</td>
                      <td>{member.email}</td>
                      <td>
                        <span className="role-badge">{member.role.replace("_", " ")}</span>
                      </td>
                      <td>
                        <span className={`chip ${member.is_active ? "chip-good" : "chip-neutral"}`}>
                          {member.is_active ? "Active" : "Removed"}
                        </span>
                      </td>
                      <td>
                        {member.is_active && (
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
