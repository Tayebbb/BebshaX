# Persona ML Implementation Report

Date: 2026-09-10. Status: working research prototype with measured limitations.

## Maintenance: Artifact Release Guards (2026-09-10)

Current continuation completed within the exclusive ML scope. The configured
lexical strategy was already implemented and passed the 42-test focused
preflight. Two actual artifact-release gaps were then reproduced test-first:

- Metadata-only readiness accepted impossible lexical/NMF topic combinations
  and a lexical algorithm declared as schema 1. The shared metadata validator
  now rejects these before claiming configured readiness, without loading weights.
- Schema-2/3 loading accepted rehashed attribution for a different source or
  revision and could silently export unknown attribution. The loader now requires
  exact attribution coverage of loaded records, while allowing provenance for
  incomplete source records filtered out during fitting.

Eighteen regression cases were added. Manifest tests first had 4 failures/4
passes, then 8 passes. Attribution tests first had 8 failures/9 passes, then 17
passes. Both fixes preserve valid artifact fingerprints, source records and
legacy schema-1 unknown provenance. No new training, threshold tuning, LLM call,
private data, dataset download, dependency install, environment/default change,
backend code edit, shared import fix, commit, push or deployment was performed.
The root coordination log remains outside this exclusive ownership scope.

### Changed Files

