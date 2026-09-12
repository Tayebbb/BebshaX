# Remote-Only Routing

## Maintenance (2026-09-10): Request-Aware Availability

This continuation resumes the existing implementation; it is not a new audit or
production sign-off. Its edits are limited to the primary adapter, its existing
LLM test module, this handoff, and [ROUTING.md](../ROUTING.md). The parent reports
policy forwarding fixed with 21 startup tests; main/config, capacity, sink/ORM,
jobs/auth/interview/frontend, and the stable embedding-space contract were not
changed or reverified here. Existing uncommitted work is retained.

### Current Flags And Evidence

| Flag | Tested Current State / Remaining Gate |
| --- | --- |
| Strict catalog denies every route? | No. The application catalog already has `kilo/stepfun/step-3.7-flash:free`, context 262144, plain chat only. Installed SDK catalog inspection found 18 providers, 236 enabled models, and zero positive context limits; unknown model limits still cannot authorize dispatch. |
| Approved synthetic production path | Real installed AsyncPool plus the checked-in catalog serves full synthetic context through `PoolRouter.stream`. Both `freellmpool` and `kilo` must be explicitly approved. This uses an injected HTTP transport, not a live availability check. |
| Default/private processing | `RemoteProcessingPolicy` still defaults to deny. Synthetic catalog metadata and configured credentials do not enable processing or grant private consent. Parent settings/ownership wiring is preserved. |
| Request-aware context metadata | Fixed: cooling targets, exhausted shared accounts, and exhausted published SDK model allowances no longer inflate `candidates_for(request)` context. Inventory `candidates()` remains separate; discovery neither reserves nor clears quota. Context and output budgets are not shortened. |
| JSON and independent secondary | The Kilo row has `supports_json=false`, so JSON requires another explicitly verified primary row or the independent OpenRouter tier. The checked-in-catalog router test reaches controlled OpenRouter native SSE with full input, explicit JSON, upstream `only`, and `allow_fallbacks=false`. |
| Native primary streaming | Installed Freellmpool 0.11.4 `AsyncPool` has no native async streaming method or response-format argument. Supported transport/event hooks remain in use; primary streaming is honestly buffered. No dependency install or upgrade was performed. |
| Deadlines, recovery, finishes, accounting | Complete LLM scope passes existing admission/discovery/committed-stream deadlines, no-splice, maximum Retry-After/no-early-probe, JSON/finish validation, cache, alias/provenance and reservation tests. This does not establish live proxy deadlines, quality, account availability, or distributed persistence. |

### Change And Verification

The first regression advertised 200000 tokens when only an 8192-token primary
was available. RED observed two failures for cooldown/account exhaustion;
GREEN passed both. A separate SDK daily-allowance case then failed for the same
reason and passed after using the public, non-consuming
`AsyncPool.quota.over_budget` check. No assumed model windows were added.

- Five new cases: three request-context gates and two complete router-stream
	paths using the checked-in primary catalog and controlled secondary SSE.
- Two existing cooldown-callback tests now use a fixed transport clock. An
	instrumented run exposed an exact floating assertion (`3599.999999999999`
	versus `3600.0`); assertions were retained, not weakened. These tests plus all
	Retry-After/no-early-probe cases passed: **16 passed in 0.60 s**.
- Final complete LLM scope: **595 passed, 0 failed in 25.29 s**; **92.92% combined
	statement/branch coverage** for `bebshax.llm.adapters.freellmpool_adapter`,
	above the explicit 80% gate. This is module coverage, not a measured coverage
	delta. The preceding coverage run had 594 passed / 1 float-assertion failure.
- Runtime evidence: workspace Python **3.12.9**, Freellmpool **0.11.4**, httpx
	**0.28.1**. Checks used isolated synchronous child processes; full-scope pytest
	disabled dotenv loading and used `--confcutdir=apps/backend/tests/llm`.
	Inference transports were injected; no local secret file or live LLM was used.
- Local artifacts are under `.tmp/routing-continuation-*`; the final run is
	`routing-continuation-llm-verified.stdout` with empty stderr and a matching
	JUnit file. Unrelated shared-terminal output was not counted as evidence.

Live provider availability and processing entitlements remain unverified.
OpenRouter needs a key, a current verified free catalog, and explicit upstream
approval. Cross-worker quotas/cooldown refresh, durable crash/replay behavior,
API/proxy finalization, live quality/latency and independent code/security review
remain external gates. No full backend suite, deployment, commit, or push ran.
The earlier activation blocker and coordinator checklist below are historical;
use this section and the current routing document for continuation status.

## Historical Batch 1D

Date: 2026-09-09. Owned runtime implementation delivered; coordinator integration and external release gates remain. This is not production sign-off or a measured latency/quality improvement claim.

