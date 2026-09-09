"""Database migration and automatic schema initialization CLI utility for BebshaX.

Usage:
    python -m bebshax.db.migrate
    python -m bebshax.db.migrate --url "postgresql://user:pass@host:5432/dbname"
    python -m bebshax.db.migrate --url "sqlite+aiosqlite:///bebshax.db"
"""

import argparse
import asyncio
import sys
from urllib.parse import urlparse

from sqlalchemy import func, select

from bebshax.config import get_settings
from bebshax.db.engine import (
    create_async_sessionmaker,
    create_engine,
    init_database,
    normalize_async_database_url,
)
from bebshax.db.models import Businesses, Studies
from bebshax.auth.models import Users


def mask_url(url: str) -> str:
    """Mask credentials in database URL for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = f"{parsed.username}:*****@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return parsed._replace(netloc=netloc).geturl()
        return url
    except Exception:
        return "<database-url>"


async def run_migration(db_url: str | None = None, seed: bool = True) -> int:
    """Execute automatic database table creation and verification."""
    settings = get_settings()
    target_url = db_url or settings.database_url
    normalized_url = normalize_async_database_url(target_url)

    print("=" * 60)
    print("[BebshaX] Database Auto-Migration & Schema Setup")
    print("=" * 60)
    print(f"Target Database: {mask_url(normalized_url)}")

    engine = create_engine(settings, url_override=target_url)
    sessionmaker_ = create_async_sessionmaker(engine)

    try:
        # 1. Initialize schema and tables
        print("\n>> Initializing schema and creating all tables...")
        tables = await init_database(engine, sessionmaker_, seed=seed)
        print(f"[OK] Successfully created / verified {len(tables)} tables:")
        for t in sorted(tables):
            print(f"   * {t}")

        # 2. Verify table records
        async with sessionmaker_() as session:
            user_count = (await session.execute(select(func.count(Users.id)))).scalar_one() or 0
            biz_count = (await session.execute(select(func.count(Businesses.id)))).scalar_one() or 0
            study_count = (await session.execute(select(func.count(Studies.id)))).scalar_one() or 0

            print("\n>> Database Status:")
            print(f"   * Registered Users: {user_count}")
            print(f"   * Businesses:       {biz_count}")
            print(f"   * Research Studies: {study_count}")

        print("\n[SUCCESS] Database is fully migrated, verified, and ready for use!")
        print("=" * 60)
        return 0

    except Exception as exc:
        print(f"\n[ERROR] Migration Failed: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="BebshaX Database Migration & Schema Initializer")
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Database URL to migrate (e.g. postgresql://..., sqlite+aiosqlite:///...). Defaults to DATABASE_URL in .env",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip seeding demo data after creating tables",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(run_migration(db_url=args.url, seed=not args.no_seed))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