- [src/bebshax_persona_ml/model.py](src/bebshax_persona_ml/model.py)
- [tests/test_ml_model.py](tests/test_ml_model.py)
- [README.md](README.md)
- [EXPERIMENTS.md](EXPERIMENTS.md)
- [DATASETS.md](DATASETS.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [MODEL_CARD.md](MODEL_CARD.md)
- This [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md).

### Commands And Results

Run from `E:/BebshaX` with the explicit repository interpreter. Test/measurement
children were launched sequentially with PowerShell `Start-Process -Wait` and
dedicated ML-local logs because other workstreams shared the terminal. Counts
come from matching completed reports/JUnit, not interleaved terminal output.
Interrupted launches are not passing evidence. Test dotenv loading was disabled;
temporary files and coverage remained under ignored `ml_persona/.verification/`.

```powershell
.venv/Scripts/python.exe -B ml_persona/tools/verify_modernization.py --scope model --keyword manifest_and_load_reject_inconsistent_strategy_dimensions
.venv/Scripts/python.exe -B ml_persona/tools/verify_modernization.py --scope model --keyword attribution
.venv/Scripts/python.exe -B ml_persona/tools/verify_modernization.py --scope ml --coverage
.venv/Scripts/python.exe -B ml_persona/tools/verify_modernization.py --scope adapter
.venv/Scripts/python.exe -B ml_persona/tools/verify_modernization.py --scope runtime
.venv/Scripts/python.exe -B ml_persona/tools/modernization_experiment.py --experiment experiment-20260909-w1-w7-1823 --phase revalidate
.venv/Scripts/python.exe -B -m bebshax_persona_ml --root E:/BebshaX smoke --backend --model data/processed/ml_persona/experiment-20260909-w1-w7-1823/model --input ml_persona/examples/business.json --threads 2
.venv/Scripts/python.exe -B -m ruff check --no-cache --select E9,F63,F7,F82 ml_persona/src/bebshax_persona_ml/model.py ml_persona/tests/test_ml_model.py
```

| Gate | Actual Result | Evidence Under `.verification/` |
| --- | --- | --- |
| Preflight lexical/relevance/manifest/tokenizer | 42 passed | `20260910T103615Z_d7beb0631800/report.json` |
| Manifest RED / GREEN | 4 failed, 4 passed / 8 passed | `20260910T103728Z_247e88306038` / `20260910T103909Z_f6b7acde099f` |
| Attribution RED / GREEN | 8 failed, 9 passed / 17 passed | `20260910T104141Z_019a851333d1` / `20260910T104433Z_64ab8d30d81d` |
| Complete ML suite, run once after code changes | 379 passed, 74.76 s pytest / 75.4332 s verifier wall, exit 0 | `20260910T104524Z_fdcafc0cb3cf/report.json` |
| ML branch-inclusive coverage | 95.45%, 80% floor; 1,191 statements, 346 branches | `20260910T104524Z_fdcafc0cb3cf/coverage.json` |
| Backend adapter | 39 passed, 2.17 s pytest, exit 0 | `20260910T105042Z_8ce943285e67/report.json` |
| Runtime readiness/pins/admission | 21 passed, 6.11 s pytest, exit 0 | `20260910T105121Z_c340afb539ac/report.json` |
| Existing-artifact revalidation | Exit 0, 128.3669590 s, all frozen bytes unchanged | `20260910T105318Z_00f185a74166/report.json` |
| Fresh-process real lexical smoke | Five stages passed, five profiles; source/prepared/model/generation/backend | `continuation-candidate-smoke-20260910.json` |
| Changed-Python bug-tier Ruff / editor diagnostics | Passed | Scoped direct checks |

No like-for-like pre-edit coverage baseline was collected, so no coverage delta
is claimed. The unchanged fresh-process provider/DB import guard passes in the
full suite after the data owner's pure-embedding/lazy-service fix. It was not
skipped, weakened or reimplemented here. No full backend, live HTTP/DB/LLM,
cross-platform packaging or independent code/security review was performed.
Independent reviewer tools were unavailable; these passes are not release sign-off.

### Artifact And Remaining Gates

The existing schema-3 candidate at
`data/processed/ml_persona/experiment-20260909-w1-w7-1823/model` loads and serves
with its recorded manifest expectation. Metadata SHA-256 is unchanged:
`dd9d15d0088a3a7500ed52cf095acdef1a6c03b3903779bb20cd0ec7108de604`.
Revision: `27ad0911014cb01e8d6d891e43dc18edf75632ae919bf3413121dbbb6a404835`.
Its historical 2,516-record, zero-NMF fit is reused, not claimed as new training.
Current validation MRR is 0.7166454265 versus frozen NMF 0.4181169683. Under the
declared business-example input, warm five-record mean/p95 is 96.1488/124.0977 ms
versus 118.2058/182.1433 ms; these are contended loaded-model timings, not an SLA.
Full resource origins, unchanged reference hashes and limitations are in
[EXPERIMENTS.md](EXPERIMENTS.md#continuation-verification-2026-09-10).

Mandatory lexical/runtime consistency and attribution-retention fixes are tested
complete at the scopes above. Promotion is separate: the NMF baseline stays at
historical revision `7eb2fa6f748fac32b6e987e9057004d477a45e834a457b2701060360ca78b247`.
No predeclared fresh relevance validation supports a default switch. The real
remaining work is independent code/security review and trusted deployment-pin
provisioning, fresh authorized business/abstention labels and an untouched
holdout with bias/student/geography assessment, then an explicit promotion
decision. MiniLM remains optional research until a parent-approved acquisition
manifest and scheduled R8-reviewed runtime exist; full-token coverage, pooling,
parity and quality must be tested before any claim. No labels were invented and
the already-inspected historical test partition was not used for tuning/scoring.

## Maintenance: Runtime Readiness (2026-09-10)

Earlier maintenance record. Its import failure is resolved in the continuation
above; the original results below remain historical evidence.

Implemented within the exclusive ML/adapter ownership scope. No main/config,
shared database, domain/API schema, other requirements, root docs, environment,
deployed artifact or historical dataset/report changes were made. No install,
download, LLM/database call, commit, push or deployment was performed.

Concrete fixes:

- Added typed, asynchronous, metadata-only adapter readiness. The startup
  fallback rejected schema 3 while the true loader accepted it. The adapter
  now uses the ML-owned schema validator; configured is not loaded/available.
- Shared manifest checks between readiness and the loader; kept bounded files,
  exact runtime/tokenizer checks, expected pins, original fingerprints and
  full numerical/payload validation. Failed weight loads remain unavailable.
- Fixed `from_settings` ignoring configured pins and feature state. Missing
  hosted pins and disabled features fail closed without any LLM fallback.
- Preserved cancellation-safe admission for readiness and inference, with
  tests at one and two slots. No already-running worker is discarded to free
  capacity prematurely; no cancelled waiter is sent to the worker pool.
- Added no-refit measurement mode with validation-only scoring, immutable
  experiment checks, current-code drift disclosure, honest timing origin and
  ML-local non-overwriting reports. Test verifier disables dotenv loading and
  isolates temporary/JUnit/coverage files within the owned ML directory.

The existing schema-3 lexical fit is preserved and reused, not unnecessarily
retrained. Its recorded 2,516-record fit took 8.7024609 seconds at two numerical
CPU threads with zero NMF calls. Current real validation still measures
MRR 0.7166454265 against frozen NMF 0.4181169683; source-preserving conversions,
strict abstention, age/exclusions, readiness and pool checks passed. All 539
old test identities remain historical/integrity-only, with no tuning or scoring.
Exact artifact/run paths and performance qualifications are in
[EXPERIMENTS.md](EXPERIMENTS.md#runtime-revalidation-2026-09-10).

Final verification records (all `.verification/` paths are ignored local evidence):

| Gate                                                     | Actual Result                                                                     | Run ID                            |
| -------------------------------------------------------- | --------------------------------------------------------------------------------- | --------------------------------- |
| Pre-edit lexical/relevance/manifest                      | 29 passed                                                                         | `20260910T041539Z_bd5cd154540a`   |
| Full ML, single process, branch coverage floor 80%       | 360 passed / 1 failed; 95.3887% combined coverage; process exit 1, 96.097 s JUnit | `20260910T044325Z_10d3542817ef`   |
| Runtime readiness/admission                              | 21 passed                                                                         | `20260910T044037Z_60c99e735a00`   |
| Backend adapter/conversions                              | 39 passed                                                                         | `20260910T044503Z_7e6bdb92008a`   |
| Existing backend schema                                  | 5 passed                                                                          | `20260910T044508Z_3f8f7836c93d`   |
| Existing adapter contracts                               | 6 passed                                                                          | `20260910T044512Z_159c03bc273f`   |
| Real saved-artifact revalidation, no fit/test scoring    | Exit 0, 52.1223003 s; frozen bytes unchanged                                      | `20260910T044658Z_cb445cd35968`   |
| Scoped bug-tier Ruff and fresh editor diagnostics        | Pass                                                                              | Direct scoped checks              |
| Edited-doc local targets / scoped diff whitespace        | 78 valid targets, 0 broken; diff check exit 0                                     | Direct scoped checks              |
| Offline package build (`python -m build --no-isolation`) | Blocked: `No module named build`; no packages installed                           | Explicit repository Python 3.12.9 |

The readiness regressions were RED before the implementation (12 failures in
`20260910T041858Z_c5631e072c00`), and the factory tests separately proved six
RED failures before the hosted-pin fix (`20260910T042745Z_bf23dbf80f35`).
An initial focused command failed because its temporary parent directory did
not exist; the isolated verifier repaired that harness problem. Shared terminal
output was interleaved with other workers, so counts above come from matching
completed verifier reports/JUnit rather than unrelated output. All actual
test/measurement children use the explicit repository Python 3.12.9, pinned
numerical versions and two CPU threads. Checks finished; no required training
or test job was left running.

### Historical Import Gate (Resolved)

`test_smoke_backend_fresh_process_avoids_settings_reads_and_external_services`
failed in that earlier run because importing `bebshax.personas.ml_adapter` executed
`personas/__init__.py -> personas/service.py -> db/models.py ->
llm/adapters/embeddings.py -> freellmpool.client`. Importing an independent
persona converter should not require a provider SDK. Those shared files are
outside this workstream; the guard was preserved unchanged. The data owner fixed
the eager dependency. The current 379-pass full ML run and actual fresh-process
lexical smoke verify the fix without edits to those shared files. No full
backend or live LLM/DB suite was run in this continuation.

The coverage total is measured over 1,180 statements and 338 branches, with
1,144 statements and 304 branches covered. Passing the coverage floor does
not turn the one-failure ML suite into a pass. Wheel/distribution packaging
was not verified because the build frontend (and local setuptools/wheel
metadata) is absent; dependency setup belongs to the parent-scheduled window.

No new main argument or domain schema is required for the fix: existing
readiness introspection accepts `configured|available|unavailable`. The exact
constructor/settings parameters and full typed status mapping are documented
in [README.md](README.md#readiness-and-parent-integration). Startup currently
projects status/reason only; preserving the other readiness fields is a
parent-owned capability-reporting enhancement, not a changed claim here.

Pretrained execution is blocked by absent runtimes and unapproved weight
acquisition. The same MiniLM model is mapped to an immutable researched
revision, with an exact minimal ONNX/tokenizer runtime candidate and no
nonworking code stub. See the [R8 review](ARCHITECTURE.md#minimal-pretrained-candidate-2026-09-10).
Fresh human business labels, geography/student membership, representativeness,
and untouched-test/promotion approval remain pending. No production promise.

## Maintenance: Batch 1E (2026-09-09)

Implemented within `ml_persona/**` only: explicit no-NMF lexical fit/load/serve,
typed strategy-aware artifacts, positive-score cohort support gate, verified
source attribution and source/code digests, optional expected-manifest and
installed-code verification, and isolated validation-only CLI experiments.
Schema-1 NMF/default behavior and reference fingerprints remain supported.
No production promotion, backend/shared adapter, setup manifest, environment,
existing runtime-data, dependency, model download, service, or root-doc edit was made.
The coordinator owns the root execution log and broader batch completion.

TDD observations: strategy 3 RED -> 21 focused GREEN; relevance 10 RED -> 12
GREEN; lexical evaluation 1 RED -> 1 GREEN; grid/CLI 3 RED -> 3 GREEN;
provenance 8 RED -> 11 GREEN; source/export 5 RED -> 5 GREEN; final boundaries
6 RED -> 11 GREEN. Serialization/indentation defects found during GREEN were
fixed before proceeding. Existing unit fixtures that expected zero-score
fillers were corrected to include relevant query text while retaining their
age/exclusion/identity/diversity assertions. No saved test data or metrics were
edited to tune the new selector. Interrupted terminal attempts are not passes.

Completed ML suite: **344 passed, 52.76 s, 95.92% branch-inclusive coverage**,
80% floor. Bug-tier Ruff and editor diagnostics passed. Coverage is measured,
not estimated; no prior matching branch-coverage baseline was captured, so no
coverage delta is claimed. There were no backend or full frontend test runs.
Independent code/security reviewers were not available in this session; hand
the ML changes and manifest trust boundary to their owners before promotion.

Actual training used existing approved prepared data, Python 3.12.9 and exactly
NumPy 2.5.2 / SciPy 1.18.1 / sklearn 1.9.0, CPU thread cap two, E: temporary
storage. The original four NMF configurations plus one lexical candidate took
46.7016760 s total fitting / 78.0080724 s training CLI wall time. Lexical won
validation MRR 0.7166454265 vs 0.4181169683 for the best NMF; the unchanged saved
NMF artifact independently reproduced 0.4181169683 on validation. No test split
evaluation, new human labels, or fresh business-quality claim was made.

New artifact: `data/processed/ml_persona/modernization-lexical/model`.
Revision: `50ad6cf6998650f0594a234453954671b9aea0159f5ad29b1ae53b980f2f304c`.
Metadata SHA-256: `6b84ddc79bb165e07fa994c4181170b46e89ae7f4eed470b83b4ba11da62d0ed`.
The real artifact passed expected-manifest and installed-training-code checks;
the real CLI export retained full synthetic source bundles, attribution and
positive scores. Full metrics/fingerprints and limits are in
[EXPERIMENTS.md](EXPERIMENTS.md#batch-1e-validation-only-benchmark); exact new
public APIs and backend handoff are in [README.md](README.md#artifact-and-integration-apis).

Real-business labels, population/student/geography validation, backend export
mapping and trusted-pin provisioning remain external gates. Hashes are not
signatures. No Git, deployment, or service actions were taken for this batch;
the publication record below describes the historical implementation only.

Publication confirmed through code commit `be92185` on `origin/main`.
[GitHub Actions run 34299654884](https://github.com/Tayebbb/BebshaX/actions/runs/34299654884)
passed backend/ML, frontend, migrations, secret scanning, and Compose checks.
The advisory, non-blocking typecheck job remained failed. This is a successful
required CI gate, not production/customer-fit approval or zero type debt.
The [publication log](../docs/IMPLEMENTATION_PLAN.md) records the commits and
the two CI compatibility fixes without rewriting earlier verification history.

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

| Dataset                       | Source / License                                                                                                                                                     | Size / Purpose / Fields                                                                                                                                                                     |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NVIDIA Nemotron-Personas-USA  | [Pinned source](https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA/blob/5b4cd35ab46490c1da1bd2b5a2324d6f871be180/README.md), NVIDIA Corporation, CC-BY-4.0 | 6,000 hash-selected synthetic profiles from one 244 MB shard; UUID, age, occupation, education, source geography and full narratives/skills/interests/goals; synthetic training priors only |
| Google Synthetic-Persona-Chat | [Source](https://huggingface.co/datasets/google/Synthetic-Persona-Chat), CC-BY-4.0                                                                                   | Researched, not used for ML: missing required demographics                                                                                                                                  |
| PersonaHub                    | [Source](https://huggingface.co/datasets/proj-persona/PersonaHub), CC-BY-NC-SA-4.0                                                                                   | Researched, not used for ML: license restrictions and insufficient structure                                                                                                                |
| UCI Restaurant Consumer Data  | [Source](https://archive.ics.uci.edu/dataset/232/restaurant+consumer+data), CC-BY-4.0                                                                                | 138 people / 1,161 ratings; not downloaded or used: real-person privacy and narrow domain conflict with the approved synthetic-only policy                                                  |

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
Missing/incompatible artifacts yield 503; unsupported/exhausted selection yields 422. Neither condition falls back to LLM persona writing. Chat still works when
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

| Method                        | Test MRR | Recall@1 | Recall@5 |
| ----------------------------- | -------- | -------- | -------- |
| Selected TF-IDF/NMF           | 0.432654 | 0.341373 | 0.530612 |
| Lexical TF-IDF baseline       | 0.751621 | 0.660482 | 0.871985 |
| Expected random               | 0.012742 | 0.001855 | 0.009276 |
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

| Gate                       | Verified result / scope                                                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Backend full offline suite | 1,284 passed, 3 integration tests deselected; 81.71% coverage; 456.45 s. Includes the packaging regressions previously checked separately. |
| Independent ML suite       | 295 passed; 97% coverage; 42.42 s                                                                                                          |
| Frontend suite             | 269 passed across 36 files after upstream sync and the CSS token correction; final run 45.01 s                                             |
| TypeScript and Vite build  | Passed after the CSS token correction; 2,398 modules; Vite build 4.07 s                                                                    |
| Theme check                | Passed after the correction, with 0 violations; CSS editor diagnostics reported no errors                                                  |
| Ruff                       | Passed after upstream sync; no Python changes followed that check                                                                          |
| Dependency consistency     | `pip check` passed                                                                                                                         |
| Compose syntax             | Both quiet Compose configuration checks passed; this is not a full app/web rehearsal                                                       |
| Real five-stage ML smoke   | All 5 stages passed using the existing trained artifact, without LLM, network, or DB settings                                              |

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

| Gate                                                   | Result                                                                                                                              |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| Backend full offline suite                             | 1,279 passed, 3 integration tests deselected; 81.68% coverage                                                                       |
| Independent ML suite                                   | 295 passed; 97% coverage                                                                                                            |
| Frontend suite / build                                 | 269 passed across 36 files; TypeScript and Vite build passed                                                                        |
| Packaging after runtime-pin fix                        | 26 passed, including 5 new tests added after the full backend run                                                                   |
| Existing real PostgreSQL integration suite             | 2 passed                                                                                                                            |
| Ruff / theme / dependency consistency / Compose syntax | Passed                                                                                                                              |
| Python vulnerability audit                             | No known vulnerabilities; two unpublished local packages skipped                                                                    |
| Real five-stage ML smoke                               | Passed, including backend conversions without an LLM or DB                                                                          |
| Real application flow                                  | Five unique ML profiles persisted/reloaded; real copilot, 10 role suggestions, two interviews, four memory rows                     |
| Freellmpool                                            | Seven successful requests served by `llm7/codestral-latest` through `freellmpool/auto`; existing OpenRouter quota cooldown worked   |
| Docker build and inference                             | Original Windows-trained bundle loaded in Linux; five unique profiles generated with `--network none`                               |
| Browser                                                | Desktop passed; mobile profile-header controls clipped. Zero JS exceptions/console errors/failed API reads in both tested viewports |

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
- [persona/**init**.py](../apps/backend/bebshax/persona/__init__.py),
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
