---
version: "3.0"
name: Poko
description: "A cool-gray project management workspace under an AppDynamics-inspired 'indigo chrome': a deep indigo/violet gradient header (#1e1650 → #3b2a8c) carrying white text and icons, a white left sidebar, a cool light-gray canvas (#f0f2f7), white cards, near-black cool ink (#1c1e2b), and #5b45d6 (indigo/violet) as the single chromatic accent. The owner chose this direction in 2026-10 to differentiate POKO from Foresight's warm-paper look; the discipline underneath is unchanged from v2 — a small, purposeful hue set, hierarchy through tone, weight and size before hue, and an accent that is earned (interactive state, selection, focus, CTAs, plus two sanctioned non-interactive marks: the WBS hierarchy rail and the data-date line). The system reads as a precision scheduling tool for construction and infrastructure professionals: structured, data-dense, calm. Navigation lives in a left sidebar — an accordion of sections (Dashboard, Projects, Programme, Delivery, Risk, Reports, Administration) that collapses to a 56px icon rail with flyouts, and becomes an off-canvas drawer under 900px. Type v3 runs Roboto across display and interface — weight 500 (Medium) for titles and labels, 400 for body, 700 only for emphasis inside dense data — with IBM Plex Mono (tabular-nums) for data cells. Uppercase is not a label device anywhere in the product: sentence case at weight 500 carries hierarchy. Tables and nav rows carry a 3px accent left-border marker on selection. Critical path rows wash with #c9261f at 12% behind a solid red left rail. Status hues are retuned toward AppDynamics' crisp red / golden amber / green, each at least 4.5:1 as text on its own soft tint. Elevation is a four-step soft, low-spread, faintly-cool shadow scale (xs resting / sm raised / md overlay / lg modal). Border radius squares up to a 3/4/6/8/10 + pill scale."

