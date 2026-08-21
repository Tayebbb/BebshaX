"""Reference `LLMService` implementation (single adapter) used until the
Phase-5 multi-pool router replaces the selection strategy.

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
from bebshax.llm.failures import (
    FAILURE_POLICIES,
    AllCandidatesFailed,
    AttemptFailed,
    ContextWindowExceeded,
)
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.types import LLMRequest, LLMResult

DEFAULT_EXPECTED_OUTPUT_TOKENS = 1024
_CHARS_PER_TOKEN = 4  # coarse heuristic; replaced by a real estimator in Phase 5


def estimate_request_tokens(request: LLMRequest) -> int:
    input_chars = sum(len(m.content) for m in request.messages)
    expected_output = request.max_output_tokens or DEFAULT_EXPECTED_OUTPUT_TOKENS
    return input_chars // _CHARS_PER_TOKEN + expected_output


class LLMService(ABC):
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResult: ...


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
            return await self._run(request, provenance)
        finally:
            provenance.total_latency_ms = (time.perf_counter() - started) * 1000
            if self._on_provenance is not None:
                self._on_provenance(provenance)

    async def _run(self, request: LLMRequest, provenance: ProvenanceRecord) -> LLMResult:
        candidates = await self._adapter.candidates()
        needed_tokens = estimate_request_tokens(request)

        eligible: list[RouteCandidate] = []
        context_excluded = False
        largest_capable_window: int | None = None
        for cand in candidates:
            skip = self._capability_skip_reason(cand, request)
            if skip is not None:
                provenance.routing_path.append(f"{cand.provider}/{cand.model} [skipped: {skip}]")
                continue
            largest_capable_window = max(largest_capable_window or 0, cand.context_window)
            if cand.context_window < needed_tokens:
                context_excluded = True
                provenance.routing_path.append(
                    f"{cand.provider}/{cand.model} "
                    f"[skipped: context {cand.context_window} < ~{needed_tokens}]"
                )
                continue
            eligible.append(cand)
            provenance.routing_path.append(f"{cand.provider}/{cand.model}")

        if not eligible:
            if context_excluded:
                raise ContextWindowExceeded(needed_tokens, largest_capable_window)
            raise AllCandidatesFailed(provenance)

        attempt_no = 0
        for cand in eligible:
            same_route_retries = 0
            while True:
                attempt_no += 1
                record = AttemptRecord(
                    attempt_number=attempt_no, provider=cand.provider, model=cand.model
                )
                provenance.attempts.append(record)
                t0 = time.perf_counter()
                try:
                    completion = await self._adapter.complete(cand, request)
                except AttemptFailed as failure:
                    record.latency_ms = (time.perf_counter() - t0) * 1000
                    record.failure_kind = failure.kind
                    record.failure_detail = failure.detail
                    policy = FAILURE_POLICIES[failure.kind]
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

    @staticmethod
    def _capability_skip_reason(cand: RouteCandidate, request: LLMRequest) -> str | None:
        if request.json_mode and not cand.supports_json:
            return "json unsupported"
        if request.tools_required and not cand.supports_tools:
            return "tools unsupported"
        return None
