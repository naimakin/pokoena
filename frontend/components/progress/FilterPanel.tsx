"use client";

import { useState } from "react";
import type { ActivityCodes, SavedActivityFilter, WbsNode } from "@/lib/types";
import { selectStyle } from "@/components/ScurveChart";
import {
  EMPTY_CRITERIA,
  FIELD_DEFS,
  FIELD_BY_KEY,
  OP_LABEL,
  criteriaIsEmpty,
  type FilterCriteria,
  type FilterOp,
  type FilterPredicate,
} from "./filter";
import { QuickFilters } from "./QuickFilters";
import { WbsTreeSelect } from "./WbsTreeSelect";

function blankPredicate(): FilterPredicate {
  const def = FIELD_DEFS[0];
  return { field: def.key, op: def.ops[0], value: "" };
}

export function FilterPanel({
  criteria,
  onChange,
  nodes,
  savedFilters,
  activeSavedId,
  filterDirty,
  onSelectSaved,
  onClearSaved,
  onSaveNew,
  onUpdateActive,
  onDeleteSaved,
  dataDate,
  codes,
  codeMembership,
  tagOptions,
}: {
  dataDate: string | null;
  codes: ActivityCodes | null;
  codeMembership: Map<string, Set<string>> | null;
  tagOptions: string[];
  criteria: FilterCriteria;
  onChange: (next: FilterCriteria) => void;
  nodes: WbsNode[];
  savedFilters: SavedActivityFilter[];
  activeSavedId: string | null;
  filterDirty: boolean;
  onSelectSaved: (f: SavedActivityFilter) => void;
  onClearSaved: () => void;
  onSaveNew: (name: string) => void;
  onUpdateActive: () => void;
  onDeleteSaved: (f: SavedActivityFilter) => void;
}) {
  const [builderOpen, setBuilderOpen] = useState(false);
  const [newName, setNewName] = useState("");

  const set = (patch: Partial<FilterCriteria>) => onChange({ ...criteria, ...patch });
  const active = savedFilters.find((f) => f.id === activeSavedId) ?? null;

  function setPredicate(i: number, patch: Partial<FilterPredicate>) {
    const predicates = criteria.predicates.map((p, idx) => (idx === i ? { ...p, ...patch } : p));
    set({ predicates });
  }

  return (
    <div className="card">
      {/* saved-filter chips */}
      {(savedFilters.length > 0 || !criteriaIsEmpty(criteria)) && (
        <div style={{ display: "flex", alignItems: "center", gap: ".4rem", flexWrap: "wrap", padding: ".7rem 1rem", borderBottom: "1px solid var(--border)" }}>
          {savedFilters.map((f) => (
            <span key={f.id} style={{ display: "inline-flex", alignItems: "center" }}>
              <button
                className={`pick-chip${f.id === activeSavedId ? " selected" : ""}`}
                onClick={() => onSelectSaved(f)}
                title={f.is_shared ? "Shared filter" : "Your filter"}
              >
                {f.name}
                {f.id === activeSavedId && filterDirty ? " *" : ""}
              </button>
              {f.id === activeSavedId && f.is_owner && (
                <button
                  className="btn btn-ghost btn-sm"
                  title="Delete filter"
                  onClick={() => onDeleteSaved(f)}
                  style={{ marginLeft: 2 }}
                >
                  ✕
                </button>
              )}
            </span>
          ))}
          {active && filterDirty && active.is_owner && (
            <button className="btn btn-secondary btn-sm" onClick={onUpdateActive}>
              Update &ldquo;{active.name}&rdquo;
            </button>
          )}
          {!criteriaIsEmpty(criteria) && !active && (
            <span style={{ display: "inline-flex", gap: ".3rem", alignItems: "center" }}>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Name this filter…"
                style={{ ...selectStyle, width: 160, height: 28 }}
              />
              <button
                className="btn btn-primary btn-sm"
                disabled={!newName.trim()}
                onClick={() => {
                  onSaveNew(newName.trim());
                  setNewName("");
                }}
              >
                Save
              </button>
            </span>
          )}
        </div>
      )}

      {/* one row: list filters on the left, the date windows on the right */}
      <QuickFilters
        criteria={criteria}
        set={set}
        dataDate={dataDate}
        codes={codes}
        codeMembership={codeMembership}
        tagOptions={tagOptions}
        lead={
          <>
            <input
              className="qf-search"
              value={criteria.search}
              onChange={(e) => set({ search: e.target.value })}
              placeholder="Search ID or name…"
              aria-label="Search activity ID or name"
            />
            <WbsTreeSelect nodes={nodes} value={criteria.wbsId} onChange={(wbsId) => set({ wbsId })} />
          </>
        }
        tail={
          <>
            <button
              type="button"
              className={`qf-trigger qf-plain${criteria.predicates.length || builderOpen ? " is-active" : ""}`}
              onClick={() => setBuilderOpen((v) => !v)}
              aria-expanded={builderOpen}
            >
              <span className="qf-label">Advanced</span>
              {criteria.predicates.length > 0 && <span className="qf-count">{criteria.predicates.length}</span>}
            </button>
            {!criteriaIsEmpty(criteria) && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  onChange(EMPTY_CRITERIA);
                  onClearSaved();
                }}
              >
                Clear all
              </button>
            )}
          </>
        }
      />

      {/* condition builder */}
      {builderOpen && (
        <div className="filter-builder" style={{ borderTop: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
            <span style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>Match</span>
            <select
              value={criteria.match}
              onChange={(e) => set({ match: e.target.value === "any" ? "any" : "all" })}
              style={{ ...selectStyle, height: 30 }}
            >
              <option value="all">All conditions</option>
              <option value="any">Any condition</option>
            </select>
          </div>

          {criteria.predicates.map((p, i) => {
            const def = FIELD_BY_KEY.get(p.field) ?? FIELD_DEFS[0];
            return (
              <div className="filter-cond" key={i}>
                <select
                  value={p.field}
                  onChange={(e) => {
                    const nd = FIELD_BY_KEY.get(e.target.value)!;
                    setPredicate(i, { field: nd.key, op: nd.ops[0], value: "", value2: undefined });
                  }}
                  style={selectStyle}
                >
                  {FIELD_DEFS.map((f) => (
                    <option key={f.key} value={f.key}>
                      {f.label}
                    </option>
                  ))}
                </select>

                <select
                  value={p.op}
                  onChange={(e) => setPredicate(i, { op: e.target.value as FilterOp })}
                  style={selectStyle}
                >
                  {def.ops.map((op) => (
                    <option key={op} value={op}>
                      {OP_LABEL[op]}
                    </option>
                  ))}
                </select>

                {def.type === "enum" && p.op === "in" && (
                  <span style={{ display: "flex", gap: ".3rem", flexWrap: "wrap" }}>
                    {def.enumValues?.map((ev) => {
                      const parts = p.value.split(",").filter(Boolean);
                      const on = parts.includes(ev.value);
                      return (
                        <button
                          key={ev.value}
                          className={`pick-chip${on ? " selected" : ""}`}
                          onClick={() =>
                            setPredicate(i, {
                              value: (on ? parts.filter((x) => x !== ev.value) : [...parts, ev.value]).join(","),
                            })
                          }
                        >
                          {ev.label}
                        </button>
                      );
                    })}
                  </span>
                )}
                {def.type === "bool" && p.op === "is" && (
                  <select
                    value={p.value || "true"}
                    onChange={(e) => setPredicate(i, { value: e.target.value })}
                    style={selectStyle}
                  >
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                  </select>
                )}
                {def.type === "text" && (
                  <input
                    value={p.value}
                    onChange={(e) => setPredicate(i, { value: e.target.value })}
                    placeholder="value"
                    style={{ ...selectStyle, width: 160 }}
                  />
                )}
                {def.type === "number" && (
                  <>
                    <input
                      type="number"
                      value={p.value}
                      onChange={(e) => setPredicate(i, { value: e.target.value })}
                      style={{ ...selectStyle, width: 90 }}
                    />
                    {p.op === "between" && (
                      <input
                        type="number"
                        value={p.value2 ?? ""}
                        onChange={(e) => setPredicate(i, { value2: e.target.value })}
                        style={{ ...selectStyle, width: 90 }}
                      />
                    )}
                  </>
                )}
                {def.type === "date" && (p.op === "before" || p.op === "after") && (
                  <input
                    type="date"
                    value={p.value}
                    onChange={(e) => setPredicate(i, { value: e.target.value })}
                    style={selectStyle}
                  />
                )}

                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => set({ predicates: criteria.predicates.filter((_, idx) => idx !== i) })}
                >
                  ✕
                </button>
              </div>
            );
          })}

          <button
            className="btn btn-secondary btn-sm"
            style={{ alignSelf: "flex-start" }}
            onClick={() => set({ predicates: [...criteria.predicates, blankPredicate()] })}
          >
            + Add condition
          </button>
        </div>
      )}
    </div>
  );
}
