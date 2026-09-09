# Persona ML Implementation Report

Date: 2026-09-09. Status: working research prototype with measured limitations.

## A. Recovery And Project Understanding

BebshaX collects business context through its existing governed LLM copilot,
generates personas, and uses those persisted identities in LLM interviews and
memory-backed research workflows. Freellmpool and Ollama remain behind the
existing adapter/LLMService boundary. The frontend and database contracts remain.

The shutdown did not lose the ML work: the synced checkout contained the
isolated package, ingestion, CLI, training, and four backend integration paths.
The licensed dataset, disjoint splits, trained bundle, experiment record, and
example output survived locally. Held-out evaluation and final verification
were incomplete. This continuation reused the model, completed evaluation,
repaired concrete integration/integrity issues, and finished documentation.
That initial recovery stage did not restore a stash, change branches, commit,
push, or fine-tune an LLM. Subsequent upstream integration and local verification
are recorded below; publication status is tracked separately.

## B. ML Approach

TF-IDF vocabulary and IDF plus NMF topics are fitted on training profiles only.
Business text is projected through the fitted representation; blended lexical
and topic similarity, diversity penalties, and seeded sampling select complete
synthetic source bundles. This is genuine fitted statistical ML, not prompting
Freellmpool to write personas. It selects prototypes, not novel identities.

scikit-learn supplies the established estimators; BebshaX supplies normalization,
context conditioning, constrained selection, diversity, provenance, safe
serialization, evaluation, and schema adapters. No pretrained weights were used.
MiniLM was researched but not adopted: it adds a transformer runtime/artifact
and needs a full-text policy for its 256-wordpiece truncation. The smaller
CPU-only pipeline matches the available hardware and approved scope.

## C. Dataset Research

