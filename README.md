# POKO

**Project Intelligence & Execution** — a controlled, multi-stakeholder schedule-update
workflow for construction, built on top of Oracle Primavera P6 (P6 stays the single
source of truth).

Admin opens a periodic update window → each subcontractor edits only their own scope
(status/dates/remaining duration save immediately; any logic, lag, or dependency change
must be flagged with a justification for admin review) → admin closes the period, and
the change queue, S-curve/EVM/Monte Carlo analysis (Phase 2), and P6 export take it from
there.

POKO is multi-tenant: POKO staff (Platform Super Admin) onboard tenant companies; each
company has its own Company Admins, Company Employees, and project/scope-restricted
Subcontractors, isolated from every other tenant by Postgres row-level security as well
as application-level checks.

## Repo layout

```
backend/        FastAPI + SQLAlchemy + Alembic + Celery — the API and the (future) analysis worker
frontend/       Next.js — platform-admin console, company dashboard/review queue, subcontractor scope view
infra/          Docker Swarm stack files, Traefik config, server bootstrap runbook
.github/        CI (lint+test on PRs) and CD (build → GHCR → deploy on push to main)
```

## Deployment

**There is no local deployment.** POKO runs as a single-node Docker Swarm stack on a
DigitalOcean droplet — `pokoena.com` (frontend) / `api.pokoena.com` (backend), Cloudflare
DNS, DigitalOcean Managed Postgres. GitHub Actions builds images, pushes them to GHCR,
and rolls them out on every push to `main`:
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml). One-time server setup,
secrets, and DNS/Cloudflare configuration: see [`infra/README.md`](infra/README.md).

A push to `main` is a real production deploy — there's no staging environment in front
of it. `backend/app/main.py`'s `/healthz` and the CI run itself are the fastest way to
confirm a deploy landed; `docker service ls` on the droplet shows which image tag
(`<12-char commit sha>` or `latest`) each service is currently running.

### Operating the live deployment

One-off admin scripts (`backend/scripts/`) run as a scheduled Docker Swarm task against
the running `backend` image, using the `db_url` secret (table-owner rights, bypasses
RLS) fed into `DATABASE_URL_FILE` — see [`infra/README.md`](infra/README.md) for the
full secrets/runbook. The three that come up in day-to-day operation:

```bash
# Create or reset a Platform Super Admin's password
docker service create --name pokoena-admin --network traefik-public \
  --secret db_url --env DATABASE_URL_FILE=/run/secrets/db_url \
  --restart-condition none --with-registry-auth \
  ghcr.io/naimakin/pokoena-backend:latest \
  python -m scripts.create_admin --email you@pokoena.com --password 'change-me' --name "Your Name"
docker service logs pokoena-admin -f
docker service rm pokoena-admin

# Seed the demo tenant (Riverside Logistics Park GC) — safe to skip in production
docker service create --name pokoena-seed --network traefik-public \
  --secret db_url --env DATABASE_URL_FILE=/run/secrets/db_url \
  --restart-condition none --with-registry-auth \
  ghcr.io/naimakin/pokoena-backend:latest python -m scripts.seed_demo
docker service logs pokoena-seed -f
docker service rm pokoena-seed

# Hard-delete every tenant and all its data (dev-stage cleanup only — irreversible,
# never touches platform admins)
docker service create --name pokoena-wipe --network traefik-public \
  --secret db_url --env DATABASE_URL_FILE=/run/secrets/db_url \
  --restart-condition none --with-registry-auth \
  ghcr.io/naimakin/pokoena-backend:latest python -m scripts.wipe_tenants --yes
docker service logs pokoena-wipe -f
docker service rm pokoena-wipe
```

Platform admins sign in at `https://pokoena.com/platform-admin/login`; everyone else at
`https://pokoena.com/login`.

## Local testing (optional)

Not how the project is deployed — useful only for testing backend/frontend changes
against a real Postgres+Redis before pushing. Requires Docker Desktop.

```bash
docker compose up
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (docs at `/docs`, health at `/healthz`)

Migrations apply automatically on `backend` startup. Same scripts as production, just
without `docker service create`/secrets — e.g. `docker compose exec backend python -m
scripts.create_admin --email you@pokoena.com --password change-me --name "Your Name"`.

Running the backend outside Docker: copy `backend/.env.example` to `backend/.env`,
`pip install -r backend/requirements-dev.txt`, then `uvicorn app.main:app --reload`
from `backend/`. Tests: `pytest` (uses an in-memory SQLite DB, no services required —
RLS itself is Postgres-only, and several bugs upstream only ever surfaced against real
Postgres in production; see `backend/tests/conftest.py` for how the suite works around
that, and be skeptical of "passes in SQLite" as proof anything RLS-related works).

## Status

**Phase 1** (current): multi-tenant auth (Platform Admin / Company Admin / Company
Employee / Subcontractor), Postgres RLS tenant isolation, invite-based onboarding, the
controlled update workflow (direct edits vs. flag-for-review), the core screens, and
the deploy pipeline.

**Phase 2** (planned): P6 (`.xer`) import/export, the S-curve/EVM/Monte Carlo analysis
engine, AI-generated risk summaries, real transactional email delivery for invites.
