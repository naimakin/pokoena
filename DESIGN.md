---
version: "1.0"
name: Poko
description: "A warm-light project management dashboard built around #f4f3ee (cream/parchment canvas), #0E1F1D (deep teal-ink), and #0e7c74 (slate teal) as the single chromatic accent. Warm paper, cool ink: the neutral ramp (surfaces, hairlines) is warm parchment/taupe while the ink ramp is a cool teal-slate — the way a set of architectural drawings reads. The system reads as a precision scheduling tool for construction and infrastructure professionals: structured, data-dense, trustworthy, and quietly refined — slate teal reads as control-room/instrument-panel precision rather than the caution-signal register amber carried. Display type is Barlow Condensed (weight 600–700) for headers and column labels — compressed, industrial, authoritative. Body copy uses Outfit (Aptos is not an open/Google font, so Outfit — the documented fallback — is the primary body face here). Monospace data cells use Space Mono with tabular-nums. Tables and nav rows carry a 3px accent left-border marker on selection. Critical path rows glow with #C0130A at 6% opacity behind a red left-border. The accent appears on primary CTAs, selected rows, focus rings, and data date markers — never decoratively. Float health is communicated through a five-step semantic color ramp from red (zero float) through green (high float), temperature-matched to the teal palette but kept visually distinct from the accent itself. Elevation is a four-step soft, low-spread, faintly-warm shadow scale (xs resting / sm raised / md overlay / lg modal). Border radius is a consistent 2px-step scale (4/6/8/10/12 + pill)."

colors:
  # CSS var name in globals.css is given in parentheses.
  primary: "#0e7c74"               # --accent
  on-primary: "#ffffff"            # --accent-contrast (light); #06211d in dark
  primary-hover: "#0a625c"         # --accent-strong (light); #3fc2b5 in dark
  primary-focus: "#084d49"         # --accent-focus (light); #6ed9ce in dark
  primary-muted: "rgba(14,124,116,0.10)"   # --accent-soft (light); 0.16 in dark
  primary-subtle: "rgba(14,124,116,0.05)"  # --accent-subtle (light); 0.08 in dark
  accent-line: "#0e7c74"           # --accent-line — the 3px row/nav selection marker
  ink: "#0E1F1D"                   # --text-primary
  ink-muted: "#3f5350"             # --text-secondary — cool teal-slate
  ink-subtle: "#748580"            # --text-muted — cool slate
  ink-tertiary: "#96a099"          # --text-tertiary — placeholders, faintest labels
  canvas: "#f4f3ee"                # --bg
  surface-1: "#ffffff"             # --surface (raised cards)
  surface-2: "#ebeae3"             # --surface-2 — warm recessed (thead, row hover, panels)
  surface-3: "#dedcd2"             # --surface-3 — warm deeper (tracks, avatars, chips)
  hairline: "#d4d2c6"              # --border — warm soft hairline
  hairline-strong: "#b8b6a8"       # --border-strong — warm divider / input border
  critical: "#C0130A"              # --crit
  critical-muted: "rgba(192,19,10,0.06)"   # --crit-soft
  critical-line: "rgba(192,19,10,0.30)"    # --crit-line — critical-row left-border
  cerulean: "#3B7EA1"              # --info
  float-zero: "#C0130A"
  float-low: "#D9603A"
  float-medium: "#D9A93A"
  float-adequate: "#6FA86B"
  float-high: "#1F8A5C"
  selection-bg: "rgba(14,124,116,0.10)"    # selected data-row tint (--accent-soft)
  selection-ink: "#0a4a45"

  # --- WBS band / status-coloring pass (Execution > Progress, Planning > WBS/Activities/Gantt) ---
  # Two purpose-specific hue families added on top of the palette above, scoped
  # to hierarchy depth and to activity status — kept deliberately distinct from
  # --accent (teal) and from each other so neither is ever mistaken for a status.
  status-active: "#2F6FED"          # --status-active — "In Progress" chip/bar; vivid azure, not --warn (real warnings) or --info (general badges)
  status-active-soft: "rgba(47,111,237,0.12)"  # --status-active-soft (0.18 in dark)
  wbs-ink: "#3D42A6"                # --wbs-ink — "blueprint indigo": base hue for the WBS depth/hierarchy ramp (d1 text/rail); #9BA3F5 in dark
  wbs-ink-deep: "#23276E"           # --wbs-ink-deep — solid fill for the d0 (root) band; #454BC4 in dark
  wbs-ink-contrast: "#F3F3FF"       # --wbs-ink-contrast — text on the solid d0 fill; #F5F5FF in dark
  wbs-soft-1: "rgba(61,66,166,0.15)"   # --wbs-soft-1 — d1 band tint (0.22 in dark)
  wbs-soft-2: "rgba(61,66,166,0.085)"  # --wbs-soft-2 — d2 band tint, also the WBS level chip fill (0.14 in dark)
  wbs-soft-3: "rgba(61,66,166,0.045)"  # --wbs-soft-3 — d3 band tint (0.08 in dark)
  wbs-soft-4: "rgba(61,66,166,0.02)"   # --wbs-soft-4 — d4 (leaf) band tint, nearly paper again (0.035 in dark)
  wbs-line-1: "rgba(61,66,166,0.6)"   # --wbs-line-1 — d1 left-rail marker, put on tr (not td) so multi-cell band rows get one rail, not one per column
  wbs-line-2: "rgba(61,66,166,0.38)"  # --wbs-line-2 — d2 rail
  wbs-line-3: "rgba(61,66,166,0.22)"  # --wbs-line-3 — d3 rail
  wbs-line-4: "rgba(61,66,166,0.12)"  # --wbs-line-4 — d4 rail (faintest tier: same dark-mode multiplier pattern as wbs-soft-1..4)
  wbs-tint-1: "#E4E5F5"             # --wbs-tint-1 — fully OPAQUE equivalent of --wbs-soft-1, for Gantt's sticky/frozen left column (#334E58 in dark)
  wbs-tint-2: "#EFEFF8"             # --wbs-tint-2 — fully OPAQUE equivalent of --wbs-soft-2, same reason (#233C40 in dark)
  crit-row-bg: "rgba(192,19,10,0.14)"  # --crit-row-bg — the tr.critical row wash, deliberately bolder than the 6%-opacity --crit-soft used for chips/buttons elsewhere (0.22 in dark)
  crit-row-line: "#C0130A"          # --crit-row-line — tr.critical's left rail, full-strength (not the 30%-opacity --crit-line used elsewhere) (#F87171 in dark)

