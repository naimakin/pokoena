"use client";

// The "Quantify for QSRA" section of a register row: what the Monte Carlo
// needs to know about a risk (backend services/risk_analysis.py). Fields save
// on blur/change, like the rest of the register row.

import { useMemo, useState } from "react";
import type { Activity, RiskItem, WbsNode } from "@/lib/types";

const SCORE_TO_PCT: Record<number, number> = { 1: 5, 2: 20, 3: 40, 4: 60, 5: 85 };

function num(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function ThreePoint({
  values,
  suffix,
  onSave,
  label,
}: {
  values: [number | null, number | null, number | null];
  suffix: string;
  onSave: (v: [number | null, number | null, number | null]) => void;
  label: string;
}) {
  const [draft, setDraft] = useState(values.map((v) => (v === null ? "" : String(v))));
  const commit = () => {
    const next = draft.map(num) as [number | null, number | null, number | null];
    if (next.some((v, i) => v !== values[i])) onSave(next);
  };
  return (
    <div className="risk-3pt" role="group" aria-label={label}>
      {["Min", "Most likely", "Max"].map((ph, i) => (
        <input
          key={ph}
          className="num field-editable"
          type="number"
          min={0}
          step="any"
          placeholder={ph}
          aria-label={`${label} ${ph.toLowerCase()}`}
          value={draft[i]}
          onChange={(e) => setDraft(draft.map((d, k) => (k === i ? e.target.value : d)))}
          onBlur={commit}
        />
      ))}
      <span style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>{suffix}</span>
    </div>
  );
}

export function QsraRiskEditor({
  risk,
  activities,
  wbsNodes,
  onPatch,
}: {
  risk: RiskItem;
  activities: Activity[];
  wbsNodes: WbsNode[];
  onPatch: (body: Record<string, unknown>) => void;
}) {
  const [search, setSearch] = useState("");
  const suffix = risk.impact_mode === "duration_pct" ? "% longer" : "working days";
  const byId = useMemo(() => new Map(activities.map((a) => [a.external_id, a])), [activities]);
  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (q.length < 2) return [];
    return activities
      .filter((a) => !risk.activity_external_ids.includes(a.external_id))
      .filter((a) => a.external_id.toLowerCase().includes(q) || a.name.toLowerCase().includes(q))
      .slice(0, 8);
  }, [search, activities, risk.activity_external_ids]);

  const label = { fontSize: ".75rem", display: "flex", alignItems: "center", gap: ".35rem" } as const;

  return (
    <div className="card" style={{ padding: ".8rem .9rem", display: "flex", flexDirection: "column", gap: ".65rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem", flexWrap: "wrap" }}>
        <label className="checkbox-row" style={{ fontWeight: 500 }}>
          <input type="checkbox" checked={risk.qsra_enabled} onChange={(e) => onPatch({ qsra_enabled: e.target.checked })} />
          Include in QSRA
        </label>
        <label className="checkbox-row" title="The P6 schedule already carries this impact — leave it out so it isn't counted twice">
          <input
            type="checkbox"
            checked={risk.impact_in_schedule}
            onChange={(e) => onPatch({ impact_in_schedule: e.target.checked })}
          />
          Impact already in the P6 schedule
        </label>
      </div>

      <div style={{ display: "flex", gap: ".8rem", flexWrap: "wrap", alignItems: "center" }}>
        <label style={label}>
          Type
          <select value={risk.risk_kind} onChange={(e) => onPatch({ risk_kind: e.target.value })}>
            <option value="threat">Threat (delays)</option>
            <option value="opportunity">Opportunity (saves time)</option>
          </select>
        </label>
        <label style={label}>
          Probability
          <input
            key={`p-${risk.probability_pct}`}
            className="num field-editable"
            type="number"
            min={0}
            max={100}
            style={{ width: 70 }}
            defaultValue={risk.probability_pct ?? ""}
            placeholder={String(SCORE_TO_PCT[risk.probability] ?? 40)}
            onBlur={(e) => {
              const v = num(e.target.value);
              if (v !== risk.probability_pct) onPatch({ probability_pct: v });
            }}
          />
          %
          {risk.probability_pct === null && (
            <span className="actid">derived from score {risk.probability} — please review</span>
          )}
        </label>
        <label style={label}>
          Impact as
          <select value={risk.impact_mode} onChange={(e) => onPatch({ impact_mode: e.target.value })}>
            <option value="duration_pct">% longer durations</option>
            <option value="delay_days">Working days of delay</option>
          </select>
        </label>
        <label style={label}>
          Distribution
          <select value={risk.impact_distribution} onChange={(e) => onPatch({ impact_distribution: e.target.value })}>
            <option value="triangular">Triangular</option>
            <option value="pert">PERT</option>
            <option value="uniform">Uniform (ignores most likely)</option>
          </select>
        </label>
      </div>

      <div style={{ display: "flex", gap: "1.2rem", flexWrap: "wrap", alignItems: "center" }}>
        <div style={label}>
          <span style={{ minWidth: 92 }}>Impact</span>
          <ThreePoint
            key={`i-${risk.impact_min}-${risk.impact_ml}-${risk.impact_max}`}
            label="Impact"
            values={[risk.impact_min, risk.impact_ml, risk.impact_max]}
            suffix={suffix}
            onSave={([a, b, c]) => onPatch({ impact_min: a, impact_ml: b, impact_max: c })}
          />
        </div>
        <div style={label}>
          <span style={{ minWidth: 92 }}>After mitigation</span>
          <input
            key={`pp-${risk.post_probability_pct}`}
            className="num field-editable"
            type="number"
            min={0}
            max={100}
            style={{ width: 70 }}
            defaultValue={risk.post_probability_pct ?? ""}
            placeholder="Same"
            aria-label="Probability after mitigation"
            onBlur={(e) => {
              const v = num(e.target.value);
              if (v !== risk.post_probability_pct) onPatch({ post_probability_pct: v });
            }}
          />
          %
          <ThreePoint
            key={`pi-${risk.post_impact_min}-${risk.post_impact_ml}-${risk.post_impact_max}`}
            label="Impact after mitigation"
            values={[risk.post_impact_min, risk.post_impact_ml, risk.post_impact_max]}
            suffix={suffix}
            onSave={([a, b, c]) => onPatch({ post_impact_min: a, post_impact_ml: b, post_impact_max: c })}
          />
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: ".45rem" }}>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center", fontSize: ".75rem" }}>
          <span style={{ fontWeight: 500 }}>Affects</span>
          <label className="checkbox-row">
            <input type="radio" checked={!risk.apply_to_wbs} onChange={() => onPatch({ apply_to_wbs: false })} />
            Linked activities ({risk.activity_external_ids.length})
          </label>
          <label className="checkbox-row">
            <input type="radio" checked={risk.apply_to_wbs} onChange={() => onPatch({ apply_to_wbs: true })} />
            Everything under a WBS
          </label>
          {risk.apply_to_wbs && (
            <select value={risk.wbs_path ?? ""} onChange={(e) => onPatch({ wbs_path: e.target.value || null })}>
              <option value="">Choose WBS…</option>
              {wbsNodes.map((n) => (
                <option key={n.wbs_id} value={n.wbs_id}>
                  {"—".repeat(n.depth)} {n.outline_code} · {n.wbs_name}
                </option>
              ))}
            </select>
          )}
        </div>

        {!risk.apply_to_wbs && (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", gap: ".35rem" }}>
              {risk.activity_external_ids.map((id) => (
                <span key={id} className="pick-chip chip chip-neutral" title={byId.get(id)?.name ?? "Not in the current schedule"}>
                  <span className="mono">{id}</span>
                  <button
                    type="button"
                    aria-label={`Unlink ${id}`}
                    className="btn-ghost"
                    style={{ border: "none", background: "none", cursor: "pointer", padding: 0, color: "inherit" }}
                    onClick={() => onPatch({ activity_external_ids: risk.activity_external_ids.filter((x) => x !== id) })}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <div style={{ position: "relative", maxWidth: 420 }}>
              <input
                placeholder="Link an activity — search ID or name"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ width: "100%" }}
              />
              {matches.length > 0 && (
                <div className="card" style={{ position: "absolute", zIndex: 5, left: 0, right: 0, top: "100%", marginTop: 4, boxShadow: "var(--shadow-md)" }}>
                  {matches.map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      className="btn btn-ghost btn-sm"
                      style={{ display: "flex", width: "100%", justifyContent: "flex-start", gap: ".5rem" }}
                      onClick={() => {
                        onPatch({ activity_external_ids: [...risk.activity_external_ids, a.external_id] });
                        setSearch("");
                      }}
                    >
                      <span className="mono">{a.external_id}</span>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {risk.impact_mode === "delay_days" && risk.activity_external_ids.length > 1 && (
              <p style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                Link a delay risk to the activity where the delay first bites. Linking it to activities in sequence adds
                the delay once per activity.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
