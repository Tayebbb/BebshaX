# BebshaX — Routing

How an LLM request travels through BebshaX, and why the routing dependencies were chosen.

## Request path (current, Phase 3)

```
caller (persona engine, API, ...)
  → LLMService.complete(LLMRequest{task, messages, constraints})     [bebshax/llm/service.py]
      pre-flight: capability filter + context-window estimate         (ineligible routes NEVER called)
      per-failure-kind fallback (FAILURE_POLICIES)                    [bebshax/llm/failures.py]
      full ProvenanceRecord on success AND failure                    [bebshax/llm/provenance.py]
  → ProviderAdapter (boundary — RULES.md R1)                          [bebshax/llm/adapters/]
      FreellmpoolAdapter → freellmpool AsyncPool.achat()
          virtual route "freellmpool/auto"; freellmpool does provider-level
          failover / quota tracking / circuit breaking internally;
          the Reply's concrete provider/model is written back into provenance
      OllamaAdapter (Phase 4) → local reliability fallback
  → Phase 5 replaces the single-adapter loop with task→pool routing across adapters.
```

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

## Verification

- Unit (no network): `apps/backend/tests/llm/test_freellmpool_adapter.py` (error mapping, parameter passthrough, concrete-route provenance), `test_boundary.py` (R1 enforcement).
- Live keyless smoke: `python scripts/smoke_freellmpool.py`.
