# POKO — one-time server bootstrap runbook

Run once, by hand, on the fresh DigitalOcean Ubuntu droplet, before CI/CD takes over.
After step 10, every push to `main` deploys `infra/app-stack.yml` automatically —
`infra/traefik/traefik-stack.yml` stays a manual deploy since it changes rarely and
a bad rollout there would take down all routing, not just one service.

## 1. System + Docker

```bash
sudo apt-get update && sudo apt-get upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
# log out/in (or `newgrp docker`) so the group membership takes effect
```

### 1a. Swap file (recommended on droplets ≤2GB RAM)

Cheap insurance against OOM kills — a burst gets slowed down by swapping instead of
a container getting killed outright.

```bash
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

On a 1GB/1vCPU droplet specifically: `infra/app-stack.yml` intentionally does not
deploy the `worker`/`redis` services (nothing in Phase 1 enqueues a Celery task) to
leave headroom for Traefik + frontend + backend. Re-add them once Phase 2's async
analysis jobs are built, ideally alongside a droplet resize.

## 2. Init single-node Swarm

```bash
docker swarm init --advertise-addr <DROPLET_PUBLIC_IP>
```

## 3. Shared overlay network Traefik + app services join

```bash
docker network create --driver=overlay --attachable traefik-public
```

## 4. Clone the repo

```bash
sudo mkdir -p /opt/pokoena && sudo chown "$USER":"$USER" /opt/pokoena
cd /opt/pokoena
git clone https://github.com/naimakin/pokoena.git .
```

## 5. Persistent GHCR login (fallback for manual ops outside CI)

Generate a classic PAT at https://github.com/settings/tokens with **only** the
`read:packages` scope.

```bash
echo "<GHCR_READ_PAT>" | docker login ghcr.io -u naimakin --password-stdin
```

## 6. DigitalOcean Managed Postgres

Row-level security needs two new, non-superuser DB roles — see the RLS design in
`backend/alembic/versions/0001_initial_schema.py` and `backend/app/db/session.py`.
The original setup's `db_url` secret held the `doadmin` superuser DSN directly (not a
dedicated least-privilege app user, despite step 6 originally saying to create one) —
**that matters a lot here**: a superuser always bypasses RLS, no exception, so the
running `backend` service can never connect as `doadmin` or every RLS policy silently
never applies. `doadmin` stays for migrations only, under its own `db_url_migrate`
secret (step 7), since it already owns the schema and DDL is the one thing the app
roles must not be able to do. Create two new roles for everything else, in the same
database — for this deployment that's `defaultdb`, substitute your own if different:

```sql
-- Run as doadmin (DO control panel → your database → Console)
CREATE ROLE poko_app LOGIN PASSWORD 'REPLACE_STRONG_PASSWORD_1';
GRANT USAGE ON SCHEMA public TO poko_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO poko_app;

CREATE ROLE poko_bypass LOGIN PASSWORD 'REPLACE_STRONG_PASSWORD_2' BYPASSRLS;
GRANT USAGE ON SCHEMA public TO poko_bypass;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO poko_bypass;

-- Applies to both, scoped to whichever role runs this (doadmin) so tables the
-- migration job creates later are covered automatically, not just existing ones.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO poko_app, poko_bypass;
```

`poko_bypass` also needs `BYPASSRLS` verified as actually grantable on your DO plan
before relying on it in production — if it isn't, the platform support-access
feature needs to stay disabled until there's another way to grant it (e.g. a
support ticket).

Also:
- **Trusted Sources**: this droplet should already be added (Databases → your
  DB → Settings → Trusted Sources) from the original setup.
- DO managed Postgres requires TLS — the DSNs below include `sslmode=require`.

## 7. Create the new Docker Swarm secrets

`jwt_secret` already exists from the original setup and doesn't change.
`db_url_app` and `db_url_bypass` are the two role DSNs from step 6 (same
host/port/database, different role names and passwords).

`db_url_migrate` is the account that owns the schema — on DigitalOcean's
managed Postgres that is `doadmin`. It exists as its own secret because the
migration job is the only thing that may issue DDL: granting `CREATE` to
`poko_app` instead would give the role every HTTP request runs under the
right to reshape the schema, which is the separation these three roles exist
to maintain. The original `db_url` secret was supposed to be this, but
production's copy turned out to hold a `poko_app` DSN, so every migration
after that substitution failed with `permission denied for schema public` —
and nothing needed a migration for long enough that it went unnoticed. An
explicit name is harder to swap by mistake.

```bash
printf 'postgresql+psycopg://poko_app:REPLACE_STRONG_PASSWORD_1@REPLACE-db-host.db.ondigitalocean.com:25060/defaultdb?sslmode=require' \
  | docker secret create db_url_app -

printf 'postgresql+psycopg://poko_bypass:REPLACE_STRONG_PASSWORD_2@REPLACE-db-host.db.ondigitalocean.com:25060/defaultdb?sslmode=require' \
  | docker secret create db_url_bypass -

# doadmin's DSN, straight from the DO control panel -> your database ->
# Connection details. Used by the CI migration job and nothing else.
printf 'postgresql+psycopg://doadmin:REPLACE_DOADMIN_PASSWORD@REPLACE-db-host.db.ondigitalocean.com:25060/defaultdb?sslmode=require' \
  | docker secret create db_url_migrate -

# Cloudflare dashboard -> My Profile -> API Tokens -> Create Token -> "Edit zone DNS"
# template, scoped to the pokoena.com zone only.
printf 'REPLACE_WITH_CLOUDFLARE_SCOPED_TOKEN' | docker secret create cf_api_token -

