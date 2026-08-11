-- Local dev bootstrap only — run automatically by the official postgres image on
-- first container init (docker-entrypoint-initdb.d/*.sql, alphabetical order).
--
-- Creates the two roles the RLS policies in
-- backend/alembic/versions/0001_initial_schema.py reference:
--   poko_app     ordinary request path, bound by row-level security
--   poko_bypass  BYPASSRLS — used only by the narrow, audited platform
--                support-access path (see backend/app/db/session.py)
--
-- In production these are created once, by hand, via the hosting provider's
-- control panel (a managed Postgres app-level user generally can't CREATE ROLE
-- itself) — see infra/README.md.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'poko_app') THEN
        CREATE ROLE poko_app LOGIN PASSWORD 'poko_app';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'poko_bypass') THEN
        CREATE ROLE poko_bypass LOGIN PASSWORD 'poko_bypass' BYPASSRLS;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO poko_app, poko_bypass;

-- Migrations run as POSTGRES_USER (poko — the table owner), so every table it
-- creates from here on automatically grants CRUD to both roles, without needing
-- to re-run GRANT after each migration.
ALTER DEFAULT PRIVILEGES FOR ROLE poko IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO poko_app, poko_bypass;
