"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useProjectContext } from "@/lib/project-context";
import { useToast } from "@/components/Toast";
import { ApiError } from "@/lib/api";
import { ChevronDownIcon, FolderPlusIcon } from "@/components/icons";

export function ProjectSwitcher() {
  const { projects, project, loading, selectProject, createProject } = useProjectContext();
  const { showToast } = useToast();
  const rootRef = useRef<HTMLDivElement>(null);

  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const created = await createProject({ name: name.trim(), code: code.trim() });
      showToast(`Project "${created.name}" created`);
      setName("");
      setCode("");
      setCreating(false);
      setOpen(false);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to create project.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="project-switcher" ref={rootRef}>
      <button
        type="button"
        className="project-switcher-trigger"
        onClick={() => setOpen((v) => !v)}
        disabled={loading}
      >
        <span className="project-switcher-name">{loading ? "Loading…" : (project?.name ?? "No project yet")}</span>
        <ChevronDownIcon className="icon" />
      </button>

      {open && (
        <div className="project-switcher-menu">
          {projects.length === 0 && !creating && <div className="project-switcher-empty">No projects yet</div>}
          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`project-switcher-item${p.id === project?.id ? " active" : ""}`}
              onClick={() => {
                selectProject(p.id);
                setOpen(false);
              }}
            >
              <span>{p.name}</span>
              <span className="project-switcher-code">{p.code}</span>
            </button>
          ))}

          <div className="project-switcher-divider" />

          {creating ? (
            <form className="project-switcher-form" onSubmit={handleCreate}>
              <input
                autoFocus
                placeholder="Project name (e.g. Aircraft Hangar)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
              <input placeholder="Code (e.g. AC-01)" value={code} onChange={(e) => setCode(e.target.value)} required />
              <div style={{ display: "flex", gap: ".4rem" }}>
                <button type="submit" className="btn btn-primary btn-sm" disabled={submitting} style={{ flex: 1 }}>
                  {submitting ? "Creating…" : "Create"}
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setCreating(false)}>
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <button type="button" className="project-switcher-item add" onClick={() => setCreating(true)}>
              <FolderPlusIcon className="icon" /> New project
            </button>
          )}
        </div>
      )}
    </div>
  );
}
