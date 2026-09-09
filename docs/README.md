# Documentation Index

Start with [project context](../PROJECT_CONTEXT.md), [engineering rules](../RULES.md),
and [setup](SETUP.md). The original phase records are historical; current
verification and limitations are recorded in [ship readiness](SHIP_READINESS_REPORT.md).

## Run and Develop

| Topic | Document |
| ----- | -------- |
| Installation, environment, and deployment | [SETUP.md](SETUP.md) |
| Team onboarding | [TEAM_SETUP.md](TEAM_SETUP.md) |
| Demonstration and offline rehearsal | [DEMO.md](DEMO.md) |
| API requests, responses, and errors | [API_CONTRACT.md](API_CONTRACT.md) |
| Database migration guidance | [DATABASE_MIGRATION.md](DATABASE_MIGRATION.md) |
| Current delivery evidence and limitations | [SHIP_READINESS_REPORT.md](SHIP_READINESS_REPORT.md) |
| Production checklist | [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) |

## Architecture and Research

| Topic | Document |
| ----- | -------- |
| System architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Persona selection, evidence, and memory | [PERSONA_ENGINE.md](PERSONA_ENGINE.md) |
| Local persona model lifecycle | [ml_persona/README.md](../ml_persona/README.md) |
| Model quality and limitations | [ml_persona/MODEL_CARD.md](../ml_persona/MODEL_CARD.md) |
| Dataset sources and licenses | [data/DATASETS.md](../data/DATASETS.md) |
| LLM routing policy | [ROUTING.md](ROUTING.md) |
| Failures and fallbacks | [FAILOVER.md](FAILOVER.md) |
| Model registry | [MODEL_REGISTRY.md](MODEL_REGISTRY.md) |
| Evaluation methodology | [EVALUATION.md](EVALUATION.md) |
| Evidence classification | [RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md) |

## UI and Exhibition

| Topic | Document |
| ----- | -------- |
| Design tokens and available components | [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) |
| UI and accessibility findings | [UI_UX_AUDIT.md](UI_UX_AUDIT.md) |
| UX verification snapshots | [UX_QUALITY_REPORT.md](UX_QUALITY_REPORT.md) |
| Visual review | [TASTE_REVIEW.md](TASTE_REVIEW.md) |
| Competition review | [COMPETITION_AUDIT.md](COMPETITION_AUDIT.md) |
| Judge questions | [JUDGE_QA.md](JUDGE_QA.md) |
| Concise project report | [PROJECT_REPORT_500W.md](PROJECT_REPORT_500W.md) |
| Adversarial coverage | [ADVERSARIAL_TESTS.md](ADVERSARIAL_TESTS.md) |

## Decisions and History

- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md): append-only implementation log.
- [PHASES.md](PHASES.md): original completed phase specifications.
- [TEAM_ASSIGNMENTS.md](TEAM_ASSIGNMENTS.md), [AUDIT_ASSIGNMENTS.md](AUDIT_ASSIGNMENTS.md),
  and [SAZID_OPEN_WORK.md](SAZID_OPEN_WORK.md): coordination and historical assignments.
- [AI_IMPLEMENTATION_PLAN.md](AI_IMPLEMENTATION_PLAN.md) and
  [AI_INFRASTRUCTURE_AUDIT.md](AI_INFRASTRUCTURE_AUDIT.md): AI decisions and infrastructure research.
- [E2E_AUDIT_2026-08-24.md](E2E_AUDIT_2026-08-24.md): dated live audit, not current status.
- [Research-integrity baseline](audits/research-integrity-baseline.md) and
  [hardening review](audits/research-integrity-hardening-2026-08-28.md): earlier evidence audits.
- Root-level [implementation report](../FINAL_IMPLEMENTATION_REPORT.md),
  [SUMMARY.md](../SUMMARY.md), and [project_summary.md](../project_summary.md)
  remain at their existing paths for compatibility. Read dated claims alongside current readiness.

## Repository Ownership

- Backend code and tests: `apps/backend/bebshax/` and `apps/backend/tests/`.
  Standalone literal-address SSRF coverage now lives in
  [test_discovery_literal_addresses.py](../apps/backend/tests/datasets/test_discovery_literal_addresses.py)
  and runs with the standard backend suite.
- Frontend code and tests: `apps/frontend/src/` and `apps/frontend/tests/`.
  Frontend dependencies belong to its package manifest, not duplicate root declarations.
- Persona model code and tests: `ml_persona/src/` and `ml_persona/tests/`.
- Operational commands: `scripts/`; deployment files: `deploy/` and root Compose configuration.
- Root package scripts launch the workspace. Root Neon dependencies and `neon.ts`
  support CLI tooling. Keep both npm lockfiles: the root workspace uses one, while
  the frontend Docker build installs from the standalone frontend lockfile.
- The root `.dockerignore` controls both image builds. Generated caches, build
  output, environments, uploads, and trained artifacts are not source cleanup targets.