colors:
  # CSS var name in globals.css is given in parentheses. Light value first;
  # the dark value (prefers-color-scheme: dark) follows in the comment.
  primary: "#5b45d6"               # --accent — indigo/violet, the single chromatic accent; #a594ff dark
  on-primary: "#ffffff"            # --accent-contrast; #170f3d dark
  primary-hover: "#4834b8"         # --accent-strong; #bcb0ff dark
  primary-focus: "#35238f"         # --accent-focus; #d6ceff dark
  primary-muted: "rgba(91,69,214,0.10)"    # --accent-soft; rgba(165,148,255,0.18) dark
  primary-subtle: "rgba(91,69,214,0.05)"   # --accent-subtle; rgba(165,148,255,0.09) dark
  accent-line: "#5b45d6"           # --accent-line — the 3px row/nav selection marker; #a594ff dark
  focus: "#5b45d6"                 # --focus — focus ring; #a594ff dark
  ink: "#1c1e2b"                   # --text-primary — cool near-black; #eef0f6 dark
  ink-muted: "#484d61"             # --text-secondary; #b6bacb dark
  ink-subtle: "#656a7e"            # --text-muted (>= 4.5:1 on canvas, surface and surface-2); #8b90a3 dark
  ink-tertiary: "#9a9eb0"          # --text-tertiary — placeholders, faintest labels; #5d6276 dark
  canvas: "#f0f2f7"                # --bg — cool light gray; #12131c dark
  surface-1: "#ffffff"             # --surface (cards, sidebar); #1b1d29 dark
  surface-2: "#f5f6fa"             # --surface-2 — recessed (thead, row hover, panels); #232635 dark
  surface-3: "#e8eaf1"             # --surface-3 — deeper (tracks, chips, avatars); #2d3142 dark
  hairline: "#e0e3eb"              # --border; #343849 dark
  hairline-strong: "#c8ccd8"       # --border-strong — divider / input border; #474c60 dark
  overlay: "rgba(14,12,38,0.52)"   # --overlay — modal + drawer backdrop; rgba(0,0,0,0.6) dark

  # --- chrome (shell only — pages never use these) ---
  chrome-bg-1: "#1e1650"           # --chrome-bg-1 — header gradient start (left); #120d33 dark
  chrome-bg-2: "#3b2a8c"           # --chrome-bg-2 — header gradient end (right); #2a1e68 dark
  chrome-text: "#ffffff"           # --chrome-text — header text/icons
  chrome-text-muted: "rgba(255,255,255,0.74)"  # --chrome-text-muted — role line, sign-out icon
  chrome-hover: "rgba(255,255,255,0.10)"       # --chrome-hover — hamburger / sign-out hover plate
  chrome-active: "rgba(255,255,255,0.18)"      # --chrome-active — avatar fill, switcher hover
  chrome-control: "rgba(255,255,255,0.10)"     # --chrome-control — project switcher fill on the bar
  chrome-border: "rgba(255,255,255,0.22)"      # --chrome-border — project switcher border on the bar
  chrome-focus: "#ffffff"          # --chrome-focus — focus ring on the bar (the indigo ring would vanish there)
  chrome-mark-bg: "#ffffff"        # --chrome-mark-bg — brand tile on the bar (inverted)
  chrome-mark-fg: "#3b2a8c"        # --chrome-mark-fg — brand glyph on the bar; #2a1e68 dark
  sidebar-bg: "#ffffff"            # --sidebar-bg; #171925 dark
  sidebar-border: "var(--border)"  # --sidebar-border
  sidebar-hover: "var(--surface-2)" # --sidebar-hover
  sidebar-text: "var(--text-secondary)"  # --sidebar-text
  sidebar-icon: "var(--text-muted)"      # --sidebar-icon

  # --- semantic status (text-safe: each >= 4.5:1 on its -soft tint over white) ---
  good: "#16793b"                  # --good; #4cc777 dark
  good-soft: "rgba(22,121,59,0.10)"        # --good-soft; 0.15 dark
  warn: "#8f6100"                  # --warn — golden amber, as bright as AA text allows; #e8b339 dark
  warn-soft: "rgba(143,97,0,0.11)"         # --warn-soft; 0.15 dark
  critical: "#c9261f"              # --crit — crisp red; #ff6b61 dark
  critical-muted: "rgba(201,38,31,0.07)"   # --crit-soft; 0.15 dark
  critical-line: "rgba(201,38,31,0.32)"    # --crit-line — critical-row left-border elsewhere; 0.38 dark
  info: "#3d6a8f"                  # --info — steel blue, the quiet member of the cerulean family; #80a9cc dark
  info-soft: "rgba(61,106,143,0.10)"       # --info-soft; 0.15 dark
  status-active: "#0b67b0"         # --status-active — "In Progress" chip/bar, the saturated cerulean; #5cb3f0 dark
  status-active-soft: "rgba(11,103,176,0.12)"  # --status-active-soft; 0.18 dark
  float-zero: "#c9261f"            # = --crit; #ff6b61 dark
  float-low: "#b04a14"             # burnt orange; #f08a4b dark
  float-medium: "#8f6100"          # = --warn; #e8b339 dark
  float-adequate: "#557315"        # olive; #a8c85a dark
  float-high: "#16793b"            # = --good; #4cc777 dark
  selection-bg: "rgba(91,69,214,0.10)"     # selected data-row tint (--accent-soft)
  selection-ink: "#35238f"
  crit-row-bg: "rgba(201,38,31,0.12)"  # --crit-row-bg — tr.critical wash, bolder than --crit-soft; 0.20 dark
  crit-row-line: "#c9261f"         # --crit-row-line — tr.critical's solid left rail; #ff6b61 dark

  # --- chart series (charts reference these, never a status hue directly) ---
  series-planned: "var(--info)"      # --series-planned — PV / planned %
  series-actual: "var(--good)"       # --series-actual — EV / actual %
  series-forecast: "var(--good)"     # --series-forecast — drawn dashed: it continues the actual line
  series-cost: "var(--text-secondary)"  # --series-cost — AC (was the accent in v2; data series don't spend the accent)
  series-baseline: "var(--text-tertiary)"  # --series-baseline — Gantt baseline bar
  chart-grid: "var(--border)"        # --chart-grid — thin solid gridlines
  chart-axis: "var(--border-strong)" # --chart-axis — baselines, ticks
  chart-datadate: "var(--accent)"    # --chart-datadate — the data-date line (sanctioned accent use)

  # --- WBS band ramp (Execution > Progress, Planning > WBS/Activities/Gantt) ---
  # Neutral cool-graphite tone steps; the only colour is the accent rail.
  wbs-ink: "#474d63"                 # --wbs-ink — d1 text/chip; #b6bccc dark
  wbs-ink-deep: "#23263a"            # --wbs-ink-deep — solid d0 band; #363b52 dark
  wbs-ink-contrast: "#f5f6fa"        # --wbs-ink-contrast — text on the d0 band
  wbs-soft-1: "rgba(71,77,99,0.10)"    # --wbs-soft-1 — d1 tint (0.14 dark)
  wbs-soft-2: "rgba(71,77,99,0.06)"    # --wbs-soft-2 — d2 tint + level chip (0.09 dark)
  wbs-soft-3: "rgba(71,77,99,0.035)"   # --wbs-soft-3 — d3 tint (0.05 dark)
  wbs-soft-4: "rgba(71,77,99,0.018)"   # --wbs-soft-4 — d4 tint (0.025 dark)
  wbs-line-1: "rgba(91,69,214,0.55)"   # --wbs-line-1 — d1 rail: the accent at low opacity (on tr, not td)
  wbs-line-2: "rgba(91,69,214,0.34)"   # --wbs-line-2
  wbs-line-3: "rgba(91,69,214,0.20)"   # --wbs-line-3
  wbs-line-4: "rgba(91,69,214,0.11)"   # --wbs-line-4
  wbs-tint-1: "#ededef"             # --wbs-tint-1 — OPAQUE --wbs-soft-1 for Gantt's frozen column (#313340 dark)
  wbs-tint-2: "#f4f4f6"             # --wbs-tint-2 — OPAQUE --wbs-soft-2 (#292b38 dark)

