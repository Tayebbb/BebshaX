"""LLMService interface, shared eligibility/attempt machinery, and the
single-adapter reference implementation (kept for tests and smoke scripts;
production uses bebshax.llm.router.PoolRouter from Phase 5 on).

Guarantees kept by every implementation:
- pre-flight eligibility: capability + context-window filtering — ineligible
  routes are skipped, NEVER called, and NEVER silently truncated around;
- per-failure-kind fallback from FAILURE_POLICIES;
- a complete ProvenanceRecord for every request, success or failure.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

from bebshax.llm.adapters.base import ProviderAdapter, RouteCandidate, StreamDelta
from bebshax.llm.estimator import (
    DEFAULT_EXPECTED_OUTPUT_TOKENS,
    estimate_request_tokens,
)
from bebshax.llm.failures import (
    FAILURE_POLICIES,
    AllCandidatesFailed,
    AttemptFailed,
    ContextWindowExceeded,
    FailureKind,
    LLMError,
)
from bebshax.llm.latency import DeadlineExpired, RequestTaskOwner, await_before, resolve_deadline
from bebshax.llm.governance import RemoteProcessingPolicy, get_llm_request_context, governed_operation
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.types import LLMRequest, LLMResult
from bebshax.llm.validation import validate_text

Entry = tuple[ProviderAdapter, RouteCandidate]
ProvenanceCallback = Callable[[ProvenanceRecord], Awaitable[None] | None]


def request_provenance(
    request: LLMRequest, policy: RemoteProcessingPolicy, *, pool: str | None = None,
) -> ProvenanceRecord:
    context = get_llm_request_context()
    classification = context.data_classification if context is not None else "unknown"
    return ProvenanceRecord(
        request_id=request.request_id, task=request.task.value, pool=pool,
        persona_id=request.persona_id, conversation_id=request.conversation_id,
        owner_user_id=context.owner_user_id if context is not None else None,
        study_id=context.study_id if context is not None else None,
        data_classification=classification, processing_policy_id=policy.policy_id,
        processing_provider_allowlist=policy.allowed_providers(classification),
        processing_openrouter_upstreams=policy.allowed_openrouter_upstreams(classification),
    )


def processing_skip_reason(
    adapter: ProviderAdapter, candidate: RouteCandidate, request: LLMRequest, provenance: ProvenanceRecord,
) -> str | None:
    if request.owner_user_id is not None and request.owner_user_id != provenance.owner_user_id:
        return "processing request owner conflicts with verified ownership"
    if request.study_id is not None and request.study_id != provenance.study_id:
        return "processing request study conflicts with verified ownership"
    if not adapter.remote_processing:
        return None
    if provenance.data_classification == "unknown":
        return "remote processing requires trusted server request context"
    if candidate.provider not in provenance.processing_provider_allowlist:
        return "remote processing destination is not approved by server policy"
    if candidate.provider == "openrouter" and not provenance.processing_openrouter_upstreams:
        return "remote processing requires an approved OpenRouter upstream allowlist"
    return None


class LLMService(ABC):
    def __init__(self) -> None:
        self._request_task_owners: set[RequestTaskOwner] = set()
        self._retirement_tasks: set[asyncio.Task] = set()
        self._retirement_errors: list[BaseException] = []
        self._closed = False

    def _begin_request(self, request_id: str) -> RequestTaskOwner:
        if self._closed:
            raise RuntimeError("LLM service is closed")
        owner = RequestTaskOwner(request_id)
        self._request_task_owners.add(owner)
        return owner

    def pending_request_tasks(self) -> dict[str, int]:
        pending: dict[str, int] = {}
        for owner in self._request_task_owners:
            if owner.pending_count:
                pending[owner.request_id] = pending.get(owner.request_id, 0) + owner.pending_count
        return pending

    def _retirement_finished(self, task: asyncio.Task) -> None:
        self._retirement_tasks.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            self._retirement_errors.append(error)

    async def _retire_request(
        self, owner: RequestTaskOwner, release: Callable[[], None], cleanup: Callable[[], Awaitable] | None = None,
    ) -> None:
        async def finish() -> None:
            try:
                await owner.drain()
                if cleanup is not None:
                    await cleanup()
            finally:
                try:
                    release()
                finally:
                    self._request_task_owners.discard(owner)
                    owner.finished.set()

        if owner.pending_count:
            task = asyncio.create_task(finish(), name=f"llm-cleanup:{owner.request_id}")
            self._retirement_tasks.add(task)
            task.add_done_callback(self._retirement_finished)
        else:
            await finish()

    async def aclose(self) -> None:
        self._closed = True
        while self._request_task_owners:
            await asyncio.gather(*(owner.finished.wait() for owner in tuple(self._request_task_owners)))
        if self._retirement_tasks:
            await asyncio.shield(asyncio.gather(*tuple(self._retirement_tasks), return_exceptions=True))
        if self._retirement_errors:
            raise LLMError("request cleanup failed") from self._retirement_errors[0]

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResult: ...

    async def stream(self, request: LLMRequest) -> AsyncIterator["StreamDelta | LLMResult"]:
        """Yield StreamDelta chunks then the final LLMResult.

        Default for non-streaming implementations: resolve complete() and emit
        the whole text as one delta — identical result, no incremental render.
        """
        result = await self.complete(request)
        yield StreamDelta(text=result.text)
        yield result


def capability_skip_reason(cand: RouteCandidate, request: LLMRequest) -> str | None:
    if request.json_mode and not cand.supports_json:
        return "json unsupported"
    if request.tools_required:
        return "tools unsupported: schemas and tool execution contract are unavailable"
    if cand.max_output_tokens is not None and request.max_output_tokens is not None and request.max_output_tokens > cand.max_output_tokens:
        return "requested output budget unsupported"
    if cand.supported_parameters is not None:
        required = {"response_format"} if request.json_mode else set()
        if request.temperature is not None:
            required.add("temperature")
        if request.max_output_tokens is not None:
            required.add("max_tokens")
        if not required.issubset(cand.supported_parameters):
            return "requested parameters unsupported"
    return None


def _stamp_request_context(
    request: LLMRequest, provenance: ProvenanceRecord, needed_tokens: int
) -> None:
    """Record the pre-flight estimate and the request parameters ONCE per
    request so provenance explains every eligibility decision."""
    if provenance.estimated_tokens is not None:
        return
    provenance.estimated_tokens = needed_tokens
    max_output = (
        str(request.max_output_tokens)
        if request.max_output_tokens is not None
        else f"{DEFAULT_EXPECTED_OUTPUT_TOKENS} (default)"
    )
    provenance.routing_path.append(
        f"[context estimate ~{needed_tokens} tokens incl. max_output {max_output}]"
    )
    provenance.routing_path.append(
        f"[params temperature={request.temperature} "
        f"max_output_tokens={request.max_output_tokens} json_mode={request.json_mode}]"
    )


def filter_eligible(
    entries: list[Entry],
    request: LLMRequest,
    provenance: ProvenanceRecord,
    extra_skip_reason: Callable[[RouteCandidate], str | None] | None = None,
) -> list[Entry]:
    """Pre-flight filtering; every considered route lands in routing_path.

    Raises ContextWindowExceeded when only context exclusions emptied the
    list (never truncate), AllCandidatesFailed when nothing was eligible.
    """
    needed_tokens = estimate_request_tokens(request)
    _stamp_request_context(request, provenance, needed_tokens)
    eligible: list[Entry] = []
    context_excluded = False
    largest_capable_window: int | None = None
    for adapter, cand in entries:
        reason = processing_skip_reason(adapter, cand, request, provenance) or (extra_skip_reason(cand) if extra_skip_reason else None) or capability_skip_reason(
            cand, request
        )
        if reason is not None:
            provenance.routing_path.append(f"{cand.provider}/{cand.model} [skipped: {reason}]")
            continue
        largest_capable_window = max(largest_capable_window or 0, cand.context_window)
        if cand.context_window < needed_tokens:
            context_excluded = True
            provenance.routing_path.append(
                f"{cand.provider}/{cand.model} "
                f"[skipped: context {cand.context_window} < ~{needed_tokens}]"
            )
            continue
        eligible.append((adapter, cand))
        provenance.routing_path.append(f"{cand.provider}/{cand.model}")

    if not eligible:
        if context_excluded:
            raise ContextWindowExceeded(needed_tokens, largest_capable_window)
        raise AllCandidatesFailed(provenance)
    return eligible


def exhaustion_error(provenance: ProvenanceRecord, request: LLMRequest) -> LLMError:
    """Error for a request that ran out of candidates.

    When EVERY attempt overflowed a context window the honest failure is
    ContextWindowExceeded (413, never truncate) — pre-flight could not catch
    it because aggregating adapters advertise a virtual window and learn the
    real per-model limits only at call time. Anything else is
    AllCandidatesFailed with the full trail.
    """
    attempts = provenance.attempts
    if attempts and all(a.failure_kind == FailureKind.CONTEXT_WINDOW_EXCEEDED for a in attempts):
        estimate = (
            provenance.estimated_tokens
            if provenance.estimated_tokens is not None
            else estimate_request_tokens(request)
        )
        return ContextWindowExceeded(estimate, None)
    return AllCandidatesFailed(provenance)


def stamp_internal_error(record: AttemptRecord, exc: Exception, started: float) -> AttemptFailed:
    """An adapter raised something other than AttemptFailed: that is a bug in
    OUR layer (R6). Stamp the attempt and return the wrapped failure to raise
    — the chain must not advance and the cause must stay attached."""
    record.latency_ms = (time.perf_counter() - started) * 1000
    record.failure_kind = FailureKind.INTERNAL_ERROR
    record.failure_detail = f"{type(exc).__name__}: {exc}"[:300]
    return AttemptFailed(
        FailureKind.INTERNAL_ERROR, record.provider, record.model, record.failure_detail
    )


def stamp_deadline(provenance: ProvenanceRecord, record: AttemptRecord | None = None) -> None:
    provenance.success = False
    provenance.routing_path.append("[deadline: absolute request budget spent]")
    if record is not None:
        record.success = False
        record.failure_kind = FailureKind.TIMEOUT
        record.failure_detail = "absolute request deadline exceeded"
        record.fallback_reason = "stopping: absolute request budget spent"
        record.notes.append("application deadline; not a provider health observation")


async def finalize_provenance(
    provenance: ProvenanceRecord, callback: ProvenanceCallback | None, started: float, deadline: float,
    *, task_owner: RequestTaskOwner | None = None,
) -> None:
    original_error = sys.exception()
    preserving_abort = isinstance(original_error, (asyncio.CancelledError, GeneratorExit))
    provenance.total_latency_ms = (time.perf_counter() - started) * 1000
    try:
        if callback is not None:
            outcome = callback(provenance)
            if inspect.isawaitable(outcome):
                provenance.persistence_status = "unknown"
                await await_before(outcome, deadline, task_owner=task_owner)
                provenance.persistence_status = "acknowledged"
            else:
                provenance.persistence_status = "submitted"
        if provenance.success and asyncio.get_running_loop().time() >= deadline:
            raise DeadlineExpired("finalization deadline exceeded")
    except asyncio.CancelledError:
        provenance.success = False
        provenance.persistence_status = "unknown"
        raise
    except DeadlineExpired as exc:
        provenance.persistence_status = "unknown"
        if preserving_abort:
            return
        stamp_deadline(provenance)
        raise AllCandidatesFailed(provenance) from exc
    except Exception as exc:
        provenance.success = False
        provenance.persistence_status = "failed"
        if preserving_abort:
            return
        raise LLMError("provenance finalization failed") from exc
    finally:
        provenance.total_latency_ms = (time.perf_counter() - started) * 1000


async def next_candidate(
    entries: Iterator[Entry] | AsyncIterator[Entry], deadline: float, *, task_owner: RequestTaskOwner | None = None,
) -> Entry | None:
    if isinstance(entries, AsyncIterator):
        try:
            return await await_before(anext(entries), deadline, task_owner=task_owner)
        except StopAsyncIteration:
            return None
    return next(entries, None)


async def attempt_candidates(
    eligible: list[Entry] | AsyncIterator[Entry],
    request: LLMRequest,
    provenance: ProvenanceRecord,
    on_cooldown: Callable[[RouteCandidate, FailureKind, float | None], None] | None = None,
    skip_reason: Callable[[RouteCandidate], str | None] | None = None,
    deadline_s: float | None = None,
    deadline_at: float | None = None,
    task_owner: RequestTaskOwner | None = None,
) -> LLMResult:
    """Policy-driven attempt loop over eligible routes. Raises
    AllCandidatesFailed with the full provenance trail on exhaustion (or
    ContextWindowExceeded when every attempt overflowed context).

    `skip_reason` is re-checked before EACH candidate: a cooldown started by an
    earlier attempt in this very request (e.g. a provider-wide 429) must skip
    the sibling routes that eligibility admitted a moment ago.

    `deadline_at` is inherited from admission; direct callers may supply a
    duration through the backwards-compatible `deadline_s` argument."""
    deadline = resolve_deadline(request.task, deadline_at=deadline_at, budget_s=deadline_s)
    attempt_no = 0
    entries = iter(eligible) if isinstance(eligible, list) else eligible
    while (entry := await next_candidate(entries, deadline, task_owner=task_owner)) is not None:
        adapter, cand = entry
        reason = skip_reason(cand) if skip_reason is not None else None
        if reason is not None:
            provenance.routing_path.append(f"{cand.provider}/{cand.model} [skipped: {reason}]")
            continue
        same_route_retries = 0
        while True:
            attempt_no += 1
            record = AttemptRecord(
                attempt_number=attempt_no, provider=cand.provider, model=cand.model
            )
            provenance.attempts.append(record)
            t0 = time.perf_counter()
            try:
                completion = await await_before(governed_operation(
                    adapter.complete(cand, request), provenance.processing_provider_allowlist,
                    provenance.processing_openrouter_upstreams,
                ), deadline, task_owner=task_owner)
                validate_text(completion.text, request, completion.provider, completion.model, finish_reason=completion.finish_reason)
            except DeadlineExpired as exc:
                record.elapsed_ms = (time.perf_counter() - t0) * 1000
                record.observations = list(getattr(exc, "observations", []))
                stamp_deadline(provenance, record)
                raise AllCandidatesFailed(provenance)
            except asyncio.CancelledError as exc:
                record.elapsed_ms = (time.perf_counter() - t0) * 1000
                record.failure_detail = "aborted by consumer; upstream consumption unknown"
                record.observations = list(getattr(exc, "observations", []))
                raise
            except AttemptFailed as failure:
                record.latency_ms = (time.perf_counter() - t0) * 1000
                record.failure_kind = failure.kind
                record.failure_detail = failure.detail
                record.observations = list(failure.observations)
                policy = FAILURE_POLICIES[failure.kind]
                if policy.cooldown_route and failure.provider_fault and not adapter.manages_cooldowns and on_cooldown is not None:
                    on_cooldown(cand, failure.kind, failure.retry_after_s)
                if asyncio.get_running_loop().time() >= deadline:
                    stamp_deadline(provenance, record)
                    raise AllCandidatesFailed(provenance)
                if policy.retry_same_once and same_route_retries == 0:
                    same_route_retries += 1
                    record.fallback_reason = "retrying same route once"
                    continue
                if not policy.try_next_candidate:
                    raise  # e.g. INTERNAL_ERROR — surface, don't burn candidates
                record.fallback_reason = f"advancing after {failure.kind}"
                break
            except Exception as exc:  # adapter bug — never advance past our own defects
                raise stamp_internal_error(record, exc, t0) from exc
            record.elapsed_ms = (time.perf_counter() - t0) * 1000
            record.latency_ms = completion.latency_ms if completion.latency_ms is not None else record.elapsed_ms
            record.success = True
            if (completion.provider, completion.model) != (cand.provider, cand.model):
                record.via = f"{cand.provider}/{cand.model}"
            record.provider = completion.provider  # concrete serving route
            record.model = completion.model
            record.notes = list(completion.notes)
            record.observations = list(completion.observations)
            record.cached = completion.cached
            provenance.success = True
            provenance.served_by_provider = completion.provider
            provenance.served_by_model = completion.model
            provenance.input_tokens = completion.usage.input_tokens
            provenance.output_tokens = completion.usage.output_tokens
            return LLMResult(
                text=completion.text,
                provider=completion.provider,
                model=completion.model,
                usage=completion.usage,
                provenance=provenance,
            )

    raise exhaustion_error(provenance, request)


class SingleAdapterLLMService(LLMService):
    def __init__(
        self,
        adapter: ProviderAdapter,
        on_provenance: ProvenanceCallback | None = None,
        *, processing_policy: RemoteProcessingPolicy | None = None,
    ) -> None:
        super().__init__()
        self._adapter = adapter
        self._on_provenance = on_provenance
        self._processing_policy = processing_policy or RemoteProcessingPolicy()

    async def complete(self, request: LLMRequest, *, deadline_at: float | None = None) -> LLMResult:
        provenance = request_provenance(request, self._processing_policy)
        started = time.perf_counter()
        deadline = resolve_deadline(request.task, deadline_at=deadline_at)
        task_owner = self._begin_request(request.request_id)
        try:
            _stamp_request_context(request, provenance, estimate_request_tokens(request))
            candidates = await await_before(governed_operation(
                self._adapter.candidates_for(request), provenance.processing_provider_allowlist,
                provenance.processing_openrouter_upstreams,
            ), deadline, task_owner=task_owner)
            entries: list[Entry] = [(self._adapter, cand) for cand in candidates]
            eligible = filter_eligible(entries, request, provenance)
            return await attempt_candidates(eligible, request, provenance, deadline_at=deadline, task_owner=task_owner)
        except DeadlineExpired:
            stamp_deadline(provenance)
            raise AllCandidatesFailed(provenance)
        finally:
            try:
                await finalize_provenance(provenance, self._on_provenance, started, deadline, task_owner=task_owner)
            finally:
                await self._retire_request(task_owner, lambda: None)
