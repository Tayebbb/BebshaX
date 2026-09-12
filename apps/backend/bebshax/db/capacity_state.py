"""DB-backed capacity state (AI plan §10): persistent cooldowns + ledger seeding.

Cooldowns: PoolRouter tracks (provider, model) → monotonic deadline in memory;
this store mirrors them to model_registry.cooldown_until in WALL time so a
restart doesn't forget a cooling route, and loads them back as
seconds-remaining at startup.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.db.models import LLMRequests, ModelRegistry
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.llm.quota import QuotaLedger

logger = logging.getLogger(__name__)


def _cooldown_deadline(seconds_remaining: float) -> datetime:
    if not math.isfinite(seconds_remaining) or seconds_remaining <= 0:
        raise ValueError("Cooldown duration must be finite and positive")
    return datetime.now(timezone.utc) + timedelta(seconds=seconds_remaining)


class CooldownStore:
    def __init__(self, sessionmaker_: Callable[[], AsyncSession]) -> None:
        self._sessionmaker = sessionmaker_
        self._tasks: set[asyncio.Task] = set()  # keep refs — loop holds tasks weakly
        self._failures = 0
        self._closed = False

    @property
    def pending_count(self) -> int:
        return len(self._tasks)

    @property
    def failed_writes(self) -> int:
        return self._failures

    async def load_active(self, clock: Callable[[], float] = time.monotonic) -> dict[tuple[str, str], float]:
        """Rows still cooling → {(provider, model): monotonic_deadline}."""
        now_wall = datetime.now(timezone.utc)
        async with self._sessionmaker() as session:
            rows = (
                await session.execute(
                    select(ModelRegistry).where(ModelRegistry.cooldown_until > now_wall)
                )
            ).scalars().all()
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
        """Schedule an atomic merge; drain/aclose acknowledges all scheduled writes."""
        if self._closed:
            raise RuntimeError("Cooldown store is closed")
        loop = asyncio.get_running_loop()
        until = _cooldown_deadline(seconds_remaining)
        task = loop.create_task(self._persist_until(provider, model, until))
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled() or task.exception() is not None:
            self._failures += 1
            logger.error("Cooldown persistence failed")

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.shield(asyncio.gather(*tuple(self._tasks), return_exceptions=True))
        if self._failures:
            raise RuntimeError("Cooldown persistence failed")

    async def aclose(self) -> None:
        self._closed = True
        await self.drain()

    async def _persist_async(self, provider: str, model: str, seconds_remaining: float) -> None:
        until = _cooldown_deadline(seconds_remaining)
        await self._persist_until(provider, model, until)

    async def _persist_until(self, provider: str, model: str, until: datetime) -> None:
        async with self._sessionmaker() as session:
            dialect = session.get_bind().dialect.name
            insert = {"postgresql": postgresql_insert, "sqlite": sqlite_insert}[dialect]
            statement = insert(ModelRegistry).values(
                id=uuid.uuid4().hex, provider_name=provider, model_name=model,
                cooldown_until=until,
            )
            incoming = statement.excluded.cooldown_until
            statement = statement.on_conflict_do_update(
                index_elements=[ModelRegistry.provider_name, ModelRegistry.model_name],
                set_={"cooldown_until": case(
                    (ModelRegistry.cooldown_until.is_(None), incoming),
                    (ModelRegistry.cooldown_until < incoming, incoming),
                    else_=ModelRegistry.cooldown_until,
                )},
            )
            await session.execute(statement)
            await session.commit()


async def load_todays_provenance(
    sessionmaker_: Callable[[], AsyncSession],
) -> list[ProvenanceRecord]:
    """Replay every request today, including failed, cached and interrupted attempts."""
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    async with sessionmaker_() as session:
        rows = (
            await session.execute(
                select(LLMRequests).where(LLMRequests.created_at >= day_start)
                .order_by(LLMRequests.created_at, LLMRequests.request_id)
            )
        ).scalars().all()
    return [
        ProvenanceRecord(
            request_id=row.request_id, task=str(row.task), pool=row.pool,
            persona_id=row.persona_id, conversation_id=row.conversation_id,
            owner_user_id=row.owner_id,
            study_id=row.study_id, data_classification=row.data_classification,
            processing_policy_id=row.processing_policy_id,
            processing_provider_allowlist=tuple(row.processing_provider_allowlist),
            processing_openrouter_upstreams=tuple(row.processing_openrouter_upstreams),
            estimated_tokens=row.estimated_tokens,
            created_at=row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc),
            routing_path=row.routing_path or [], attempts=row.attempts or [],
            served_by_provider=row.served_by_provider,
            served_by_model=row.response_model or "unknown",
            input_tokens=row.input_tokens, output_tokens=row.output_tokens,
            total_latency_ms=row.total_latency_ms, success=row.success,
            persistence_status="acknowledged",
        )
        for row in rows
    ]


async def load_todays_consumption(
    sessionmaker_: Callable[[], AsyncSession],
) -> tuple[dict[str, int], dict[str, int]]:
    """Compatibility aggregate; production uses idempotent full-record replay."""
    ledger = QuotaLedger()
    ledger.seed_provenance(await load_todays_provenance(sessionmaker_))
    rows = [row for row in ledger.snapshot() if row["requests_today"]]
    return (
        {row["provider"]: row["requests_today"] for row in rows},
        {row["provider"]: row["tokens_today"] for row in rows},
    )


_NON_ROUTE_PROVIDERS = frozenset({"ollama", "ollama_cloud", "freellmpool", "openrouter", "unknown"})


async def load_recent_route_observations(
    sessionmaker_: Callable[[], AsyncSession],
    days: int = 3,
    limit: int = 500,
    per_target_cap: int = 8,
) -> list[tuple[str, str, float]]:
    """Replay genuine primary endpoint timings, never outer adapter duration."""
    if days <= 0 or limit <= 0 or per_target_cap <= 0:
        raise ValueError("Observation window, limit and per-target cap must be positive")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with sessionmaker_() as session:
        rows = (
            await session.execute(
                select(LLMRequests.created_at, LLMRequests.attempts)
                .where(LLMRequests.created_at >= cutoff)
                .order_by(LLMRequests.created_at.desc(), LLMRequests.request_id.desc())
                .limit(limit)
            )
        ).all()
    observations = []
    for created_at, attempts in rows:
        for attempt in attempts or []:
            if not isinstance(attempt, dict) or attempt.get("cached"):
                continue
            if "served from freellmpool response cache" in attempt.get("notes", []):
                continue
            for observation in attempt.get("observations", []):
                if not isinstance(observation, dict):
                    continue
                provider, model = observation.get("provider"), observation.get("requested_model")
                latency = observation.get("latency_ms")
                if (
                    not provider or provider in _NON_ROUTE_PROVIDERS
                    or not model or model in {"auto", "unknown", "*"}
                    or observation.get("outcome") != "succeeded"
                    or observation.get("consumption") != "known"
                    or isinstance(latency, bool) or not isinstance(latency, (int, float))
                    or not math.isfinite(latency) or latency < 0
                ):
                    continue
                started_at = observation.get("started_at")
                try:
                    timestamp = datetime.fromisoformat(started_at) if isinstance(started_at, str) else created_at
                except ValueError:
                    continue
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                observations.append((timestamp, str(provider), str(model), float(latency)))
    capped: list[tuple[str, str, float]] = []
    seen: dict[tuple[str, str], int] = {}
    for _, provider, model, latency in sorted(observations, key=lambda row: row[0], reverse=True):
        key = (provider, model)
        if seen.get(key, 0) < per_target_cap:
            seen[key] = seen.get(key, 0) + 1
            capped.append((provider, model, latency))
    return list(reversed(capped))