typography:
  # Type v3: Roboto (static 300/400/500/700 via next/font) across display and
  # interface; IBM Plex Mono for data cells. Weight separates the roles —
  # 500 for display/titles/labels, 400 for body, 700 only for emphasis in
  # dense data. Roboto has no 600: anything specified 600 renders as Bold, so
  # the codebase uses 500 for labels. No uppercase label device anywhere.
  display-xl:
    fontFamily: Roboto
    fontSize: 32px
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: -0.01em
  display-lg:
    fontFamily: Roboto
    fontSize: 24px
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: -0.01em
  display-md:
    fontFamily: Roboto
    fontSize: 18px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: -0.01em
  card-title:
    fontFamily: Roboto
    fontSize: 15px
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: -0.01em
  headline:
    fontFamily: Roboto, system-ui
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.4
  body:
    fontFamily: Roboto, system-ui
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: Roboto, system-ui
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: Roboto, system-ui
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0
  mono:
    fontFamily: IBM Plex Mono, Consolas, monospace
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0
  mono-sm:
    fontFamily: IBM Plex Mono, Consolas, monospace
    fontSize: 11px
    fontWeight: 400
    letterSpacing: 0

spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
  3xl: 48px

layout:
  header-h: 56px          # --header-h — sticky indigo header
  sidebar-w: 240px        # --sidebar-w — expanded sidebar
  sidebar-rail-w: 56px    # --sidebar-rail-w — collapsed icon rail
  drawer-breakpoint: 900px  # at or below: the sidebar is an off-canvas drawer

borders:
  # v3 squares up — CSS var name in parentheses
  radius-xs: 3px    # (--radius-xs) chips-in-rows, small badges, btn-sm, focus outline
  radius-sm: 4px    # (--radius-sm) buttons, inputs, nav rows, menu items
  radius-md: 6px    # (--radius-md) dropdown menus, flyouts, banners, toast, segmented
  radius-lg: 8px    # (--radius-lg) cards, activity cards, dropzone
  radius-xl: 10px   # (--radius-xl) modals, subcontractor frame corners
  radius-pill: 999px
  activity-row-left: "3px solid transparent"
  activity-row-selected: "inset 3px 0 0 #5b45d6 (box-shadow) + rgba(91,69,214,0.10) tint"
  activity-row-critical: "inset 3px 0 0 #c9261f (box-shadow) + rgba(201,38,31,0.12) tint"
  nav-active-marker: "3px accent bar, 18px tall, on ::before of the active sidebar row (.sidenav-row.is-active / .sidenav-child.is-active)"

