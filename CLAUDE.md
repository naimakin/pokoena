# POKO — Claude Agent Instructions

## Design System (REQUIRED — read before any UI work)

**Always read `DESIGN.md`** (project root) before generating or modifying any frontend code. It
contains Poko's complete color tokens, typography, spacing, component patterns, and design
principles — ported from a colleague's reference P6 desktop app and implemented as CSS custom
properties in `frontend/app/globals.css` (this project has no Tailwind).

## Project Stack

- **Frontend:** Next.js (App Router) + TypeScript, plain CSS custom properties (no Tailwind),
  `frontend/app/`
- **Backend:** Python FastAPI, `backend/app/`, multi-tenant Postgres with row-level security
  (RLS) — every tenant-scoped table is isolated per company; see `backend/app/db/session.py`
  and `backend/alembic/versions/0001_initial_schema.py`
- **Auth:** cookie-based JWT sessions, two independent token types — tenant sessions
  (`poko_tenant_session`) for Platform Admin / Company Admin / Company Employee / Subcontractor,
  and platform sessions (`poko_platform_session`) for POKO staff. See `backend/app/deps.py`.
- **Deployment:** DigitalOcean Docker Swarm — there is no local deployment; see root `README.md`
  and `infra/README.md` before assuming anything runs locally.

## Design Enforcement Rules

1. **Color:** Never introduce new colors. Use only the CSS custom properties defined in
   `frontend/app/globals.css` (`--accent`, `--good`/`--warn`/`--crit`/`--info`, etc.) and
   documented in `DESIGN.md`.
2. **Typography:** Figtree for both display/headers (`var(--font-display)`, weight
   `var(--display-weight)`) and body (`var(--font-ui)`); IBM Plex Mono (`var(--font-mono)`, also
   just `.mono`/`.num` classes) for data cells. Never use `text-transform: uppercase` as a label
   device — sentence case at weight 600 carries hierarchy instead (see DESIGN.md "Type System v2").
3. **Accent discipline:** `var(--accent)` (blueprint blue) is the ONLY chromatic accent. Use
   sparingly — interactive states and CTAs only, plus the one sanctioned non-interactive
   exception, the WBS hierarchy rail (`--wbs-line-*`).
4. **Critical path / risk:** Red tint (`var(--crit-soft)`) only for genuinely critical/blocking
   states, never decorative.
5. **Float badges:** When float-health data ships, use the 5-step float color ramp documented in
   `DESIGN.md` (`float-zero` → `float-high`), not generic red/green.
6. **Locale:** All UI strings must be in English. No Turkish in user-facing text (conversation
   with the project owner is in Turkish — that's fine — but anything a user of the app sees is
   English only).

## Architecture

```
frontend/app/
  (tenant)/(company)/   ← company_admin/company_employee shell + pages (sidebar nav)
  (tenant)/(subcontractor)/  ← separate, minimal shell — subcontractors never see the full sidebar
  platform-admin/       ← POKO-staff-only console (tenant onboarding, platform admins)
  globals.css           ← full design-token implementation
lib/                     ← api.ts (fetch wrapper + silent session refresh), types.ts, auth.ts (server-only)
components/               ← shared (Toast, icons.tsx, ActivityCard, FlagReviewModal)
backend/app/
  models/, schemas/, api/routes/, services/, deps.py (auth/RLS plumbing)
  alembic/versions/      ← migrations, sequential (0001, 0002, ...)
DESIGN.md                 ← full design system spec
```

## Key Patterns

- Tenant isolation is enforced at TWO layers: Postgres RLS (`set_rls_context` must be called
  before any query against a tenant-scoped table) AND application-level checks in
  `backend/app/deps.py` (`require_tenant_access`, `require_project_permission`, etc.) — never
  rely on just one.
- A user's capabilities within a tenant come from `project_roles` (a list, not a single value —
  someone can hold several of Project Administrator / All Access / Execution / User Management /
  Activity Status Updater at once) plus their coarse `TenantRole` (company_admin/
  company_employee/subcontractor).
- No real transactional email provider is wired up yet — invite links and password-reset links
  are surfaced directly in the UI to whoever creates them (see `services/invites.py`,
  `services/password_reset.py`) rather than emailed.
- Durations and floats are stored in hours and shown in days by dividing by the activity's OWN
  calendar day length (P6 `CALENDAR.day_hr_cnt`, stored as `Calendar.hours_per_day`, exposed as
  `Activity.hours_per_day`) — never a flat `/ 8`. Use `backend/app/engine/durations.py` and
  `frontend/lib/duration.ts`.
- All date/schedule formatting should eventually match P6 convention (`DD-MMM-YYYY`) once real
  schedule data lands — not yet enforced since no page renders real activity dates today.

## Where the real P6 analysis engine is coming from

A colleague built a separate, working single-tenant desktop app with a real CPM scheduler, EVM/
S-curve engine, DCMA 14-point check, Monte Carlo risk engine, and XER parser/writer (Python,
~7,700 lines) plus matching React pages (~7,000 lines). That project has no tenant concept and
stores everything as JSON files + one SQLite DB per project on local disk — porting it here means
re-modeling that data as proper multi-tenant Postgres tables under RLS, not copying its storage
layer. The sidebar/page structure and design system in this project were already aligned to match
it; the actual engine/data porting happens incrementally, feature by feature, planned each time
before writing migrations (the data-model choices are the hard part, not the algorithms — the
CPM/EVM/DCMA/Monte-Carlo engines themselves are pure functions with no filesystem coupling and
port over largely as-is).

## Forbidden

- Installing new npm/pip packages without confirming with user
- Writing Turkish text in any user-facing UI element
- Introducing new color values not in `DESIGN.md`
- Pushing to `main` without the user's go-ahead — every push deploys straight to production
  (DigitalOcean), there is no staging environment
- Bypassing RLS (querying a tenant-scoped table without `set_rls_context`, or using the
  `BYPASSRLS` connection outside the narrow, audited cases it's already used for) — this exact
  mistake broke tenant login and invite acceptance in production once already this project
