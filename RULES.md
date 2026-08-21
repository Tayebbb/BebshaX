# BebshaX — Engineering Rules

Binding for every contributor and every AI agent working on this repo. Violations block merge.

## R1 — Adapter boundary
Only code inside `apps/backend/bebshax/llm/adapters/` may import `freellmpool`, Ollama clients, or any provider SDK. Everything else calls `LLMService`. Enforced by `tests/llm/test_boundary.py`.

## R2 — Quality is sacred
- Never truncate, drop, or compress persona identity/memory/evidence to fit a smaller model.
- If nothing fits → raise `ContextWindowExceeded`. Explicit failure beats silent degradation, always.
- Low answer quality is **not** a `FailureKind` and must never trigger infrastructure fallback; quality checks live in the evaluation layer (Phase 11).

## R3 — Every LLM call is a governed call
- Goes through `LLMService.complete(LLMRequest)` with an explicit `TaskType` (the app always knows its task — never ask an LLM to classify it).
- Produces a complete `ProvenanceRecord`: provider, model, routing path, attempts, latency, tokens, failure/fallback reasons, final serving model. No untracked calls.

## R4 — Secrets and keys
- Keys live in `.env` (gitignored) / environment variables only. Never in code, config files, commits, logs, or screenshots. `.env.example` documents names with empty values.
- Mask keys in any output (`gsk_****`). If a key leaks into a commit: rotate it immediately, then tell the team — history rewriting comes second.

## R5 — Legitimate free-tier use only
No duplicate accounts, no rate-limit evasion mechanisms, no scraped/unauthorized APIs, no shared personal keys without the owner's consent. Each teammate configures their own legitimately-obtained keys. Respect provider ToS — some free tiers train on prompts; we send only synthetic data (no real PII).

## R6 — Failure taxonomy is closed
New failure kinds require: enum entry + `FailurePolicy` + tests, in one PR. `INTERNAL_ERROR` (our bugs) must surface, never burn fallback candidates.

## R7 — Tests gate everything
- `python -m pytest apps/backend/tests -q` must be green before every commit.
- New behavior ⇒ new tests in the same commit. Chaos paths (429/timeout/context/all-fail) are tested with `FakeAdapter` — never against real providers.
- Real-network smoke scripts live in `scripts/` and are excluded from the unit suite.

## R8 — Dependencies need a written review
Before adding any dependency or vendored repo, record in the relevant doc (`docs/ROUTING.md`, plan log, or audit): why it's needed, what it replaces/provides, license, maintenance/activity, and whether it's actually necessary. Prefer existing OSS behind a thin adapter over building infrastructure ourselves.

## R9 — Datasets
- Only through `scripts/setup_datasets.py` with a named profile (`minimal`/`development`/`evaluation`/`full`). No manual dumps into `data/`.
- Every dataset documented in `data/DATASETS.md`: source URL, license, size estimate, purpose, download+preprocessing method, required/optional.
- Streaming/subsets over bulk downloads. **No model training/fine-tuning with them.**

## R10 — Working style
- Incremental phases (see PROJECT_CONTEXT.md roadmap); don't start a phase while the previous is red.
- After each phase: run tests → fix → update `docs/IMPLEMENTATION_PLAN.md` implementation log → commit.
- Commit messages: `Phase N: <what>` for phase work; `fix:`/`docs:`/`chore:` otherwise. Small commits.
- Work on branches for anything experimental; `main` stays green and demoable.
- Don't over-engineer: no Kubernetes, no Redis clusters, no message queues, no custom LLM gateway, no ML router in the request path.

## R11 — User experience
End users see ONE AI system ("Generate Persona"), never provider/model pickers. Routing internals are exposed only in the developer dashboard, clearly labeled. Demo mode must clearly indicate when a cached result is shown.