shadows:
  # soft, low-spread, faintly cool (rgba(22,24,48,x) light / rgba(0,0,0,x) dark)
  xs: "0 1px 2px rgba(22,24,48,0.06)"                                    # (--shadow-xs) resting — cards, brand mark
  sm: "0 1px 2px rgba(22,24,48,0.06), 0 2px 6px rgba(22,24,48,0.07)"     # (--shadow-sm) raised — segmented active, primary-btn hover
  md: "0 2px 6px rgba(22,24,48,0.08), 0 8px 24px rgba(22,24,48,0.12)"    # (--shadow-md) overlay — dropdowns, rail flyouts, sticky run bar, login card
  lg: "0 6px 16px rgba(22,24,48,0.12), 0 24px 48px rgba(22,24,48,0.20)"  # (--shadow-lg) modal, toast, open mobile drawer
  chrome: "0 1px 0 rgba(22,16,64,0.10), 0 2px 8px rgba(22,16,64,0.18)"   # (--chrome-shadow) under the header bar

canvas-wash: "none in v3 — a flat cool-gray --bg. The colour lives in the header chrome, so the working area stays quiet. (v2 painted two faint radial washes on body.)"

motion:
  ease: "cubic-bezier(.2,0,0,1)"   # (--ease)
  dur-1: 120ms                     # (--dur-1) hover/color/border state changes
  dur-2: 170ms                     # (--dur-2) sidebar width, drawer slide, flyout, dropzone
  note: "all animation + transition globally disabled under prefers-reduced-motion"

animations:
  page-in: "opacity 0 → 1, duration 200ms ease-out"
  fade-up: "opacity 0 → 1, translateY 6px → 0, duration 300ms ease-out"
  flyout-in: "opacity 0 → 1, translateX -4px → 0, duration 170ms"
  shimmer: "background-position sweep, duration 2s linear infinite"
  saved-flash: "opacity 1 → 0.4 → 1, duration 600ms ease-in-out"
  spin: "rotate 360deg, duration 800ms linear infinite"
  btn-press: "translateY(0.5px) on :active"

patterns:
  shell: "sticky header (indigo gradient, --header-h) over a row of sidebar + main. Header: hamburger (toggles expanded/collapsed on desktop, opens/closes the drawer below 900px), brand tile inverted (white tile, indigo glyph), project switcher in chrome tokens, avatar + name/role + sign-out. The document scrolls; header and sidebar stay put (html gets scroll-padding-top so scrollIntoView clears the header)."
  sidebar: "white --sidebar-bg, 240px. Sections are accordion rows (icon, label, chevron; 40px tall, weight 500); several may be open; the one holding the current page opens itself and its row turns ink with an accent icon (.is-current). Children are indented 32px rows, weight 400; the active page gets accent-soft fill + accent-strong text + a 3px accent ::before bar. Dashboard (no children) is a plain row with the same active treatment."
  sidebar-rail: "collapsed state (desktop only), 56px, remembered per viewer in localStorage (key poko:sidebar; set on <html data-sidebar> by an inline script before first paint). Icons only, native title tooltip, aria-label kept. The section holding the current page gets the accent-soft fill + bar. A section icon opens a flyout to the right (surface card, shadow-md, title + child links) — closes on outside click, Escape (focus returns to the icon), Tab, or route change; arrow keys move between links."
  sidebar-drawer: "below 900px: fixed under the header, min(300px, 86vw) wide, slides in over the page with an --overlay backdrop; always the expanded form; closes on navigation, backdrop click and Escape; visibility:hidden while closed keeps it out of the tab order."
  activity-table: "virtualized rows, 32px height, surface-2 header, row hover → surface-2, selected row → inset 3px accent left-border + accent-soft tint (tr.selected / .row-selected), critical rows → inset 3px red left-border + crit-row-bg wash (tr.critical), IBM Plex Mono tabular-nums for date/float/duration cells"
  card: "white surface, 1px --border hairline, --radius-lg, --shadow-xs. Header row: title (Roboto 500, 15px) with an optional muted count beside it (.card-count, weight 400), an optional one-line description below, and on the right either a chip or a chevron link (.card-link — accent text + ChevronRightIcon) where the card leads somewhere."
  kpi-card: "white card, Roboto 500 stat values with tabular-nums; optional accent top-edge marker via .card.accent-top (inset 0 2px 0 accent) on a headline metric"
  charts: "thin solid gridlines (--chart-grid), axes/ticks in --chart-axis, series from --series-* (planned steel blue, actual green, forecast = actual dashed, cost graphite), data-date line in --chart-datadate (the accent). Don't pick status hues for a series directly."
  input: "surface background, hairline-strong border, hover → border ink-subtle, focus → 2px accent outline + 4px accent-soft halo"
  badge-float: "pill shape, float-* color ramp based on TF value, mono font"
  focus-ring: "2px solid --focus outline, 2px offset, plus 0 0 0 4px accent-soft halo — consistent across buttons, inputs, links, [tabindex]. On the header bar the ring is --chrome-focus (white) with no halo."
  dashboard-widgets: "user-configurable widget grid (Dashboard menu). Categorical chart series never use free hex — they resolve to --dash-1..4, remapped by a [data-dash-theme] on the page root: 'calm' (info/good/warn/accent), 'high-contrast' (info/crit/accent-strong/ink), 'mono-amber' (accent tints — the key name predates both the blueprint-blue and the indigo accent and is kept as-is since it's a persisted user preference value, not user-facing copy; the modal label reads 'Mono accent'). All three still hold in v3: calm is steel blue / green / golden amber / indigo, four distinct hues; mono-amber is three indigo depths plus muted ink. Theme + which widgets show + their order are chosen in the configure modal and saved per user per project."

