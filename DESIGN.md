---
version: "2.0"
name: Poko
description: "A warm-paper project management dashboard built around #f7f6f1 (paper canvas), #1d2024 (neutral graphite ink), and #2e5aac (blueprint blue) as the single chromatic accent. Warm paper, cool graphite ink: the neutral ramp (surfaces, hairlines) is warm paper/taupe while the ink ramp is true neutral graphite — the way a set of architectural drawings reads, without tinting the ink toward any one status hue. The system reads as a precision scheduling tool for construction and infrastructure professionals: structured, data-dense, trustworthy, and quietly refined — restrained the way a well-made instrument panel is, not decorated. Display type is Barlow Condensed (weight 600–700) for headers and column labels — compressed, industrial, authoritative. Body copy uses Outfit (Aptos is not an open/Google font, so Outfit — the documented fallback — is the primary body face here). Monospace data cells use Space Mono with tabular-nums. Tables and nav rows carry a 3px accent left-border marker on selection. Critical path rows glow with #c21f13 at 6% opacity behind a red left-border. The accent appears on primary CTAs, selected rows, focus rings, data date markers, and — its one sanctioned non-interactive use — the WBS hierarchy rail; never decoratively beyond that. v2 narrowed the palette from seven chromatic hues down to five deliberate ones: blueprint blue (accent), green/amber/red (good/warn/crit), and the original brand teal demoted from 'the accent' to a quieter informational/in-progress role. The WBS depth ramp, previously its own bespoke 'blueprint indigo' hue family, is now a neutral graphite tone/weight/size ramp instead — hierarchy communicated by shade and typography, the way the rest of the system already does it, not by adding a sixth hue. Elevation is a four-step soft, low-spread, faintly-warm shadow scale (xs resting / sm raised / md overlay / lg modal). Border radius is a consistent 2px-step scale (4/6/8/10/12 + pill)."

colors:
  # CSS var name in globals.css is given in parentheses.
  primary: "#2e5aac"               # --accent — "blueprint blue", the single chromatic accent
  on-primary: "#ffffff"            # --accent-contrast (light); #0b1b3b in dark
  primary-hover: "#24488a"         # --accent-strong (light); #8fb3ff in dark
  primary-focus: "#1b3568"         # --accent-focus (light); #b7ccff in dark
  primary-muted: "rgba(46,90,172,0.10)"    # --accent-soft (light); 0.18 in dark
  primary-subtle: "rgba(46,90,172,0.05)"   # --accent-subtle (light); 0.09 in dark
  accent-line: "#2e5aac"           # --accent-line — the 3px row/nav selection marker
  ink: "#1d2024"                   # --text-primary — neutral graphite (no longer teal-tinted)
  ink-muted: "#54585f"             # --text-secondary
  ink-subtle: "#787c84"            # --text-muted
  ink-tertiary: "#a7aab0"          # --text-tertiary — placeholders, faintest labels
  canvas: "#f7f6f1"                # --bg — warm paper
  surface-1: "#ffffff"             # --surface (raised cards)
  surface-2: "#f0efe8"             # --surface-2 — warm recessed (thead, row hover, panels)
  surface-3: "#e4e2d8"             # --surface-3 — warm deeper (tracks, avatars, chips)
  hairline: "#d8d6ca"              # --border — warm soft hairline
  hairline-strong: "#c2bfae"       # --border-strong — warm divider / input border
  critical: "#c21f13"              # --crit
  critical-muted: "rgba(194,31,19,0.06)"   # --crit-soft
  critical-line: "rgba(194,31,19,0.30)"    # --crit-line — critical-row left-border
  info: "#3f6f69"                  # --info — quiet informational hue (the demoted brand teal, pulled grayer); #8fb5ae in dark
  float-zero: "#c21f13"
  float-low: "#c9622f"
  float-medium: "#b5720e"
  float-adequate: "#4a9a6e"
  float-high: "#1f8f5f"
  selection-bg: "rgba(46,90,172,0.10)"     # selected data-row tint (--accent-soft)
  selection-ink: "#1b3568"

  # --- WBS band / status-coloring pass (Execution > Progress, Planning > WBS/Activities/Gantt) ---
  # v2: the WBS depth ramp moved OFF its own bespoke hue and onto the neutral
  # graphite ramp (hierarchy = shade/weight/size, matching how the rest of
  # the system already communicates structure), with --accent (blue) kept as
  # a single, quiet exception for the rail marker only. "In Progress" status
  # now shares the demoted brand-teal family with --info at a bolder depth,
  # instead of a third unrelated hue.
  status-active: "#0e7c74"          # --status-active — "In Progress" chip/bar; the brand teal at full saturation, distinct from --info (same family, quieter) and from --accent (blue)
  status-active-soft: "rgba(14,124,116,0.12)"  # --status-active-soft (0.18 in dark)
  wbs-ink: "#4b5160"                 # --wbs-ink — neutral graphite: base tone for the WBS depth/hierarchy ramp (d1 text/chip); #b9bec9 in dark
  wbs-ink-deep: "#1e2230"            # --wbs-ink-deep — solid fill for the d0 (root) band; #3a4050 in dark
  wbs-ink-contrast: "#f5f6f8"        # --wbs-ink-contrast — text on the solid d0 fill; same in dark
  wbs-soft-1: "rgba(75,81,96,0.10)"    # --wbs-soft-1 — d1 band tint (0.14 in dark)
  wbs-soft-2: "rgba(75,81,96,0.06)"    # --wbs-soft-2 — d2 band tint, also the WBS level chip fill (0.09 in dark)
  wbs-soft-3: "rgba(75,81,96,0.035)"   # --wbs-soft-3 — d3 band tint (0.05 in dark)
  wbs-soft-4: "rgba(75,81,96,0.018)"   # --wbs-soft-4 — d4 (leaf) band tint, nearly paper again (0.025 in dark)
  wbs-line-1: "rgba(46,90,172,0.55)"   # --wbs-line-1 — d1 left-rail marker: the real accent blue at low opacity, NOT the neutral wbs-ink — the one deliberate "blueprint" wayfinding touch. Put on tr (not td) so multi-cell band rows get one rail, not one per column
  wbs-line-2: "rgba(46,90,172,0.34)"  # --wbs-line-2 — d2 rail
  wbs-line-3: "rgba(46,90,172,0.20)"  # --wbs-line-3 — d3 rail
  wbs-line-4: "rgba(46,90,172,0.11)"  # --wbs-line-4 — d4 rail (faintest tier)
  wbs-tint-1: "#edeeef"             # --wbs-tint-1 — fully OPAQUE equivalent of --wbs-soft-1, for Gantt's sticky/frozen left column (#32353d in dark)
  wbs-tint-2: "#f4f5f5"             # --wbs-tint-2 — fully OPAQUE equivalent of --wbs-soft-2, same reason (#2a2d35 in dark)
  crit-row-bg: "rgba(194,31,19,0.14)"  # --crit-row-bg — the tr.critical row wash, deliberately bolder than the 6%-opacity --crit-soft used for chips/buttons elsewhere (0.22 in dark)
  crit-row-line: "#c21f13"          # --crit-row-line — tr.critical's left rail, full-strength (not the 30%-opacity --crit-line used elsewhere) (#f17b6e in dark)

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
  activity-row-selected: "inset 3px 0 0 #2e5aac (box-shadow) + rgba(46,90,172,0.10) tint"
  activity-row-critical: "inset 3px 0 0 rgba(194,31,19,0.30) (box-shadow) + rgba(194,31,19,0.06) tint"
  nav-active-marker: "3px accent bar, 16px tall, on ::before of .navitem.active"

