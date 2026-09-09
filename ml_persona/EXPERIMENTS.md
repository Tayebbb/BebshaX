# Persona ML Experiments

Last verified: 2026-09-09.

## Run And Evidence

Training artifacts survived the interrupted session; the selected bundle was
evaluated after resuming on 2026-09-09. Numerical results below come from the
saved experiment and the completed held-out evaluation. The recovered model
was not retrained or retuned after inspecting the test results.

| Record | Local Path |
| --- | --- |
| Ingestion | `data/metadata/nemotron_personas_usa_ml.json` |
| Preparation | `data/processed/ml_persona/preparation.json` |
| Selection | `data/processed/ml_persona/experiment.json` |
| Versioned selection | `data/processed/ml_persona/experiments/<model_version>.json` |
| Final test | `data/processed/ml_persona/evaluation.json` |
| Fitted bundle | `data/processed/ml_persona/model/` |

These are local outputs, not clean-checkout download links. The selected model
version is `7eb2fa6f748fac32b6e987e9057004d477a45e834a457b2701060360ca78b247`.
Dataset fingerprint:
`d0e9d8f4e9c2af263aa2c8c5ee59710468a00f7bf0be08f02466e6aa663e71c1`.
Experiment fingerprint:
`b8d7fd09ff220a5e9e38b787e95392a604f6bfc510a555bb1f3d084c5dca98c3`.
The preparation/source-verification and backend-smoke hardening on resume did
not require replacing the selected model or its recorded fingerprints.

## Preparation And Selection Protocol

The bounded approved source emits 6,000 profiles. Normalization accepts 4,694,
rejects 1,306 as `invalid_schema`, and reports no first-pass ID/content
duplicates. Removing 1,078 incomplete and 22 duplicate-identity candidates
leaves 3,594 usable records. Seed 42 produces train/validation/test counts of
2,516/539/539 with 70/15/15 shares and disjoint identities. Ingestion scalar
missing/invalid counters are a different check and were all zero; see
[DATASETS.md](DATASETS.md).

Only training records fit TF-IDF vocabulary/IDF, NMF topics, and profile
representations. [The configuration](configs/training.json) searches the
Cartesian product of 16/32 topics and lexical weights 0.35/0.7. Other settings
are seed 42, 8,000 maximum features, 300 maximum iterations, diversity weight
0.25, temperature 0.03, CPU, and two numerical threads. Selection maximizes
validation `retrieval.model.mrr`; a tie uses ascending canonical config JSON.
The test partition does not select hyperparameters or refit the model.

| Topics | Lexical Weight | Validation MRR |
| --- | --- | --- |
| 16 | 0.35 | 0.19710149642765074 |
| 16 | 0.70 | 0.36913421943750657 |
| 32 | 0.35 | 0.2383700341543759 |
| 32 | 0.70 | **0.41811696827631073** |
| Lexical TF-IDF baseline | 1.00 | **0.7166454265071603** |

The last NMF configuration wins the configured grid but loses to the lexical
baseline. The standalone lexical baseline is evaluated, not installed as the
production selector. The experiment record's `test_evaluated: false` describes
the selection stage; the separate resumed test report now exists.

Recorded environment: Python 3.12.9, NumPy 2.5.2, SciPy 1.18.1,
scikit-learn 1.9.0; Windows 11 (`Windows-11-10.0.26200-SP0`), AMD64,
Intel64 Family 6 Model 154 Stepping 3, 16 logical CPUs, two numerical threads.
The four fits took 43.6982491 seconds in total, excluding validation and other
lifecycle work. No GPU/PyTorch was involved. Exact numerical versions are
required by the loader and recorded in [constraints.txt](constraints.txt).

## Final Test Protocol And Results

[Evaluation code](src/bebshax_persona_ml/evaluation.py) uses culinary and hobby
narratives as queries, and complementary professional, sports, arts, travel,
skills, and goals as candidate profiles. Identity description and explicit
protected fields are excluded from those views. There are 539 held-out
candidates/queries, all 539 with scorable views, and no missing/OOV pairs.
Training-only transforms rank the held-out candidates; the correct match is the
other view of the same held-out identity. Missing/OOV views would count as misses,
not be removed from the denominator.

Random ranking is the exact expected uniform rank, not a lucky sampled run.
The popularity baseline uses training occupation frequencies with seeded random
ties. Neither baseline fits held-out labels. Retrieval results do not evaluate
MMR batch selection quality directly; generation has separate structural probes.

| Method | MRR | Recall@1 | Recall@5 | Recall@10 |
| --- | --- | --- | --- | --- |
| Selected model | 0.43265430767833196 | 0.3413729128 | 0.5306122449 | 0.6141001855 |
| Lexical TF-IDF | 0.7516210382537256 | 0.6604823748 | 0.8719851577 | 0.9294990724 |
| Expected random | 0.012741852676724338 | 0.0018552876 | 0.0092764378 | 0.0185528757 |
| Popular occupation | 0.011943168742486186 | 0.0018552876 | 0.0092764378 | 0.0129870130 |

No tuning followed this test. The NMF blend is weaker than lexical TF-IDF on
both validation and test. This is a synthetic cross-view retrieval result,
not measured customer demand, attribute predictive accuracy, or real
business-labelled relevance. There are no real business-labelled evaluations.

## Generation Probe

Up to 32 seeded, scorable held-out queries request five training prototypes
each. Oversized contexts would be skipped rather than truncated. The recorded
test run produced 32 successful batches and 160 selected profiles.