design_principles:
  - "Data density over decoration — tables are the primary canvas"
  - "The accent is earned — spent on interactive state, selection, CTA and focus, plus two sanctioned non-interactive marks: the WBS hierarchy rail and the data-date line"
  - "Colour lives in the chrome, not the canvas — the indigo header frames a quiet cool-gray working area with white cards"
  - "One family (Roboto) for display and interface — weight (500 vs 400) separates the roles, so the UI reads as a single calm surface"
  - "Uppercase is not a label device — sentence case at weight 500 carries hierarchy"
  - "Elevation is layered, not outlined — a coherent xs/sm/md/lg soft cool shadow scale over hairline borders"
  - "Status colour is text-safe — every status hue clears 4.5:1 on its own soft tint, in light and dark"
  - "Float health color ramp is semantic, never decorative — always tied to TF values, and stays visually distinct from the accent"
  - "A small, purposeful chromatic set — accent indigo, good green, warn golden amber, crit red, and one cerulean family at two depths for info / in-progress — hierarchy and state read through shade, weight and size before a new hue is ever reached for"
  - "WBS depth is a neutral graphite tone/weight/size ramp, not its own hue family — the tree shouldn't compete with the app's one real accent for attention"
  - "Monospace type in data cells ensures column alignment at 1× screens"
  - "Micro-interactions are fast (120–170ms) and crisp, and vanish under reduced-motion"
---

# Poko Design System

Poko is a Primavera P6–compatible CPM schedule analyzer for construction and infrastructure projects.
The UI prioritizes schedule data legibility — thousands of activity rows, date columns, float values,
S-curves — over visual flair. Design decisions favor the field professional reviewing a schedule at
70% zoom on a laptop, not a marketing screenshot.

## Brand Voice
Professional, precise, measured. No playful iconography. Indigo signals action; red signals risk;
the cerulean family (--info / --status-active) marks quiet, informational or in-progress state. The
tool should feel like a precision instrument — a control room, not a consumer app.

## Color System v3 — indigo chrome (2026-10)

**Why.** The owner chose an AppDynamics-inspired direction to differentiate POKO from Foresight,
whose warm-paper look v2 sat too close to. v3 changes the *materials*, not the discipline: the
v2 rules — a small, purposeful hue set; hierarchy through tone, weight and size before hue; an
accent that is earned — all still hold.

**Where the colour lives.** In the chrome, not the canvas:

- **Header bar** — a deep indigo → violet gradient (`--chrome-bg-1` `#1e1650` → `--chrome-bg-2`
  `#3b2a8c`, left to right) with white text and icons (`--chrome-text`, `--chrome-text-muted`).
  Controls on the bar use translucent white plates (`--chrome-hover`, `--chrome-active`,
  `--chrome-control`, `--chrome-border`); the focus ring there is `--chrome-focus` (white) because
  the indigo ring would vanish on indigo. The brand tile inverts (`--chrome-mark-bg` white,
  `--chrome-mark-fg` indigo glyph).