## Scope And Safety

- Changes are confined to `apps/backend/bebshax/llm/`, `apps/backend/tests/llm/`, `providers.toml`, and this authorized handoff.
- No edits to main/config/API/DB/scripts/frontend/dependency manifests. No dependency installation, live inference, server, database, secret-file access, commit, push, or deployment was requested or performed by this batch.
- Python checks used `E:/BebshaX/.venv/Scripts/python.exe` (venv metadata: 3.12.9), synchronous isolated child processes and workspace-local `.tmp/routing-batch1d/` artifacts. Isolation was necessary because concurrent workers shared the terminal.
- The local contracts, Python/security instructions, RT-01 through RT-16, removal map, and latency contract were read. External backend-patterns/TDD skill files were outside the permitted working directory; their contents were not accessed. Implementation used incremental failing-test/implementation/scoped-test cycles.

## Delivered Behavior

| ID    | Owned implementation                                                                                                                                                                                                                                                                                                              | Remaining integration or evidence                                                                                                                                                                                            |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RT-01 | All six pools, including emergency, are Freellmpool then independent OpenRouter; local pool and runtime adapter exports removed. Ranking, preferences and unhinted probes cannot promote a secondary tier. Dynamic SDK catalog filtering excludes local endpoints, Ollama Cloud, nested OpenRouter and unknown transport plugins. | Stage an app-owned catalog with verified context metadata; finish external removal map.                                                                                                                                      |
| RT-02 | One monotonic deadline covers admission, discovery, attempts, stream entry/reads, validation, bounded cancellation/cleanup and awaited provenance. Late success is rejected. Optional `deadline_at` accepts an earlier caller deadline.                                                                                           | API ingress, prompt assembly, turn/memory transaction and proxy/client finalization must propagate the same deadline. Non-cooperative work has bounded cancellation attempts; unresolved cleanup is not a success guarantee. |
| RT-03 | Actual installed AsyncPool cancellation retains concrete active-target observations, aborted/unknown consumption and no fabricated endpoint latency sample. Caller cancellation survives slow provenance cleanup.                                                                                                                 | Verify under actual network/server cancellation and durable persistence.                                                                                                                                                     |
| RT-04 | Supported `Pool`, `on_event` and `AsyncPool(apost=...)` hooks preserve structured HTTP outcomes and enforce cooldown exclusion. Transport programming errors escape the SDK broad Exception handler as INTERNAL_ERROR without fallback.                                                                                           | Release must retain/reverify the reviewed SDK hook contract.                                                                                                                                                                 |
| RT-05 | JSON is explicitly requested for OpenAI-shaped and Gemini SDK transports; full object validation uses the existing parser with incomplete-root/suffix protection. OpenRouter never drops response_format after 400.                                                                                                               | Application semantic/schema validation remains mandatory.                                                                                                                                                                    |
| RT-06 | Full verified free catalog retained before request-aware ranking; operator pins must be in current verified catalog. Unknown context, malformed/stale catalog and unavailable discovery do not authorize assumed seed limits.                                                                                                     | Token estimates are conservative heuristics, not tokenizer proofs; live catalog/capability verification remains external.                                                                                                    |
| RT-07 | Nested OpenRouter dispatch and its credential aliases are excluded from the primary. Direct OpenRouter siblings share outer provider/account cooldown scope.                                                                                                                                                                      | Cross-process account admission and quota reconciliation belong to the DB/integration owner.                                                                                                                                 |
| RT-08 | Numeric and HTTP-date Retry-After plus header/body reset hints use maximum monotonic deadlines. Shorter/out-of-order updates cannot shorten recovery; hinted/restored cooldowns cannot be half-open probed. Public hooks restore/persist concrete primary cooldowns.                                                              | Existing DB upsert is not atomic-max; implement atomic merge and shared-worker refresh.                                                                                                                                      |
| RT-09 | Both health_check methods require injected `llm_service`; diagnostics use EMERGENCY_FALLBACK, JSON validation and governed provenance. No direct diagnostic POST remains. Other serving providers/unknown models return unverified.                                                                                               | Wire shared routing adapter/service into API, preserve authorization/rate limits and expose provider/request_id.                                                                                                             |
| RT-10 | Actual stop/length/refusal/tool termination is validated; exact-budget stop is valid. SDK thinking-model token-floor expansion is corrected in the supported transport hook; requested limits are preserved.                                                                                                                      | Unreported finish reasons remain explicitly unknown, not inferred from token usage.                                                                                                                                          |
| RT-11 | Cache hits do not consume upstream quota. Attempted/succeeded/failed/aborted/unknown consumption is retained; replay by request ID is idempotent. SDK attempts reserve daily allowance before dispatch, including rejected output. Exhausted accounts are excluded.                                                               | Atomic cross-worker account reservations and DB replay of full observations remain external; legacy success-only SQL seed must be replaced.                                                                                  |
| RT-12 | Configuration-only diagnostics remain separate from governed verification; candidate existence is not used by the diagnostic to claim authenticated success.                                                                                                                                                                      | Fleet health/capacity/evaluation APIs still need configured/eligible/recent-success/unknown states and truthful denominators.                                                                                                |
| RT-13 | First non-whitespace answer text commits a route; no later retry/provider splice. Canonical text must match visible text. Classified committed errors carry provenance.                                                                                                                                                           | API SSE handling must serialize failure.kind rather than internal_error and keep persistence/done semantics atomic.                                                                                                          |
| RT-14 | Native HTTPX OpenRouter SSE supports early real text, normalized terminal/usage, bounded handshake/cleanup and validated structured buffering. Freellmpool remains explicitly buffered.                                                                                                                                           | Proxy/client stream rehearsal and measured first-text timing remain external.                                                                                                                                                |
| RT-15 | Per-target observations separate requested/reported/unknown models, endpoint latency and outer elapsed time. Managed primary metric replay filters secondary/unverified aliases.                                                                                                                                                  | DB replay must use observations' requested target and endpoint latency, never whole-adapter duration.                                                                                                                        |
| RT-16 | Tools-required requests are unavailable without a schema/execution contract. OpenRouter pins require verified zero prompt/completion price; requests enforce data_collection=deny and require_parameters=true.                                                                                                                    | Verify all billing dimensions, account privacy/retention entitlements and approved primary processing policies before release.                                                                                               |

