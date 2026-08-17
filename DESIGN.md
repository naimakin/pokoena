---
version: "1.0"
name: Poko
description: "A warm-light project management dashboard built around #f7f5f1 (cream/parchment canvas), #0F1A2A (deep navy ink), and #f59e0b (amber-500) as the single chromatic accent. The system reads as a precision scheduling tool for construction and infrastructure professionals: structured, data-dense, trustworthy, and quietly refined. Display type is Barlow Condensed (weight 600–700) for headers and column labels — compressed, industrial, authoritative. Body copy uses Outfit (Aptos is not an open/Google font, so Outfit — the documented fallback — is the primary body face here). Monospace data cells use Space Mono. Tables and activity rows carry amber left-border highlights on selection/hover. Critical path rows glow with #C0130A at 6–10% opacity. The amber accent appears on primary CTAs, selected rows, and data date markers — never decoratively. Float health is communicated through a five-step semantic color ramp from red (zero float) through green (high float)."

colors:
  primary: "#f59e0b"
  on-primary: "#ffffff"
  primary-hover: "#d97706"
  primary-focus: "#b45309"
  primary-muted: "rgba(245,158,11,0.10)"
  primary-subtle: "rgba(245,158,11,0.04)"
  ink: "#0F1A2A"
  ink-muted: "#44403c"
  ink-subtle: "#78716c"
  ink-tertiary: "#a8a29e"
  canvas: "#f7f5f1"
  surface-1: "#ffffff"
  surface-2: "#fafaf9"
  surface-3: "#f5f5f4"
  surface-4: "#e7e5e4"
  hairline: "#d6d3d1"
  hairline-strong: "#a8a29e"
  critical: "#C0130A"
  critical-muted: "rgba(192,19,10,0.06)"
  critical-hover: "rgba(192,19,10,0.09)"
  cerulean: "#0F6B8A"
  violet: "#6D3FA0"
  float-zero: "#C0130A"
  float-low: "#EA580C"
  float-medium: "#D97706"
  float-adequate: "#65A30D"
  float-high: "#16A34A"
  selection-bg: "rgba(245,158,11,0.20)"
  selection-ink: "#92400e"

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
  radius-sm: 4px
  radius-md: 6px
  radius-lg: 8px
  activity-row-left: "3px solid transparent"
  activity-row-selected: "3px solid #f59e0b"
  activity-row-critical: "3px solid rgba(192,19,10,0.30)"

shadows:
  card: "0 1px 3px rgba(15,26,42,0.08), 0 1px 2px rgba(15,26,42,0.04)"
  dropdown: "0 4px 12px rgba(15,26,42,0.12)"
  modal: "0 8px 24px rgba(15,26,42,0.15)"

animations:
  page-in: "opacity 0 → 1, translateY 4px → 0, duration 200ms ease-out"
  fade-up: "opacity 0 → 1, translateY 6px → 0, duration 300ms ease-out"
  shimmer: "background-position sweep, duration 2s linear infinite"
  saved-flash: "opacity 1 → 0.4 → 1, duration 600ms ease-in-out"
  spin: "rotate 360deg, duration 800ms linear infinite"

patterns:
  activity-table: "virtualized rows, 32px height, amber left border on hover/select, critical rows tinted red at 6% opacity, Space Mono for date/float/duration cells"
  kpi-card: "white surface-1 card, shadow-card, amber accent top border on important metrics, Barlow Condensed stat values"
  sidebar: "canvas background, amber indicator for active nav item, ink-subtle for inactive"
  input: "surface-1 background, hairline border, amber focus ring"
  badge-float: "pill shape, float-* color ramp based on TF value, mono font"

design_principles:
  - "Data density over decoration — tables are the primary canvas"
  - "Amber is earned — only use on interactive state, CTA, or critical data marker"
  - "Barlow Condensed for headings creates professional authority without heaviness"
  - "Warm cream canvas (#f7f5f1) distinguishes from cold-gray SaaS tools"
  - "Float health color ramp is semantic, never decorative — always tied to TF values"
  - "Monospace type in data cells ensures column alignment at 1× screens"
---

# Poko Design System

Poko is a Primavera P6–compatible CPM schedule analyzer for construction and infrastructure projects.
The UI prioritizes schedule data legibility — thousands of activity rows, date columns, float values,
S-curves — over visual flair. Design decisions favor the field professional reviewing a schedule at
70% zoom on a laptop, not a marketing screenshot.

## Brand Voice
Professional, precise, measured. No playful iconography. Amber signals action; red signals risk.
The tool should feel like a precision instrument, not a consumer app.

## Where this lives in the codebase

Unlike the original reference implementation (a Vite/Tailwind desktop app), this project has no
Tailwind config — every token above is implemented as a CSS custom property in
`frontend/app/globals.css` (`:root` for light, `@media (prefers-color-scheme:dark)` for a derived
dark variant this design system doesn't itself define) and consumed by every component through
those variables (`var(--accent)`, `var(--font-display)`, etc.). The three type families are loaded
via `next/font/google` in `frontend/app/layout.tsx`.

## Component Conventions
- All tables use `poko-activity-row` class with amber left-border selection pattern
- Critical path activities: `critical` class modifier → red tint background
- All numeric/date cells: `poko-mono-xs` (Space Mono 10px)
- Section headers: Barlow Condensed, uppercase, 700 weight
- Primary action buttons: amber-500 background, white text, md radius
- Destructive/warning badges: float-* color ramp, not generic red/green
