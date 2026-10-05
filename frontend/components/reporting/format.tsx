// Formatting shared by Float Path and every report block, so a date or a float
// value reads the same wherever it appears in an issued document.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** P6 convention: DD-MMM-YYYY (see CLAUDE.md). */
export function fmtP6Date(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCDate()).padStart(2, "0")}-${MONTHS[d.getUTCMonth()]}-${d.getUTCFullYear()}`;
}

export function fmtP6DateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${fmtP6Date(iso)} ${hh}:${mm}`;
}

export function fmtDays(days: number | null | undefined): string {
  if (days == null) return "—";
  const rounded = Math.round(days * 10) / 10;
  return `${rounded > 0 ? "+" : ""}${rounded}d`;
}

/** Always en-US grouping — an issued report must not switch to "0,00" /
 *  "153.128" because the reader's browser is set to another locale. */
export function fmtNum(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 10) / 10}%`;
}

/** The five-step total-float ramp from DESIGN.md, keyed off float in days. */
export function floatClass(days: number | null | undefined): string {
  if (days == null) return "float-badge";
  if (days <= 0) return "float-badge float-zero";
  if (days <= 5) return "float-badge float-low";
  if (days <= 15) return "float-badge float-medium";
  if (days <= 30) return "float-badge float-adequate";
  return "float-badge float-high";
}

export function FloatBadge({ days }: { days: number | null | undefined }) {
  return <span className={floatClass(days)}>{fmtDays(days)}</span>;
}
