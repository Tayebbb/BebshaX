"""DB-backed capacity state (AI plan §10): persistent cooldowns + ledger seeding.

Cooldowns: PoolRouter tracks (provider, model) → monotonic deadline in memory;
this store mirrors them to model_registry.cooldown_until in WALL time so a
restart doesn't forget a cooling route, and loads them back as
seconds-remaining at startup.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.db.models import LLMRequests, ModelRegistry

logger = logging.getLogger(__name__)


class CooldownStore:
    def __init__(self, sessionmaker_: sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker_
        self._tasks: set[asyncio.Task] = set()  # keep refs — loop holds tasks weakly

    async def load_active(self, clock=time.monotonic) -> dict[tuple[str, str], float]:
        """Rows still cooling → {(provider, model): monotonic_deadline}."""
        now_wall = datetime.now(timezone.utc)
        try:
            async with self._sessionmaker() as session:
                rows = (
                    await session.execute(
                        select(ModelRegistry).where(ModelRegistry.cooldown_until > now_wall)
                    )
                ).scalars().all()
        except Exception:
            logger.warning("cooldown load failed — starting with none", exc_info=True)
            return {}
        result = {}
        for r in rows:
            until = r.cooldown_until if r.cooldown_until.tzinfo else r.cooldown_until.replace(tzinfo=timezone.utc)
            remaining = (until - now_wall).total_seconds()
            if remaining > 0:
                result[(r.provider_name, r.model_name)] = clock() + remaining
        if result:
            logger.info("restored %d active cooldown(s) from model_registry", len(result))
        return result

    def persist(self, provider: str, model: str, seconds_remaining: float) -> None:
        """Fire-and-forget upsert — persistence must never block or fail a request."""
        try:
            task = asyncio.get_running_loop().create_task(
                self._persist_async(provider, model, seconds_remaining)
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except RuntimeError:
            pass  # no running loop (sync test context) — in-memory cooldown still applies

    async def _persist_async(self, provider: str, model: str, seconds_remaining: float) -> None:
        until = datetime.now(timezone.utc) + timedelta(seconds=seconds_remaining)
        try:
            async with self._sessionmaker() as session:
                row = (
                    await session.execute(
                        select(ModelRegistry).where(
                            ModelRegistry.provider_name == provider,
                            ModelRegistry.model_name == model,
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = ModelRegistry(
                        id=uuid.uuid4().hex, provider_name=provider, model_name=model
                    )
                    session.add(row)
                row.cooldown_until = until
                await session.commit()
        except Exception:
            logger.warning("cooldown persist failed for %s/%s", provider, model, exc_info=True)


async def load_todays_consumption(
    sessionmaker_: sessionmaker[AsyncSession],
) -> tuple[dict[str, int], dict[str, int]]:
    """Seed data for QuotaLedger: today's per-provider requests and tokens."""
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        async with sessionmaker_() as session:
            rows = (
                await session.execute(
                    select(
                        LLMRequests.served_by_provider,
                        func.count(LLMRequests.request_id),
                        func.coalesce(func.sum(LLMRequests.input_tokens), 0)
                        + func.coalesce(func.sum(LLMRequests.output_tokens), 0),
                    )
                    .where(
                        LLMRequests.created_at >= day_start,
                        LLMRequests.success.is_(True),
                        LLMRequests.served_by_provider.is_not(None),
                    )
                    .group_by(LLMRequests.served_by_provider)
                )
            ).all()
    except Exception:
        logger.warning("quota ledger seed failed — starting from zero", exc_info=True)
        return {}, {}
    requests = {p: int(c) for p, c, _ in rows}
    tokens = {p: int(t or 0) for p, _, t in rows}
    return requests, tokens
