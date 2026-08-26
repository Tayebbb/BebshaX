"""Asynchronous provenance sink: writes LLM request records to the database
without letting DB latency/failure surface as LLM failures (RULES.md R2).

Rationale: The failure taxonomy is closed and load-bearing. A synchronous DB
write would introduce a 14th failure mode (DB latency/down) that doesn't belong
in the taxonomy. Provenance is observability; observability must never be able
to fail a request. We prefer provenance loss under backpressure over request
failure—document the trade-off explicitly.
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.db.models import LLMRequests
from bebshax.llm.provenance import ProvenanceRecord

logger = logging.getLogger(__name__)


class ProvenanceSink:
    """Synchronous sink (queue.put_nowait) + async writer task.

    The LLM path calls sink(record) synchronously and synchronously;
    the writer task runs in the background, draining and inserting.
    """

    def __init__(
        self,
        sessionmaker_: sessionmaker[AsyncSession],
        batch_size: int = 100,
        batch_timeout_ms: int = 5000,
        log_interval: int = 100,
    ):
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

    def __call__(self, record: ProvenanceRecord) -> None:
        """Synchronous sink: enqueue a provenance record.

        Never raises. On queue full, increments counter + log warning, returns.
        """
        try:
            self.queue.put_nowait(record)
            self.total_enqueued += 1
        except asyncio.QueueFull:
            self.queue_full_count += 1
            if self.queue_full_count % 10 == 0:
                logger.warning(
                    f"ProvenanceSink: queue full; dropped {self.queue_full_count} records"
                )

    async def _writer(self) -> None:
        """Background writer task: drain queue and insert to DB.

        Runs until a sentinel (None) is received. Never dies—DB errors are
        logged (rate-limited) and the batch is dropped, but the writer
        continues pulling from the queue.
        """
        batch: list[ProvenanceRecord] = []
        last_flush = asyncio.get_event_loop().time()

        while self.writer_running:
            try:
                # Drain up to batch_size or wait for batch_timeout_ms
                timeout_remaining = (
                    self.batch_timeout_ms / 1000
                    - (asyncio.get_event_loop().time() - last_flush)
                )

                if timeout_remaining > 0:
                    try:
                        record = await asyncio.wait_for(
                            self.queue.get(), timeout=timeout_remaining
                        )
                    except asyncio.TimeoutError:
                        record = None
                else:
                    record = None

                # Sentinel (None) triggers shutdown
                if record is None:
                    if batch:
                        await self._insert_batch(batch)
                    break

                batch.append(record)

                # Flush on batch full or timeout
                if len(batch) >= self.batch_size or (
                    asyncio.get_event_loop().time() - last_flush
                    >= self.batch_timeout_ms / 1000
                ):
                    await self._insert_batch(batch)
                    batch = []
                    last_flush = asyncio.get_event_loop().time()

            except Exception as e:
                logger.exception(f"ProvenanceSink writer: unexpected error: {e}")

    async def _insert_batch(self, batch: list[ProvenanceRecord]) -> None:
        """Insert a batch of records to the database.

        On failure, log (rate-limited) and drop the batch. Never re-raises.
        """
        if not batch:
            return

        try:
            async with self.sessionmaker() as session:
                records = [
                    LLMRequests(
                        request_id=r.request_id,
                        task=str(r.task),  # ProvenanceRecord.task is already a str
                        pool=r.pool,
                        persona_id=r.persona_id,
                        conversation_id=r.conversation_id,
                        created_at=r.created_at,
                        routing_path=r.routing_path,
                        # mode="json" → datetimes become ISO strings (JSON column)
                        attempts=[a.model_dump(mode="json") for a in r.attempts],
                        served_by_provider=r.served_by_provider,
                        request_model=r.served_by_model,  # OTel naming
                        response_model=r.served_by_model,
                        input_tokens=r.input_tokens,
                        output_tokens=r.output_tokens,
                        total_latency_ms=r.total_latency_ms,
                        success=r.success,
                    )
                    for r in batch
                ]
                session.add_all(records)
                await session.commit()
                self.total_written += len(batch)
        except Exception as e:
            self.total_db_errors += 1
            # Always log the FIRST error; rate-limit the rest (audit finding B1).
            if self.total_db_errors == 1 or self.total_db_errors % self.log_interval == 0:
                logger.error(
                    f"ProvenanceSink: DB error #{self.total_db_errors} "
                    f"(logging 1 per {self.log_interval} after the first): {e}"
                )
            self.total_dropped += len(batch)

    async def start(self) -> None:
        """Start the writer task."""
        self.writer_running = True
        self.writer_task = asyncio.create_task(self._writer())

    async def flush(self) -> None:
        """Wait for queue to drain (for tests)."""
        await self.queue.join()

    async def stop(self, timeout_s: float = 5.0) -> None:
        """Graceful shutdown: push sentinel, wait for writer to finish.

        Args:
            timeout_s: max time to wait for writer to finish
        """
        self.writer_running = False
        await self.queue.put(None)

        if self.writer_task:
            try:
                await asyncio.wait_for(self.writer_task, timeout=timeout_s)
            except asyncio.TimeoutError:
                logger.warning(
                    f"ProvenanceSink: writer did not finish within {timeout_s}s; cancelling"
                )
                self.writer_task.cancel()

        logger.info(
            f"ProvenanceSink stopped: {self.total_enqueued} enqueued, "
            f"{self.total_written} written, {self.total_dropped} dropped, "
            f"{self.total_db_errors} DB errors, {self.queue_full_count} queue full"
        )
