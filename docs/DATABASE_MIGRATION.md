# BebshaX Database Migration & Dynamic Switching Guide

BebshaX supports **zero-friction database switching** — with one rule: **alembic migrations are the single source of schema truth.** Startup auto-creation is a bootstrap convenience for _empty_ databases only.

---

## 1. Schema initialization on startup (bootstrap only)

When the backend starts (`uvicorn bebshax.main:app`), [`init_database`](../apps/backend/bebshax/db/engine.py) runs and:

1. Detects the database dialect (PostgreSQL, SQLite, MySQL) and configures required extensions (`CREATE EXTENSION IF NOT EXISTS vector` on PostgreSQL).
2. Checks who owns the schema:
   - **`alembic_version` table present** → alembic owns the schema; `create_all` is **skipped entirely**. Apply changes with `alembic upgrade head`.
   - **Truly empty database** → all tables are created via `Base.metadata.create_all` **and the current migration head is stamped** into `alembic_version`, so later `alembic upgrade head` runs cleanly instead of fighting the bootstrap.
   - **Legacy `create_all` schema without `alembic_version`** → missing tables are created, a WARNING is logged, and the revision is deliberately **not** stamped — reconcile manually with `alembic stamp <revision>`.
3. Seeds demo records **only when `BEBSHAX_DEMO_MODE=true`** (founder user, fintech business, sample persona/studies). Seeding failures are logged, never silent.

---

## 2. CLI Migration Script (`scripts/migrate_db.py`)

You can run the standalone migration script to verify connectivity, initialize tables, and view current database records:

```bash
# Migrate the database configured in your .env (DATABASE_URL)
python scripts/migrate_db.py

# Migrate a custom Postgres database
python scripts/migrate_db.py --url "postgresql://user:password@host:5432/dbname"

# Migrate a local SQLite file (zero external dependencies)
python scripts/migrate_db.py --url "sqlite+aiosqlite:///bebshax.db"
```

---

## 3. Supported Database Providers & Connection Formats

Set `DATABASE_URL` in your `.env` file (gitignored) to switch databases:

### A. Local Docker Compose (Default dev setup)

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/bebshax
```

Start container: `docker compose up -d db`

### B. Neon Serverless Postgres

```env
DATABASE_URL=postgresql://user:password@ep-sample-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
```

### C. Supabase / Railway / Render

```env
DATABASE_URL=postgresql://postgres:password@db.supabase.co:5432/postgres?sslmode=require
```

### D. SQLite (Local offline file)

```env
DATABASE_URL=sqlite+aiosqlite:///bebshax.db
```

---

## 4. Architectural Guarantees & Dialect Normalization

- **URL Dialect Normalization:** PostgreSQL `postgres://` or `postgresql://` connection strings are automatically mapped to `postgresql+asyncpg://`, with SSL parameters sanitized for `asyncpg`.
- **Dialect-Aware Pooling:** Connection pooling (`pool_size=5`, `pool_recycle=1800`) is automatically applied to production engines and bypassed on SQLite engines.
- **Fail-Soft LLM Logging:** Provenance records and generation requests are written through a non-blocking queue (`ProvenanceSink`), ensuring temporary database downtime never breaks LLM generation workflows.
