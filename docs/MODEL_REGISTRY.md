# Model Registry

An honest description of `model_registry`: what exists, what is actually used, and what is deliberately deferred.

## The table (`db/models.py::ModelRegistry`, migration `cb7c7deda755`)

| Column group | Columns | Status |
| --- | --- | --- |
| Identity | `id`, `provider_name` + `model_name` (unique pair index), `enabled` | populated when rows are created |
| Capabilities | `context_window`, `supports_tools`, `supports_json`, `supports_vision`, `reasoning_level` | **schema only — nothing writes them in production** |
| Scores | `quality_score`, `latency_score`, `health_score`, `last_checked` | **schema only — registry sync jobs are unowned** |
| Operational | `cooldown_until` | **actively used** |

## What is actually live

`cooldown_until` is the one production column: `CooldownStore` (`db/capacity_state.py`) persists every router cooldown as wall-clock deadlines and `load_active()` restores them into `PoolRouter` at startup. That closes the restart gap — a provider that 429'd us seconds before a reboot stays quiet after it.

## Where capability data really comes from today

Live discovery, not the registry:

- **freellmpool** ships its own provider/model inventory (configured via the repo's `providers.toml` through `FREELLMPOOL_CONFIG`) with per-route context windows and circuit breakers; the concrete serving route is written to provenance per call.
- **Ollama** is discovered at request time: `GET /api/tags` (60 s TTL cache) for installed models, `POST /api/show` per model for `context_length`, capped at **16,384** tokens for the 4 GB VRAM dev GPU (fallback window 8,192), candidates ordered smallest-first because smaller models are faster on that hardware. The adapter refuses (`CONTEXT_WINDOW_EXCEEDED`) rather than let Ollama silently truncate (R2).
- **Quality/latency ranking** happens through the router's ranker hook (`quota_aware_ranker`) fed by the `QuotaLedger` (re-seeded from `llm_requests` at boot) and freellmpool's fast-routing metrics warmed from recent route observations — none of it round-trips through the registry score columns.

## Deliberately deferred

Registry sync jobs (probing providers to fill capability/score columns) were assigned to a later phase and never scheduled; the routing layer proved sufficient without them for the ~100 personas/day target (see docs/AI_IMPLEMENTATION_PLAN.md §10). If they are ever built, the schema is ready and the ranker hook is the single integration point — no request-path changes required (R10: no ML routers in the request path).
