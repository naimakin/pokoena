"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import type { Project, ProjectCreatePayload } from "@/lib/types";

const STORAGE_KEY = "poko:selected-project-id";

interface ProjectContextValue {
  projects: Project[];
  project: Project | null;
  loading: boolean;
  error: string | null;
  selectProject: (id: string) => void;
  createProject: (payload: ProjectCreatePayload) => Promise<Project>;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

// Single source of truth for "which project is the user looking at" across
// every (company) page — replaces the old pattern of each page fetching
// /projects and silently defaulting to projects[0].
export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.get<Project[]>("/projects");
      setProjects(list);
      setSelectedId((prev) => {
        if (prev && list.some((p) => p.id === prev)) return prev;
        const stored = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
        if (stored && list.some((p) => p.id === stored)) return stored;
        return list[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load projects.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function selectProject(id: string) {
    setSelectedId(id);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, id);
  }

  async function createProject(payload: ProjectCreatePayload): Promise<Project> {
    const created = await api.post<Project>("/projects", payload);
    setProjects((prev) => [...prev, created]);
    selectProject(created.id);
    return created;
  }

  const project = useMemo(() => projects.find((p) => p.id === selectedId) ?? null, [projects, selectedId]);

  const value: ProjectContextValue = { projects, project, loading, error, selectProject, createProject };

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProjectContext(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProjectContext must be used within a ProjectProvider");
  return ctx;
}
