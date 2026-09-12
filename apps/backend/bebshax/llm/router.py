"""PoolRouter — the production LLMService.

task → pool (config) → candidates from the pool's adapters in preference
order → eligibility (capabilities + context estimate + cooldowns) → attempt
loop with per-failure-kind policies -> independent remote fallback tiers.

Ranking is pool order by default; `ranker` is the injection point — production
wires the §10 quota-aware ranker there. Cooldowns are in-memory
`(provider, model) → deadline` — or `(provider, "*")` when the failure policy
scopes the cooldown to the whole provider (account-level signals such as 429)
— restored from and mirrored to `model_registry.cooldown_until` via
bebshax.db.capacity_state.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import aclosing

from bebshax.llm.adapters.base import (
    ProviderAdapter,
    RouteCandidate,
    StreamDelta,
    StreamDone,
)
from bebshax.llm.estimator import estimate_request_tokens
from bebshax.llm.failures import (
    FAILURE_POLICIES,
    AllCandidatesFailed,
    AttemptFailed,
    ContextWindowExceeded,
    FailureKind,
    LLMError,
)
from bebshax.llm.latency import DeadlineContext, DeadlineExpired, await_before, resolve_deadline
from bebshax.llm.governance import RemoteProcessingPolicy, governed_operation
from bebshax.llm.pools import POOLS, TASK_POOL_MAP, PoolConfig
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.service import (
    Entry,
    LLMService,
    ProvenanceCallback,
    _stamp_request_context,
    attempt_candidates,
    capability_skip_reason,
    exhaustion_error,
    filter_eligible,
    finalize_provenance,
    next_candidate,
    processing_skip_reason,
    request_provenance,
    stamp_deadline,
    stamp_internal_error,
)
from bebshax.llm.types import LLMRequest, LLMResult, TaskType
from bebshax.llm.validation import validate_text

DEFAULT_COOLDOWN_SECONDS = 60.0
PROVIDER_WIDE = "*"  # model slot of a provider-scoped cooldown key
PROBE_NOTE = "cooldown probe: every usable route is cooling down, trying the soonest to recover"


def cooldown_key(cand: RouteCandidate, kind: FailureKind) -> tuple[str, str]:
    """(provider, model) for route-scoped policies, (provider, "*") for
    provider-scoped ones — the same key shape persists to model_registry."""
    if FAILURE_POLICIES[kind].cooldown_scope == "provider":
        return (cand.provider, PROVIDER_WIDE)
    return (cand.provider, cand.model)


def _compact_routes(entries: list[Entry]) -> str:
    return ", ".join(f"{cand.provider}/{cand.model}" for _, cand in entries)


def _apply_preference(
    entries: list[Entry], request: LLMRequest, provenance: ProvenanceRecord
) -> list[Entry]:
    """§7 model selection: stable-partition preferred routes to the front.
    Preference is advisory — never exclusive — so fallback to Auto is free."""
    if request.preferred_provider is None and request.preferred_model is None:
        return entries

    def _matches(entry: Entry) -> bool:
        cand = entry[1]
        return (
            request.preferred_provider is None or cand.provider == request.preferred_provider
        ) and (request.preferred_model is None or cand.model == request.preferred_model)

    preferred = [e for e in entries if _matches(e)]
    rest = [e for e in entries if not _matches(e)]
    provenance.routing_path.append(
        f"[preference {request.preferred_provider or '*'}/{request.preferred_model or '*'}: "
        f"{len(preferred)} route(s) prioritized]"
    )
    return preferred + rest


class PoolRouter(LLMService):
    def __init__(
        self,
        adapters: dict[str, ProviderAdapter],
        pools: dict[str, PoolConfig] | None = None,
        task_pool_map: dict[TaskType, str] | None = None,
        on_provenance: ProvenanceCallback | None = None,
        ranker: Callable[[list[Entry]], list[Entry]] | None = None,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        initial_cooldowns: dict[tuple[str, str], float] | None = None,
        on_cooldown_change: Callable[[str, str, float], None] | None = None,
        processing_policy: RemoteProcessingPolicy | None = None,
    ) -> None:
        super().__init__()
        self._adapters = adapters
        self._processing_policy = processing_policy or RemoteProcessingPolicy()
        self._pools = pools if pools is not None else POOLS
        self._task_pool_map = task_pool_map if task_pool_map is not None else TASK_POOL_MAP
        self._on_provenance = on_provenance
        self._ranker = ranker
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        # absolute deadlines in `clock` time — CooldownStore.load_active() converts
        # wall→deadline; on_cooldown_change receives a DURATION in seconds
        self._cooldown_until: dict[tuple[str, str], float] = dict(initial_cooldowns or {})
        self._hinted_until: dict[tuple[str, str], float] = dict(initial_cooldowns or {})
        self._on_cooldown_change = on_cooldown_change
        # Routes currently being probed while cooling (half-open breaker): at
        # most one in-flight request per route, so a struggling free provider
        # is never stampeded by every waiting caller at once.
        self._probing: set[tuple[str, str]] = set()

        for pool in self._pools.values():
            unknown = [name for name in pool.adapters if name not in adapters]
            if unknown:
                raise ValueError(f"pool '{pool.name}' references unknown adapter(s): {unknown}")
        self._semaphores = {
            name: asyncio.Semaphore(p.max_concurrency) for name, p in self._pools.items()
        }
        self._active_requests: dict[str, int] = {name: 0 for name in self._pools}

    def is_cooling(self, cand: RouteCandidate) -> bool:
        """Public cooling check — observability endpoints must not touch privates."""
        return self._cooling_reason(cand) is not None

    def pool_utilization(self) -> dict[str, dict[str, int]]:
        """Real per-pool concurrency snapshot: {pool: {max_concurrency, active_requests}}."""
        return {
            name: {
                "max_concurrency": pool.max_concurrency,
                "active_requests": self._active_requests[name],
            }
            for name, pool in self._pools.items()
        }

    def _cooling_reason(self, cand: RouteCandidate) -> str | None:
        now = self._clock()
        for key in ((cand.provider, cand.model), (cand.provider, PROVIDER_WIDE)):
            until = self._cooldown_until.get(key)
            if until is not None and now < until:
                scope = " (provider-wide)" if key[1] == PROVIDER_WIDE else ""
                return f"cooling down for {until - now:.0f}s more{scope}"
        return None

    def _provider_cooling_reason(self, cand: RouteCandidate) -> str | None:
        now = self._clock()
        until = self._cooldown_until.get((cand.provider, PROVIDER_WIDE))
        if until is not None and now < until:
            return f"cooling down for {until - now:.0f}s more (provider-wide)"
        return None

    def _cooldown_remaining(self, cand: RouteCandidate) -> float:
        now = self._clock()
        return max(
            (self._cooldown_until.get(key, now) - now)
            for key in ((cand.provider, cand.model), (cand.provider, PROVIDER_WIDE))
        )

    def _probe_block_reason(self, cand: RouteCandidate) -> str | None:
        for key in ((cand.provider, cand.model), (cand.provider, PROVIDER_WIDE)):
            if self._hinted_until.get(key, 0.0) > self._clock():
                return "provider recovery hint or restored cooldown has not expired"
        return self._provider_cooling_reason(cand)

    def _cooldown_probe(
        self, entries: list[Entry], request: LLMRequest, provenance: ProvenanceRecord
    ) -> list[Entry]:
        """Half-open breaker: every otherwise-usable route is cooling down.

        Failing in 0 ms would keep a sole keyless route dark for its whole
        cooldown with nothing learned — one slow reply would then black out
        every feature for 30-60 s. Instead the routes that are capable, fit
        the context and are not already being probed are admitted in order of
        soonest recovery. A probe that fails re-arms its cooldown normally.
        Provider-wide cooldowns must expire before any route is admitted.
        """
        needed = estimate_request_tokens(request)
        probe = [
            (adapter, cand)
            for adapter, cand in entries
            if self._cooling_reason(cand) is not None
            and self._probe_block_reason(cand) is None
            and processing_skip_reason(adapter, cand, request, provenance) is None
            and capability_skip_reason(cand, request) is None
            and cand.context_window >= needed
            and (cand.provider, cand.model) not in self._probing
        ]
        tier_order: dict[int, int] = {}
        for index, (adapter, _) in enumerate(entries):
            tier_order.setdefault(id(adapter), index)
        probe.sort(key=lambda entry: (tier_order[id(entry[0])], self._cooldown_remaining(entry[1])))
        if probe:
            provenance.routing_path.append(f"[{PROBE_NOTE}: {_compact_routes(probe)}]")
        return probe

    def _start_cooldown(
        self, cand: RouteCandidate, kind: FailureKind, retry_after_s: float | None = None
    ) -> None:
        provider, model = cooldown_key(cand, kind)
        key = (provider, model)
        now = self._clock()
        seconds = FAILURE_POLICIES[kind].cooldown_seconds or self._cooldown_seconds
        if retry_after_s is not None and math.isfinite(retry_after_s) and retry_after_s > 0:
            seconds = max(seconds, retry_after_s)
            self._hinted_until[key] = max(self._hinted_until.get(key, now), now + seconds)
        until = max(self._cooldown_until.get(key, now), now + seconds)
        self._cooldown_until[key] = until
        if self._on_cooldown_change is not None:
            # fire-and-forget persistence — cooldown state must survive restarts;
            # provider-scoped cooldowns persist with model "*" and load back as-is
            self._on_cooldown_change(provider, model, until - now)

    async def _pool_entries(
        self, pool: PoolConfig, request: LLMRequest, provenance: ProvenanceRecord,
        *, adapter_names: list[str] | None = None,
    ) -> list[Entry]:
        entries: list[Entry] = []
        for adapter_name in adapter_names if adapter_names is not None else pool.adapters:
            adapter = self._adapters.get(adapter_name)
            if adapter is None:
                continue
            try:
                candidates = await governed_operation(
                    adapter.candidates_for(request), provenance.processing_provider_allowlist,
                    provenance.processing_openrouter_upstreams,
                )
                tier = [(adapter, cand) for cand in candidates]
                if not tier:
                    approved = ", ".join(provenance.processing_provider_allowlist) or "none"
                    provenance.routing_path.append(
                        f"[{adapter_name}: no eligible candidates (policy {provenance.processing_policy_id} "
                        f"approves: {approved}; classification={provenance.data_classification}; json_mode={request.json_mode})]"
                    )
            except AttemptFailed as exc:
                if exc.kind == FailureKind.INTERNAL_ERROR:
                    raise
                provenance.routing_path.append(f"[{adapter_name} discovery unavailable: {exc.kind}]")
                continue
            if self._ranker is not None:
                ranked = self._ranker(tier)
                if [candidate for _, candidate in ranked] != [candidate for _, candidate in tier]:
                    provenance.routing_path.append(
                        f"[ranker reordered: {_compact_routes(tier)} -> {_compact_routes(ranked)}]"
                    )
                tier = ranked
            entries.extend(_apply_preference(tier, request, provenance))
        return entries

    async def _eligible_entries(
        self, pool: PoolConfig, request: LLMRequest, provenance: ProvenanceRecord
    ) -> tuple[list[Entry], Callable[[RouteCandidate], str | None] | None]:
        """Eligible routes plus the per-candidate skip check the attempt loop
        must re-run. When cooldowns alone emptied the list, the cooldown probe
        is returned instead. A missing skip check marks a probe; callers must
        reserve those routes and still recheck provider-wide cooldowns."""
        entries = await self._pool_entries(pool, request, provenance)
        try:
            eligible = filter_eligible(
                entries, request, provenance, extra_skip_reason=self._cooling_reason
            )
        except AllCandidatesFailed:
            probe = self._cooldown_probe(entries, request, provenance)
            if not probe:
                raise
            return probe, None
        return eligible, self._cooling_reason

    def _mark_probing(self, entries: list[Entry]) -> set[tuple[str, str]]:
        keys = {(cand.provider, cand.model) for _, cand in entries}
        self._probing |= keys
        return keys

    async def _candidate_entries(
        self, pool: PoolConfig, request: LLMRequest, provenance: ProvenanceRecord,
        probing: set[tuple[str, str]],
    ) -> AsyncGenerator[Entry, None]:
        considered: list[Entry] = []
        had_eligible = False
        context_excluded = False
        largest_window: int | None = None
        for adapter_name in pool.adapters:
            entries = await self._pool_entries(pool, request, provenance, adapter_names=[adapter_name])
            considered.extend(entries)
            try:
                eligible = filter_eligible(entries, request, provenance, extra_skip_reason=self._cooling_reason)
            except ContextWindowExceeded as exc:
                context_excluded = True
                largest_window = max(largest_window or 0, exc.largest_window or 0)
                continue
            except AllCandidatesFailed:
                continue
            had_eligible = True
            for entry in eligible:
                yield entry
        if not had_eligible:
            probe = self._cooldown_probe(considered, request, provenance)
            if probe:
                probing.update(self._mark_probing(probe))
                for entry in probe:
                    yield entry
            elif context_excluded:
                raise ContextWindowExceeded(estimate_request_tokens(request), largest_window)
            else:
                raise AllCandidatesFailed(provenance)

    def _dispatch_skip_reason(self, candidate: RouteCandidate, probing: set[tuple[str, str]]) -> str | None:
        if (candidate.provider, candidate.model) in probing:
            return self._probe_block_reason(candidate)
        return self._cooling_reason(candidate)

    async def complete(self, request: LLMRequest, *, deadline_at: float | None = None) -> LLMResult:
        pool_name = self._task_pool_map.get(request.task)
        if pool_name is None or pool_name not in self._pools:
            raise LLMError(f"no pool mapped for task {request.task}")
        pool = self._pools[pool_name]

        provenance = request_provenance(request, self._processing_policy, pool=pool_name)
        started = time.perf_counter()
        deadline = resolve_deadline(request.task, deadline_at=deadline_at)
        task_owner = self._begin_request(request.request_id)
        probing: set[tuple[str, str]] = set()
        admitted = False
        eligible: AsyncGenerator[Entry, None] | None = None

        async def admit() -> None:
            nonlocal admitted
            await self._semaphores[pool_name].acquire()
            admitted = True
            self._active_requests[pool_name] += 1

        def release() -> None:
            self._probing.difference_update(probing)
            if admitted:
                self._active_requests[pool_name] -= 1
                self._semaphores[pool_name].release()

        try:
            _stamp_request_context(request, provenance, estimate_request_tokens(request))
            await await_before(admit(), deadline, task_owner=task_owner)
            eligible = self._candidate_entries(pool, request, provenance, probing)
            return await attempt_candidates(
                eligible, request, provenance, on_cooldown=self._start_cooldown,
                skip_reason=lambda candidate: self._dispatch_skip_reason(candidate, probing),
                deadline_at=deadline, task_owner=task_owner,
            )
        except DeadlineExpired:
            stamp_deadline(provenance)
            raise AllCandidatesFailed(provenance)
        finally:
            try:
                await finalize_provenance(provenance, self._on_provenance, started, deadline, task_owner=task_owner)
            finally:
                await self._retire_request(task_owner, release, eligible.aclose if eligible is not None else None)

    async def stream(
        self, request: LLMRequest, *, deadline_at: float | None = None
    ) -> AsyncIterator[StreamDelta | LLMResult]:
        """Streaming complete(): yields StreamDelta chunks, then the final
        LLMResult (canonical text + full provenance).

        Fallback semantics: candidates that fail BEFORE their first delta are
        skipped per the same failure policies; once a route has produced text
        the stream is committed to it — a mid-answer swap would splice two
        different personas' voices (R2), so the failure surfaces instead.
        """
        pool_name = self._task_pool_map.get(request.task)
        if pool_name is None or pool_name not in self._pools:
            raise LLMError(f"no pool mapped for task {request.task}")
        pool = self._pools[pool_name]

        provenance = request_provenance(request, self._processing_policy, pool=pool_name)
        started = time.perf_counter()
        deadline = resolve_deadline(request.task, deadline_at=deadline_at)
        task_owner = self._begin_request(request.request_id)
        probing: set[tuple[str, str]] = set()
        admitted = False
        finalized = False
        eligible: AsyncGenerator[Entry, None] | None = None

        async def admit() -> None:
            nonlocal admitted
            await self._semaphores[pool_name].acquire()
            admitted = True
            self._active_requests[pool_name] += 1

        def release() -> None:
            self._probing.difference_update(probing)
            if admitted:
                self._active_requests[pool_name] -= 1
                self._semaphores[pool_name].release()

        try:
            _stamp_request_context(request, provenance, estimate_request_tokens(request))
            await await_before(admit(), deadline, task_owner=task_owner)
            if admitted:
                try:
                    eligible = self._candidate_entries(pool, request, provenance, probing)
                    attempt_no = 0
                    while (entry := await next_candidate(eligible, deadline, task_owner=task_owner)) is not None:
                        adapter, cand = entry
                        cooling = self._dispatch_skip_reason(cand, probing)
                        if cooling is not None:
                            provenance.routing_path.append(
                                f"{cand.provider}/{cand.model} [skipped: {cooling}]"
                            )
                            continue
                        same_route_retries = 0
                        while True:
                            attempt_no += 1
                            record = AttemptRecord(
                                attempt_number=attempt_no, provider=cand.provider, model=cand.model
                            )
                            provenance.attempts.append(record)
                            t0 = time.perf_counter()
                            committed = False
                            visible_text: list[str] = []
                            try:
                                stream_context = DeadlineContext(aclosing(adapter.stream(cand, request)), deadline, task_owner=task_owner)
                                async with stream_context as adapter_stream:
                                    pending_text = ""
                                    while True:
                                        try:
                                            event = await await_before(governed_operation(
                                                anext(adapter_stream), provenance.processing_provider_allowlist,
                                                provenance.processing_openrouter_upstreams,
                                            ), deadline, task_owner=task_owner)
                                        except StopAsyncIteration:
                                            break
                                        if isinstance(event, StreamDelta):
                                            if request.json_mode:
                                                continue
                                            pending_text += event.text
                                            if committed or pending_text.strip():
                                                committed = True
                                                visible_text.append(pending_text)
                                                yield StreamDelta(text=pending_text)
                                                pending_text = ""
                                        elif isinstance(event, StreamDone):
                                            completion = event.completion
                                            await stream_context.aclose()
                                            validate_text(completion.text, request, completion.provider, completion.model, finish_reason=completion.finish_reason)
                                            if committed and "".join(visible_text) != completion.text:
                                                raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, completion.provider, completion.model, "canonical completion differs from visible text")
                                            record.latency_ms = (time.perf_counter() - t0) * 1000
                                            record.success = True
                                            if (completion.provider, completion.model) != (
                                                cand.provider,
                                                cand.model,
                                            ):
                                                record.via = f"{cand.provider}/{cand.model}"
                                            record.provider = completion.provider
                                            record.model = completion.model
                                            record.notes = list(completion.notes)
                                            record.observations = list(completion.observations)
                                            record.cached = completion.cached
                                            record.elapsed_ms = record.latency_ms
                                            if completion.latency_ms is not None:
                                                record.latency_ms = completion.latency_ms
                                            provenance.success = True
                                            provenance.served_by_provider = completion.provider
                                            provenance.served_by_model = completion.model
                                            provenance.input_tokens = completion.usage.input_tokens
                                            provenance.output_tokens = completion.usage.output_tokens
                                            finalized = True
                                            await finalize_provenance(provenance, self._on_provenance, started, deadline, task_owner=task_owner)
                                            if request.json_mode:
                                                committed = True
                                                yield StreamDelta(text=completion.text)
                                            yield LLMResult(
                                                text=completion.text,
                                                provider=completion.provider,
                                                model=completion.model,
                                                usage=completion.usage,
                                                provenance=provenance,
                                            )
                                            return
                                # Stream ended without StreamDone: treat as malformed.
                                raise AttemptFailed(
                                    FailureKind.MALFORMED_RESPONSE,
                                    cand.provider,
                                    cand.model,
                                    "stream ended without a terminal completion",
                                )
                            except DeadlineExpired as exc:
                                record.latency_ms = (time.perf_counter() - t0) * 1000
                                record.observations = list(getattr(exc, "observations", []))
                                stamp_deadline(provenance, record)
                                if committed:
                                    failure = AttemptFailed(
                                        FailureKind.TIMEOUT, record.provider, record.model,
                                        "absolute request deadline exceeded after stream commitment",
                                    )
                                    failure.provenance = provenance
                                    raise failure from exc
                                raise AllCandidatesFailed(provenance) from exc
                            except (GeneratorExit, asyncio.CancelledError) as exc:
                                # Consumer abort — but closing AFTER StreamDone was
                                # consumed lands here too (GeneratorExit at the final
                                # yield), so never overwrite a successful record.
                                if not record.success:
                                    record.elapsed_ms = (time.perf_counter() - t0) * 1000
                                    record.latency_ms = None
                                    record.failure_detail = "aborted by consumer"
                                    record.observations = list(getattr(exc, "observations", []))
                                raise
                            except AttemptFailed as failure:
                                record.latency_ms = (time.perf_counter() - t0) * 1000
                                record.failure_kind = failure.kind
                                record.failure_detail = failure.detail
                                record.observations = list(failure.observations)
                                policy = FAILURE_POLICIES[failure.kind]
                                if policy.cooldown_route and failure.provider_fault and not adapter.manages_cooldowns:
                                    self._start_cooldown(cand, failure.kind, failure.retry_after_s)
                                # Deliberate order difference from attempt_candidates:
                                # a committed route must never retry or advance — the
                                # user already saw its words (R2).
                                if committed or not policy.try_next_candidate:
                                    failure.provenance = provenance
                                    raise
                                if asyncio.get_running_loop().time() >= deadline:
                                    stamp_deadline(provenance, record)
                                    raise AllCandidatesFailed(provenance)
                                if policy.retry_same_once and same_route_retries == 0:
                                    same_route_retries += 1
                                    record.fallback_reason = "retrying same route once"
                                    continue
                                record.fallback_reason = f"advancing after {failure.kind}"
                                break
                            except AllCandidatesFailed:
                                raise
                            except Exception as exc:  # adapter bug — surface, never advance
                                raise stamp_internal_error(record, exc, t0) from exc
                    raise exhaustion_error(provenance, request)
                finally:
                    if eligible is not None and not task_owner.pending_count:
                        await eligible.aclose()
        except DeadlineExpired:
            stamp_deadline(provenance)
            raise AllCandidatesFailed(provenance)
        finally:
            try:
                if not finalized:
                    await finalize_provenance(provenance, self._on_provenance, started, deadline, task_owner=task_owner)
            finally:
                await self._retire_request(task_owner, release, eligible.aclose if eligible is not None else None)