| Check | Result |
| --- | --- |
| Failed batches | 0 |
| Incomplete / underage profiles | 0 / 0 |
| Within-batch duplicate IDs / names / descriptions | 0 / 0 / 0 |
| Bundle mismatch / location rewrite | 0 / 0 |
| Exact normalized-source reuse | 1.0, expected for prototype selection |
| Mean within-batch TF-IDF cosine distance | 0.8779632658 over 320 pairs |
| Age Jensen-Shannon divergence | 0.030183258935548987, base 2, against held-out synthetic records |
| Selected `not_in_workforce` occupation | 72 / 160, a material bias |
| Warm five-persona generation | Mean 32.971875 ms; p95 34.304875 ms, two CPU threads |

Duplicate counts are within batches, not a promise of globally unique future
requests. Age divergence excludes unknown/invalid ages and counts them
separately; none occurred here. The latency measurement times loaded-model
generation only, excluding cold load, API scheduling, DB persistence, and
network latency. It is not a service SLA or throughput benchmark. Reused source
profiles and structural consistency are not novel identities or validated
student/Bangladesh customer fit.

## Verification (2026-09-09)

These direct local checks passed after upstream sync. Exact timings and scope
are in the [post-sync verification record](IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09);
commit, push, and CI results are separate from these local passes.

| Gate | Reported Result |
| --- | --- |
| Backend offline suite | 1,284 passed, 3 deselected; coverage 81.71%, floor 68% |
| Independent ML suite | 295 passed; coverage 97% |
| Frontend suite | 269 passed across 36 files after sync and the CSS token correction; final run 45.01 s |
| Packaging regressions | Included in the full 1,284-test backend run; earlier standalone 26-case result retained in the implementation report's baseline |
| Build / TypeScript / theme checks | Latest checks PASS after the four-declaration CSS token correction; 0 theme violations; no frontend `lint` script is declared |
| Ruff | PASS after upstream sync; no subsequent Python changes |
| Dependency consistency / Compose default and full syntax | `pip check` PASS; both quiet Compose syntax checks PASS |
| Real CLI `smoke --backend --input ml_persona/examples/business.json` | PASS: source, prepared, model, generation, backend conversion |
| Pyright | Unavailable; remaining static-analysis debt is advisory, not a passing Pyright run |

After documentation push `453a403`, fresh CI dependencies exposed an exact
Starlette/AnyIO deprecation during test collection. The approved warning-policy
follow-up passed **1,287 backend tests / 3 deselected, 81.64% coverage**, including
three tests that preserve fatal handling of unrelated warnings. This does not
change the model, training, or evaluation. The [implementation log](../docs/IMPLEMENTATION_PLAN.md)
separates the first CI failure from local follow-up verification.

The subsequent Linux run reached ML tests and exposed the source fixture's
overly broad subprocess mock, which intercepted `uname -p` hardware reporting.
The exact-verifier-only mock and three new regression cases pass locally:
**298 ML tests**. This is a test-isolation correction, not model retraining or
changed evaluation. Linux CI must confirm the corrected fixture independently.

### Earlier Live And Dependency Checks

These checks predate upstream sync and were not repeated:

| Gate | Reported Result |
| --- | --- |
| Existing PostgreSQL integration tests | 2 passed against the isolated local database |
| Python dependency audit | No known vulnerabilities; local `bebshax` and `bebshax-persona-ml` packages skipped as not on PyPI |
| Backend Docker build and offline inference | PASS with reference-runtime constraints; five unique sources, ages 19/20/19/20/24, networking disabled |
| Live API / database / provider flow | 5 unique ML profiles persisted/reloaded, 22 SYNTHETIC attributes reported, zero persona-generation LLM calls; real copilot, 10 role suggestions, 2 interview turns, 4 memory rows |
| Live browser | Desktop 1440x1000 passed; mobile 390x844 showed clipped profile-header controls. Both had zero JS exceptions, console errors, or failed API reads |

The browser result predates upstream styling. The later token-only correction
does not fix the mobile clipping or constitute browser re-verification.

The backend smoke exercises real `GeneratedPersona`, `PersonaProfile`, draft,
and workflow mappings, preserved source data, and zero observed evidence. It
uses no LLM, network, settings initialization, or DB connection. Local unit and
conversion checks are separate from the real database/provider checks.

The live flow used a new local scratch database, not the configured cloud DB.
Seven successful routed requests were served by `llm7/codestral-latest` through
`freellmpool/auto`; OpenRouter quota exhaustion was handled by existing routing.
The sanitized local run record is
`data/metadata/ml_persona_live_20260909_20260908_215004_181812.json`.
An initial probe-only JSONB comparison correction left a second cohort, so
10 scratch persona rows remain; reported uniqueness concerns the verified
five-profile cohort. No repeated-provider attempts were used to conceal failure.

The first Docker inference failed correctly because an unconstrained build
installed NumPy 2.5.3 rather than the artifact's 2.5.2. The image now applies
the reviewed runtime constraints; the same network-disabled check passed on
rebuild without changing artifact metadata. A full Compose app/web rehearsal
and cross-conversation memory retrieval were not performed in this run.

## Next Experiments (Not Implemented)

Compare TF-IDF with the same MMR-style diversity selection using validation
only; the existing lexical result is a reason to test that simpler selector,
not to claim it has already replaced the current model. Separately obtain
authorized held-out business-labelled relevance judgments, including explicit
student and geography mismatch review. Freeze the next choice before any new
untouched test evaluation; do not recycle the already-inspected test set for
tuning. These follow-up experiments have not been implemented.