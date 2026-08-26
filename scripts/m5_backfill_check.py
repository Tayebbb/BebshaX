"""One-off inspection + supplementary backfill for M5 (see audit fix log).

Re-applies the CORRECTED legacy-header extraction to rows the first (buggy)
backfill missed: TM-only headers, and verifies no pipe-less corruption occurred.
Idempotent for legacy-writer output: rows with either column already populated
are skipped entirely, so re-runs never touch user content twice.
"""

import asyncio
import importlib.util
from pathlib import Path

from sqlalchemy import text

from bebshax.config import get_settings
from bebshax.db.engine import create_engine

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "apps/backend/alembic/versions/c4d5e6f7a8b9_m5_business_industry_target_market.py"
)


def _load_split():
    spec = importlib.util.spec_from_file_location("m5_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._split_legacy_header


async def main() -> None:
    split = _load_split()
    eng = create_engine(get_settings())
    async with eng.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, name, industry, target_market, description FROM businesses"
                )
            )
        ).fetchall()
        print(f"businesses total: {len(rows)}")
        fixed = 0
        for r in rows:
            desc = r.description or ""
            print(f"- {r.id[:8]} {r.name!r} industry={r.industry!r} tm={r.target_market!r} desc={desc[:60]!r}")
            if desc.startswith("Industry: ") or desc.startswith("Target Market: "):
                if r.industry is not None or r.target_market is not None:
                    continue  # already migrated — never re-parse user content
                ind, tm, clean = split(desc)
                if ind is None and tm is None:
                    continue  # user content — leave alone
                await conn.execute(
                    text(
                        "UPDATE businesses SET industry = COALESCE(industry, :ind), "
                        "target_market = COALESCE(target_market, :tm), description = :d "
                        "WHERE id = :id"
                    ),
                    {"ind": ind, "tm": tm, "d": clean, "id": r.id},
                )
                fixed += 1
        print(f"supplementary backfill updated: {fixed}")
    await eng.dispose()


asyncio.run(main())
