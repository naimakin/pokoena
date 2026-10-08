"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useProjectContext } from "@/lib/project-context";
import type { Activity } from "@/lib/types";
import { SearchIcon } from "@/components/icons";

export interface SearchPage {
  href: string;
  label: string;
  /** Sidebar section or menu the page lives in, shown as a hint. */
  group: string;
}

interface Result {
  key: string;
  href: string;
  title: string;
  hint: string;
  kind: "page" | "activity";
}

const MAX_ACTIVITIES = 8;

/** Header search (Ctrl/⌘+K): jump to any page by name, or to an activity of
 *  the selected project by ID or name — activities open in Activity Workspace
 *  pre-filtered (/activity-workspace?q=…). The activity list is fetched once per
 *  project, the first time the dialog opens. */
export function GlobalSearch({ pages }: { pages: SearchPage[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const { project } = useProjectContext();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [activities, setActivities] = useState<Activity[] | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listId = useId();

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActive(0);
    triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    setOpen(false);
    setQuery("");
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    if (!project || loadedFor === project.id) return;
    setLoadedFor(project.id);
    setActivities(null);
    api
      .get<Activity[]>(`/activities?project_id=${project.id}`)
      .then(setActivities)
      .catch(() => setActivities([]));
  }, [open, project, loadedFor]);

  const results = useMemo<Result[]>(() => {
    const q = query.trim().toLowerCase();
    const pageHits = pages
      .filter((p) => !q || p.label.toLowerCase().includes(q) || p.group.toLowerCase().includes(q))
      .map((p) => ({ key: `p:${p.href}`, href: p.href, title: p.label, hint: p.group, kind: "page" as const }));
    if (!q) return pageHits;
    const activityHits = (activities ?? [])
      .filter((a) => (a.task_type ?? "") !== "TT_WBS")
      .filter((a) => a.external_id.toLowerCase().includes(q) || a.name.toLowerCase().includes(q))
      .slice(0, MAX_ACTIVITIES)
      .map((a) => ({
        key: `a:${a.external_id}`,
        href: `/activity-workspace?q=${encodeURIComponent(a.external_id)}`,
        title: a.name,
        hint: a.external_id,
        kind: "activity" as const,
      }));
    return [...pageHits, ...activityHits];
  }, [query, pages, activities]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  function go(r: Result | undefined) {
    if (!r) return;
    close();
    router.push(r.href);
  }

  function onInputKey(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(results[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  const pageResults = results.filter((r) => r.kind === "page");
  const activityResults = results.filter((r) => r.kind === "activity");
  const q = query.trim();

  function renderItem(r: Result) {
    const index = results.indexOf(r);
    return (
      <li
        key={r.key}
        id={`${listId}-${index}`}
        role="option"
        aria-selected={index === active}
        className={`gsearch-item${index === active ? " is-active" : ""}`}
        onMouseEnter={() => setActive(index)}
        onMouseDown={(e) => {
          e.preventDefault();
          go(r);
        }}
      >
        <span className="gsearch-title">{r.title}</span>
        <span className={`gsearch-hint${r.kind === "activity" ? " mono" : ""}`}>{r.hint}</span>
      </li>
    );
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="header-search"
        onClick={() => setOpen(true)}
        aria-label="Search pages and activities"
        title="Search (Ctrl+K)"
      >
        <SearchIcon className="icon" />
        <span className="header-search-text">Search</span>
        <kbd className="header-search-kbd">Ctrl K</kbd>
      </button>

      {open && (
        <div className="gsearch-backdrop" onMouseDown={close}>
          <div
            className="gsearch"
            role="dialog"
            aria-modal="true"
            aria-label="Search"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="gsearch-field">
              <SearchIcon className="icon" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onInputKey}
                placeholder={project ? `Search pages, or activities in ${project.code}…` : "Search pages…"}
                role="combobox"
                aria-expanded="true"
                aria-controls={listId}
                aria-activedescendant={results.length ? `${listId}-${active}` : undefined}
              />
              <kbd className="gsearch-esc">Esc</kbd>
            </div>
            <ul className="gsearch-list" id={listId} role="listbox">
              {pageResults.length > 0 && <li className="gsearch-group" role="presentation">Pages</li>}
              {pageResults.map(renderItem)}
              {q && project && (
                <li className="gsearch-group" role="presentation">
                  Activities in {project.code}
                </li>
              )}
              {q && project && activities === null && <li className="gsearch-empty">Loading activities…</li>}
              {activityResults.map(renderItem)}
              {q && activities !== null && results.length === 0 && (
                <li className="gsearch-empty">Nothing matches “{q}”.</li>
              )}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
