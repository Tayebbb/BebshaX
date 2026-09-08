# AGENTS.md — Contract for every AI agent and coding tool in this repo

You (the agent) MUST follow this file for any work in this repository. It applies to the entire repo, regardless of which tool loaded you (VS Code Copilot, Cursor, Claude Code, Codex, Windsurf, ...).

## Read before doing anything (in this order)

1. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) — what BebshaX is, decided stack, phase roadmap/status. It wins all conflicts.
2. [RULES.md](RULES.md) — binding rules R1–R12.
3. [docs/PHASES.md](docs/PHASES.md) — the executable spec for each phase.
4. [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md) — who owns which paths.

## Hard rules digest (full text in RULES.md — violating any means your change is wrong)

- **R1:** provider SDK imports (`freellmpool`, ollama clients, `litellm`, `openai`, `anthropic`) ONLY inside `apps/backend/bebshax/llm/adapters/`. Test-enforced.
- **R2:** never truncate/compress persona identity, memory, or evidence to fit a model. If nothing fits → raise `ContextWindowExceeded`. Low answer quality is NEVER an infrastructure failure.
- **R3:** every LLM call goes through `LLMService.complete(LLMRequest)` with an explicit `TaskType` and produces a full `ProvenanceRecord`.
- **R4:** no secrets in code, commits, logs, or docs. Keys live in `.env` (gitignored) only.
- **R5:** legitimate free-tier use only — never build anything that evades rate limits or multiplies accounts.
- **R6:** the failure taxonomy is closed; new kinds need enum + policy + tests in one commit.
- **R7:** `python -m pytest apps/backend/tests -q` green before every commit; new behavior ships with tests; chaos paths use `FakeAdapter`, never real providers.
- **R8:** any new dependency requires a written review (why / what it provides / license / activity / necessity) in the docs before installing.
- **R9:** datasets only via `scripts/setup_datasets.py` profiles + `data/DATASETS.md`; **no LLM fine-tuning**. The owner-approved `ml_persona` profile alone permits reviewed public synthetic data for non-LLM persona training (2026-09-08).
- **R10:** no Kubernetes, Redis clusters, message queues, custom gateways, or ML routers in the request path. Check mature OSS before building anything.

## Phase Execution Protocol

Triggers: a user says **"implement phase N"**, **"implement the next one"**, or runs `/implement-phase`.

1. **Resolve N.** If not stated, N = the first ⬜ phase in the PROJECT_CONTEXT.md roadmap.
2. **Load the spec** — the `## Phase N` section of [docs/PHASES.md](docs/PHASES.md). It defines prerequisites, allowed paths, steps, and exit criteria.
3. **Gate.** Verify prerequisites are ✅ and the test suite is green. If not, STOP and report what's blocking instead of starting.
4. **Stay in scope.** Touch only the spec's allowed paths plus the doc files in step 6. Needing anything else = stop and ask the user.
5. **Implement incrementally** with tests in the same commit (R7). Run every verification command listed in the spec's exit criteria — all must pass.
6. **Mandatory doc updates (same commit as the code — never skip):**
   - Append a `### Phase N — <name> (<date>)` entry to the implementation log in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md): what was built, findings, deviations, new dependencies with their R8 review.
   - Flip the phase status in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) roadmap AND in [docs/PHASES.md](docs/PHASES.md).
   - Update every doc the spec lists (e.g. docs/ROUTING.md, data/DATASETS.md).
7. **Commit** as `Phase N: <summary>`; push to `origin main` unless the user says otherwise. CI must pass.
8. **Report:** what was delivered, test count, deviations from the spec, and which phase is next.

## Definition of Done for ANY code change (also outside phases)

- Tests green; new behavior has tests.
- Affected docs updated in the same commit (for non-phase work, add a `### Maintenance (<date>)` entry to the implementation log).
- No stale statuses, no dead links, no secrets in the diff.
- Commit message: `Phase N: <what>` or `fix:/docs:/chore: <what>`.

## Environment facts

- Dev machine is Windows; venv commands: `.venv\Scripts\python -m pytest apps/backend/tests -q` (CI runs Ubuntu — write portable code/tests).
- API: `.venv\Scripts\python -m uvicorn bebshax.main:app --port 8000` → `/api/health`.
- DB: `docker compose up -d db` → pgvector on `localhost:5433` (native PG16 owns 5432 and lacks pgvector).
- GPU: RTX 3050 **4 GB VRAM** — local models ≤4B run fully resident; `qwen3.5:latest` (6.6 GB) works with CPU offload; never configure 70B-class models.
- Zero API keys is a supported configuration (keyless providers); teammates add their own keys via `.env`.

## Never

- Import provider SDKs outside `adapters/`.
- Silently truncate persona/evidence, swap persona identity, or hide fallbacks from provenance.
- Treat low answer quality as an infrastructure failure.
- Commit secrets, `.env`, or real PII.
- Create duplicate accounts or evade provider limits.
- Fine-tune LLMs, or train on datasets not explicitly allowlisted under R9.
- Finish a task with stale docs.
