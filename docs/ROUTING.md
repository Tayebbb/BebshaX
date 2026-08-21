# BebshaX — Routing

How an LLM request travels through BebshaX, and why the routing dependencies were chosen.

## Request path (current, Phase 5)

```
caller (persona engine, API, ...)
  → PoolRouter.complete(LLMRequest{task, ...})                       [bebshax/llm/router.py]
      task → pool (config map, all 16 task types)                    [bebshax/llm/pools.py]
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

| Pool | Adapter order | Concurrency | Tasks |
|---|---|---|---|
| `reasoning` | freellmpool → ollama | 2 | PERSONA_GENERATION, PERSONA_REFINEMENT, PERSONA_VALIDATION, CONTRADICTION_CHECK, CRITIC |
| `conversation` | freellmpool → ollama | 5 | PERSONA_INTERVIEW, PERSONA_RESPONSE |
| `structured` | freellmpool → ollama | 3 | STRUCTURED_OUTPUT, EVIDENCE_EXTRACTION, EVIDENCE_CLASSIFICATION, BROWSER_AGENT, TOOL_CALLING |
| `fast` | freellmpool → ollama | 5 | MEMORY_RETRIEVAL, MEMORY_SUMMARIZATION |
| `long_context` | freellmpool → ollama | 2 | REPORT_GENERATION |
| `local` | ollama | 2 | (reserved for explicit local-only calls) |
| `emergency` | **ollama → freellmpool** (local-first) | 2 | EMERGENCY_FALLBACK |

- Every pool terminates at the local adapter (chaos-tested: remote exhausted → Ollama serves).
- **Ranking:** pool/adapter order today; `PoolRouter(ranker=...)` is the hook where Phase-6 registry scores (quality/latency/health) and Phase-11 strategy experiments plug in.
- **Cooldowns:** failure kinds with `cooldown_route=True` (429, quota, 5xx, auth, provider/model unavailable) put `(provider, model)` on a 60 s in-memory cooldown; cooling routes are skipped with a routing-path note and return automatically. DB-backed state is Phase 6.
- **Token estimator:** deterministic chars/3.5 + 4 tokens/message overhead + expected output — deliberately over-estimates so mis-sizing can only pick a roomier model, never truncate.
- Tool-requiring tasks map to `structured` but no adapter advertises tool support yet → they fail explicitly (`AllCandidatesFailed`) until tool plumbing lands (honest by design).

## Failure classification

| freellmpool / transport outcome | BebshaX `FailureKind` | Policy |
|---|---|---|
| `ContextWindowExceeded` (caught before its parent) | `CONTEXT_WINDOW_EXCEEDED` | advance to larger-context candidate; never truncate |
| `AllProvidersExhausted` (client_status=429) | `RATE_LIMITED` | advance + cooldown |
| `AllProvidersExhausted` (other) | `PROVIDER_UNAVAILABLE` | advance + cooldown |
| `NoProvidersConfigured` | `PROVIDER_UNAVAILABLE` | advance + cooldown |
| `ProviderHTTPError` 401/403 | `AUTH_INVALID` | advance + cooldown |
| `ProviderHTTPError` 404 | `MODEL_UNAVAILABLE` | advance + cooldown |
| `ProviderHTTPError` 5xx | `SERVER_ERROR` | advance + cooldown |
| `httpx.TimeoutException` | `TIMEOUT` | advance |
| `httpx.TransportError` | `CONNECTION` | retry same once, then advance |
| empty/whitespace reply | `MALFORMED_RESPONSE` | retry same once, then advance |

Low answer quality is deliberately absent — it is handled by the evaluation layer (Phase 11), never by infrastructure fallback (RULES.md R2).

## Dependency review (RULES.md R8)

### freellmpool 0.11.4 — ADOPTED (Phase 3)

- **Why needed:** aggregates ~18–24 legitimate free LLM providers (200+ live routes) behind one API with failover, per-key quota tracking, Retry-After-aware cooldowns, per-route circuit breakers, context-limit learning, and keyless start. This *is* the "aggregate free capacity" requirement.
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
- Routing mode: `FreellmpoolAdapter(routing=...)` accepts freellmpool modes (`quality`, `fast`, `fair`, ...); task-type → routing-mode mapping arrives with Phase 5 pools.

## Local fallback (Ollama) — Phase 4

- **Adapter:** `bebshax/llm/adapters/ollama_adapter.py` — plain `httpx` against Ollama's **native `/api/chat`** (no SDK dependency). *Deliberate spec deviation:* the OpenAI-compat endpoint cannot set `options.num_ctx`, and Ollama silently truncates prompts beyond the runtime context — so the adapter pins `num_ctx` to a generous per-request estimate (chars/3 + output + headroom) and **refuses** (`CONTEXT_WINDOW_EXCEEDED`) instead of ever truncating (R2).
- **Candidates:** discovered live from `/api/tags` with honest per-model windows from `/api/show`, capped at 16k for the 4 GB card, **sorted smallest-first** — under RAM pressure the small model is the one most likely to load, and resilience is this tier's job.
- **Measured on the dev machine (2026-08-22, 3-run medians, `data/metadata/ollama_benchmark.json`):**

| Model | Size | Status | tok/s | TTFT |
|---|---|---|---|---|
| `llama3.2:3b` | 2.0 GB | ✅ primary local fallback | 25.2 (59.8 warm) | ~2.8 s cold |
| `qwen3:4b` | 2.5 GB | ✅ secondary (better quality, needs more staging RAM) | 22.4 | 217 ms warm |
| `qwen3.5:latest` | 6.6 GB | ❌ **unusable under real load** — HTTP 500 / runner OOM with <2 GB free system RAM | — | — |

- **Finding:** with VS Code + browser + Docker running, free RAM sits near 1–2 GB, so the 6.6 GB model cannot load (`"model requires more system memory (1.8 GiB) than is available"` was observed even for the 2.5 GB model until WSL was shut down). The fully-GPU-resident small models are therefore the *only* dependable local tier; `qwen3.5` remains installed but the router's TIMEOUT/SERVER_ERROR policies simply advance past it when it fails.
- Ops note: `wsl --shutdown` frees the Docker VM's RAM when the local tier is needed and Docker isn't (Docker restarts on demand for Phase 6 work).

## Verification

- Unit (no network): `apps/backend/tests/llm/test_freellmpool_adapter.py` (error mapping, parameter passthrough, concrete-route provenance), `test_ollama_adapter.py` (mock-transport error mapping, candidate discovery/caps, `num_ctx` passthrough, oversize refusal), `test_boundary.py` (R1 enforcement).
- Live keyless smoke: `python scripts/smoke_freellmpool.py`.
- Live local smoke: `python scripts/smoke_ollama.py`; benchmarks: `python scripts/benchmark_ollama.py`.