- **Sidebar** — white (`--sidebar-bg`) with a hairline right border; rows in `--sidebar-text`,
  icons in `--sidebar-icon`, hover `--sidebar-hover`.
- **Canvas** — a flat cool light gray (`--bg` `#f0f2f7`); v2's radial corner washes are gone.
- **Cards** — white (`--surface`) with a hairline border and the `--shadow-xs` rest shadow.

**The accent** moves from blueprint blue (`#2e5aac`) to **indigo/violet** (`--accent` `#5b45d6`,
6.4:1 on white; `#a594ff` in dark). Same job as before: interactive state, selection (the 3px
accent bar on the active nav row and on selected table rows), focus, CTAs, links, and the two
sanctioned non-interactive marks — the WBS rail (`--wbs-line-*`) and the data-date line
(`--chart-datadate`). It is not a chart series colour: the S-curve's Actual Cost line, which used
the accent in v2, now uses `--series-cost` (graphite).

**Status hues** are retuned toward AppDynamics' health colours — crisp red, golden amber, clean
green — under one hard constraint: every status colour must stay **WCAG AA as text on its own
`-soft` tint** (these tokens are used for chip text, not only fills). That caps how bright amber can
go in light mode (`--warn` `#8f6100`, an ochre-gold; it is a true golden `#e8b339` in dark mode where
the constraint runs the other way). Measured over white:

| token | light | on its tint | dark | on its tint (over --surface) |
|---|---|---|---|---|
| `--crit` | `#c9261f` | 4.98:1 | `#ff6b61` | 4.83:1 |
| `--warn` | `#8f6100` | 4.68:1 | `#e8b339` | 6.41:1 |
| `--good` | `#16793b` | 4.78:1 | `#4cc777` | 5.85:1 |
| `--info` | `#3d6a8f` | 5.01:1 | `#80a9cc` | 5.19:1 |
| `--status-active` | `#0b67b0` | 4.94:1 | `#5cb3f0` | 5.21:1 |
| `--accent` | `#5b45d6` | 5.53:1 | `#a594ff` | 4.82:1 |

**Info / in-progress** is now one **cerulean family at two depths** (v2 did the same with the
demoted brand teal): `--status-active` `#0b67b0` (saturated) for "In Progress" chips and bars,
`--info` `#3d6a8f` (steel, grayer) for neutral badges, the Gantt "Normal" bar, low-severity risk
markers and the planned series. Teal would have sat too close to green in the charts.

**Float ramp** stays five steps and stays coherent with the status ends: `--float-zero` = `--crit`,
`--float-medium` = `--warn`, `--float-high` = `--good`, with `--float-low` a burnt orange
(`#b04a14`) and `--float-adequate` an olive (`#557315`) between them — the hue walks red → orange →
gold → olive → green, each step AA on its tint.

**Neutrals** go from warm paper/taupe to cool gray (`--surface-2` `#f5f6fa`, `--surface-3`
`#e8eaf1`, `--border` `#e0e3eb`, `--border-strong` `#c8ccd8`), and the ink ramp from neutral graphite
to a cool near-black (`--text-primary` `#1c1e2b` … `--text-tertiary` `#9a9eb0`). `--text-muted`
(`#656a7e`) clears 4.5:1 on white, `--surface-2` and the canvas.

**WBS ramp** keeps its v2 shape — a solid deep d0 band, decreasing washes to d4, and the accent rail
as its only colour — re-based on the cool graphite (`--wbs-ink` `#474d63`, `--wbs-ink-deep`
`#23263a`) with the rail in the new indigo. `--wbs-tint-1/-2` are re-blended opaque equivalents.

**Chart tokens (new).** Charts reference `--series-planned` (info), `--series-actual` (good),
`--series-forecast` (good, drawn dashed — it continues the actual), `--series-cost` (graphite),
`--series-baseline`, `--chart-grid` (thin *solid* gridlines — v3 drops the dotted ones),
`--chart-axis` and `--chart-datadate`, so a palette change is a token change.

**Shape and depth.** Radii square up (3/4/6/8/10 + pill) and shadows turn faintly cool — AppDynamics'
cards are near-square and quiet. `--overlay` is the one backdrop colour (modals, mobile drawer).