| Dataset | Source / License | Size / Purpose / Fields |
| --- | --- | --- |
| NVIDIA Nemotron-Personas-USA | [Pinned source](https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA/blob/5b4cd35ab46490c1da1bd2b5a2324d6f871be180/README.md), NVIDIA Corporation, CC-BY-4.0 | 6,000 hash-selected synthetic profiles from one 244 MB shard; UUID, age, occupation, education, source geography and full narratives/skills/interests/goals; synthetic training priors only |
| Google Synthetic-Persona-Chat | [Source](https://huggingface.co/datasets/google/Synthetic-Persona-Chat), CC-BY-4.0 | Researched, not used for ML: missing required demographics |
| PersonaHub | [Source](https://huggingface.co/datasets/proj-persona/PersonaHub), CC-BY-NC-SA-4.0 | Researched, not used for ML: license restrictions and insufficient structure |
| UCI Restaurant Consumer Data | [Source](https://archive.ics.uci.edu/dataset/232/restaurant+consumer+data), CC-BY-4.0 | 138 people / 1,161 ratings; not downloaded or used: real-person privacy and narrow domain conflict with the approved synthetic-only policy |

The approved revision is `5b4cd35ab46490c1da1bd2b5a2324d6f871be180`.
Licensing was rechecked against its upstream card. [DATASETS.md](DATASETS.md)
and [SOURCES.json](SOURCES.json) record ownership, fields, exact checksums,
transforms, exclusions, and bias limitations. Private studies, uploads, and
conversations are not training data. Source-derived outputs retain NVIDIA
attribution and modification notices; no project software license is invented.

## D. Architecture And Integration

```text
Existing Freellmpool copilot -> business/product context
    -> MLPersonaAdapter -> fitted TF-IDF/NMF + diversity-aware selection
    -> existing persona schemas and JSON provenance -> existing persistence
    -> unchanged LLM interview engine and memory
```

All four production generation paths use the shared server-side adapter:
legacy business personas, study generation/jobs/regeneration, role-based
workflow generation, and dataset-based generation. Existing `GeneratedPersona`,
`PersonaProfile`, and `GeneratedPersonaDraft` shapes remain authoritative.
There is no second chatbot, provider gateway, frontend, or database migration.

Claims remain SYNTHETIC with empty evidence IDs and zero observed grounding.
Source occupation/location and full documents are preserved; missing income,
budget, or OCEAN values are not fabricated. Roles/geography are retrieval hints,
not validated customer membership. Explicit ages are hard constraints.
Missing/incompatible artifacts yield 503; unsupported/exhausted selection yields
422. Neither condition falls back to LLM persona writing. Chat still works when
the ML artifact is unavailable, as covered by regression tests.

## E. Training And Artifacts

Normalization accepted 4,694 of 6,000 rows, rejected 1,306 at strict schema
validation, removed 1,078 incomplete profiles and 22 repeated identities.
The remaining 3,594 split into 2,516 train / 539 validation / 539 test with
seed 42. Canonical source/split validation rejects substituted claims even if
their local split and report hashes are recomputed.

Four validation candidates searched 16/32 topics and lexical weights 0.35/0.70.
The selected model has 32 topics, 8,000 features, lexical weight 0.70,
diversity weight 0.25, temperature 0.03, and maximum 300 NMF iterations.
Recorded fit time is 43.70 seconds total on two CPU threads. No GPU is required.

Model: `7eb2fa6f748fac32b6e987e9057004d477a45e834a457b2701060360ca78b247`.
Recorded runtime: Python 3.12.9, NumPy 2.5.2, SciPy 1.18.1, scikit-learn 1.9.0.
[constraints.txt](constraints.txt) reproduces the numerical dependency versions.
The 32.54 MiB JSON/NPZ bundle is ignored by Git at
`data/processed/ml_persona/model`; build it with the lifecycle commands below.
The loader uses `allow_pickle=False`, bounded files, hashes, strict schema and
numerical validation. Hashes are not signatures or a license to trust arbitrary
third-party model bundles.

## F. Evaluation

| Method | Test MRR | Recall@1 | Recall@5 |
| --- | --- | --- | --- |
| Selected TF-IDF/NMF | 0.432654 | 0.341373 | 0.530612 |
| Lexical TF-IDF baseline | 0.751621 | 0.660482 | 0.871985 |
| Expected random | 0.012742 | 0.001855 | 0.009276 |
| Training occupation frequency | 0.011943 | 0.001855 | 0.009276 |

This is 539-identity held-out cross-view retrieval, not customer-demand or
business-fit accuracy. **The custom NMF blend loses to lexical TF-IDF.** No
tuning followed inspection of this test. The next model comparison should use
validation-only selection and genuinely untouched business-labelled evaluation.

The generation probe returned 160 profiles across 32 batches with zero measured
structural failures, within-batch duplicate identities, or source-bundle changes.
Cosine diversity: 0.877963; age Jensen-Shannon divergence: 0.030183.
Exact source reuse is 100%, as intended. `not_in_workforce` accounts for 72/160
selections, revealing bias. Warm five-profile generation averaged 32.97 ms,
p95 34.30 ms on two CPU threads; this is not cold-load or API latency.

## G. Continuation Fixes

- Added optional backend-contract validation to the independent smoke command;
  lazy persona exports prevent schemas from initializing application settings.
- Bound prepared records and split membership back to the approved source,
  rather than relying only on editable local checksums.
- Excluded active owner-scoped source identities on repeated legacy, study,
  and dataset requests; corrected active counts and partial-batch persistence.
- Pinned Docker numerical dependencies after a real NumPy patch-version mismatch;
  preserved the artifact and strict compatibility checks.
- Added the missing model documentation, experiment results, and runtime guidance.

## H. Verification And Existing Functionality

### Post-Sync Verification (2026-09-09)

Five upstream commits were integrated and the saved ML work reapplied. The
following direct local checks passed after that sync; their scope and timing
are explicit so earlier live checks and publication are not conflated.

| Gate | Verified result / scope |
| --- | --- |
| Backend full offline suite | 1,284 passed, 3 integration tests deselected; 81.71% coverage; 456.45 s. Includes the packaging regressions previously checked separately. |
| Independent ML suite | 295 passed; 97% coverage; 42.42 s |
| Frontend suite | 269 passed across 36 files after upstream sync and the CSS token correction; final run 45.01 s |
| TypeScript and Vite build | Passed after the CSS token correction; 2,398 modules; Vite build 4.07 s |
| Theme check | Passed after the correction, with 0 violations; CSS editor diagnostics reported no errors |
| Ruff | Passed after upstream sync; no Python changes followed that check |
| Dependency consistency | `pip check` passed |
| Compose syntax | Both quiet Compose configuration checks passed; this is not a full app/web rehearsal |
| Real five-stage ML smoke | All 5 stages passed using the existing trained artifact, without LLM, network, or DB settings |

The documentation was subsequently pushed in `453a403`. Its first CI run passed
frontend, secret scanning, and Compose configuration, but fresh AnyIO 4.15.1
made Starlette's deprecated `BlockingPortal` import fatal during test collection.
The user-approved follow-up exempts only that exact third-party warning and
adds three tests proving other deprecations still fail. The full local backend
rerun passed **1,287 tests / 3 deselected**, **81.64%** coverage, in 474.91 s.
No package upgrades, application changes, or blanket warning suppression were
introduced. See the [implementation log](../docs/IMPLEMENTATION_PLAN.md) for
the initial CI failure and follow-up publication status.

The next CI run passed application tests and migrations but exposed a Linux-only
ML fixture issue: its broad subprocess mock intercepted Python's `uname -p`
hardware probe. The fixture now intercepts only the exact dataset verifier
command. Three additional regression cases pass; the complete ML suite now
passes **298 tests** locally. Production code and model artifacts are unchanged.
Linux CI verification is separate from that Windows result.

The theme check initially failed on upstream CSS. The user-approved correction
replaced four declarations across three stylesheets with existing theme tokens:
the new-study send shadow and studies CTA shadow use `var(--reflect)`, the light
selected tab uses `var(--bg-card)`, and the light interview glass uses
`var(--glass-soft)`. This separate, small frontend change does not alter layout
or JavaScript behavior; resolved token colors vary by theme. It does not fix or
reverify the mobile persona-header clipping observed before upstream styling.

The earlier live record of five unique USA-synthetic prototypes and 22 reported
synthetic attributes, two PostgreSQL integration tests, Linux inference from the
original Windows artifact with networking disabled, and the zero-known-CVE
audit below were not repeated as post-sync checks. They remain scoped evidence,
not observed customer validation. Pyright remains unavailable; full Compose
app/web and cross-conversation retrieval rehearsals were not repeated.

These local results do not establish successful publication. Commit, push,
and CI results are tracked in the [implementation log](../docs/IMPLEMENTATION_PLAN.md);
no push or CI success is claimed here.

### Earlier Verification Baseline (Before Upstream Sync)

| Gate | Result |
| --- | --- |
| Backend full offline suite | 1,279 passed, 3 integration tests deselected; 81.68% coverage |
| Independent ML suite | 295 passed; 97% coverage |
| Frontend suite / build | 269 passed across 36 files; TypeScript and Vite build passed |
| Packaging after runtime-pin fix | 26 passed, including 5 new tests added after the full backend run |
| Existing real PostgreSQL integration suite | 2 passed |
| Ruff / theme / dependency consistency / Compose syntax | Passed |
| Python vulnerability audit | No known vulnerabilities; two unpublished local packages skipped |
| Real five-stage ML smoke | Passed, including backend conversions without an LLM or DB |
| Real application flow | Five unique ML profiles persisted/reloaded; real copilot, 10 role suggestions, two interviews, four memory rows |
| Freellmpool | Seven successful requests served by `llm7/codestral-latest` through `freellmpool/auto`; existing OpenRouter quota cooldown worked |
| Docker build and inference | Original Windows-trained bundle loaded in Linux; five unique profiles generated with `--network none` |
| Browser | Desktop passed; mobile profile-header controls clipped. Zero JS exceptions/console errors/failed API reads in both tested viewports |

Live verification used a new local database, never the configured cloud DB.
The complete sanitized local evidence record is
`data/metadata/ml_persona_live_20260909_20260908_215004_181812.json`.
An initial probe-only correction left two cohorts (10 rows), all preserved.
No authentication credentials, provider keys, or existing databases were changed.

## I. Files

The recovered implementation already contained the model, preprocessing,
evaluation, CLI, dataset pipeline, four backend integrations, and their tests.
This continuation created:

- [README.md](README.md), [MODEL_CARD.md](MODEL_CARD.md),
  [EXPERIMENTS.md](EXPERIMENTS.md), this report, and
  [constraints.txt](constraints.txt).

Runtime and test changes in this continuation:

- [cli.py](src/bebshax_persona_ml/cli.py),
  [pipeline.py](src/bebshax_persona_ml/pipeline.py),
  [test_ml_pipeline.py](tests/test_ml_pipeline.py).
- [persona/__init__.py](../apps/backend/bebshax/persona/__init__.py),
  [persona/generation.py](../apps/backend/bebshax/persona/generation.py),
  [api/personas.py](../apps/backend/bebshax/api/personas.py),
  [personas/service.py](../apps/backend/bebshax/personas/service.py),
  [datasets/service.py](../apps/backend/bebshax/datasets/service.py).
- [ML contract tests](../apps/backend/tests/api/test_ml_persona_generation_contracts.py),
  [packaging tests](../apps/backend/tests/test_ops_env_parity.py),
  [backend Dockerfile](../apps/backend/Dockerfile).

Documentation updated: ML architecture/datasets; project README/context;
application architecture, persona engine, evaluation, API contract, setup, and
the append-only implementation log. Evaluation and live evidence were generated
locally; model weights and split files were preserved, not committed.

## J. Run From The Repository Root

```powershell
# Install the numerical runtime used by the reference artifact.
.venv/Scripts/pip.exe install -c ml_persona/constraints.txt -e ml_persona -e "apps/backend[dev]"

# Fresh checkout: fetch, prepare, fit on train/select on validation, evaluate.
.venv/Scripts/python.exe -m bebshax_persona_ml download
.venv/Scripts/python.exe -m bebshax_persona_ml prepare
.venv/Scripts/python.exe -m bebshax_persona_ml validate
.venv/Scripts/python.exe -m bebshax_persona_ml train --config ml_persona/configs/training.json
.venv/Scripts/python.exe -m bebshax_persona_ml evaluate

# Already-trained checkout: inference and complete local contract smoke.
.venv/Scripts/python.exe -m bebshax_persona_ml generate --input ml_persona/examples/business.json --num-personas 5
.venv/Scripts/python.exe -m bebshax_persona_ml smoke --backend --input ml_persona/examples/business.json

# Offline regression tests; live DB tests require an isolated configured DB.
.venv/Scripts/python.exe -m pytest apps/backend/tests -q
.venv/Scripts/python.exe -m pytest ml_persona/tests -q
npm --prefix apps/frontend test -- --run --maxWorkers=1 --minWorkers=1
npm --prefix apps/frontend run build

# Existing application launcher; uses the application's configured database.
node scripts/dev.js
```

On this recovered checkout, preparation/training/evaluation outputs already
exist: use inference/smoke directly. Existing outputs are not overwritten
without explicit `--force`. Do not retune on the test set already inspected.
Full environment/auth/database setup is in [SETUP.md](../docs/SETUP.md).

## K. Known Limitations

This is not production-ready customer modeling: USA-only synthetic prototypes,
regex-derived pain points, weak student/geographic fit, demographic/selection
bias, and the stronger lexical baseline limit its research claims. No real
business-labelled relevance or predictive attribute-accuracy evaluation exists.
No incomes, purchase frequencies, or personality measurements are learned here.

Sequential source exclusions do not impose a transactional uniqueness lock on
independent concurrent requests. Mobile profile-header clipping was observed
before upstream styling, with a working lower Close button; the token-only
correction neither fixes it nor constitutes a new browser check. Pyright was
unavailable, a full Compose app/web rehearsal was not repeated, and
cross-conversation retrieval was not tested live. The earlier audit found no
known dependency CVEs, but unpublished local code is outside PyPI vulnerability
coverage. Review and customer validation are still required before relying on
these personas for business decisions.

Final independent scoped review approved the integrity, exclusion, and packaging
fixes with no new high/medium findings. At the end of that recorded verification,
the changes were uncommitted and the remote branch was five commits ahead of
the tested working tree. This is a historical session snapshot, not the ongoing
publication status. Subsequent upstream integration and local gate results are
recorded in [Post-Sync Verification](#post-sync-verification-2026-09-09).
Commit, push, and CI results belong in the
[implementation log](../docs/IMPLEMENTATION_PLAN.md); successful publication is
not asserted by this report.