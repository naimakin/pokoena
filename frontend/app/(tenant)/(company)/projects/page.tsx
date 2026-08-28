"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { FolderPlusIcon } from "@/components/icons";
import type { Project, ProjectCreatePayload, User } from "@/lib/types";

export default function ProjectsPage() {
  const { showToast } = useToast();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [isCompanyAdmin, setIsCompanyAdmin] = useState(false);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api
      .get<Project[]>("/projects")
      .then(setProjects)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load projects."))
      .finally(() => setLoading(false));
    api
      .get<User>("/auth/me")
      .then((user) => setIsCompanyAdmin(user.role === "company_admin"))
      .catch(() => setIsCompanyAdmin(false));
  }, []);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    try {
      const payload: ProjectCreatePayload = { name, code };
      const created = await api.post<Project>("/projects", payload);
      setProjects((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
      showToast(`Project ${created.name} created`);
      setName("");
      setCode("");
      setShowForm(false);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to create project.");
    } finally {
      setCreating(false);
    }
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter((p) => p.name.toLowerCase().includes(q) || p.code.toLowerCase().includes(q));
  }, [projects, search]);

  return (
    <>
      <div className="a-topbar">
        <span className="crumb">
          <b>Projects</b>
        </span>
      </div>

      <div className="a-content">
        <div className="page-head">
          <div>
            <div className="page-title">Projects</div>
            <div className="page-desc">Every project your company runs through Poko.</div>
          </div>
          {isCompanyAdmin && (
            <button className="btn btn-primary" onClick={() => setShowForm((v) => !v)}>
              <FolderPlusIcon className="icon" /> New Project
            </button>
          )}
        </div>

        {isCompanyAdmin && showForm && (
          <div className="card">
            <div className="card-head">
              <div className="card-title">New project</div>
            </div>
            <form className="form-grid" style={{ padding: "1rem 1.1rem" }} onSubmit={handleCreate}>
              <div className="form-row">
                <div className="field">
                  <label htmlFor="new-project-name">Project name</label>
                  <input id="new-project-name" required value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="new-project-code">Code</label>
                  <input
                    id="new-project-code"
                    required
                    placeholder="RLP-P2"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />
                </div>
              </div>
              <div className="form-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>
                  Cancel
                </button>
                <button className="btn btn-primary" type="submit" disabled={creating}>
                  {creating ? "Creating…" : "Create project"}
                </button>
              </div>
            </form>
          </div>
        )}

        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">All projects</div>
              <div className="card-title-sub">{projects.length} total</div>
            </div>
            <div className="field" style={{ minWidth: 220 }}>
              <input
                type="text"
                placeholder="Search by name or code…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
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
                    <th>Code</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={2} className="empty-state">
                        {projects.length === 0 ? "No projects yet." : "No projects match your search."}
                      </td>
                    </tr>
                  )}
                  {filtered.map((p) => (
                    <tr key={p.id}>
                      <td className="subname">{p.name}</td>
                      <td className="mono">{p.code}</td>
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