## Installed SDK Findings

Reviewed workspace venv Freellmpool 0.11.4, without changing site-packages. `AsyncPool.achat` has no response_format or native async streaming argument. The SDK raises output token floors for thinking-model names, appends cooling targets to its candidate sequence, catches ordinary Exceptions, and constructs bare AllProvidersExhausted from `(target, reason-string)` tuples. ProviderHTTPError has status/retryable, not response headers. AllProvidersExhausted.client_status is optional and not populated by the ordinary async exhaustion loop.

The implementation therefore uses the supported injected transport and event hooks to observe actual structured outcomes before the SDK loses them. It does not invent missing exception attributes or infer new classifications from SDK error strings. Existing HTTP-body classification policy is reused. `Pool(..., cache=None, env=..., quota=...)` avoids default-config/home/plugin/hidden-answer-cache activation.

**Activation blocker:** inspected packaged providers and the checked-in overrides do not supply verified context limits. These primary targets are deliberately ineligible until approved limits are added to app-owned provider model rows (`context = <verified integer>`). Do not restore a virtual 1M or assumed 128K window to make the smoke pass. The actual-library tests supply explicit synthetic verified metadata. No library upgrade is needed for the implemented hooks; native SDK streaming would require a separately reviewed supported release/API.

## Exact Coordinator Wiring

