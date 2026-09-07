#!/usr/bin/env python3
"""BebshaX Database Migration & Schema Initializer Script.

Run this script whenever you change your database provider or URL (Neon, Supabase,
local PostgreSQL, SQLite, Railway, etc.) to automatically create all tables,
configure vector extensions, and seed initial demo data.

Examples:
    # Migrate the database configured in .env (DATABASE_URL):
    python scripts/migrate_db.py

    # Migrate a specific PostgreSQL instance:
    python scripts/migrate_db.py --url "postgresql://postgres:password@localhost:5433/bebshax"

    # Migrate a Neon / Supabase cloud Postgres instance:
    python scripts/migrate_db.py --url "postgresql://user:pass@ep-cool-db.us-east-2.aws.neon.tech/neondb?sslmode=require"

    # Migrate a local standalone SQLite file for zero-infrastructure offline dev:
    python scripts/migrate_db.py --url "sqlite+aiosqlite:///bebshax.db"
"""

import sys
from pathlib import Path

# Ensure backend package is in python path
backend_path = Path(__file__).parent.parent / "apps" / "backend"
sys.path.insert(0, str(backend_path))

from bebshax.db.migrate import main

if __name__ == "__main__":
    main()
