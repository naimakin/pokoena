"use client";

import { useEffect, useState } from "react";
import type { DashboardThemeKey, DashboardWidgetConfig, DashboardWidgetKey } from "@/lib/types";
import { WIDGET_REGISTRY, WIDGET_ORDER } from "@/components/dashboard/DashboardWidgets";
import { ChevronDownIcon, ChevronUpIcon, GridIcon, SparkleIcon } from "@/components/icons";

const THEMES: { key: DashboardThemeKey; label: string }[] = [
  { key: "calm", label: "Calm" },
  { key: "high-contrast", label: "High contrast" },
  { key: "mono-amber", label: "Mono accent" },
];

interface Props {
  open: boolean;
  initialWidgets: DashboardWidgetConfig[];
  initialTheme: DashboardThemeKey;
  saving: boolean;
  onCancel: () => void;
  onSave: (widgets: DashboardWidgetConfig[], theme: DashboardThemeKey) => void;
}

function normalize(widgets: DashboardWidgetConfig[]): DashboardWidgetConfig[] {
  const known = new Map<DashboardWidgetKey, DashboardWidgetConfig>(
    widgets.filter((w) => WIDGET_ORDER.includes(w.key)).map((w) => [w.key, w]),
  );
  const ordered = [...known.values()].sort((a, b) => a.order - b.order);
  for (const key of WIDGET_ORDER) {
    if (!known.has(key)) ordered.push({ key, order: ordered.length, enabled: false, options: {} });
  }
  return ordered.map((w, i) => ({ ...w, order: i }));
}

export function DashboardConfigModal({ open, initialWidgets, initialTheme, saving, onCancel, onSave }: Props) {
  const [widgets, setWidgets] = useState<DashboardWidgetConfig[]>([]);
  const [theme, setTheme] = useState<DashboardThemeKey>(initialTheme);
  const [dragKey, setDragKey] = useState<DashboardWidgetKey | null>(null);

  useEffect(() => {
    if (open) {
      setWidgets(normalize(initialWidgets));
      setTheme(initialTheme);
      setDragKey(null);
    }
  }, [open, initialWidgets, initialTheme]);

  if (!open) return null;

  const enabledCount = widgets.filter((w) => w.enabled).length;

  function toggle(key: DashboardWidgetKey) {
    setWidgets((prev) => prev.map((w) => (w.key === key ? { ...w, enabled: !w.enabled } : w)));
  }

  function move(index: number, delta: number) {
    setWidgets((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((w, i) => ({ ...w, order: i }));
    });
  }

  function reorderByKey(from: DashboardWidgetKey, to: DashboardWidgetKey) {
    setWidgets((prev) => {
      const fromIdx = prev.findIndex((w) => w.key === from);
      const toIdx = prev.findIndex((w) => w.key === to);
      if (fromIdx < 0 || toIdx < 0 || fromIdx === toIdx) return prev;
      const next = [...prev];
      const [moved] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, moved);
      return next.map((w, i) => ({ ...w, order: i }));
    });
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="modal dash-config">
        <div className="modal-head">
          <GridIcon className="icon-lg" />
          <div>
            <div className="modal-title">Configure dashboard</div>
            <div className="modal-desc">
              Choose which widgets to show, drag to reorder, and pick a colour theme. Saved for you on this project.
            </div>
          </div>
        </div>

        <div className="modal-body">
          <div className="field">
            <label>Colour theme</label>
            <div className="segmented">
              {THEMES.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  className={theme === t.key ? "active" : ""}
                  onClick={() => setTheme(t.key)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <label>
              Widgets <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>· {enabledCount} shown</span>
            </label>
            <div className="dash-reorder">
              {widgets.map((w, i) => {
                const def = WIDGET_REGISTRY[w.key];
                return (
                  <div
                    key={w.key}
                    className={`dash-reorder-item${w.enabled ? "" : " off"}${dragKey === w.key ? " dragging" : ""}`}
                    draggable
                    onDragStart={() => setDragKey(w.key)}
                    onDragEnd={() => setDragKey(null)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => {
                      if (dragKey) reorderByKey(dragKey, w.key);
                      setDragKey(null);
                    }}
                  >
                    <svg className="grip icon" viewBox="0 0 16 16" aria-hidden="true">
                      <circle cx="6" cy="4" r="1.2" fill="currentColor" stroke="none" />
                      <circle cx="10" cy="4" r="1.2" fill="currentColor" stroke="none" />
                      <circle cx="6" cy="8" r="1.2" fill="currentColor" stroke="none" />
                      <circle cx="10" cy="8" r="1.2" fill="currentColor" stroke="none" />
                      <circle cx="6" cy="12" r="1.2" fill="currentColor" stroke="none" />
                      <circle cx="10" cy="12" r="1.2" fill="currentColor" stroke="none" />
                    </svg>
                    <span>
                      <span className="rlabel">{def.title}</span> <span className="rdesc">— {def.description}</span>
                    </span>
                    <span className="dash-reorder-move">
                      <button type="button" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                        <ChevronUpIcon className="icon" />
                      </button>
                      <button
                        type="button"
                        aria-label="Move down"
                        disabled={i === widgets.length - 1}
                        onClick={() => move(i, 1)}
                      >
                        <ChevronDownIcon className="icon" />
                      </button>
                    </span>
                    <label className="rtoggle checkbox-row">
                      <input type="checkbox" checked={w.enabled} onChange={() => toggle(w.key)} />
                    </label>
                  </div>
                );
              })}
            </div>
            <div className="dash-ai-row">
              <SparkleIcon className="icon" />
              Custom AI widget from a prompt <span className="soon">Soon</span>
            </div>
          </div>
        </div>

        <div className="modal-foot">
          <button className="btn btn-ghost" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={saving || enabledCount === 0}
            onClick={() => onSave(widgets.map((w, i) => ({ ...w, order: i })), theme)}
          >
            {saving ? "Saving…" : "Save dashboard"}
          </button>
        </div>
      </div>
    </div>
  );
}
