"""Awaited durable provenance with a legacy best-effort queue API.

Persistence failure is a finalization error, never a provider fallback signal.
Failed or ambiguously committed records remain available for reconciliation.
"""

import asyncio
import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.db.models import LLMRequests
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.tenancy_context import capture_provenance_owner

logger = logging.getLogger(__name__)


class ProvenanceSink:
    """Use await persist(record) for commit acknowledgment; __call__ only submits."""

    def __init__(
        self,
        sessionmaker_: Callable[[], AsyncSession],
        batch_size: int = 100,
        batch_timeout_ms: int = 5000,
        log_interval: int = 100,
    ) -> None:
        """Initialize the sink.

        Args:
            sessionmaker_: async sessionmaker for database access
            batch_size: max records per insert() call
            batch_timeout_ms: max time to wait before flushing a partial batch
            log_interval: rate-limit DB error logs to 1 per N errors
        """
        self.sessionmaker = sessionmaker_
        self.batch_size = batch_size
        self.batch_timeout_ms = batch_timeout_ms
        self.log_interval = log_interval

        self.queue: asyncio.Queue[Optional[ProvenanceRecord]] = asyncio.Queue(
            maxsize=1000
        )
        self.writer_task: Optional[asyncio.Task] = None
        self.writer_running = False

        # Counters for observability
        self.total_enqueued = 0
        self.total_written = 0
        self.total_dropped = 0
        self.total_db_errors = 0
        self.queue_full_count = 0
        self.failed_records: dict[str, ProvenanceRecord] = {}
        self._owners: dict[str, str | None] = {}
        self._closed = False

    def _capture_owner(self, record: ProvenanceRecord) -> None:
        owner = capture_provenance_owner(record)
        if record.owner_user_id is not None:
            declared_owner = capture_provenance_owner(
                SimpleNamespace(owner_id=record.owner_user_id)
            )
            if owner is not None and owner != declared_owner:
                raise ValueError("Provenance owner conflicts with submission identity")
            owner = declared_owner
        if record.request_id in self._owners:
            if owner is not None and owner != self._owners[record.request_id]:
                raise ValueError("Provenance owner conflicts with submission identity")
        else:
            self._owners[record.request_id] = owner

    async def persist(self, record: ProvenanceRecord) -> None:
        """Return only after commit; retain the complete record on every failure."""
        if self._closed:
            record.persistence_status = "failed"
            self.failed_records[record.request_id] = record
            raise RuntimeError("Provenance persistence failed: sink is closed")
        record.persistence_status = "submitted"
        try:
            self._capture_owner(record)
            await self._write_batch([record])
        except asyncio.CancelledError:
            record.persistence_status = "unknown"
            self.failed_records[record.request_id] = record
            raise
        except Exception:
            self._record_failure([record])
            raise RuntimeError("Provenance persistence failed") from None

    def _record_failure(self, records: list[ProvenanceRecord]) -> None:
        self.total_db_errors += 1
        for record in records:
            record.persistence_status = "failed"
            self.failed_records[record.request_id] = record
        if self.total_db_errors == 1 or self.total_db_errors % max(1, self.log_interval) == 0:
            logger.error("ProvenanceSink: database commit failed (%d failures)", self.total_db_errors)

    def __call__(self, record: ProvenanceRecord) -> None:
        """Synchronous sink: enqueue a provenance record.

        Never raises. On queue full, increments counter + log warning, returns.
        """
        if self._closed:
            record.persistence_status = "failed"
            self.failed_records[record.request_id] = record
            self.total_dropped += 1
            return
        try:
            self._capture_owner(record)
            record.persistence_status = "submitted"
            self.queue.put_nowait(record)
            self.total_enqueued += 1
        except asyncio.QueueFull:
            record.persistence_status = "failed"
            self.failed_records[record.request_id] = record
            self.total_dropped += 1
            self.queue_full_count += 1
            if self.queue_full_count % 10 == 0:
                logger.warning(
                    f"ProvenanceSink: queue full; dropped {self.queue_full_count} records"
                )
        except ValueError:
            record.persistence_status = "failed"
            self.failed_records[record.request_id] = record
            self.total_dropped += 1
            logger.error("ProvenanceSink: invalid submission ownership")

    async def _writer(self) -> None:
        """Background writer task: drain queue and insert to DB.

        Runs until a sentinel (None) is received. Never dies—DB errors are
        logged (rate-limited) and the batch is dropped, but the writer
        continues pulling from the queue.
        """
        batch: list[ProvenanceRecord] = []
        loop = asyncio.get_event_loop()
        last_flush = loop.time()
        _IDLE = object()  # idle-timeout marker — must NOT be confused with the None sentinel

        while True:
            try:
                timeout_remaining = self.batch_timeout_ms / 1000 - (loop.time() - last_flush)
                if timeout_remaining > 0:
                    try:
                        record = await asyncio.wait_for(
                            self.queue.get(), timeout=timeout_remaining
                        )
                    except asyncio.TimeoutError:
                        record = _IDLE
                else:
                    record = _IDLE

                if record is None:
                    # Explicit shutdown sentinel from stop(): final flush, then exit.
                    if batch:
                        await self._insert_batch(batch)
                        for _ in batch:
                            self.queue.task_done()
                    self.queue.task_done()  # the sentinel itself
                    break

                if record is _IDLE:
                    # Idle tick: flush what we have and keep running. The old code
                    # treated this as the sentinel — the writer died ~5s after
                    # startup and silently dropped every later record (found live
                    # 2026-08-26; unit tests called _insert_batch directly).
                    if batch:
                        await self._insert_batch(batch)
                        for _ in batch:
                            self.queue.task_done()
                        batch = []
                    last_flush = loop.time()
                    continue

                batch.append(record)

                # Flush on batch full or timeout
                if len(batch) >= self.batch_size or (
                    loop.time() - last_flush >= self.batch_timeout_ms / 1000
                ):
                    await self._insert_batch(batch)
                    for _ in batch:
                        self.queue.task_done()
                    batch = []
                    last_flush = loop.time()

            except asyncio.CancelledError:
                for record in batch:
                    record.persistence_status = "unknown"
                    self.failed_records[record.request_id] = record
                    self.queue.task_done()
                raise
            except Exception:
                logger.error("ProvenanceSink writer failed")

    async def _insert_batch(self, batch: list[ProvenanceRecord]) -> None:
        """Legacy queued delivery: retain failures without raising to producers."""
        if not batch:
            return
        try:
            await self._write_batch(batch)
        except Exception:
            self._record_failure(batch)
            self.total_dropped += len(batch)

    async def _write_batch(self, batch: list[ProvenanceRecord]) -> None:
        for record in batch:
            if record.request_id not in self._owners:
                self._capture_owner(record)
        async with self.sessionmaker() as session:
            rows = [
                LLMRequests(
                    request_id=record.request_id,
                    owner_id=self._owners[record.request_id],
                    study_id=record.study_id,
                    data_classification=record.data_classification,
                    processing_policy_id=record.processing_policy_id,
                    processing_provider_allowlist=list(record.processing_provider_allowlist),
                    processing_openrouter_upstreams=list(record.processing_openrouter_upstreams),
                    estimated_tokens=record.estimated_tokens,
                    task=str(record.task),
                    pool=record.pool,
                    persona_id=record.persona_id,
                    conversation_id=record.conversation_id,
                    created_at=record.created_at,
                    routing_path=list(record.routing_path),
                    attempts=[attempt.model_dump(mode="json") for attempt in record.attempts],
                    served_by_provider=record.served_by_provider,
                    request_model=record.served_by_model,
                    response_model=record.served_by_model,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    total_latency_ms=record.total_latency_ms,
                    success=record.success,
                )
                for record in batch
            ]
            session.add_all(rows)
            await session.commit()
        self.total_written += len(batch)
        for record in batch:
            record.persistence_status = "acknowledged"
            self.failed_records.pop(record.request_id, None)
            self._owners.pop(record.request_id, None)

    async def start(self) -> None:
        """Start the writer task."""
        if self._closed:
            raise RuntimeError("Provenance sink is closed")
        if self.writer_task is not None and not self.writer_task.done():
            return
        self.writer_running = True
        self.writer_task = asyncio.create_task(self._writer())

    async def flush(self) -> None:
        """Wait until everything enqueued so far is written or dropped."""
        await self.queue.join()

    async def stop(self, timeout_s: float = 5.0) -> None:
        """Graceful shutdown: push sentinel, wait for writer to finish.

        Args:
            timeout_s: max time to wait for writer to finish
        """
        if self._closed:
            return
        self._closed = True
        self.writer_running = False
        if self.writer_task and not self.writer_task.done():
            try:
                async with asyncio.timeout(timeout_s):
                    await self.queue.put(None)
                    await self.writer_task
            except asyncio.TimeoutError:
                logger.warning("ProvenanceSink: writer shutdown timed out")
                self.writer_task.cancel()
                await asyncio.gather(self.writer_task, return_exceptions=True)

        while not self.queue.empty():
            record = self.queue.get_nowait()
            if record is not None:
                record.persistence_status = "failed"
                self.failed_records[record.request_id] = record
                self.total_dropped += 1
            self.queue.task_done()

        logger.info(
            f"ProvenanceSink stopped: {self.total_enqueued} enqueued, "
            f"{self.total_written} written, {self.total_dropped} dropped, "
            f"{self.total_db_errors} DB errors, {self.queue_full_count} queue full"
        )
