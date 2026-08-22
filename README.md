# BebshaX

BebshaX is a synthetic-user / persona research system: it continuously generates realistic, evidence-grounded personas for a specific business or product and lets those personas participate in interviews and simulations — built on essentially zero API budget by aggregating **legitimate** free LLM capacity behind intelligent routing, failover, and context-aware model selection.

> Renamed from *SignalLens* on 2026-08-22. No other historical relationship — the project is greenfield.

**Team members start here:** [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) (single source of truth) → [RULES.md](RULES.md) (binding engineering rules) → [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md) (machine setup) → [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md) (your track).

**Working with an AI agent?** It auto-loads [AGENTS.md](AGENTS.md). To build the next milestone, just tell it: **“Implement phase N”** — specs live in [docs/PHASES.md](docs/PHASES.md).

## Repository layout

| Path | Purpose |
|---|---|
| `apps/backend/` | FastAPI backend (Python 3.12, async) — package `bebshax` |
| `apps/frontend/` | React + Vite single-page app (added in Phase 12) |
| `services` (inside backend) | `bebshax.llm` policy layer → adapters → freellmpool / Ollama |
| `data/raw` · `data/processed` · `data/metadata` | Datasets (reproducible via `scripts/`, not committed) |
| `scripts/` | Setup, dataset, and evaluation tooling |
| `docs/` | [AI_INFRASTRUCTURE_AUDIT.md](docs/AI_INFRASTRUCTURE_AUDIT.md) · [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) |

## Quickstart (state: Phases 1–7, 11, 12 ✅ complete)

```powershell
# Backend
python -m venv .venv
.venv\Scripts\pip install -e "apps/backend[dev]"
.venv\Scripts\python -m pytest apps/backend/tests -q

# Run the API
.venv\Scripts\python -m uvicorn bebshax.main:app --port 8000
# → GET http://127.0.0.1:8000/api/health

# Database (pgvector; the native PG16 install lacks the extension, so Docker on port 5433)
docker compose up -d db   # used from Phase 6 onward

# Run the Frontend
cd apps/frontend
npm install
npm run dev
# → http://localhost:5173
```

Configuration is environment-driven (`BEBSHAX_*` variables; see [.env.example](.env.example)). Provider API keys are **optional** — add whatever legitimate free-tier keys the team has; keyless providers work with none.

---

# 📌 How we work (read once, follow always)

Everything below is enforced by [AGENTS.md](AGENTS.md), [RULES.md](RULES.md), tests, and CI — this section is the human summary. If any doc disagrees with another, [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) wins.

## 1. One-time setup (day 1, ~5 min)

1. Follow [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md) exactly: venv → `pip install -e "apps/backend[dev]"` → run tests. Don't continue until the suite passes.
2. Copy `.env.example` → `.env`. Provider keys are **optional** (keyless providers work); add only free-tier keys from accounts **you personally own**. Never share keys, never commit `.env`.
3. Read, in this order: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) → [RULES.md](RULES.md) → [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md) (find your name) → your phase's section in [docs/PHASES.md](docs/PHASES.md). ~20 minutes total.

## 2. Your lane (no overlap, no waiting on each other)

| Who | Track | Completed Phases | Up Next | You own (nobody else touches) |
|---|---|---|---|---|
| **Tayeb** | A — LLM infra | 1, 2, 3, 4, 5 ✅ | Phase 8 (Persona engine), Phase 10 | `apps/backend/bebshax/llm/**`, `docs/ROUTING.md` |
| **Sazid** | B — Data layer | 6, 7 ✅ | Phase 9 (Memory engine) | `apps/backend/bebshax/db/**`, `alembic/`, `data/**`, dataset scripts |
| **Shehab** | C — Frontend & Eval | 11, 12-foundation ✅ | Phase 12 (live wiring) | `apps/frontend/**`, `apps/backend/bebshax/evaluation/**`, `docs/API_CONTRACT.md`, `docs/EVALUATION.md` |

Stay inside your paths. Need to change something outside them → PR + ping the owner. Full matrix and the convergence order for phases 8–15: [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md).

## 3. How to build your phase

Open the repo in VS Code (or Cursor / Claude Code / Codex — all of them auto-load [AGENTS.md](AGENTS.md)), open the AI chat, and say:

> **"Implement phase N"**

The agent will: check prerequisites + green tests → implement only within your phase's allowed paths → run the exit-criteria commands from [docs/PHASES.md](docs/PHASES.md) → **update all docs in the same commit** → commit as `Phase N: …` and push.

**Your job is to verify, not to trust.** Before anything lands on `main`, confirm:

1. tests green;
2. the implementation log in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) has your phase entry;
3. status flipped in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) **and** [docs/PHASES.md](docs/PHASES.md);
4. no secrets in the diff.

If the agent skipped a doc update, tell it: *"You violated AGENTS.md step 6 — update the docs."*

## 4. Doc rules (how everything stays in sync)

- **A task with stale docs is an unfinished task** (RULES.md R12). Code and its doc updates travel in the **same commit** — never "I'll document later."
- Any change, even tiny non-phase fixes → append a `### Maintenance (date)` entry to the implementation log.
- The log is **append-only**: add your block at the top, never edit anyone else's entries. Status flips: only your own phase's row.
- Docs disagree? [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) wins — fix the other doc in the same commit you noticed it.
- Adding a dependency? The written review (why / license / activity / necessity) goes in the docs **before** installing (R8).

## 5. Git rules

- `git pull --rebase` **before every push**. Push small, push often.
- Commit format: `Phase N: <what>` or `fix:/docs:/chore: <what>`.
- `main` must always be green — CI runs pytest on every push; if you break it, fixing it is your top priority.
- Contract files (`bebshax/llm/types.py`, `provenance.py`, `failures.py`, `adapters/base.py`, `docs/API_CONTRACT.md`) are the interfaces our parallel work depends on → changing them needs **all three of us** to agree first.

## 6. The never list (instant revert territory)

- No provider SDK imports outside `bebshax/llm/adapters/` (a test fails anyway).
- Never truncate persona/evidence to fit a model — explicit failure, always.
- Low answer quality is **not** an infrastructure failure — don't add it to fallback.
- No secrets / `.env` / real PII in commits. No duplicate accounts or rate-limit evasion. No fine-tuning on datasets. No Kubernetes / Redis / queues / custom gateways.

## 7. When stuck

Blocked by a prerequisite phase → say so in the group chat, don't start anyway. Unsure if something's in scope → the phase spec's "Out of scope" line decides. Agent behaving weirdly → make it re-read [AGENTS.md](AGENTS.md). Genuinely ambiguous → ask Tayeb (owner) rather than guessing.

**TL;DR: clone → read the 4 docs → say "Implement phase N" → verify tests + doc updates → rebase → push. The repo explains itself; keep it that way.**
