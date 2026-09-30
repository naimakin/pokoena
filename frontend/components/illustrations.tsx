// Empty-state line drawings (120×80). Neutral only: the ink ramp and surfaces via
// the .illo classes in globals.css, one --text-secondary stroke marking the thing
// to act on. The accent stays on the call to action below the drawing.
// Rule: at most one illustration per screen, never in table rows or "Loading…".

const svg = { className: "illo", viewBox: "0 0 120 80", "aria-hidden": true, focusable: "false" } as const;

/** A blank drawing sheet — "No project yet". */
export const NoProjectIllo = () => (
  <svg {...svg}>
    <rect className="recess" x="25" y="12" width="80" height="62" rx="3" />
    <rect className="paper" x="20" y="7" width="80" height="62" rx="3" />
    <rect className="hair" x="25" y="12" width="70" height="52" rx="1" />
    <path className="hair" d="M70 56H95M70 56V64M82 56V64" />
    <rect className="em dash" x="38" y="22" width="26" height="24" rx="2" />
    <path className="em" d="M51 29V39M46 34H56" />
  </svg>
);

/** A .xer sheet with an upload badge — "No schedule imported yet". */
export const UploadScheduleIllo = () => (
  <svg {...svg}>
    <path className="hair" d="M24 72H96" />
    <path className="paper" d="M44 6h24l10 10v38a2 2 0 0 1-2 2H44a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z" />
    <path d="M68 6v8a2 2 0 0 0 2 2h8" />
    <path className="bar" d="M48 24h14M56 31h12M52 38h10" />
    <path className="em-fill" d="M69 34.5l3.5 3.5-3.5 3.5-3.5-3.5Z" />
    <text x="48" y="50">.xer</text>
    <circle className="paper em" cx="80" cy="58" r="9" />
    <path className="em" d="M80 62.5V53.5M76.5 57 80 53.5 83.5 57" />
  </svg>
);

/** Bars over dashed, missing baseline bars, with a lock — "No baseline yet". */
export const NoBaselineIllo = () => (
  <svg {...svg}>
    <rect className="paper" x="16" y="8" width="84" height="58" rx="4" />
    <path className="hair" d="M16 18H100M38 18V66M60 18V66M82 18V66" />
    <path className="bar" d="M24 28h22M42 40h26M62 52h22" />
    <path className="dash" d="M24 33.5h22M42 45.5h26M62 57.5h22" />
    <circle className="paper em" cx="98" cy="62" r="10" />
    <rect className="em" x="93.5" y="61" width="9" height="7" rx="1.5" />
    <path className="em" d="M95.5 61v-2.5a2.5 2.5 0 0 1 5 0V61" />
  </svg>
);

/** Construction-line bars and a 45° set square — planned pages. */
export const DraftingIllo = () => (
  <svg {...svg}>
    <rect className="paper" x="14" y="6" width="74" height="62" rx="3" />
    <path className="hair" d="M14 16H88" />
    <path className="dash" d="M22 26h24M34 36h28M48 46h22M40 56h24" />
    <path className="hair" d="M46 26v10M62 36v10" />
    <path className="paper em" d="M70 72H106L70 36Z" />
    <path className="em" d="M77 65H89L77 53Z" />
    <path className="hair" d="M76 72v-3M82 72v-3M88 72v-3M94 72v-3M100 72v-3" />
  </svg>
);