# Traefik dashboard basic auth (bcrypt):
sudo apt-get install -y apache2-utils
htpasswd -nbB admin 'REPLACE_DASHBOARD_PASSWORD' | docker secret create traefik_dashboard_htpasswd -
```

To rotate a secret later: create it under a new name (e.g. `jwt_secret_v2`), update
the reference in the stack file, redeploy, then remove the old one — Swarm secrets
are immutable by value.

## 8. Cloudflare DNS (dashboard → pokoena.com zone → DNS)

| Type | Name | Value | Proxy |
|---|---|---|---|
| A | pokoena.com | `<DROPLET_PUBLIC_IP>` | Proxied (orange cloud) |
| A | www | `<DROPLET_PUBLIC_IP>` | Proxied |
| A | api | `<DROPLET_PUBLIC_IP>` | Proxied |
| A | traefik | `<DROPLET_PUBLIC_IP>` | DNS only (simpler for the dashboard) |

**SSL/TLS mode → Full (strict)** (SSL/TLS → Overview). Not Flexible — combined with
Traefik's forced HTTPS redirect, Flexible causes an infinite redirect loop. DNS-01
challenge (already configured in `traefik-stack.yml`) works with the proxy on, so
there's no need to ever pause Cloudflare's CDN/DDoS protection for cert issuance.

## 9. Deploy Traefik (once)

```bash
docker stack deploy -c infra/traefik/traefik-stack.yml traefik
docker service logs traefik_traefik -f   # watch for successful ACME cert issuance
```

## 10. First app deploy (bootstrap only — CI takes over after this)

Run migrations *before* the first deploy so `backend` isn't crash-looping against an
empty database on its first boot (subsequent deploys run migrations before the stack
update the same way, via `deploy.yml`):

```bash
docker service create --name pokoena-migrate --network traefik-public \
  --secret db_url_migrate --env DATABASE_URL_MIGRATE_FILE=/run/secrets/db_url_migrate \
  --restart-condition none --with-registry-auth \
  ghcr.io/naimakin/pokoena-backend:latest alembic upgrade head
docker service logs pokoena-migrate -f
docker service rm pokoena-migrate

IMAGE_TAG=latest docker stack deploy -c infra/app-stack.yml --with-registry-auth pokoena
```

## 11. GitHub Actions secrets

Repo → Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `DO_SSH_HOST` | Droplet public IP/hostname |
| `DO_SSH_USER` | The SSH user added to the `docker` group in step 1 |
| `DO_SSH_KEY` | Private half of a dedicated deploy keypair (public half in that user's `~/.ssh/authorized_keys`) |

## 12. Seed data + first admin user

Run once, on the droplet, against the running `backend` service image. `--network
traefik-public` is just for internet egress to the managed Postgres host — these jobs
publish nothing and carry no Traefik labels.

```bash
docker service create --name pokoena-seed --network traefik-public \
  --secret db_url_app --env DATABASE_URL_FILE=/run/secrets/db_url_app \
  --restart-condition none --with-registry-auth \
  ghcr.io/naimakin/pokoena-backend:latest python -m scripts.seed_demo
docker service logs pokoena-seed -f
docker service rm pokoena-seed

docker service create --name pokoena-admin --network traefik-public \
  --secret db_url_app --env DATABASE_URL_FILE=/run/secrets/db_url_app \
  --restart-condition none --with-registry-auth \
  ghcr.io/naimakin/pokoena-backend:latest \
  python -m scripts.create_admin --email admin@pokoena.com --password 'REPLACE_ME' --name "Jordan Diaz"
docker service logs pokoena-admin -f
docker service rm pokoena-admin
```

## 13. Verify

```bash
docker stack services traefik
docker stack services pokoena
curl -I https://pokoena.com
curl -I https://api.pokoena.com/healthz
```

## Secrets inventory

| Secret | Lives in | Purpose |
|---|---|---|
| `DO_SSH_HOST` / `DO_SSH_USER` / `DO_SSH_KEY` | GitHub Actions secrets | Deploy job's `DOCKER_HOST=ssh://` |
| `GITHUB_TOKEN` | Built-in per workflow run | Push images to GHCR; forwarded for `--with-registry-auth` |
| GHCR read PAT | Local `docker login` on the droplet only (not a GitHub secret) | Manual `docker service` ops outside CI |
| `db_url_migrate` | Docker Swarm secret | Postgres DSN as `doadmin` (owns the schema) — the migration job only, nothing else mounts it |
| `db_url` | Docker Swarm secret | Legacy. Was meant to be the `doadmin` DSN, but production's copy holds a `poko_app` DSN, which is why the migration job broke — see step 7. Nothing reads it any more. |
| `db_url_app` | Docker Swarm secret | Postgres DSN as `poko_app` (ordinary, RLS-bound) — what `backend` actually connects with |
| `db_url_bypass` | Docker Swarm secret | Postgres DSN as `poko_bypass` (BYPASSRLS) — platform support-access path only |
| `jwt_secret` | Docker Swarm secret | JWT signing key — wired to both `backend` and `frontend` (middleware/`auth()` verify the same JWTs) in `app-stack.yml` |
| `cf_api_token` | Docker Swarm secret | Traefik's Cloudflare DNS-01 ACME resolver |
| `traefik_dashboard_htpasswd` | Docker Swarm secret | Basic auth on `traefik.pokoena.com` |
| DO Trusted Sources allowlist | DigitalOcean control panel | Firewall for the managed Postgres instance |

No production `.env` file — secrets go through Swarm secrets, non-sensitive config
through each stack file's `environment:` block. `.env` / `docker-compose.yml` (repo
root) are local-dev-only.
