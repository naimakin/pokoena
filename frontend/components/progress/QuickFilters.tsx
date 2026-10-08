"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronDownIcon } from "@/components/icons";
import { fmtP6Date } from "@/components/reporting/format";
import type { ActivityCodes } from "@/lib/types";
import {
  ACTIVITY_TYPES,
  DATE_PRESETS,
  resolveRange,
  RISK_INDICATORS,
  type DateAnchor,
  type DateRange,
  type FilterCriteria,
} from "./filter";

/** Trigger + panel, closed by an outside click or Escape. */
function Popover({
  label,
  summary,
  active,
  width = 300,
  align = "left",
  children,
}: {
  label: string;
  summary: string | null;
  active: boolean;
  width?: number;
  align?: "left" | "right";
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="qf" ref={ref}>
      <button
        type="button"
        className={`qf-trigger${active ? " is-active" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="qf-label">{label}</span>
        {summary && <span className="qf-summary">{summary}</span>}
        <ChevronDownIcon className="icon qf-caret" />
      </button>
      {open && (
        <div className={`gantt-pop qf-pop${align === "right" ? " is-right" : ""}`} style={{ width }}>
          {children}
        </div>
      )}
    </div>
  );
}

function CheckList({
  options,
  selected,
  onChange,
}: {
  options: { value: string; label: string; hint?: string }[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="qf-checks">
      {options.map((o) => {
        const on = selected.includes(o.value);
        return (
          <label key={o.value} className={`qf-check${on ? " is-on" : ""}`}>
            <input
              type="checkbox"
              checked={on}
              onChange={() => onChange(on ? selected.filter((v) => v !== o.value) : [...selected, o.value])}
            />
            <span>
              {o.label}
              {o.hint && <span className="qf-hint">{o.hint}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}

function PopFoot({ onClear, disabled, children }: { onClear: () => void; disabled: boolean; children?: ReactNode }) {
  return (
    <div className="qf-foot">
      <span className="qf-foot-note">{children}</span>
      <button type="button" className="btn btn-ghost btn-sm" onClick={onClear} disabled={disabled}>
        Clear
      </button>
    </div>
  );
}

function listSummary(selected: string[], options: { value: string; label: string }[]): string | null {
  if (selected.length === 0) return null;
  if (selected.length === 1) return options.find((o) => o.value === selected[0])?.label ?? "1 selected";
  return `${selected.length} selected`;
}

const ANCHORS: { key: DateAnchor; label: string }[] = [
  { key: "today", label: "From today" },
  { key: "data_date", label: "From data date" },
  { key: "fixed", label: "Fixed dates" },
];

function rangeSummary(r: DateRange | null): string | null {
  if (!r) return null;
  if (r.anchor === "fixed") {
    if (r.from && r.to) return `${fmtP6Date(r.from)} – ${fmtP6Date(r.to)}`;
    if (r.from) return `From ${fmtP6Date(r.from)}`;
    if (r.to) return `Until ${fmtP6Date(r.to)}`;
    return null;
  }
  const preset = DATE_PRESETS.find((p) => p.key === r.preset)?.label;
  if (!preset) return null;
  return r.anchor === "data_date" ? `${preset} of data date` : preset;
}

function DateRangeFilter({
  label,
  value,
  onChange,
  dataDate,
}: {
  label: string;
  value: DateRange | null;
  onChange: (next: DateRange | null) => void;
  dataDate: string | null;
}) {
  const [anchor, setAnchor] = useState<DateAnchor>(value?.anchor ?? "today");
  const [from, to] = value ? resolveRange(value, dataDate) : [null, null];
  const summary = rangeSummary(value);

  return (
    <Popover label={label} summary={summary} active={Boolean(summary)} width={330}>
      <div className="segmented qf-tabs" role="tablist">
        {ANCHORS.map((a) => (
          <button
            key={a.key}
            type="button"
            role="tab"
            aria-selected={anchor === a.key}
            className={anchor === a.key ? "active" : ""}
            disabled={a.key === "data_date" && !dataDate}
            title={a.key === "data_date" && !dataDate ? "This program has no data date" : undefined}
            onClick={() => setAnchor(a.key)}
          >
            {a.label}
          </button>
        ))}
      </div>

      {anchor === "fixed" ? (
        <div className="qf-fixed">
          <label>
            <span>From</span>
            <input
              type="date"
              value={value?.anchor === "fixed" ? value.from ?? "" : ""}
              onChange={(e) =>
                onChange({ anchor: "fixed", from: e.target.value || undefined, to: value?.anchor === "fixed" ? value.to : undefined })
              }
            />
          </label>
          <label>
            <span>To</span>
            <input
              type="date"
              value={value?.anchor === "fixed" ? value.to ?? "" : ""}
              onChange={(e) =>
                onChange({ anchor: "fixed", from: value?.anchor === "fixed" ? value.from : undefined, to: e.target.value || undefined })
              }
            />
          </label>
        </div>
      ) : (
        <div className="qf-presets">
          {(["prev", "next"] as const).map((dir) => (
            <div key={dir} className="qf-preset-col">
              <span className="qf-preset-head">{dir === "prev" ? "Looking back" : "Looking ahead"}</span>
              {DATE_PRESETS.filter((p) => p.key.startsWith(dir)).map((p) => {
                const on = value?.anchor === anchor && value.preset === p.key;
                return (
                  <button
                    key={p.key}
                    type="button"
                    className={`qf-preset${on ? " is-on" : ""}`}
                    onClick={() => onChange(on ? null : { anchor, preset: p.key })}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}

      <PopFoot onClear={() => onChange(null)} disabled={!value}>
        {from || to ? `${from ? fmtP6Date(from) : "…"} → ${to ? fmtP6Date(to) : "…"}` : "Any date"}
      </PopFoot>
    </Popover>
  );
}

export function QuickFilters({
  criteria,
  set,
  dataDate,
  codes,
  codeMembership,
  tagOptions,
}: {
  criteria: FilterCriteria;
  set: (patch: Partial<FilterCriteria>) => void;
  dataDate: string | null;
  codes: ActivityCodes | null;
  codeMembership: Map<string, Set<string>> | null;
  tagOptions: string[];
}) {
  const [codeQuery, setCodeQuery] = useState("");

  const codeOptions = useMemo(() => {
    if (!codes) return [];
    const typeById = new Map(codes.code_types.map((t) => [t.id, t.name]));
    return codes.code_values
      .map((v) => ({
        id: v.id,
        label: `${typeById.get(v.code_type_id) ?? "Code"}: ${v.name}`,
        count: codeMembership?.get(v.id)?.size ?? 0,
      }))
      .filter((o) => o.count > 0)
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [codes, codeMembership]);

  const inc = criteria.codesInclude;
  const exc = criteria.codesExclude;
  function toggleCode(id: string, mode: "include" | "exclude") {
    const isInc = inc.includes(id);
    const isExc = exc.includes(id);
    if (mode === "include") {
      set({ codesInclude: isInc ? inc.filter((x) => x !== id) : [...inc, id], codesExclude: exc.filter((x) => x !== id) });
    } else {
      set({ codesExclude: isExc ? exc.filter((x) => x !== id) : [...exc, id], codesInclude: inc.filter((x) => x !== id) });
    }
  }
  const codeSummary =
    inc.length + exc.length === 0
      ? null
      : [inc.length ? `${inc.length} included` : "", exc.length ? `${exc.length} excluded` : ""].filter(Boolean).join(" · ");

  const flagCount = (criteria.importantOnly ? 1 : 0) + criteria.tags.length;

  return (
    <div className="qf-row">
      <Popover label="Activity type" summary={listSummary(criteria.types, ACTIVITY_TYPES)} active={criteria.types.length > 0} width={220}>
        <CheckList options={ACTIVITY_TYPES} selected={criteria.types} onChange={(types) => set({ types })} />
        <PopFoot onClear={() => set({ types: [] })} disabled={criteria.types.length === 0} />
      </Popover>

      <DateRangeFilter
        label="Start"
        value={criteria.startRange}
        onChange={(startRange) => set({ startRange })}
        dataDate={dataDate}
      />
      <DateRangeFilter
        label="Finish"
        value={criteria.finishRange}
        onChange={(finishRange) => set({ finishRange })}
        dataDate={dataDate}
      />

      <Popover
        label="Risk indicators"
        summary={listSummary(criteria.risks, RISK_INDICATORS)}
        active={criteria.risks.length > 0}
        width={320}
      >
        <CheckList options={RISK_INDICATORS} selected={criteria.risks} onChange={(risks) => set({ risks })} />
        <PopFoot onClear={() => set({ risks: [] })} disabled={criteria.risks.length === 0}>
          Shows activities with any of these
        </PopFoot>
      </Popover>

      {codes && (
        <Popover label="Activity codes" summary={codeSummary} active={Boolean(codeSummary)} width={440}>
          {codeOptions.length === 0 ? (
            <p className="gantt-pop-empty">No activity codes in this program.</p>
          ) : (
            <>
              <input
                type="search"
                className="gantt-pop-search"
                placeholder="Search codes…"
                value={codeQuery}
                onChange={(e) => setCodeQuery(e.target.value)}
              />
              <div className="gantt-pop-list">
                {codeOptions
                  .filter((o) => o.label.toLowerCase().includes(codeQuery.trim().toLowerCase()))
                  .slice(0, 300)
                  .map((o) => {
                    const included = inc.includes(o.id);
                    const excluded = exc.includes(o.id);
                    return (
                      <div key={o.id} className={`gantt-opt${included ? " is-included" : ""}${excluded ? " is-excluded" : ""}`}>
                        <span className="gantt-opt-label" title={o.label}>
                          {o.label} <span className="gantt-opt-count">(~{o.count} activities)</span>
                        </span>
                        <span className="gantt-opt-actions">
                          <button type="button" className={included ? "is-on" : undefined} onClick={() => toggleCode(o.id, "include")}>
                            Include
                          </button>
                          <button type="button" className={excluded ? "is-on" : undefined} onClick={() => toggleCode(o.id, "exclude")}>
                            Exclude
                          </button>
                        </span>
                      </div>
                    );
                  })}
              </div>
            </>
          )}
          <PopFoot onClear={() => set({ codesInclude: [], codesExclude: [] })} disabled={!codeSummary}>
            Included codes match any; excluded codes always drop
          </PopFoot>
        </Popover>
      )}

      <Popover
        label="Flags & tags"
        summary={flagCount === 0 ? null : flagCount === 1 && criteria.importantOnly ? "Important" : `${flagCount} selected`}
        active={flagCount > 0}
        width={260}
        align="right"
      >
        <div className="qf-checks">
          <label className={`qf-check${criteria.importantOnly ? " is-on" : ""}`}>
            <input type="checkbox" checked={criteria.importantOnly} onChange={(e) => set({ importantOnly: e.target.checked })} />
            <span>
              Important
              <span className="qf-hint">Flagged as important in the activity window</span>
            </span>
          </label>
        </div>
        <div className="qf-section-head">Tags</div>
        {tagOptions.length === 0 ? (
          <p className="gantt-pop-empty">No tags on these activities yet.</p>
        ) : (
          <CheckList
            options={tagOptions.map((t) => ({ value: t, label: t }))}
            selected={criteria.tags}
            onChange={(tags) => set({ tags })}
          />
        )}
        <PopFoot onClear={() => set({ importantOnly: false, tags: [] })} disabled={flagCount === 0} />
      </Popover>
    </div>
  );
}
