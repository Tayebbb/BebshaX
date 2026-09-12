# Model Registry

An honest description of `model_registry`: what exists, what is actually used, and what is deliberately deferred.

**Persona ML is separate (2026-09-09).** The CPU selector is not a provider route
or a new registry row. Its Git-ignored JSON/NPZ artifact carries model version,
source records, hashes, and numerical-runtime metadata; existing persona JSON
stores source/model provenance. No registry sync or DB migration is needed for
ML generation. See [ML architecture](../ml_persona/ARCHITECTURE.md) and
[artifact setup](SETUP.md#persona-ml-artifact).

## The table (`db/models.py::ModelRegistry`, migration `cb7c7deda755`)

| Column group | Columns                                                                                   | Status                                              |
| ------------ | ----------------------------------------------------------------------------------------- | --------------------------------------------------- |
| Identity     | `id`, `provider_name` + `model_name` (unique pair index), `enabled`                       | populated when rows are created                     |
| Capabilities | `context_window`, `supports_tools`, `supports_json`, `supports_vision`, `reasoning_level` | **schema only — nothing writes them in production** |
| Scores       | `quality_score`, `latency_score`, `health_score`, `last_checked`                          | **schema only — registry sync jobs are unowned**    |
| Operational  | `cooldown_until`                                                                          | **actively used**                                   |

## What is actually live

`CooldownStore` persists router cooldowns as wall-clock deadlines and
`load_active()` restores them into monotonic deadlines at startup. Provider-wide
entries use model `*`; atomic maximum-deadline writes do not shorten longer
recovery hints. The unique provider/model constraint is required. This is not
live cross-worker refresh or distributed quota admission: PostgreSQL concurrency,
restart/crash behavior and account reservation durability remain external gates.

## Where capability data really comes from today

Current metadata, not registry score columns, authorizes capabilities:

- **Freellmpool primary** merges its packaged catalog with the explicitly loaded
	application [providers.toml](../providers.toml). Legacy environment/home/plugin
	catalogs are not eligibility authorities. Only configured, approved remote
	destinations with positive verified context may dispatch; JSON additionally
	requires explicit `supports_json=true`. The virtual route reports the largest
	verified request-appropriate context, not an assumed million-token window.
- **Verified keyless metadata (2026-09-10):** the public
	[Kilo model catalog](https://api.kilo.ai/api/gateway/models) reports
	`stepfun/step-3.7-flash:free` at 262144 tokens and zero prompt/completion prices.
	JSON-format capability is not declared, so it remains false. The absent
	`poolside/laguna-xs.2:free` is disabled. Kilo's training-on-prompts flag prevents
	treating free/configured status as a privacy approval. This was metadata-only
	inspection, not an inference health or latency measurement.
- **Independent OpenRouter secondary** retains all verified free catalog models
	until request-specific filtering. Pins, aliases, stale metadata and unknown
	limits never create capabilities. Upstream allowlists and no-paid-route
	constraints apply to diagnostics as well as ordinary completion/streaming.
- **Ollama history** remains historical and inactive. No local/cloud Ollama
	discovery is executable through production composition. A legacy `ollama`
	provider identifier alone does not prove whether a historical call was local
	or cloud; do not rewrite it into a verified route kind.
- **Ranking/accounting** uses `quota_aware_ranker`, the shared `QuotaLedger` and
	concrete per-attempt observations. Requested aliases, reported identities,
	unknown consumption and whole-adapter elapsed time remain distinct. Cached or
	aborted work must not create a healthy endpoint-latency sample. Tier priority
	remains Freellmpool then OpenRouter regardless of ranker scores.

Configured, eligible, recently successful, unavailable and unknown are distinct
states. Candidate presence or an HTTP 200 with an empty completion is not proof
of inference health. Configuration GETs never spend inference quota; diagnostics
that do invoke a model must use the governed service, explicit task and durable
provenance contract described in [ROUTING.md](ROUTING.md).

The 2026-09-10 API projection preserves this distinction: unresolved virtual
model counts are null, all-cooling routes are unavailable, and historical Ollama
label counts live in `historical_ollama_provider_rate`, not a measured local
serving rate. Provenance exposes `requested_model` separately from
`served_by_model`; absent reported identity remains `unknown`. No registry or
historical request row is rewritten to supply missing evidence.

## Deliberately deferred

Registry sync jobs (probing providers to fill capability/score columns) were assigned to later work and remain unimplemented. The ~100 personas/day figure was an unmeasured LLM-era planning target, not evidence of capacity, and current ML selection does not consume persona-generation LLM quota (see [AI_IMPLEMENTATION_PLAN.md](AI_IMPLEMENTATION_PLAN.md)). If sync jobs are built, the schema and ranker hook already exist; the separate persona selector is not an ML router (R10).