**Dashboard themes** (`[data-dash-theme]`) needed no remap: `calm` resolves to steel blue / green /
golden amber / indigo — four distinct hues — and `mono-amber` to three indigo depths plus muted ink.

## Type System v3 — Roboto

v3 replaces Figtree with **Roboto** for display *and* interface (loaded through `next/font/google`
as `--font-roboto`, wired into `--font-display` / `--font-ui`), and keeps **IBM Plex Mono** for data
cells (`.num` / `.mono`).

- **Why Roboto.** It is a neutral, engineered grotesque that sits quietly under a coloured header
  instead of competing with it — the AppDynamics register — and it holds up at the 11–12px sizes the
  tables live at. Figtree's rounder, friendlier voice belonged to the warm-paper system.
- **Weights.** Roboto is served static (300 / 400 / 500 / 700). `--display-weight` drops from 800 to
  **500** (Medium): Roboto at 700–800 is heavy, and AppDynamics headings run ~400–500 even at large
  sizes. Card titles, page titles, modal titles and big KPI numerals all use `var(--display-weight)`.
  **Labels move from 600 to 500** — Roboto has no 600, and a 600 request renders as Bold, which
  turned every label, button and table header heavier than intended. 700 is kept for emphasis inside
  dense data (chips, badges, a few strong cells). Body stays 400.
- **Tracking.** `--display-tracking` relaxes from -0.022em to **-0.01em**; Roboto is already
  tight-set and doesn't need Figtree's display squeeze.
- **Unchanged rule:** no `text-transform: uppercase` as a label device — sentence case, now at 500.

## Color System v2 — rationale *(superseded by Color System v3, 2026-10)*

> Kept for its reasoning, which v3 still follows. The hex values below are historical — the live
> tokens are in the YAML above and in `frontend/app/globals.css`.

The v1 palette (teal accent + a bespoke "blueprint indigo" WBS hue + azure "in progress" + cerulean
info, on top of the usual green/amber/red) spent seven distinct chromatic hues. That's more than a
restrained system needs, and it meant hierarchy (WBS depth) and state (activity status) were both
competing for attention against the interactive accent. v2 narrows this to five deliberate hues:

- **Accent — blueprint blue (`--accent`)**: the only interactive/CTA color. Buttons, links, the
  focus ring, selection markers, the data-date line in the Gantt, and — its one sanctioned
  non-interactive use — the WBS hierarchy rail (`--wbs-line-*`), a thin low-opacity marker that ties
  the tree back to the app's single accent without ever using it as a fill.
- **Good / Warn / Crit (green / amber / red)**: unchanged in role, retuned slightly for contrast
  against the new neutral ramp.
- **Info / Status-active (the demoted brand teal)**: the *former* accent (`#0e7c74`) stepped back
  from "the one CTA color" to a quieter, two-depth semantic role — `--status-active` (solid) for
  "In Progress" chips/bars, `--info` (grayer, quieter) for general/neutral badges, the Gantt's
  "Normal" bar color, and low-severity risk markers. Reusing one hue at two depths for two closely
  related meanings, instead of inventing a second unrelated hue, is the same "materials over
  saturation" move applied everywhere else in v2.

The **WBS depth ramp** — previously its own indigo hue family (`--wbs-ink*`) — is the biggest
change: it's now a **neutral graphite tone/weight/size ramp** (see `colors.wbs-*` above), matching
how the rest of the system already communicates hierarchy (typography weight, indentation, shade)
rather than reaching for a new hue just because the data is tree-shaped. d0 (root) is a solid dark
graphite band; d1–d4 taper through decreasing neutral-gray washes down to near-paper at the leaf —
the same taper shape as v1, just desaturated. The only color left in the ramp is the accent-blue
rail (`--wbs-line-*`), a deliberate, restrained "blueprint" wayfinding touch, not a fill.

## Type System v2 — rationale *(superseded by Type System v3 — Roboto, 2026-10)*

> Kept for its reasoning (one family across both roles; uppercase retired as a label device), which
> v3 still follows with Roboto in place of Figtree.

