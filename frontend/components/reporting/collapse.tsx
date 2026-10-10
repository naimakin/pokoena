"use client";

import { createContext, useContext, useId, useMemo, useState, type ReactNode } from "react";
import { ChevronDownIcon, ChevronUpIcon } from "@/components/icons";
import { HelpTip } from "@/components/HelpTip";
import type { HelpKey } from "@/lib/help";

// Expand/collapse for report blocks and the long sections on the Reporting
// pages. A page that wants "Expand all / Collapse all" owns the set of closed
// keys and provides it through <FoldProvider>; each section names itself with
// <FoldKey>. A section rendered without either keeps its own local state, so
// every block still works on its own.
//
// Folding only hides the body on screen: it stays mounted (blocks keep their
// data) and @media print forces every body open, so a report printed with
// half its blocks folded still prints in full.

interface FoldRegistry {
  isOpen: (key: string) => boolean;
  setOpen: (key: string, open: boolean) => void;
}

const FoldContext = createContext<FoldRegistry | null>(null);
const FoldKeyContext = createContext<string | null>(null);

export function FoldProvider({
  closed,
  onChange,
  children,
}: {
  closed: ReadonlySet<string>;
  onChange: (key: string, open: boolean) => void;
  children: ReactNode;
}) {
  const value = useMemo<FoldRegistry>(
    () => ({ isOpen: (key) => !closed.has(key), setOpen: onChange }),
    [closed, onChange],
  );
  return <FoldContext.Provider value={value}>{children}</FoldContext.Provider>;
}

export function FoldKey({ id, children }: { id: string; children: ReactNode }) {
  return <FoldKeyContext.Provider value={id}>{children}</FoldKeyContext.Provider>;
}

/** Open state for one section — shared when a provider and key are present,
 *  local otherwise. */
export function useFold(defaultOpen: boolean) {
  const registry = useContext(FoldContext);
  const key = useContext(FoldKeyContext);
  const [localOpen, setLocalOpen] = useState(defaultOpen);
  const bodyId = useId();

  const open = registry && key != null ? registry.isOpen(key) : localOpen;
  const toggle = () => {
    if (registry && key != null) registry.setOpen(key, !open);
    else setLocalOpen(!open);
  };
  return { open, toggle, bodyId };
}

/** A card whose header folds it shut. The whole header is the button (the
 *  existing .section-head pattern), inside an h2 so a printed or exported
 *  report keeps its heading outline. `hint` only shows while folded — it is
 *  there to say what is hidden ("24 activities"), not to repeat the body. */
export function FoldCard({
  title,
  subtitle,
  meta,
  hint,
  defaultOpen = true,
  className,
  help,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  meta?: ReactNode;
  hint?: string;
  defaultOpen?: boolean;
  className?: string;
  /** A "?" beside the header (lib/help.ts) — outside the fold button. */
  help?: HelpKey;
  children: ReactNode;
}) {
  const { open, toggle, bodyId } = useFold(defaultOpen);
  const showHint = !open && !!hint;

  return (
    <section className={`card fold-card${className ? ` ${className}` : ""}`}>
      <h2 className="fold-heading">
        <button
          type="button"
          className="section-head fold-head"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={toggle}
        >
          <ChevronDownIcon className="icon icon-sm section-caret" aria-hidden="true" />
          <span className="fold-head-text">
            <span className="card-title">{title}</span>
            {subtitle && <span className="card-title-sub">{subtitle}</span>}
          </span>
          {(meta || showHint) && (
            <span className="fold-meta">
              {showHint && <span className="fold-hint">{hint}</span>}
              {meta}
            </span>
          )}
        </button>
        {help && <HelpTip id={help} />}
      </h2>
      <div id={bodyId} className={`fold-body${open ? "" : " is-folded"}`}>
        {children}
      </div>
    </section>
  );
}

/** "Expand all / Collapse all" — screen only, never printed. */
export function FoldAllControls({
  onExpand,
  onCollapse,
  canExpand,
  canCollapse,
}: {
  onExpand: () => void;
  onCollapse: () => void;
  canExpand: boolean;
  canCollapse: boolean;
}) {
  return (
    <div className="fold-controls no-print" role="group" aria-label="Expand or collapse sections">
      <button type="button" className="btn btn-ghost btn-sm" onClick={onExpand} disabled={!canExpand}>
        <ChevronDownIcon className="icon icon-sm" aria-hidden="true" /> Expand all
      </button>
      <button type="button" className="btn btn-ghost btn-sm" onClick={onCollapse} disabled={!canCollapse}>
        <ChevronUpIcon className="icon icon-sm" aria-hidden="true" /> Collapse all
      </button>
    </div>
  );
}

/** A card that folds shut from its header, for cards whose header also
 *  carries controls (a button, a checkbox): the title is the toggle and
 *  `actions` sit beside it, outside the button. Shares the fold registry, so
 *  a page's Expand all / Collapse all reaches it through <FoldKey>. */
export function FoldPanel({
  title,
  sub,
  actions,
  defaultOpen = true,
  help,
  children,
}: {
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  defaultOpen?: boolean;
  /** A "?" at the header's right end (lib/help.ts), shown folded or not. */
  help?: HelpKey;
  children: ReactNode;
}) {
  const { open, toggle, bodyId } = useFold(defaultOpen);
  return (
    <section className="card fold-panel">
      <div className={`card-head fold-panel-head${open ? "" : " is-folded"}`}>
        <button type="button" className="fold-panel-toggle" aria-expanded={open} aria-controls={bodyId} onClick={toggle}>
          <ChevronDownIcon className="icon icon-sm section-caret" aria-hidden="true" />
          <span className="fold-head-text">
            <span className="card-title">{title}</span>
            {sub && <span className="card-title-sub">{sub}</span>}
          </span>
        </button>
        {((actions && open) || help) && (
          <div className="card-head-end">
            {actions && open && <div className="fold-panel-actions">{actions}</div>}
            {help && <HelpTip id={help} />}
          </div>
        )}
      </div>
      <div id={bodyId} className={`fold-body${open ? "" : " is-folded"}`}>
        {children}
      </div>
    </section>
  );
}