typography:
  display-xl:
    fontFamily: Barlow Condensed
    fontSize: 32px
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.5px
    textTransform: uppercase
  display-lg:
    fontFamily: Barlow Condensed
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: -0.3px
    textTransform: uppercase
  display-md:
    fontFamily: Barlow Condensed
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.2px
  headline:
    fontFamily: Outfit, system-ui
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: -0.1px
  body:
    fontFamily: Outfit, system-ui
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: Outfit, system-ui
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: Outfit, system-ui
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0.03em
    textTransform: uppercase
  mono:
    fontFamily: Space Mono, Courier New, monospace
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0.02em
  mono-sm:
    fontFamily: Space Mono, Courier New, monospace
    fontSize: 10px
    fontWeight: 400
    letterSpacing: 0.02em

spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
  3xl: 48px

borders:
  # consistent 2px-step scale — CSS var name in parentheses
  radius-xs: 4px    # (--radius-xs) chips-in-rows, small badges, btn-sm, focus outline
  radius-sm: 6px    # (--radius-sm) buttons, inputs, nav rows, menu items
  radius-md: 8px    # (--radius-md) dropdown menus, banners, modal-diff, toast, segmented
  radius-lg: 10px   # (--radius-lg) cards, activity cards, dropzone
  radius-xl: 12px   # (--radius-xl) modals, subcontractor frame corners
  radius-pill: 999px
  activity-row-left: "3px solid transparent"
  activity-row-selected: "inset 3px 0 0 #0e7c74 (box-shadow) + rgba(14,124,116,0.10) tint"
  activity-row-critical: "inset 3px 0 0 rgba(192,19,10,0.30) (box-shadow) + rgba(192,19,10,0.06) tint"
  nav-active-marker: "3px accent bar, 16px tall, on ::before of .navitem.active"

shadows:
  # soft, low-spread, faintly warm (rgba(31,25,16,x) light / rgba(0,0,0,x) dark)
  xs: "0 1px 2px rgba(31,25,16,0.06)"                                    # (--shadow-xs) resting — cards, topnav, brand mark
  sm: "0 1px 2px rgba(31,25,16,0.05), 0 2px 5px rgba(31,25,16,0.06)"     # (--shadow-sm) raised — segmented active, primary-btn hover
  md: "0 2px 6px rgba(31,25,16,0.07), 0 8px 20px rgba(31,25,16,0.10)"    # (--shadow-md) overlay — dropdowns, sticky sub-footer, login card
  lg: "0 4px 12px rgba(24,19,12,0.10), 0 20px 44px rgba(24,19,12,0.16)"  # (--shadow-lg) modal, toast

canvas-wash: "two faint radial washes on body — warm accent-tinted teal (top-left, ~4%) + cool blue (top-right, ~2.5%) over the solid --bg. Subtle; opaque full-bleed pages sit on top."

motion:
  ease: "cubic-bezier(.2,0,0,1)"   # (--ease)
  dur-1: 120ms                     # (--dur-1) hover/color/border state changes
  dur-2: 170ms                     # (--dur-2) dropzone, larger surface transitions
  note: "all animation + transition globally disabled under prefers-reduced-motion"

