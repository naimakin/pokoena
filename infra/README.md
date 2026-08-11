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

Row-level security needs three separate DB roles — see the RLS design in
`backend/alembic/versions/0001_initial_schema.py` and `backend/app/db/session.py`.
A managed-Postgres app user generally can't `CREATE ROLE` itself, so all three are
created once, by hand, via the DO control panel (your database →
**Users & Databases**) — never reuse the default admin superuser for any of them:

- `poko` (or your migration user) — schema owner, runs `alembic upgrade`. Needs
  `CREATE`/`ALTER`/`GRANT` on the `public` schema (DO's "Add new user" gives a
  normal role by default; grant it schema ownership once via `doadmin`).
- `poko_app` — ordinary request path. RLS-bound: no special grants beyond normal
  table CRUD (RLS policies restrict rows automatically once `poko` grants them).
- `poko_bypass` — platform support-access path only. Needs `BYPASSRLS`, granted via
  `ALTER ROLE poko_bypass BYPASSRLS;` as `doadmin`. **Verify DO's managed offering
  actually allows granting BYPASSRLS to a non-admin role before relying on this in
  production** — if it doesn't, the platform support-access feature needs to stay
  disabled until there's another way to grant it (e.g. a support ticket).

Also:
- **Trusted Sources**: add this droplet (Databases → your DB → Settings → Trusted
  Sources → add droplet). Connections are refused otherwise, even with correct
  credentials.
- DO managed Postgres requires TLS — the DSNs below include `sslmode=require`.

## 7. Create Docker Swarm secrets

```bash
printf 'postgresql+psycopg://poko_app:REPLACE_DB_PASSWORD@REPLACE-db-host.db.ondigitalocean.com:25060/poko?sslmode=require' \
  | docker secret create db_url -

printf 'postgresql+psycopg://poko_bypass:REPLACE_DB_PASSWORD@REPLACE-db-host.db.ondigitalocean.com:25060/poko?sslmode=require' \
  | docker secret create db_url_bypass -

printf 'postgresql+psycopg://poko:REPLACE_DB_PASSWORD@REPLACE-db-host.db.ondigitalocean.com:25060/poko?sslmode=require' \
  | docker secret create db_url_migrate -

openssl rand -base64 48 | docker secret create jwt_secret -

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

Migrations run as the schema-owner role, not `poko_app` — use `db_url_migrate`:

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
  --secret db_url --env DATABASE_URL_FILE=/run/secrets/db_url \
  --restart-condition none --with-registry-auth \
  ghcr.io/naimakin/pokoena-backend:latest python -m scripts.seed_demo
docker service logs pokoena-seed -f
docker service rm pokoena-seed

docker service create --name pokoena-admin --network traefik-public \
  --secret db_url --env DATABASE_URL_FILE=/run/secrets/db_url \
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
| `db_url` | Docker Swarm secret | Postgres DSN for `backend` as `poko_app` (RLS-bound, ordinary requests) |
| `db_url_bypass` | Docker Swarm secret | Postgres DSN as `poko_bypass` (BYPASSRLS) — platform support-access path only |
| `db_url_migrate` | Docker Swarm secret | Postgres DSN as the schema-owner role — `alembic upgrade` only, not a running service |
| `jwt_secret` | Docker Swarm secret | JWT signing key — also needed by `frontend` (middleware/`auth()` verify the same JWTs), currently only wired to `backend` in `app-stack.yml` |
| `cf_api_token` | Docker Swarm secret | Traefik's Cloudflare DNS-01 ACME resolver |
| `traefik_dashboard_htpasswd` | Docker Swarm secret | Basic auth on `traefik.pokoena.com` |
| DO Trusted Sources allowlist | DigitalOcean control panel | Firewall for the managed Postgres instance |

No production `.env` file — secrets go through Swarm secrets, non-sensitive config
through each stack file's `environment:` block. `.env` / `docker-compose.yml` (repo
root) are local-dev-only.