1. In main, create/restore `QuotaLedger` and `CooldownStore` before constructing adapters. Call `build_default_adapters(quota_ledger=ledger, provider_config=repo_root / "providers.toml", initial_cooldowns=initial_cooldowns, on_cooldown_change=cooldown_store.persist)`. Stage the explicit catalog path in deployment; do not rely on FREELLMPOOL_CONFIG or a home-directory config.
2. Keep `PoolRouter(..., ranker=quota_aware_ranker(ledger), initial_cooldowns=initial_cooldowns, on_cooldown_change=cooldown_store.persist)`. Remove `warn_if_local_tier_down`, its invocation, and `app.state.local_tier_up`; revise API health fields consuming it.
3. `on_provenance` now accepts `Callable[[ProvenanceRecord], Awaitable[None] | None]`. An async callback must acknowledge the durable sink before returning; the existing `sink(record)` merely queues work and is labeled submitted, not acknowledged. Keep accounting and persistence, and do not swallow failed durable finalization.
4. Replace success-only startup aggregates with `ledger.seed_provenance(records)` over today's full ProvenanceRecords. Do not also seed the same rows using legacy aggregates. Preserve `attempts[].observations`, `elapsed_ms`, cached flags and top-level persistence status in the DB contract. Historic rows default conservatively; cached/aborted/unknown consumption must not disappear.
5. `on_cooldown_change(provider, model, seconds_remaining)` remains a synchronous callback. The model slot `"*"` denotes an account/provider cooldown. Persist `max(existing_until, incoming_until)` atomically, coordinate concurrent upsert/refresh and reload concrete primary keys into the factory as well as outer router. Windows SDK quota files are not a cross-process atomic admission system.
6. Primary metric replay tuples must be `(observation.provider, observation.requested_model, observation.latency_ms)` for genuine successful endpoint observations. Exclude cached/aborted/unknown, independent OpenRouter and legacy whole-adapter observations. Keep chronological ordering and per-target caps.
7. For the diagnostic API, use `OpenRouterService(request.app.state.llm_adapters["openrouter"])` and call `await service.health_check(model=model, llm_service=request.app.state.llm_service)`. The independent default singleton has no verified discovery catalog and must not replace the routing instance. Add optional provider/request_id to its response model; unverified is not healthy. A primary answer is allowed by routing policy but does not authenticate OpenRouter.
8. At ingress establish an absolute loop-time deadline before assembly. Pass it as `PoolRouter.complete(request, deadline_at=deadline)` or `.stream(...)`; external prompt assembly and DB turn/memory finalization must use the remaining budget. Post-commit AttemptFailed exposes `.kind` and `.provenance`; map them faithfully and never replay a committed answer.
9. Config: retain `embedding_backend="local"` as deterministic hash; allow only local/freellmpool. Remove auto/Ollama configuration and reject stale auto. Pin remote embedding models explicitly. Migrate existing embedding spaces by re-embedding complete source texts; never relabel old vectors.
10. Scripts: retire smoke_ollama, benchmark_ollama and judge_local_interview executable paths; remove demo_preflight.check_ollama and its required-model checks. Change run_cross_route_eval defaults to verified remote routes (Freellmpool primary/OpenRouter secondary); smoke_freellmpool and measure_capacity must use the explicit app catalog and report missing verified context as unavailable. No offline live-inference fallback claim remains.
11. UI/API: expose `streaming_mode` (`native` OpenRouter, `buffered` Freellmpool), not invented token-streaming/health claims. Complete the roadmap's external simulation, deployment, historical-provenance and documentation removal map.

## Files

New runtime modules: `adapters/provider_policy.py`, `adapters/freellmpool_transport.py`, `retry.py`, `validation.py` under the owned LLM package. Updated: base/embeddings/factory/Freellmpool/OpenRouter adapters; failures, latency, service/router, pools, quota, provenance, types, diagnostic service; `providers.toml`.

Ten new test modules: test_remote_accounting, test_remote_deadline_contract, test_remote_factory, test_remote_finalization, test_remote_freellmpool_sdk, test_remote_health_governor, test_remote_openrouter_contract, test_remote_provider_policy, test_remote_retry_hints, test_remote_stream_contract. Existing affected generic tests were retained and aligned with the new contracts.

**Physical deletion limitation:** three apply_patch Delete attempts reported success but left the files on disk. All executable contents of `adapters/ollama_adapter.py` were subsequently removed using Update; only a retirement docstring remains. Its exclusive transport/discovery tests were replaced with no-runtime tests; old auto-embedding/GPU-rung tests were replaced with hash/remote full-context checks. No file is falsely reported deleted. A later physical cleanup may remove the marker and adjust the retirement assertions.

## Verification Evidence

- Incremental RED/GREEN covered pool order, factory/embedding removal, provider exclusions, queue/discovery/deadlines, strict JSON/catalog metadata, recovery hints, real-SDK failures/cooling/cancellation, SSE commitment/terminal, diagnostics, accounting and finalization.
- One LLM-directory convergence run: **456 passed, 9 failed in 8.64s**, excluding five then-unremoved retired files and API/DB integration modules (`test_fast_routing_seed.py`, `test_routing_hardening_openrouter_health.py`). Eight stale generic expectations were corrected: **23 passed in 2.54s**. The removal failure was resolved as runtime retirement with the physical-file limitation above.
- Later focused shared-deadline/remote-contract sweep: **156 passed in 2.96s**. Subsequent final changes were checked at their touched scopes, not mislabeled as a fresh whole-suite pass.
- Final actual-SDK/cooldown-hook checks: **36 passed in 0.80s**. Recovery-order/hint checks: **22 passed in 0.69s**. Runtime-retirement checks: **10 passed in 0.35s**. Hash/remote-context replacements: **7 passed in 0.33s**.
- Final boundary/taxonomy/retirement/actual-SDK verification: **49 passed in 6.12s**. Final repository bug-tier Ruff: **All checks passed**. Final editor diagnostics: **no errors**. Owned `git diff --check`: **pass**. Outputs are recorded separately in `.tmp/routing-batch1d/`; no style-wide reformatting was applied.
- No full backend run, live provider/key check, DB test/server, latency percentile measurement, cross-worker persistence validation, browser rehearsal, commit, or production-readiness claim. Coordinator must run the integrated gate after wiring and verified catalog activation.
