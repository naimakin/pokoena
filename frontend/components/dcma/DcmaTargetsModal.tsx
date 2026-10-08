"use client";

// The project's own DCMA 14-Point targets. Every check lists its target
// number(s) beside DCMA's default; saving stores only the ones that differ
// (backend: PUT /projects/{id}/dcma/thresholds), and "DCMA defaults" puts
// every one back.

import { useEffect, useRef, useState } from "react";
import { XIcon } from "@/components/icons";
import { api, ApiError } from "@/lib/api";
import { DCMA_CATEGORIES, DCMA_DEFAULTS, CHECK_IDS, metaById, type TargetField, type Thresholds } from "@/lib/dcma";

const UNIT: Record<TargetField["unit"], string> = { "%": "%", days: "working days", index: "" };

function step(f: TargetField): number {
  return f.unit === "index" ? 0.01 : f.unit === "days" ? 1 : 0.5;
}

function fmtDefault(f: TargetField, v: number): string {
  if (f.unit === "index") return v.toFixed(2);
  return `${Math.round(v * 100) / 100}${f.unit === "%" ? "%" : "d"}`;
}

export function DcmaTargetsModal({
  projectId,
  thresholds,
  defaults,
  focusCheck,
  onClose,
  onSaved,
}: {
  projectId: string;
  thresholds: Thresholds;
  defaults: Thresholds;
  focusCheck: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const base = { ...DCMA_DEFAULTS, ...defaults };
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(thresholds).map(([k, v]) => [k, String(v)])),
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (focusCheck == null) return;
    const row = bodyRef.current?.querySelector<HTMLElement>(`[data-check="${focusCheck}"]`);
    row?.scrollIntoView({ block: "center" });
    row?.querySelector<HTMLInputElement>("input")?.focus();
  }, [focusCheck]);

  const parsed: Record<string, number> = {};
  const localErrors: Record<string, string> = {};
  for (const [k, raw] of Object.entries(draft)) {
    const v = Number(raw);
    if (raw.trim() === "" || Number.isNaN(v)) localErrors[k] = "Enter a number";
    else parsed[k] = v;
  }
  if (parsed.cp_length_min > parsed.cp_length_max) localErrors.cp_length_min = "Above the upper bound";
  if (parsed.bei_min > parsed.bei_max) localErrors.bei_min = "Above the upper bound";
  const shownErrors = { ...errors, ...localErrors };
  const changed = Object.keys(parsed).filter((k) => parsed[k] !== base[k]).length;

  async function save() {
    if (Object.keys(localErrors).length) return;
    setSaving(true);
    setErrors({});
    try {
      await api.put(`/projects/${projectId}/dcma/thresholds`, parsed);
      onSaved();
    } catch (err) {
      const detail = err instanceof ApiError ? (err.detail as { errors?: Record<string, string> } | null) : null;
      if (detail && typeof detail === "object" && detail.errors) setErrors(detail.errors);
      else setErrors({ _: err instanceof ApiError ? err.message : "Could not save the targets." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && !saving && onClose()}>
      <div className="modal-lg dcma-targets" role="dialog" aria-modal="true" aria-labelledby="dcma-targets-title">
        <div className="modal-head">
          <div style={{ flex: 1 }}>
            <div className="modal-title" id="dcma-targets-title">
              Project targets
            </div>
            <div className="modal-desc">
              What each check is measured against on this project. Change any target, or put one back to DCMA&apos;s with the link beside it. The
              dashboard&apos;s schedule quality score follows the same targets.
            </div>
          </div>
          <button type="button" className="act-btn" onClick={onClose} aria-label="Close">
            <XIcon className="icon" />
          </button>
        </div>

        <div className="modal-body dcma-targets-body" ref={bodyRef}>
          {DCMA_CATEGORIES.map((cat) => {
            const ids = CHECK_IDS.filter((id) => metaById(id).category === cat.key && metaById(id).fields.length > 0);
            return (
              <div key={cat.key} className="dcma-targets-group">
                <div className="dcma-targets-cat">{cat.label}</div>
                {ids.map((id) => {
                  const m = metaById(id, { ...base, ...parsed });
                  const custom = m.fields.some((f) => parsed[f.key] !== base[f.key]);
                  return (
                    <div key={id} className={`dcma-targets-row${custom ? " is-custom" : ""}`} data-check={id}>
                      <div className="dcma-targets-name">
                        <span className="mono dcma-card-no">{String(id).padStart(2, "0")}</span>
                        <span>
                          <span className="dcma-targets-title">{m.title}</span>
                          <span className="dcma-targets-measures">{m.measures}</span>
                          {m.rule && <span className="dcma-targets-measures">{m.rule}</span>}
                        </span>
                      </div>
                      <div className="dcma-targets-fields">
                        {m.fields.map((f) => (
                          <label key={f.key} className="dcma-targets-field">
                            <span className="dcma-targets-label">{f.label}</span>
                            <span className="dcma-targets-input">
                              <input
                                type="number"
                                step={step(f)}
                                min={f.unit === "days" ? 1 : 0}
                                max={f.unit === "%" ? 100 : f.unit === "index" ? 2 : undefined}
                                value={draft[f.key] ?? ""}
                                aria-invalid={Boolean(shownErrors[f.key])}
                                onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                              />
                              <span className="dcma-targets-unit">{UNIT[f.unit]}</span>
                            </span>
                            <span className="dcma-targets-default">
                              {parsed[f.key] !== base[f.key] ? (
                                <button
                                  type="button"
                                  className="dcma-targets-reset"
                                  onClick={() => setDraft((d) => ({ ...d, [f.key]: String(base[f.key]) }))}
                                  title="Back to DCMA's target"
                                >
                                  DCMA {fmtDefault(f, base[f.key])}
                                </button>
                              ) : (
                                `DCMA ${fmtDefault(f, base[f.key])}`
                              )}
                            </span>
                            {shownErrors[f.key] && <span className="sim-row-error">{shownErrors[f.key]}</span>}
                          </label>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}
          {shownErrors._ && <p className="sim-row-error">{shownErrors._}</p>}
        </div>

        <div className="modal-foot">
          <button
            type="button"
            className="btn btn-ghost dcma-targets-defaults"
            disabled={saving}
            onClick={() => setDraft(Object.fromEntries(Object.entries(base).map(([k, v]) => [k, String(v)])))}
          >
            DCMA defaults
          </button>
          <span className="dcma-targets-count">
            {changed ? `${changed} target${changed === 1 ? "" : "s"} differ from DCMA` : "All DCMA targets"}
          </span>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={save} disabled={saving || Object.keys(localErrors).length > 0}>
            {saving ? "Saving…" : "Save targets"}
          </button>
        </div>
      </div>
    </div>
  );
}