shadows:
  # soft, low-spread, faintly warm (rgba(31,25,16,x) light / rgba(0,0,0,x) dark)
  xs: "0 1px 2px rgba(31,25,16,0.06)"                                    # (--shadow-xs) resting — cards, topnav, brand mark
  sm: "0 1px 2px rgba(31,25,16,0.05), 0 2px 5px rgba(31,25,16,0.06)"     # (--shadow-sm) raised — segmented active, primary-btn hover
  md: "0 2px 6px rgba(31,25,16,0.07), 0 8px 20px rgba(31,25,16,0.10)"    # (--shadow-md) overlay — dropdowns, sticky sub-footer, login card
  lg: "0 4px 12px rgba(24,19,12,0.10), 0 20px 44px rgba(24,19,12,0.16)"  # (--shadow-lg) modal, toast

canvas-wash: "two faint radial washes on body — accent blue (top-left, ~5-7%) + quiet info teal (top-right, ~3.5-5%) over the solid --bg. Subtle; opaque full-bleed pages sit on top."

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
  dashboard-widgets: "user-configurable widget grid (Dashboard menu). Categorical chart series never use free hex — they resolve to --dash-1..4, remapped by a [data-dash-theme] on the page root: 'calm' (info/good/warn/accent), 'high-contrast' (info/crit/accent-strong/ink), 'mono-amber' (accent tints — key name predates the current blueprint-blue accent — the palette has been retuned twice now — and is kept as-is since it's a persisted user preference value, not user-facing copy; the modal label reads 'Mono accent'). Theme + which widgets show + their order are chosen in the configure modal and saved per user per project."

design_principles:
  - "Data density over decoration — tables are the primary canvas"
  - "The accent is earned — spent on interactive state, CTA, focus, and critical data markers, plus one sanctioned non-interactive exception: the WBS hierarchy rail (see below)"
  - "Warm paper, cool ink — parchment/taupe neutral ramp against a true neutral graphite ink ramp (the ink is no longer tinted toward any status hue, so it never competes with the accent or the info/status-active teal)"
  - "Barlow Condensed for headings creates professional authority without heaviness"
  - "Warm paper canvas (#f7f6f1) distinguishes from cold-gray SaaS tools"
  - "Elevation is layered, not outlined — a coherent xs/sm/md/lg soft warm shadow scale"
  - "Float health color ramp is semantic, never decorative — always tied to TF values, and stays visually distinct from the accent"
  - "A small, purposeful chromatic set — five hues total (accent blue, good green, warn amber, crit red, info/status-active teal) — hierarchy and state read through shade, weight and size before a new hue is ever reached for"
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
Professional, precise, measured. No playful iconography. Blueprint blue signals action; red signals
risk; the demoted brand teal (--info / --status-active) marks quiet, informational or in-progress
state. The tool should feel like a precision instrument — a control room, not a consumer app.

## Color System v2 — rationale

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
