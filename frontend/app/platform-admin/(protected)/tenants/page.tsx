"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { BuildingIcon } from "@/components/icons";
import type { Tenant } from "@/lib/types";

export default function PlatformTenantsPage() {
  const { showToast } = useToast();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminFullName, setAdminFullName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const items = await api.get<Tenant[]>("/platform/tenants");
      setTenants(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load tenants.");
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
      await api.post("/platform/tenants", {
        name,
        slug,
        admin_email: adminEmail,
        admin_full_name: adminFullName,
      });
      showToast(`${name} created — invite sent to ${adminEmail}`);
      setName("");
      setSlug("");
      setAdminEmail("");
      setAdminFullName("");
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to create tenant.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSuspend(tenant: Tenant) {
    try {
      await api.post(`/platform/tenants/${tenant.id}/suspend`);
      showToast(`${tenant.name} suspended`);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to suspend tenant.");
    }
  }

  async function handleDelete(tenant: Tenant) {
    try {
      await api.delete(`/platform/tenants/${tenant.id}`);
      showToast(`${tenant.name} deleted`);
      load();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to delete tenant.");
    }
  }

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          <b>Tenants</b>
        </span>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Tenant companies</div>
            <div className="page-desc">Onboard a new company or manage an existing one.</div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Onboard a company</div>
          </div>
          <form className="form-grid" style={{ padding: "1rem 1.1rem" }} onSubmit={handleCreate}>
            <div className="form-row">
              <div className="field">
                <label htmlFor="name">Company name</label>
                <input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="slug">Slug</label>
                <input
                  id="slug"
                  required
                  placeholder="acme-construction"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                />
              </div>
            </div>
            <div className="form-row">
              <div className="field">
                <label htmlFor="admin-email">First admin&rsquo;s email</label>
                <input
                  id="admin-email"
                  type="email"
                  required
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="admin-name">First admin&rsquo;s name</label>
                <input
                  id="admin-name"
                  required
                  value={adminFullName}
                  onChange={(e) => setAdminFullName(e.target.value)}
                />
              </div>
            </div>
            <div className="form-actions">
              <button className="btn btn-primary" type="submit" disabled={submitting}>
                <BuildingIcon className="icon" /> {submitting ? "Creating…" : "Create tenant & send invite"}
              </button>
            </div>
          </form>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">All tenants</div>
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
                    <th>Slug</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.length === 0 && (
                    <tr>
                      <td colSpan={5} className="empty-state">
                        No tenants yet.
                      </td>
                    </tr>
                  )}
                  {tenants.map((tenant) => (
                    <tr key={tenant.id}>
                      <td className="subname">{tenant.name}</td>
                      <td className="mono">{tenant.slug}</td>
                      <td>
                        <span
                          className={`chip ${
                            tenant.status === "active"
                              ? "chip-good"
                              : tenant.status === "suspended"
                                ? "chip-warn"
                                : "chip-crit"
                          }`}
                        >
                          {tenant.status}
                        </span>
                      </td>
                      <td>{new Date(tenant.created_at).toLocaleDateString()}</td>
                      <td>
                        <div className="actions">
                          {tenant.status === "active" && (
                            <button className="btn btn-secondary btn-sm" onClick={() => handleSuspend(tenant)}>
                              Suspend
                            </button>
                          )}
                          {tenant.status !== "deleted" && (
                            <button className="btn btn-danger btn-sm" onClick={() => handleDelete(tenant)}>
                              Delete
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
    </>
  );
}
