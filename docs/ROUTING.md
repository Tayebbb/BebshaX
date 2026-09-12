# BebshaX — Routing

Current remote-only routing policy, local verification, and integration requirements.

**Persona ML boundary (2026-09-09):** business, study/jobs/regeneration, workflow
role, and dataset persona generation use the shared CPU `MLPersonaAdapter`, not
this request path. No LLM call or fallback writes those profiles. Copilot context,
role suggestions, interviews, memory, and other LLM features keep the existing
router. Source/model provenance is stored with the persona; it is not a synthetic
`llm_requests` entry. See [PERSONA_ENGINE.md](PERSONA_ENGINE.md).

## Current Policy (2026-09-10)

The approved policy is Freellmpool primary, independent OpenRouter secondary.
All six production pools use that order. Local and cloud Ollama, nested
OpenRouter primary routes, provider plugins, home-directory catalogs, and
legacy environment-selected catalogs cannot restore excluded inference.
Hash embeddings remain a separate network-free component. There is no offline
live-inference guarantee and no claim that free access establishes privacy.

### Request And Processing Ownership

Every completion or stream uses `LLMService` with an explicit `TaskType`.
`PoolRouter` and `SingleAdapterLLMService` take an optional `processing_policy`:
`RemoteProcessingPolicy` defaults to deny. A trusted server boundary must set
`llm_request_context(LLMRequestContext(...))` after authenticating ownership and
classifying the data; request body fields never grant approval.

- `private` context requires `owner_user_id`. Optional `study_id` is captured
    from the same trusted boundary. Conflicting caller ownership is rejected.
- Synthetic and private provider allowlists are separate immutable policy
    fields. Primary dispatch requires approval of both `freellmpool` and the
    concrete catalog provider ID. Outer-tier approval alone is insufficient.
- OpenRouter also requires the applicable `synthetic_openrouter_upstreams` or
    `private_openrouter_upstreams`. Dispatch sends `provider.only`,
    `allow_fallbacks=false`, `require_parameters=true`, `data_collection=deny`, and
    zero prompt/completion `max_price`. Account/provider terms still require
    independent operator review; these settings are not a ZDR certification.
- Provenance records immutable `owner_user_id`, `study_id`,
    `data_classification`, `processing_policy_id`,
    `processing_provider_allowlist`, and `processing_openrouter_upstreams`.
    Missing server context is `unknown`, not anonymous-public permission.
- New adapters default to `remote_processing=True`; only explicit network-free
    test adapters opt out. Context snapshots propagate per operation, not across
    stream yields or unrelated requests.

### Pools, Deadlines, And Streaming

| Pool | Adapter Order | Concurrency |
| --- | --- | --- |
| reasoning | freellmpool, openrouter | 2 |
| conversation | freellmpool, openrouter | 5 |
| long_context | freellmpool, openrouter | 2 |
| structured | freellmpool, openrouter | 3 |
| fast | freellmpool, openrouter | 5 |
| emergency | freellmpool, openrouter | 2 |

The exhaustive 18-task mapping remains in
[pools.py](../apps/backend/bebshax/llm/pools.py). Compatibility persona task
entries do not re-enable LLM persona generation.

Discovery is lazy by tier. A ready primary is attempted before secondary
catalog discovery; rankers and caller preferences cannot promote the secondary.
One monotonic deadline covers admission, discovery, attempts, stream reads,
and provenance finalization. Late success is rejected. Cancellation and
application deadlines are not fabricated provider health/latency samples.
Request-owned resistant tasks retain admission until they finish;
`pending_request_tasks()` exposes outstanding work and `LLMService.aclose()`
stops new admission and drains it. A non-cooperative operation cannot be killed
by Python cancellation; drain may outlast the response deadline and must remain
visible to the parent's shutdown policy.

OpenRouter uses native HTTP SSE through the installed httpx API; its owned
client disables environment proxies and redirects. Real nonempty answer text
commits the route; empty/whitespace events do not. Committed errors
remain classified and never splice a fallback answer. JSON streams buffer until
a complete validated object exists. A terminal event, consistent serving-model
identity, finish reason, and canonical text are checked before completion.

Freellmpool remains `streaming_mode="buffered"`: installed 0.11.4 `AsyncPool`
has no native async streaming method. Its full completion becomes one delta;
this is not time-to-first-token streaming. No new library was installed and no
private SDK streaming API was assumed.

### Verified Capabilities And Readiness

Freellmpool construction uses supported `Pool(providers, ...)`,
`AsyncPool(pool, apost=...)`, and event hooks. The existing
[provider policy](../apps/backend/bebshax/llm/adapters/provider_policy.py) filters
remote HTTPS destinations and excluded services. Its transport retains
per-target status, retry hints, requested/reported model identity, finish reason,
usage, outcome, and known/unknown consumption. JSON is requested and validated;
an exact-budget `stop` is valid while a length termination is rejected. Context
and requested output are never shortened; tool execution remains unavailable.

Local inspection of installed **freellmpool 0.11.4** on 2026-09-09 found **18
packaged providers, 236 enabled models, and 0 positive known context limits**.
The SDK `Model` exposes only name, daily quota, enabled state, and context.
Application-owned model rows must provide verified positive `context`; structured
requests additionally require explicit `supports_json=true`. The adapter also
accepts `json_models=frozenset({(provider_id, model_name), ...})` for reviewed
injected catalogs. Unknown JSON metadata does not remove a verified plain-chat
route, and JSON virtual context is computed only from JSON-approved models.
Request-aware `candidates_for(request)` additionally excludes cooling targets,
exhausted shared accounts, and exhausted published SDK model allowances before
computing that window. A blocked large model cannot advertise space on behalf
of a smaller available model. `candidates()` remains catalog inventory, not an
availability claim. These discovery checks neither reserve nor clear quota;
dispatch retains its own final admission checks.

