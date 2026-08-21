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
from collections.abc import Callable

from bebshax.llm.adapters.base import ProviderAdapter, RouteCandidate
from bebshax.llm.estimator import estimate_request_tokens
from bebshax.llm.failures import (
    FAILURE_POLICIES,
    AllCandidatesFailed,
    AttemptFailed,
    ContextWindowExceeded,
    FailureKind,
)
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.types import LLMRequest, LLMResult

Entry = tuple[ProviderAdapter, RouteCandidate]


class LLMService(ABC):
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResult: ...


def capability_skip_reason(cand: RouteCandidate, request: LLMRequest) -> str | None:
    if request.json_mode and not cand.supports_json:
        return "json unsupported"
    if request.tools_required and not cand.supports_tools:
        return "tools unsupported"
    return None


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


async def attempt_candidates(
    eligible: list[Entry],
    request: LLMRequest,
    provenance: ProvenanceRecord,
    on_cooldown: Callable[[RouteCandidate, FailureKind], None] | None = None,
) -> LLMResult:
    """Policy-driven attempt loop over eligible routes. Raises
    AllCandidatesFailed with the full provenance trail on exhaustion."""
    attempt_no = 0
    for adapter, cand in eligible:
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
                    on_cooldown(cand, failure.kind)
                if policy.retry_same_once and same_route_retries == 0:
                    same_route_retries += 1
                    record.fallback_reason = "retrying same route once"
                    continue
                if not policy.try_next_candidate:
                    raise  # e.g. INTERNAL_ERROR — surface, don't burn candidates
                record.fallback_reason = f"advancing after {failure.kind}"
                break
            record.latency_ms = (time.perf_counter() - t0) * 1000
            record.success = True
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

    raise AllCandidatesFailed(provenance)


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
