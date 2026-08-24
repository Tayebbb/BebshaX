# BebshaX Database Migration & Dynamic Switching Guide

BebshaX supports **zero-friction database switching** with automatic schema creation, PostgreSQL extension configuration, and demo data initialization across any database engine.

---

## 1. Automatic Schema Initialization on Startup

When the backend starts up (`uvicorn bebshax.main:app`), it automatically executes [`init_database`](file:///E:/Github%20Projects/BebshaX/apps/backend/bebshax/db/engine.py):
1. Detects the database dialect (PostgreSQL, SQLite, MySQL).
2. Configures required extensions (`CREATE EXTENSION IF NOT EXISTS vector` on PostgreSQL).
3. Automatically creates all **13 core application tables**:
   - `users` (Authentication & Google SSO profiles)
   - `businesses` (Business context)
   - `personas`, `persona_details`, `persona_attributes`, `persona_evidence` (Empirically grounded personas)
   - `memory_items` (Episodic, semantic, and reflection memory vectors)
   - `conversations`, `conversation_turns` (Multi-turn interview simulation transcripts)
   - `studies` (User-scoped research studies with 5-step state)
   - `saved_audiences` (Persona library audience groups)
   - `llm_requests`, `model_registry` (OTel provenance tracking)
4. Seeds initial demo records (founder user, fintech business, Sarah Chen persona, and sample studies) if the database is newly initialized.

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
