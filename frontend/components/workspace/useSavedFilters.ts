"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/Toast";
import type { SavedActivityFilter } from "@/lib/types";
import { normalizeCriteria, type FilterCriteria } from "@/components/progress/filter";

// Saved filters keep the Activity Ledger's view key, so every filter people
// saved there shows up in Activity Workspace unchanged.
const VIEW = "progress";

export function useSavedFilters({
  projectId,
  criteria,
  setCriteriaState,
}: {
  projectId: string | null;
  criteria: FilterCriteria;
  setCriteriaState: (c: FilterCriteria) => void;
}) {
  const { showToast } = useToast();
  const [savedFilters, setSavedFilters] = useState<SavedActivityFilter[]>([]);
  const [activeSavedId, setActiveSavedId] = useState<string | null>(null);
  const [filterDirty, setFilterDirty] = useState(false);

  const loadFilters = useCallback(async () => {
    if (!projectId) {
      setSavedFilters([]);
      return;
    }
    try {
      setSavedFilters(await api.get<SavedActivityFilter[]>(`/projects/${projectId}/saved-filters?view=${VIEW}`));
    } catch {
      setSavedFilters([]);
    }
  }, [projectId]);

  useEffect(() => {
    loadFilters();
  }, [loadFilters]);

  /** Every criteria change from the filter UI goes through here, so editing a
   *  selected saved filter marks it modified ("*", Update). */
  const setCriteria = useCallback(
    (next: FilterCriteria) => {
      setCriteriaState(next);
      if (activeSavedId) setFilterDirty(true);
    },
    [activeSavedId, setCriteriaState],
  );

  function selectSaved(f: SavedActivityFilter) {
    setCriteriaState(normalizeCriteria(f.criteria));
    setActiveSavedId(f.id);
    setFilterDirty(false);
  }

  const clearSaved = useCallback(() => {
    setActiveSavedId(null);
    setFilterDirty(false);
  }, []);

  async function saveNew(name: string) {
    if (!projectId) return;
    try {
      const created = await api.post<SavedActivityFilter>(`/projects/${projectId}/saved-filters?view=${VIEW}`, {
        name,
        criteria: criteria as unknown as Record<string, unknown>,
        filter_version: 1,
      });
      await loadFilters();
      setActiveSavedId(created.id);
      setFilterDirty(false);
      showToast("Filter saved.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not save filter.", "error");
    }
  }

  async function updateActive() {
    if (!projectId || !activeSavedId) return;
    try {
      await api.put<SavedActivityFilter>(`/projects/${projectId}/saved-filters/${activeSavedId}`, {
        criteria: criteria as unknown as Record<string, unknown>,
      });
      await loadFilters();
      setFilterDirty(false);
      showToast("Filter updated.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not update filter.", "error");
    }
  }

  async function deleteSaved(f: SavedActivityFilter) {
    if (!projectId) return;
    try {
      await api.delete(`/projects/${projectId}/saved-filters/${f.id}`);
      if (activeSavedId === f.id) clearSaved();
      await loadFilters();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not delete filter.", "error");
    }
  }

  return {
    savedFilters,
    activeSavedId,
    filterDirty,
    setCriteria,
    selectSaved,
    clearSaved,
    saveNew,
    updateActive,
    deleteSaved,
  };
}