The original trio — Barlow Condensed for display, Outfit for body, Space Mono for data — read as
machinery rather than as an instrument. Barlow Condensed is a compressed industrial grotesque built
for signage; Space Mono puts a typewriter quirk on every date and float value. On top of that,
all-caps with wide tracking was doing label duty in roughly thirty places (CSS rules plus inline
styles), and uppercase tracking is the single strongest "technical readout" signal in a UI. For a
tool people sit in front of all day, that added up to cold, not precise.

v2 replaces all three with **Figtree** (variable, 300–900) for display *and* interface, plus
**IBM Plex Mono** for data cells:

- **One family across both roles.** Weight (`--display-weight`, 800) and tracking
  (`--display-tracking`, -0.022em) separate a heading from body text, rather than a second typeface.
  A single family is what makes a dense screen read as one calm surface; two families make it read
  as assembled parts.
- **Figtree over a neutral grotesque.** Rounder bowls and softer terminals take the hardness out
  without tipping into decorative, and it holds up at the 11–12px sizes this product's tables live at.
- **IBM Plex Mono over Space Mono.** Plex is drawn for numeric legibility in tables; Space Mono's
  character is charming in isolation and noisy across 2,000 rows of dates.
- **Uppercase retired as a label device.** Every label, table header, chip and WBS band name is now
  sentence case at weight 600 with zero tracking, typically one step larger, since sentence case at
  the same pixel size reads smaller than caps did. The only survivors are the two tiny "Soon" status
  badges, where caps is conventional and the string is three letters long.

## Where this lives in the codebase

Unlike the original reference implementation (a Vite/Tailwind desktop app), this project has no
Tailwind config — every token above is implemented as a CSS custom property in
`frontend/app/globals.css` (`:root` for light, `@media (prefers-color-scheme:dark)` for the dark
variant) and consumed by every component through those variables (`var(--accent)`,
`var(--font-display)`, etc.). Roboto and IBM Plex Mono are loaded via `next/font/google` in
`frontend/app/layout.tsx` (the favicon and browser `theme-color` there repeat a few token hexes and
must be kept in sync by hand). The company shell is `frontend/app/(tenant)/(company)/layout.tsx`
(header, sidebar state, drawer) plus `frontend/components/SideNav.tsx` (accordion, rail, flyout);
the subcontractor shell and the platform-admin console pick up the same tokens and font without the
company sidebar.

## Component Conventions
- Data rows: `tr.selected` / `.row-selected` → inset 3px accent left-border + accent-soft tint;
  `tr.critical` → inset 3px red left-border + crit-row-bg wash (the signature selection pattern)
- Active nav item: accent-soft fill + accent-strong text + a 3px accent `::before` bar
  (`.sidenav-row.is-active`, `.sidenav-child.is-active`; in the rail, the current section's icon)
- All numeric/date cells: `.num` or `.mono` (IBM Plex Mono, `font-variant-numeric: tabular-nums`)
- Section headers / display type: Roboto, `var(--display-weight)` (500), `var(--display-tracking)` (-0.01em)
- Labels: sentence case, weight 500, `--text-muted` or `--text-secondary` — never uppercase
- Card header: `.card-title` (+ optional `.card-count`), `.card-title-sub`, and on the right a chip
  or a `.card-link` chevron link
- Charts: series from `--series-*`, gridlines `--chart-grid`, axes `--chart-axis`, data date
  `--chart-datadate`
- Primary action buttons: `--accent` background, white text, `--radius-sm`, `--shadow-xs` at rest →
  `--shadow-sm` on hover, `--accent-focus` on `:active`
- Destructive/warning badges: float-* color ramp, not generic red/green. Implemented as
  `--float-zero` … `--float-high` (plus a `-soft` tint for each) with the `.float-badge` class;
  pick the step with `floatClass()` in `components/reporting/format.tsx`, which bands on total
  float in days at 0 / 5 / 15 / 30. `--float-zero` shares `--crit`'s value so a zero-float badge
  and a critical row agree.
- Radius: use the `--radius-*` scale (xs 3 / sm 4 / md 6 / lg 8 / xl 10 / pill), never ad-hoc px
- Elevation: use the `--shadow-*` scale (xs/sm/md/lg), never ad-hoc shadows
- Focus: rely on the global `:focus-visible` rule (accent outline + accent-soft halo) — don't restyle
  per component (the header bar's white ring is the one shell-level exception)
- Chrome tokens (`--chrome-*`, `--sidebar-*`) are for the shell only; pages never use them
