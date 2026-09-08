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

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable

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
from bebshax.llm.latency import request_deadline_s
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.types import LLMRequest, LLMResult

Entry = tuple[ProviderAdapter, RouteCandidate]


class LLMService(ABC):
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
    if request.tools_required and not cand.supports_tools:
        return "tools unsupported"
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
        reason = (extra_skip_reason(cand) if extra_skip_reason else None) or capability_skip_reason(
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


async def attempt_candidates(
    eligible: list[Entry],
    request: LLMRequest,
    provenance: ProvenanceRecord,
    on_cooldown: Callable[[RouteCandidate, FailureKind], None] | None = None,
    skip_reason: Callable[[RouteCandidate], str | None] | None = None,
    deadline_s: float | None = None,
) -> LLMResult:
    """Policy-driven attempt loop over eligible routes. Raises
    AllCandidatesFailed with the full provenance trail on exhaustion (or
    ContextWindowExceeded when every attempt overflowed context).

    `skip_reason` is re-checked before EACH candidate: a cooldown started by an
    earlier attempt in this very request (e.g. a provider-wide 429) must skip
    the sibling routes that eligibility admitted a moment ago.

    `deadline_s` (default: the task's request budget) bounds the WHOLE chain:
    after a failed attempt the loop stops advancing once the budget is spent,
    so a caller never waits through every slow route in turn."""
    budget = request_deadline_s(request.task) if deadline_s is None else deadline_s
    loop_started = time.perf_counter()
    attempt_no = 0
    for adapter, cand in eligible:
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
                completion = await adapter.complete(cand, request)
            except AttemptFailed as failure:
                record.latency_ms = (time.perf_counter() - t0) * 1000
                record.failure_kind = failure.kind
                record.failure_detail = failure.detail
                policy = FAILURE_POLICIES[failure.kind]
                if policy.cooldown_route and on_cooldown is not None:
                    on_cooldown(cand, failure.kind, failure.retry_after_s)
                elapsed = time.perf_counter() - loop_started
                if policy.try_next_candidate and elapsed >= budget:
                    record.fallback_reason = f"stopping: request budget of {budget:.0f}s spent"
                    provenance.routing_path.append(
                        f"[deadline: {budget:.0f}s request budget spent after {attempt_no} attempt(s)]"
                    )
                    raise exhaustion_error(provenance, request)
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
            record.latency_ms = (time.perf_counter() - t0) * 1000
            record.success = True
            if (completion.provider, completion.model) != (cand.provider, cand.model):
                record.via = f"{cand.provider}/{cand.model}"
            record.provider = completion.provider  # concrete serving route
            record.model = completion.model
            record.notes = list(completion.notes)
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
        on_provenance: Callable[[ProvenanceRecord], None] | None = None,
    ) -> None:
        self._adapter = adapter
        self._on_provenance = on_provenance

    async def complete(self, request: LLMRequest) -> LLMResult:
        provenance = ProvenanceRecord(
            request_id=request.request_id,
            task=request.task.value,
            persona_id=request.persona_id,
            conversation_id=request.conversation_id,
        )
        started = time.perf_counter()
        try:
            candidates = await self._adapter.candidates()
            entries: list[Entry] = [(self._adapter, cand) for cand in candidates]
            eligible = filter_eligible(entries, request, provenance)
            return await attempt_candidates(eligible, request, provenance)
        finally:
            provenance.total_latency_ms = (time.perf_counter() - started) * 1000
            if self._on_provenance is not None:
                self._on_provenance(provenance)
