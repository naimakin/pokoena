"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { CheckIcon, UsersIcon, XIcon } from "@/components/icons";
import type { PlatformAdmin, PlatformAdminCreatePayload } from "@/lib/types";

export default function PlatformAdminsPage() {
  const { showToast } = useToast();
  const [admins, setAdmins] = useState<PlatformAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [title, setTitle] = useState("");
  const [phone, setPhone] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const items = await api.get<PlatformAdmin[]>("/platform/admins");
      setAdmins(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load admins.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const payload: PlatformAdminCreatePayload = {
        email,
        password,
        full_name: fullName,
        title: title || undefined,
        phone: phone || undefined,
      };
      await api.post("/platform/admins", payload);
      showToast(`Platform admin ${email} created`);
      setEmail("");
      setPassword("");
      setFullName("");
      setTitle("");
      setPhone("");
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to create admin.", "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeactivate(admin: PlatformAdmin) {
    if (!window.confirm(`Deactivate ${admin.full_name}? They won't be able to sign in until reactivated.`)) return;
    try {
      await api.post(`/platform/admins/${admin.id}/deactivate`);
      showToast(`${admin.full_name} deactivated`);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to deactivate admin.", "error");
    }
  }

  async function handleActivate(admin: PlatformAdmin) {
    try {
      await api.post(`/platform/admins/${admin.id}/activate`);
      showToast(`${admin.full_name} activated`);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to activate admin.", "error");
    }
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          <b>Admins</b>
        </span>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Platform admins</div>
            <div className="page-desc">POKO staff who can onboard and manage tenant companies.</div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Add a platform admin</div>
          </div>
          <form className="form-grid" style={{ padding: "1rem 1.1rem" }} onSubmit={handleCreate}>
            <div className="form-row">
              <div className="field">
                <label htmlFor="admin-email">Email</label>
                <input
                  id="admin-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="admin-password">Password</label>
                <input
                  id="admin-password"
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>
            <div className="form-row">
              <div className="field">
                <label htmlFor="admin-name">Full name</label>
                <input id="admin-name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="admin-title">Title</label>
                <input id="admin-title" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="admin-phone">Phone</label>
              <input id="admin-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </div>
            <div className="form-actions">
              <button className="btn btn-primary" type="submit" disabled={submitting}>
                <UsersIcon className="icon" /> {submitting ? "Creating…" : "Create admin"}
              </button>
            </div>
          </form>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">All admins</div>
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
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {admins.length === 0 && (
                    <tr>
                      <td colSpan={6} className="empty-state">
                        No platform admins yet.
                      </td>
                    </tr>
                  )}
                  {admins.map((admin) => (
                    <tr key={admin.id}>
                      <td className="subname">{admin.full_name}</td>
                      <td>{admin.email}</td>
                      <td>{admin.title ?? "—"}</td>
                      <td>{admin.phone ?? "—"}</td>
                      <td>
                        <span className={`chip ${admin.is_active ? "chip-good" : "chip-neutral"}`}>
                          {admin.is_active ? "Active" : "Deactivated"}
                        </span>
                      </td>
                      <td>
                        {admin.is_active ? (
                          <button
                            className="act-btn act-reject"
                            title="Deactivate"
                            onClick={() => handleDeactivate(admin)}
                          >
                            <XIcon className="icon" />
                          </button>
                        ) : (
                          <button
                            className="act-btn act-approve"
                            title="Activate"
                            onClick={() => handleActivate(admin)}
                          >
                            <CheckIcon className="icon" />
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