animations:
  page-in: "opacity 0 → 1, translateY 4px → 0, duration 200ms ease-out"
  fade-up: "opacity 0 → 1, translateY 6px → 0, duration 300ms ease-out"
  shimmer: "background-position sweep, duration 2s linear infinite"
  saved-flash: "opacity 1 → 0.4 → 1, duration 600ms ease-in-out"
  spin: "rotate 360deg, duration 800ms linear infinite"
  btn-press: "translateY(0.5px) on :active"

patterns:
  activity-table: "virtualized rows, 32px height, warm surface-2 header, row hover → surface-2, selected row → inset 3px accent left-border + accent-soft tint (tr.selected / .row-selected), critical rows → inset 3px red left-border + crit-soft tint (tr.critical), Space Mono tabular-nums for date/float/duration cells"
  kpi-card: "white surface-1 card, shadow-xs at rest, Barlow Condensed stat values with tabular-nums; optional accent top-edge marker via .card.accent-top (inset 0 2px 0 accent) on a headline metric"
  sidebar: "surface background, active nav item → accent-soft fill + accent text + 3px accent ::before marker, ink-subtle for inactive, 120ms color/background transition"
  input: "surface-1 background, hairline-strong border, hover → border ink-subtle, focus → 2px accent outline + 4px accent-soft halo"
  badge-float: "pill shape, float-* color ramp based on TF value, mono font"
  focus-ring: "2px solid accent outline, 2px offset, plus 0 0 0 4px accent-soft halo — consistent across buttons, inputs, links, [tabindex]"
  dashboard-widgets: "user-configurable widget grid (Dashboard menu). Categorical chart series never use free hex — they resolve to --dash-1..4, remapped by a [data-dash-theme] on the page root: 'calm' (info/good/warn/accent), 'high-contrast' (info/crit/accent-strong/ink), 'mono-amber' (accent tints — key name predates the slate-teal accent and is kept as-is since it's a persisted user preference value, not user-facing copy; the modal label reads 'Mono accent'). Theme + which widgets show + their order are chosen in the configure modal and saved per user per project."

design_principles:
  - "Data density over decoration — tables are the primary canvas"
  - "The accent is earned — only use on interactive state, CTA, focus, or critical data marker"
  - "Warm paper, cool ink — parchment/taupe neutral ramp against a teal-slate ink ramp"
  - "Barlow Condensed for headings creates professional authority without heaviness"
  - "Warm cream canvas (#f4f3ee) distinguishes from cold-gray SaaS tools"
  - "Elevation is layered, not outlined — a coherent xs/sm/md/lg soft warm shadow scale"
  - "Float health color ramp is semantic, never decorative — always tied to TF values, and stays visually distinct from the accent"
  - "Monospace type in data cells ensures column alignment at 1× screens"
  - "Micro-interactions are fast (120–170ms) and crisp, and vanish under reduced-motion"
---

# Poko Design System

Poko is a Primavera P6–compatible CPM schedule analyzer for construction and infrastructure projects.
The UI prioritizes schedule data legibility — thousands of activity rows, date columns, float values,
S-curves — over visual flair. Design decisions favor the field professional reviewing a schedule at
70% zoom on a laptop, not a marketing screenshot.

## Brand Voice
Professional, precise, measured. No playful iconography. Slate teal signals action; red signals risk.
The tool should feel like a precision instrument — a control room, not a consumer app.

## Where this lives in the codebase

Unlike the original reference implementation (a Vite/Tailwind desktop app), this project has no
Tailwind config — every token above is implemented as a CSS custom property in
`frontend/app/globals.css` (`:root` for light, `@media (prefers-color-scheme:dark)` for a derived
dark variant this design system doesn't itself define) and consumed by every component through
those variables (`var(--accent)`, `var(--font-display)`, etc.). The three type families are loaded
via `next/font/google` in `frontend/app/layout.tsx`.

## Component Conventions
- Data rows: `tr.selected` / `.row-selected` → inset 3px accent left-border + accent-soft tint;
  `tr.critical` → inset 3px red left-border + crit-soft tint (the signature selection pattern)
- Active nav item: accent-soft fill + accent text + a 3px accent `::before` bar
- All numeric/date cells: `.num` or `.mono` (Space Mono, `font-variant-numeric: tabular-nums`)
- Section headers / display type: Barlow Condensed, weight 700, `letter-spacing: -0.015em`
- Uppercase micro-labels: 0.06–0.11em tracking, weight 500–600, `--text-muted`
- Primary action buttons: `--accent` background, white text, `--radius-sm`, `--shadow-xs` at rest →
  `--shadow-sm` on hover, `--accent-focus` on `:active`
- Destructive/warning badges: float-* color ramp, not generic red/green
- Radius: use the `--radius-*` scale (xs 4 / sm 6 / md 8 / lg 10 / xl 12 / pill), never ad-hoc px
- Elevation: use the `--shadow-*` scale (xs/sm/md/lg), never ad-hoc shadows
- Focus: rely on the global `:focus-visible` rule (accent outline + accent-soft halo) — don't restyle per component