The 2026-09-10 public [Kilo model catalog](https://api.kilo.ai/api/gateway/models)
reports `stepfun/step-3.7-flash:free` with `context_length=262144`, the same
top-provider context, and zero prompt/completion prices. The checked-in override
now records that limit. Its supported parameters do not include a JSON response
format, so `supports_json=false`; descriptive marketing copy is not capability
verification. `poolside/laguna-xs.2:free` was absent and is disabled. The catalog
inspection sent no prompt or credentials and proves neither current inference
availability nor latency. Other unknown limits remain ineligible.

Kilo marks this model `mayTrainOnYourPrompts=true`. Metadata does not authorize
processing: the default policy still denies remote dispatch, and synthetic
requests require separate approval of both `freellmpool` and `kilo`. Private
content must not inherit that approval. Operators must review metadata freshness
and processor terms before enabling a destination; no verified private processor
approval or live quality measurement is claimed here.

OpenRouter requires a legitimately owned key plus current verified `:free`
catalog entries with zero prompt/completion price, positive context, supported
parameters, and approved upstream processing. All eligible catalog models are
retained until request-specific filtering; pins and seed names cannot authorize
unknown, stale, or paid models. Configuration GETs do not run inference and
candidate presence is not a successful health probe. Diagnostics require an
injected governed service, explicit task, provenance, and a valid response.

### Recovery And Accounting

Numeric/date `Retry-After`, supported reset headers, and nested provider hints
use the longest valid recovery duration. Shorter/out-of-order updates never
shorten cooldowns. Hinted/restored cooldowns prohibit early half-open probes;
unhinted route probes retain tier order and never override capabilities or
privacy. Primary cooldowns belong to concrete targets, not the virtual tier.

`CooldownStore` performs atomic maximum-deadline upserts on PostgreSQL/SQLite,
retains pending write tasks, and shields them from a cancelled drain. The model
registry provider/model uniqueness constraint is required. Replay preserves the
existing DB `owner_id` as `owner_user_id`; absent reported models stay `unknown`
instead of promoting a requested alias.

The factory shares `QuotaLedger.reserve_attempt` between primary and secondary.
In-process reservation occurs before HTTP so concurrent requests cannot both
spend the last account slot. `ProviderObservation.account_reservation_id` avoids
double charging during provenance finalization. Cached/skipped, attempted,
succeeded, failed, aborted, and unknown-consumption outcomes remain distinct.
Failed/rejected generated responses consume allowance. Published inner-model
allowance also gates Freellmpool transport.

Reservations and live eligibility are **not a distributed account-admission
service**. Cross-process quota transactions, crash-safe pending reservations,
and live cross-worker cooldown refresh remain parent integration requirements.
Atomic cooldown persistence alone does not prove those properties.

### Remote Embeddings

`build_embedding_backend(backend="local", model=None, *, provider_config=None,
processing_policy=None)` now accepts the startup factory keyword. Hash output
and `local-hash-384` are unchanged; `auto`, `ollama`, and unknown names fail.

`FreellmpoolEmbedding(model, pool=None, *, provider_config=None, transport=None,
timeout_s=30.0, processing_policy=None)` uses an explicit application catalog,
not `Pool.from_default_config`. Unmanaged pool injection is rejected; tests may
inject a sync httpx transport. Exactly one approved, configured OpenAI-compatible
or Cloudflare destination must contain the enabled pinned model with a verified
positive context. Ambiguous model names across providers fail rather than
silently changing vector spaces. Explicit catalog approval defaults only to
trusted synthetic requests; private data additionally needs an independent
server processing policy approving the exact destination.

Inputs remain complete and use the shared conservative estimator. Oversize or
unknown contexts fail before HTTP. Responses must match input count and ordered
indices, preserve the pinned model when reported, and contain finite nonzero
native 384-dimensional vectors. No truncation, zero padding, or cross-provider
fallback occurs. Vectors are normalized without resizing, under
`freellmpool:<provider>:<model>:native-384`; historical
`freellmpool:<model>` projected vectors are not relabeled or compared to them.
Existing remote vector inventories need deliberate re-embedding/backfill; a
native dimension other than 384 requires parent storage integration, not a slice.

The reusable HTTP client refuses redirects and environment proxies. Attempt
quotas count failed/rejected work once, with no SDK success double count;
HTTP-date recovery hints block early follow-up calls. Embedding recovery state is
currently instance-local, so restart/multi-worker recovery sharing remains a gap.
An empty batch performs no discovery. A deadline covers queueing and HTTP;
cancellation leaves the worker task owning its lock until the sync thread stops.
`aclose()` stops admission, waits for owned workers, then closes transport;
cancelling the close await does not abandon that drain.

### Parent Integration Requirements

1. Startup now passes typed `Settings.remote_processing_policy` to `PoolRouter`
    and remote embeddings, preserving the deny default. No further main/config
    change is requested for that interface. Owners must still verify trusted
    `llm_request_context` at each authenticated request/job and diagnostic
    boundary; client approval fields or configured keys never supply consent.
2. Persist new immutable provenance fields and per-observation reservation IDs.
     The shared table already has `owner_id`; map `owner_user_id` to it without
     deriving ownership later from a persona. Study/classification/policy fields
     need coordinated sink/schema/migration handling. This change does not edit
     the shared sink, models, API, or Alembic files.
3. Startup already registers the router as an owned resource and its async
    provenance callback awaits `sink.persist(record)`. Preserve those contracts
    through shutdown; verify durable database acknowledgement and crash/restart
    behavior independently. Propagate committed `AttemptFailed` through API SSE
    without translating every failure to `internal_error` or mixing providers.
4. Keep endpoint readiness/configuration distinct from inference success, wire
     shared cross-worker account admission, verify actual processing terms and
     metadata, and complete PostgreSQL/full-stack verification independently.

### API Contract Changes (2026-09-10)

- `GET /api/routes/status` now uses the shared runtime observation snapshot.
    `configured`, `available`, `degraded`, `unavailable` and `unknown` are distinct;
    candidate presence is never `healthy`. `candidate_count` is a catalog count,
    not a live fleet count. `available_models` is null for an unresolved virtual
    route or missing cooldown state, and zero when all candidates are cooling.
    `recent_success` remains a separate historical observation. Request-specific
    processing/capability approval is still required before inference.
- A legacy `ollama` identifier has type `unknown`, not inferred local/cloud
    attribution. Evaluation `local_serve_rate` is null because locality was not
    measured; `historical_ollama_provider_rate` retains the counted label share,
    and `metrics_window.route_kind_measured=false` records that limit. Aborted
    inner observations do not classify a provider as degraded.
- `GET /api/provenance` exposes `requested_model` separately. `served_by_model`
    uses the recorded response model, or `unknown`; it never substitutes a
    requested alias. Existing rows are not rewritten.
- `POST /api/health/openrouter/test` stamps the authenticated owner's identity
    and trusted synthetic classification around its fixed server-authored probe.
    Deny-default and missing-upstream policies still prohibit dispatch. Its GET
    remains configuration-only and produces no inference or provenance event.

The frontend/API-contract owner must accept the new status values and nullable
metrics without rendering unknown as zero. The journey assertion in
[test_tournaments_e2e.py](../apps/backend/tests/api/test_tournaments_e2e.py)
still assumes numeric `local_serve_rate`; its owner must update that assertion
and verify the journey. It was not edited or executed here.

The separate health owner must reconcile cancellation in
`record_provider_observations`: its current candidate-observation filter admits
`aborted` work as a failed health sample. The evaluator is corrected here, but
the shared runtime snapshot may still report degradation after cancellation.
No edit to shared health/startup/auth/persistence files is part of this scope.

### Latest Routing-Only Verification (2026-09-10)

This continuation changes only the primary adapter, its existing SDK test
module, this document, and [the routing handoff](audits/modernization-routing.md).
The parent-reported 21 startup tests/policy-forwarding fix is preserved, not
rerun. No main/config, capacity, sink/ORM, embedding-space, jobs/auth/interview,
frontend, provider-template, or dependency change was needed.

The request-context bug was observed RED: a cooling or account-exhausted
200000-token model inflated an available 8192-token route. A further failing
case covered the SDK's published daily model allowance. All three now pass
without assuming context limits, consuming quota during discovery, or relaxing
processing policy. Two additional `PoolRouter.stream` tests prove the checked-in
plain-chat primary and independently configured JSON secondary preserve full
synthetic identity/memory/evidence, requested output, visible/canonical text,
terminal finish reason, processing restrictions and provenance. Secondary SSE
uses a controlled free-model catalog; it is not a live OpenRouter model claim.

Final complete LLM scope: **595 passed, 0 failed in 25.29 s**, with **92.92%
combined statement/branch coverage** for the changed Freellmpool adapter (80%
required). Five cases were added. Two existing exact cooldown-duration tests
were made deterministic with a fixed transport clock after the instrumented
run exposed float cancellation; their assertions remain exact. The focused
cooldown/Retry-After/no-early-probe selection passed **16 tests in 0.60 s**.
No comparable pre-change coverage delta was collected.

Installed-library inspection reconfirmed Python 3.12.9, Freellmpool 0.11.4,
httpx 0.28.1, no native async SDK streaming API, and the catalog counts above.
The current gate is explicit processing approval, not a deny-all catalog bug:
plain primary chat has one verified Kilo row; primary JSON metadata is absent;
independent OpenRouter requires its own key, verified free catalog and upstream
allowlist. Default/private processing remains denied without the applicable
server policy. Native primary streaming, live availability/quality/latency,
cross-worker quota/persistence, API/proxy finalization and independent review
are not certified by these tests. No live LLM, dotenv access, dependency install,
full backend run, commit or push was performed.

Pytest used the existing dotenv-disabled bootstrap below with
`apps/backend/tests/llm --confcutdir=apps/backend/tests/llm -q --tb=short`,
`--cov=bebshax.llm.adapters.freellmpool_adapter --cov-branch --cov-fail-under=80`,
and an isolated coverage file. Final stdout/JUnit and coverage JSON are under
`.tmp/routing-continuation-*`; unrelated shared-terminal output is excluded.

### Maintenance Evidence (2026-09-10)

The following API/routing record is earlier evidence. The latest routing-only
verification above supersedes its final test counts and continuation status.

This continuation edits the three assigned API modules, their direct tests,
LLM tests, provider configuration and three owned routing documents. Existing
uncommitted implementation is retained; shared startup/configuration,
persistence and execution-ledger files are not edited. Interpreter: workspace
`.venv` Python 3.12.9; installed Freellmpool
0.11.4 and httpx 0.28.1. No dependency change, live LLM call, external database,
or git publication is part of this run.

Commands below use `E:\BebshaX\.venv\Scripts\python.exe -m pytest` from the
repository root with `-q --no-cov --tb=short`:

| Selection | Observed Result |
| --- | --- |
| `apps/backend/tests/llm/test_remote_provider_policy.py apps/backend/tests/llm/test_remote_governance.py apps/backend/tests/llm/test_remote_freellmpool_sdk.py apps/backend/tests/llm/test_remote_openrouter_contract.py apps/backend/tests/llm/test_openrouter_catalogue_discovery.py` | Baseline: 103 passed, 1.82 s. |
| `apps/backend/tests/llm/test_remote_freellmpool_sdk.py -k app_catalog_exposes_a_context_verified_keyless_primary_candidate` | RED: 1 failed / 34 deselected, 0.65 s; GREEN: 1 passed / 34 deselected, 0.06 s. An earlier import-interrupted run is not test evidence. |
| `apps/backend/tests/llm` | Before the envelope fixture repair: 566 passed / 22 failed, 12.83 s. |
| `apps/backend/tests/llm/test_exhibition_routing_openrouter_envelopes.py` | All 22 repaired cases passed as part of the next LLM run: 588 passed, 15.29 s. Early shared-terminal attempts returned other owners' output and are not counted. |
| `apps/backend/tests/llm/test_remote_freellmpool_sdk.py -k verified_app_catalog_dispatch` | 2 passed / 35 deselected, 0.44 s; real SDK plus injected transport proves complete context and private denial with the checked-in catalog. |
| Direct routing/evaluation API selection | Initial 13 failed / 5 passed / 7 deselected, 17.21 s: stale evaluation fixture lacked developer authentication. Fixture repair plus auth-denial cases: 15 passed, 15.00 s; typed async-session follow-up: 15 passed, 14.45 s. |
| `apps/backend/tests/api/test_remote_routes_status.py` | RED: 9 failed, 0.45 s; GREEN: 9 passed, 0.11 s. |
| `apps/backend/tests/api/test_evaluation_metrics.py -k provider_labels_do_not_establish_historical_locality` | RED: 2 failed / 15 deselected, 2.64 s; full narrow evaluation GREEN: 17 passed, 21.94 s. Final settings-type cleanup: 17 passed, 24.81 s. |
| `apps/backend/tests/api/test_remote_diagnostic_policy.py` | RED: 3 failed / 1 passed, 0.42 s; GREEN: 4 passed, 0.23 s. |
| `apps/backend/tests/api/test_evaluation_metrics.py -k 'cancelled_latest_attempt or unwired_metrics'` | RED: 1 failed / 1 passed / 17 deselected, 2.71 s; GREEN: 2 passed / 17 deselected, 2.49 s. |
| `apps/backend/tests/api/test_api_hardening_routes.py -k provenance_separates_requested_alias` | RED: 2 failed / 12 deselected, 2.04 s; GREEN: 2 passed / 12 deselected, 2.26 s. |
| Final `apps/backend/tests/llm --confcutdir=apps/backend/tests/llm` | **590 passed, 11.35 s**, native process exit 0. No coverage collected for this final LLM run. |
| Final owned API coverage selection below | **37 passed, 27.51 s; 84.60% combined statement/branch coverage**, above the explicit 80% gate. |
| Bug-tier Ruff on all nine edited Python files | **PASS**. `get_errors` reports no diagnostics in edited Python/config files. |

The 22 failures were in a stale envelope-test fixture without server synthetic
classification or an approved OpenRouter upstream. The fixture now supplies
both explicitly and uses a neutral fallback fake; production policy is not
relaxed. There are **24 added parametrized test cases**, plus repaired existing
fixtures. An initial 33-test API coverage run passed behavior but failed the
80% module gate at 73.84%; cancellation/window coverage raised the measured
combined result to 84.60%. The final per-module rounded figures are evaluation
87%, OpenRouter health 87%, routes 79%. This is module coverage, not measured
diff-only coverage; no pre-change coverage delta is claimed.

Shared terminal interference sometimes returned unrelated output or interrupted
imports. Such results were discarded, not counted as passes. Successful native
runs captured stdout/stderr in the ignored LLM test cache; final stderr was
empty. Required owned processes were drained. No async terminal UUID was
issued, no server was started, and no command is intentionally left running.
Reviewer/subagent and graph tools were unavailable; independent multi-agent
code/security verification remains a coordinator gate, not a claimed pass.
Earlier verification below belongs to the interrupted implementation and must
not be added to this continuation's counts.

#### Exact Final Commands

These PowerShell commands record the final child executable/arguments. Native
`Start-Process -Wait -PassThru` was used to capture output independently of the
shared terminal. The Python bootstrap disables dotenv loading before app imports;
the suite uses local SQLite and fake or injected provider transports only.

```powershell
$python = 'E:\BebshaX\.venv\Scripts\python.exe'
$llmBootstrap = 'import os, sys; assert sys.version_info[:2] == (3, 12); os.environ.setdefault(''BEBSHAX_JWT_SECRET'', ''synthetic-llm-tests-only-0123456789abcdef''); from pydantic_settings import DotEnvSettingsSource; DotEnvSettingsSource._read_env_files = lambda source: {}; import pytest; sys.exit(pytest.main(sys.argv[1:]))'
$llmArgs = @('-c', ('"' + $llmBootstrap + '"'), 'apps/backend/tests/llm', '--confcutdir=apps/backend/tests/llm', '-q', '--no-cov', '--tb=short', '--basetemp=E:/BebshaX/.tmp/llm-owned-final', '--junitxml=E:/BebshaX/.tmp/llm-owned-final.xml')
(Start-Process -FilePath $python -WorkingDirectory E:\BebshaX -ArgumentList $llmArgs -RedirectStandardOutput E:\BebshaX\apps\backend\tests\llm\__pycache__\continuation-llm-final.stdout -RedirectStandardError E:\BebshaX\apps\backend\tests\llm\__pycache__\continuation-llm-final.stderr -Wait -PassThru) | Select-Object Id, HasExited, ExitCode

$apiBootstrap = 'import os, sys; assert sys.version_info[:2] == (3, 12); os.environ[''COVERAGE_FILE''] = ''E:/BebshaX/.tmp/llm-continuation-api.coverage''; from pydantic_settings import DotEnvSettingsSource; DotEnvSettingsSource._read_env_files = lambda source: {}; import pytest; sys.exit(pytest.main(sys.argv[1:]))'
$apiArgs = @(
    '-c', ('"' + $apiBootstrap + '"'),
    'apps/backend/tests/api/test_evaluation_metrics.py',
    'apps/backend/tests/api/test_remote_routes_status.py',
    'apps/backend/tests/api/test_remote_diagnostic_policy.py',
    'apps/backend/tests/api/test_api_hardening_routes.py::test_anonymous_provenance_requires_authentication',
    'apps/backend/tests/api/test_api_hardening_routes.py::test_owner_sees_only_stamped_rows_with_redacted_failure_details',
    'apps/backend/tests/api/test_api_hardening_routes.py::test_redact_attempts_is_pure_and_keeps_other_fields',
    'apps/backend/tests/api/test_api_hardening_routes.py::test_provenance_separates_requested_alias_from_reported_serving_identity',
    '-q', '--tb=short', '--basetemp=E:/BebshaX/.tmp/llm-api-final',
    '--cov=bebshax.api.routes', '--cov=bebshax.api.evaluation', '--cov=bebshax.api.openrouter_health',
    '--cov-branch', '--cov-report=term-missing',
    '--cov-report=json:E:/BebshaX/.tmp/llm-continuation-api-coverage.json', '--cov-fail-under=80'
)
(Start-Process -FilePath $python -WorkingDirectory E:\BebshaX -ArgumentList $apiArgs -RedirectStandardOutput E:\BebshaX\apps\backend\tests\llm\__pycache__\continuation-api-last.stdout -RedirectStandardError E:\BebshaX\apps\backend\tests\llm\__pycache__\continuation-api-last.stderr -Wait -PassThru) | Select-Object Id, HasExited, ExitCode

& $python -m ruff check apps/backend/bebshax/api/routes.py apps/backend/bebshax/api/evaluation.py apps/backend/bebshax/api/openrouter_health.py apps/backend/tests/llm/test_remote_freellmpool_sdk.py apps/backend/tests/llm/test_exhibition_routing_openrouter_envelopes.py apps/backend/tests/api/test_api_hardening_routes.py apps/backend/tests/api/test_evaluation_metrics.py apps/backend/tests/api/test_remote_routes_status.py apps/backend/tests/api/test_remote_diagnostic_policy.py
```

#### RT Verification And Remaining Gates

| RT IDs | Local Evidence / Remaining Gate |
| --- | --- |
| RT-01, RT-07 | Remote-only tier/pool/factory/provider policy and exclusive OpenRouter credential dispatch pass scoped tests. Other owners must verify remaining tools/deployment composition; no global runtime claim is made. |
| RT-02 | Queue, discovery, late success, streaming and cancellation-resistant ownership tests pass. Real proxy/API/client deadlines and shutdown drain require integration verification. |
| RT-03, RT-04 | Actual installed AsyncPool plus injected transport tests pass cancellation attribution, all-429/all-401/exhaustion, cooling exclusion and closed failure policy. Other SDK versions are not certified. |
| RT-05, RT-10 | Structured-output, exact-budget stop/length, full-context and requested-limit tests pass. No real provider quality or format-compliance measurement was performed. |
| RT-06 | Real checked-in keyless catalog now has one publicly verified plain-chat model; unknown limits stay denied. JSON primary metadata, ongoing catalog freshness and actual model availability remain limited/unverified. |
| RT-08 | Numeric/date/reset hints and monotonic-max recovery tests pass, including local storage tests. Live PostgreSQL cross-worker refresh, restart and atomic recovery are not verified here. |
| RT-09 | Governed POST diagnostic owns trusted synthetic provenance and still denies unapproved upstreams; GET spends no inference. Operator processing approval and actual auth/availability remain external. |
| RT-11 | Attempt/cache/rejected/aborted accounting and in-process admission tests pass. Distributed reservation, crash-safe replay and multi-worker account limits remain unresolved external integration work. |
| RT-12 | Owned status/evaluation APIs no longer invent fleet health or locality; cancellation stays unknown. Shared health observation cancellation filtering and nullable client/journey contracts remain cross-owner work. |
| RT-13 | LLM stream commitment/no-splice tests pass. Interview API classified SSE propagation and canonical persisted completion belong to the domain/proxy owners and were not certified here. |
| RT-14 | Mocked native OpenRouter SSE contract passes. Freellmpool 0.11.4 remains honestly buffered, not native async streaming. Real browser/proxy first-token, disconnect and asset-free workflow verification remains external. |
| RT-15 | Requested/reported identities, observations and latency attribution tests pass, including owned provenance API projection. Durable per-observation persistence/replay still requires live database verification. |
| RT-16 | Tool execution remains unavailable; paid/unknown pins and absent upstream approvals are denied in tests. Provider retention terms, account privacy and entitlements require operator review. |

Durable provenance acknowledgement is awaited by existing startup wiring and
covered by mocked/local component tests. Full sink/database crash recovery,
independent security/code review, user journeys and latency/quality measurements
are not complete. No RT row is a blanket release certification.

### Earlier Scoped Verification

All inference was fake or transport-mocked; no real provider credentials,
provider calls, installs, commits, or nested agents were used. Python was the
explicit workspace `.venv` **3.12.9**, with httpx **0.28.1** and freellmpool
**0.11.4**. Tests used unique E: paths and isolated upload settings. Graph and
environment-selection tools were unavailable. Shared-conftest runs were
interrupted in unrelated ML imports; successful runs used
`--confcutdir=apps/backend/tests/llm` with the existing asyncio plugin. This is not
a full-backend, live PostgreSQL, or production-readiness result.

- Required first RED: embedding factory/policy **3 failed, 6 passed**; minimal
    repair **9 passed**. Later embedding cycles covered native space, cancellation,
    context, privacy, quota and recovery; final embedding scope **34 passed**.
- Whole LLM scope once after initial embedding repairs: **529 passed**, 19.09 s,
    **89.63%** combined LLM/capacity statement coverage (rounded terminal: 90%).
- Subsequent RED cycles observed missing ownership/policy, unapproved inner
    destinations, eager secondary discovery, JSON metadata, abandoned cleanup,
    persistence/replay, and quota reservation failures before their repairs.
- Final combined behavior selection: **341 passed, 235 deselected**, 21.17 s,
    **87.02%** coverage. This selection was narrower and later than the 529-test
    run, so the percentage is not a comparable coverage regression/delta.
- Additional primary-transport/persistence/admission selection: **60 passed**,
    7.51 s; **90.70%** combined targeted coverage (transport 91%, capacity 90%).
- Final governance/owned-transport file: **17 passed**, 0.43 s; the last
    proxy-isolation regression was observed RED before its one-line repair.
- Configured bug-tier Ruff passed for LLM, capacity state, and LLM tests.
    Untouched tests still have existing editor typing diagnostics; independent
    review and parent integration are not claimed complete.

R8: no dependency change. The reviewed installed SDK/httpx APIs were reused;
any upgrade remains owned by the dependency agent and needs its written review.

### Earlier RT Contract Snapshot

This historical snapshot predates the current verified Kilo catalog and parent
policy wiring. Current status and remaining gates are recorded above; this is
not the execution ledger or release sign-off.

| ID | Verified Here | Remaining Boundary |
| --- | --- | --- |
| RT-01 | Remote-only tables, lazy independent tiers, preference order, primary destination exclusions | Reviewed policy must be wired by parent |
| RT-02 | Admission/discovery/attempt/stream/finalization deadline; late success rejected; cleanup retains capacity | Non-cooperative work can outlast response deadline; parent shutdown must expose/drain it |
| RT-03 | Real SDK cancellation keeps active target and unknown consumption without fake latency | Durable observation persistence remains a sink gate |
| RT-04 | Actual AsyncPool all-429/all-401/exhaustion classification and cooling exclusion | Live endpoints not exercised |
| RT-05 | Explicit JSON metadata, requested output format, validated complete objects | Provider capability evidence must be supplied |
| RT-06 | Long fitting catalog routes retained; unknown contexts/pins fail closed | Installed primary context metadata is currently absent |
| RT-07 | Exclusive direct OpenRouter dispatch; shared in-process account reservations | Cross-process account admission remains open |
| RT-08 | Date/reset hints, nonshortening atomic upserts, no early hinted/restored probes | Live cross-worker refresh and embedding restart cooldown sharing remain open |
| RT-09 | Governed diagnostic service and network-free configuration inspection | Authenticated API wiring and immutable diagnostic ownership remain parent work |
| RT-10 | Exact-budget stop accepted; length termination and output-limit expansion rejected | No live provider benchmark claimed |
| RT-11 | Attempt reservations, rejected/aborted/cached distinctions, idempotent replay | Durable pending reservations and distributed quotas remain open |
| RT-12 | Configuration/candidate metadata is not claimed as inference health | Fleet API status and evaluation denominators are outside this writable scope |
| RT-13 | Empty deltas do not commit; classified committed failures never fall back | API SSE error mapping/durable completion remains parent work |
| RT-14 | Mocked native OpenRouter SSE; Freellmpool explicitly buffered | Primary async streaming unsupported by installed SDK |
| RT-15 | Requested/reported identity separation, per-target observations, replayed unknowns | Shared sink must persist new provenance fields |
| RT-16 | Tools unavailable, free-price restriction, server-owned processing and upstream approvals | Actual retention/entitlement approval remains an external gate |

## Historical Policy And Evidence

Everything below is retained historical material, not current configuration,
operational instructions, readiness certification, or permission to restore
Ollama. The current sections above supersede the old local-first/OpenRouter-first
orders, top-four/seed fallback, and unrestricted catalog descriptions.

### Historical Request Path (Phase 5)

```
LLM caller (copilot, interview, research, report, compatibility code, ...)
  → PoolRouter.complete(LLMRequest{task, ...})                       [bebshax/llm/router.py]
      task → pool (config map, all 18 task types)                    [bebshax/llm/pools.py]
      per-pool asyncio.Semaphore (concurrency limits)
      candidates gathered from the pool's adapters in preference order
      pre-flight: cooldown check + capability filter + token estimate [bebshax/llm/estimator.py]
          (ineligible routes NEVER called; nothing fits → ContextWindowExceeded)
      per-failure-kind fallback (FAILURE_POLICIES) + route cooldowns  [bebshax/llm/failures.py]
      full ProvenanceRecord incl. pool, on success AND failure        [bebshax/llm/provenance.py]
  → ProviderAdapter (boundary — RULES.md R1)                          [bebshax/llm/adapters/]
      FreellmpoolAdapter → freellmpool AsyncPool.achat()
          virtual route "freellmpool/auto"; provider-level failover /
          quotas / circuit breaking happen inside freellmpool;
          the Reply's concrete provider/model lands in provenance
      OllamaAdapter → local reliability fallback (native /api/chat)
```

Wired in `create_app` lifespan: `app.state.llm_router = PoolRouter(build_default_adapters())`.
`SingleAdapterLLMService` remains for tests and smoke scripts.

## Pools and task mapping (Phase 5)

| Pool           | Adapter order                          | Concurrency | Tasks                                                                                                                             |
| -------------- | -------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `reasoning`    | openrouter† → freellmpool → ollama     | 2           | PERSONA_GENERATION, PERSONA_REFINEMENT, PERSONA_VALIDATION, CONTRADICTION_CHECK, CRITIC, PERSONA_NARRATIVE, BEHAVIORAL_SIMULATION |
| `conversation` | **openrouter → freellmpool → ollama**  | 5           | PERSONA_INTERVIEW, PERSONA_RESPONSE                                                                                               |
| `structured`   | openrouter† → freellmpool → ollama     | 3           | STRUCTURED_OUTPUT, EVIDENCE_EXTRACTION, EVIDENCE_CLASSIFICATION, BROWSER_AGENT, TOOL_CALLING                                      |
| `fast`         | **openrouter → freellmpool → ollama**  | 5           | MEMORY_RETRIEVAL, MEMORY_SUMMARIZATION                                                                                            |
| `long_context` | openrouter† → freellmpool → ollama     | 2           | REPORT_GENERATION                                                                                                                 |
| `local`        | ollama                                 | 2           | (reserved for explicit local-only calls)                                                                                          |
| `emergency`    | **ollama → freellmpool** (local-first) | 2           | EMERGENCY_FALLBACK                                                                                                                |

`PERSONA_GENERATION`, `PERSONA_REFINEMENT`, and `PERSONA_VALIDATION` remain in
the exhaustive task map for compatibility. Their presence does not mean the
production persona-generation routes still invoke an LLM. A missing/invalid ML
artifact yields 503; an unsupported/exhausted selection yields 422, not a router
attempt, cooldown, or LLM fallback.

† **OpenRouterAdapter is a TESTING-ONLY first preference** (owner decision 2026-08-26). Keyless → it contributes no routes and the pool behaves as before. Free-tier reality at $0: 20 req/min, 50 req/day (extra accounts do not raise limits); paid `openrouter/auto` was removed from freellmpool's override list — do not fund the key. Its pool position contradicts D1/the capacity plan and must be revisited before production (`docs/AI_IMPLEMENTATION_PLAN.md` §10).

**OpenRouter free catalogue is discovered, not hard-coded (2026-09-08).** The previous three `:free` seeds had all been delisted (404 → `MODEL_UNAVAILABLE` → three dead attempts and three 60 s cooldowns per request). With a key present the production adapter (`OpenRouterAdapter(discover_catalogue=True)`, wired only in `adapters/factory.py`) fetches the public `/api/v1/models` catalogue (no key needed), keeps the `:free` chat models (safety/code/reasoning families excluded), prefers routes that accept `response_format`, then larger context windows, and offers the top 4 with their real context windows and capability flags. Cached 30 min; a failed refresh keeps the last good list and records the error. Precedence: `BEBSHAX_OPENROUTER_MODELS` pin → discovered catalogue → `DEFAULT_MODELS` seed (offline only). `GET /api/health/openrouter` reports `catalogue` (pinned / discovered / error). Unit tests never discover (default off).

**Interactive pools now prefer OpenRouter (owner decision 2026-09-09).** `conversation`/`fast` were previously local-first, locked by the 2026-08-26/27 judged gate below. In practice local `ollama/llama3.2:3b` measured **14-24 s/turn** on the dev machine under real load (VRAM/RAM pressure), so interactive replies now put OpenRouter's fast free models first; Ollama stays **last** as the on-machine fallback so cross-adapter failover still terminates locally. The gate data is kept for the record — it does not describe the current order:

**Latency stack (2026-08-26/27, judged gate — all three runs, HISTORICAL):** `ollama/llama3.2:3b` (arm A) vs the `freellmpool/fast` cloud route (arm B), blind LLM judge, 8/10 production bar, **n = 1 persona × 5 questions per run** (`scripts/judge_local_interview.py`; artifacts `data/metadata/local_3b_gate_*.json`):

| Run              | A weighted / avg s/turn | B weighted / avg s/turn | B served by                                   | Judge route           | Caveat                                                                              |
| ---------------- | ----------------------- | ----------------------- | --------------------------------------------- | --------------------- | ----------------------------------------------------------------------------------- |
| 2026-08-26 23:56 | **9.65** / 6.1 s        | 8.25 / 53.0 s           | kilo/stepfun step-3.7-flash, llm7/codestral   | llm7/codestral-latest | judge model also served part of arm B (self-preference risk, unflagged at the time) |
| 2026-08-27 10:19 | **9.05** / 6.8 s        | 8.05 / 2.5 s            | llm7/codestral-latest                         | llm7/codestral-latest | judge == arm B model for every turn; B was _faster_ than local in this run          |
| 2026-08-27 11:45 | **9.2** / 4.8 s         | 8.2 / 56.3 s            | kilo/stepfun step-3.7-flash, ovh/Mistral-Nemo | llm7/codestral-latest | `self_preference_risk: false` — the only run with no judge/arm overlap              |

Reading: local clears the 8/10 bar in all three runs and beats cloud-fast on quality by ~1 point each time, but this is a small-n gate (one persona, five questions, one judge family), not a benchmark; the latency advantage is real in 2 of 3 runs and reversed in run 2. Earlier docs quoted only run 1 ("9.65 vs 53 s"). `FreellmpoolAdapter(routing="fast")` enables freellmpool's smoothed-latency-first ranking; per-task attempt budgets live in `bebshax/llm/latency.py` (interactive 25 s / standard 75 s / long-context 150 s → TIMEOUT advances the candidate chain). The repo's `providers.toml` is now actually loaded (`FREELLMPOOL_CONFIG` set by `bebshax.main`); it removes Kilo's double-proxy routes (`openrouter/free`, `kilo-auto/free`) and the 185 s nemotron-120b, and keeps only measured-fast OpenRouter models.

- Every pool includes the local adapter. Emergency is local-first; conversation/fast/reasoning/structured/long-context put Ollama last, as shown in the source-backed table above.
- **Ranking:** pool/adapter order today; `PoolRouter(ranker=...)` is the hook where Phase-6 registry scores (quality/latency/health) and Phase-11 strategy experiments plug in.
- **Cooldowns:** failure kinds with `cooldown_route=True` (429, quota, 5xx, auth, provider/model unavailable) cool the route for 60 s (TIMEOUT: 30 s, `FailurePolicy.cooldown_seconds`); RATE_LIMITED / QUOTA_EXHAUSTED / AUTH_INVALID are **provider-scoped** (key `(provider, "*")`, added 2026-09-06) because they are account-level signals, the rest are route-scoped `(provider, model)`. Cooling routes are skipped with a routing-path note (`(provider-wide)` suffix for provider scope) and return automatically; state persists in `model_registry.cooldown_until` via `CooldownStore` and is restored at startup ([FAILOVER.md](FAILOVER.md) § Cooldowns).
- **Cooldown probe (half-open breaker, 2026-09-08):** when cooldowns alone leave a pool with nothing eligible, the router does **not** fail in 0 ms. The routes that are capable, fit the context and are not already being probed are admitted in order of soonest recovery (`[cooldown probe: …]` in the routing path), one in-flight probe per route; a probe that fails re-arms its cooldown normally. Observed live before the fix: a single 75 s freellmpool timeout benched the only keyless route and every feature returned `all_candidates_failed` instantly for 30 s. Capability and context exclusions are never overridden.
- **Token estimator:** deterministic chars/3.5 + 4 tokens/message overhead + expected output — deliberately over-estimates so mis-sizing can only pick a roomier model, never truncate.
- Tool-requiring tasks map to `structured` but no adapter advertises tool support yet → they fail explicitly (`AllCandidatesFailed`) until tool plumbing lands (honest by design).

## Failure classification

| freellmpool / transport outcome                    | BebshaX `FailureKind`     | Policy                                              |
| -------------------------------------------------- | ------------------------- | --------------------------------------------------- |
| `ContextWindowExceeded` (caught before its parent) | `CONTEXT_WINDOW_EXCEEDED` | advance to larger-context candidate; never truncate |
| `AllProvidersExhausted` (client_status=429)        | `RATE_LIMITED`            | advance + cooldown                                  |
| `AllProvidersExhausted` (other)                    | `PROVIDER_UNAVAILABLE`    | advance + cooldown                                  |
| `NoProvidersConfigured`                            | `PROVIDER_UNAVAILABLE`    | advance + cooldown                                  |
| `ProviderHTTPError` 401/403                        | `AUTH_INVALID`            | advance + cooldown                                  |
| `ProviderHTTPError` 404                            | `MODEL_UNAVAILABLE`       | advance + cooldown                                  |
| `ProviderHTTPError` 5xx                            | `SERVER_ERROR`            | advance + cooldown                                  |
| `httpx.TimeoutException`                           | `TIMEOUT`                 | advance                                             |
| `httpx.TransportError`                             | `CONNECTION`              | retry same once, then advance                       |
| empty/whitespace reply                             | `MALFORMED_RESPONSE`      | retry same once, then advance                       |

OpenRouter-specific (2026-09-08, `openrouter_adapter._map_http_status`): a 429 whose body names one model's **upstream shared pool** (`limit_source=upstream_provider_shared_pool`, "…is temporarily rate-limited upstream") is `MODEL_UNAVAILABLE` (route-scoped cooldown) — only an account-level 429 is `RATE_LIMITED` (provider-wide). Routes whose catalogue entry exposes the `reasoning` toggle are called with `reasoning: {enabled: false}`; a reply with no content after N reasoning tokens is still `MALFORMED_RESPONSE`, with the token count and `finish_reason` in the attempt detail.

Low answer quality is deliberately absent — it is handled by the evaluation layer (Phase 11), never by infrastructure fallback (RULES.md R2).

## Dependency review (RULES.md R8)

### freellmpool 0.11.4 — ADOPTED (Phase 3)

- **Why needed:** aggregates legitimate free LLM providers (18 in the catalog bundled with the pinned 0.11.4 — verified 2026-08-28, re-verified 2026-09-06; the "~24 providers / 222 routes" in earlier docs came from the 2026-08-22 audit of the upstream project and does not describe what is installed; the repo's own `providers.toml` only overrides `kilo` and `openrouter`) behind one API with failover, per-key quota tracking, Retry-After-aware cooldowns, per-route circuit breakers, context-limit learning, and keyless start. This _is_ the "aggregate free capacity" requirement.
- **What it replaces:** building our own multi-provider router/gateway (explicitly forbidden by the brief §42 / owner rule #12).
- **License:** MIT. **Activity:** v0.11.4 on PyPI, commits within 3 weeks of adoption, CI, security policy. **Risk:** small project (single-maintainer) → mitigated by the adapter boundary; it is swappable without touching application code, and MIT allows vendoring.
- **Runtime deps:** `httpx` only.
- **Necessity check:** compared against freelm, free-model-router, freerouter, NadirClaw, APIKeyRotator — all strict subsets or wrong-focus (see audit §6.1). Verified live 2026-08-22: keyless completion served by `llm7/codestral-latest` with 3 internal failover attempts, zero keys configured.

### Gate B — LiteLLM: **SKIPPED** (decision recorded 2026-08-22)

- The needed provider surface (Groq, Gemini, NVIDIA NIM, Mistral, Cerebras, OpenRouter, Cohere, GitHub Models, Cloudflare, HF router + keyless tiers + Ollama) is fully covered by freellmpool + a native Ollama adapter.
- LiteLLM's proxy/gateway would add Postgres/Prisma/Redis-scale infrastructure for capabilities we already have; the SDK alone would duplicate freellmpool's dispatch.
- **Revisit trigger:** a concretely required provider/endpoint that freellmpool cannot reach. The adapter boundary makes a later `LiteLLMAdapter` a drop-in.

## Provider configuration

- Keys are environment variables only (see [.env.example](../.env.example)); freellmpool reads standard names (`GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, ...). Multiple keys per provider: comma-separated. Zero keys is a supported configuration (keyless providers).
- The BebshaX app never hard-codes a provider list (owner decision #10); enabling/disabling providers is freellmpool configuration (`providers.toml` / env), surfaced later via the model registry (Phase 5/6).
- Routing mode: `FreellmpoolAdapter(routing=...)` accepts freellmpool modes (`quality`, `fast`, `fair`, ...); the existing `TASK_POOL_MAP` chooses BebshaX pools, separately from freellmpool's internal ranking mode.

## Local fallback (Ollama) — Phase 4

- **Adapter:** `bebshax/llm/adapters/ollama_adapter.py` — plain `httpx` against Ollama's **native `/api/chat`** (no SDK dependency). _Deliberate spec deviation:_ the OpenAI-compat endpoint cannot set `options.num_ctx`, and Ollama silently truncates prompts beyond the runtime context — so the adapter pins `num_ctx` to a generous per-request estimate (chars/3 + output + headroom) and **refuses** (`CONTEXT_WINDOW_EXCEEDED`) instead of ever truncating (R2).
- **Candidates:** discovered live from `/api/tags` with honest per-model windows from `/api/show`, capped at 16k for the 4 GB card, **sorted smallest-first** — under RAM pressure the small model is the one most likely to load, and resilience is this tier's job.
- **Measured on the dev machine (2026-08-22, 3-run medians, `data/metadata/ollama_benchmark.json`):**

| Model            | Size   | Status                                                                             | tok/s            | TTFT        |
| ---------------- | ------ | ---------------------------------------------------------------------------------- | ---------------- | ----------- |
| `llama3.2:3b`    | 2.0 GB | ✅ primary local fallback                                                          | 25.2 (59.8 warm) | ~2.8 s cold |
| `qwen3:4b`       | 2.5 GB | ✅ secondary (better quality, needs more staging RAM)                              | 22.4             | 217 ms warm |
| `qwen3.5:latest` | 6.6 GB | ❌ **unusable under real load** — HTTP 500 / runner OOM with <2 GB free system RAM | —                | —           |

- **Finding:** with VS Code + browser + Docker running, free RAM sits near 1–2 GB, so the 6.6 GB model cannot load (`"model requires more system memory (1.8 GiB) than is available"` was observed even for the 2.5 GB model until WSL was shut down). The fully-GPU-resident small models are therefore the _only_ dependable local tier; `qwen3.5` remains installed but the router's TIMEOUT/SERVER_ERROR policies simply advance past it when it fails.
- Ops note: `wsl --shutdown` frees the Docker VM's RAM when the local tier is needed and Docker isn't (Docker restarts on demand for Phase 6 work).
- Ops note (H2, 2026-08-26): the Ollama daemon has **no autostart** on the dev machine — after a reboot run `ollama serve` (or launch the desktop app). The backend logs a startup WARNING and sets `app.state.local_tier_up=False` when the local tier contributes no routes.

## Verification

The 2026-09-09 ML continuation recorded seven successful Freellmpool responses
served by `llm7/codestral-latest` through `freellmpool/auto`, for copilot context,
role suggestions, and two interview turns. Existing OpenRouter quota cooldown
was observed. Seven successes in this smoke sample are not a measured provider
success rate or a cross-route benchmark. Persona selection made zero LLM calls.
Historical local-model latency/quality tables above retain their original dates
and small-sample limits; ML warm-selection latency is not LLM/API latency.

- Unit (no network): `apps/backend/tests/llm/test_freellmpool_adapter.py` (error mapping, parameter passthrough, concrete-route provenance), `test_ollama_adapter.py` (mock-transport error mapping, candidate discovery/caps, `num_ctx` passthrough, oversize refusal), `test_boundary.py` (R1 enforcement).
- Live keyless smoke: `python scripts/smoke_freellmpool.py`.
- Live local smoke: `python scripts/smoke_ollama.py`; benchmarks: `python scripts/benchmark_ollama.py`.
