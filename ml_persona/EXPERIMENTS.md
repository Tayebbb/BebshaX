# Persona ML Experiments

Last verified: 2026-09-10. Historical test results below are not fresh holdout evidence.

## Continuation Verification (2026-09-10)

This is the current verification record; the earlier runtime run below is
retained as historical evidence. The existing lexical implementation already
passed 42 focused model tests. Two additional release-guard gaps were reproduced
and fixed: inconsistent strategy/topic metadata passed metadata-only readiness,
and schemas 2/3 accepted rehashed attribution for a different source/revision.
Eighteen regression cases were added. No selection weights, training settings,
prepared records, model artifacts, dependencies or application defaults changed.

The complete ML suite was run once after the code changes: **379 passed in
74.76 s**, **95.45% branch-inclusive coverage**, 80% floor, exit 0. The unchanged
fresh-process import guard now passes after the data owner's fix. Separately,
39 adapter tests passed in 2.17 s and 21 runtime tests passed in 6.11 s. These
include full-record conversions, expected pins, hosted fail-closed settings,
input bounds, exclusions and cancellation-safe admission at one/two slots.
All five actual-candidate smoke stages passed in a fresh interpreter. Exact
commands and evidence IDs are in the
[implementation report](IMPLEMENTATION_REPORT.md#maintenance-artifact-release-guards-2026-09-10).

### Saved-Artifact Comparison

No fit, search, test-partition scoring, download or install occurred. Revalidation
report `.verification/20260910T105318Z_00f185a74166/report.json` completed with
exit 0 in **128.3669590 s**, checked approved preparation/source integrity and
both archived selections, and verified frozen model/split/report bytes before
and after. Fitting is blocked by the harness. The historical 539 test records
were integrity-checked, never scored. Both comparisons use the same 539-record
validation partition, with 539/539 scorable pairs.

| Loaded Artifact | Validation MRR | Recall@1 | Recall@5 | Recall@10 |
| --- | --- | --- | --- | --- |
| Schema-3 lexical | 0.7166454265 | 0.6196660482 | 0.8367346939 | 0.8979591837 |
| Frozen schema-1 NMF | 0.4181169683 | 0.3320964750 | 0.4953617811 | 0.5955473098 |

Lexical equals its own TF-IDF baseline; this is not a new business-quality or
untouched-holdout result. The validation generation probe still selects
`not_in_workforce` 47/160 times for lexical. The complete canonical source
records are unchanged, not relabelled as observed customers or students.

### Separate Resource Probe

Declared input: [examples/business.json](examples/business.json), food delivery,
hard ages 18-24, five complete records, seeds 0-31. Python 3.12.9, NumPy 2.5.2,
SciPy 1.18.1 and scikit-learn 1.9.0; CPU only, two numerical threads. Measurements
run sequentially after validation in one process. A fresh adapter is not a cold
interpreter or cold filesystem; other workstreams were active. These timings
are slower than the earlier run, which remains below rather than being removed.

| Measurement | Lexical | NMF Reference |
| --- | --- | --- |
| Fresh-adapter model load, s | 2.0639278 | 1.5634776 |
| First adapter request, s | 2.1979549 | 1.6805701 |
| Warm five-record model generation mean, ms | 96.1488469 | 118.2058469 |
| Warm five-record model generation p95, ms | 124.0976950 | 182.1432600 |
| Whole-process working set after serving, bytes | 259,121,152 | 280,993,792 |

Each artifact loaded once, preserved 160/160 complete warm-probe bundles with
zero hard-age or zero-score violations, passed 20 backend conversion checks,
returned ten distinct sequential excluded sources, and abstained on OOV and
exhausted requests. Admission-1 probes offered concurrency 1/4/8, three repeats
each; raw queue/worker/total samples are retained in the report. Lexical invoked
zero NMF constructors and has null topics. Memory is whole-process working set,
not incremental model RAM; no HTTP, DB, sustained throughput or SLA was measured.
The separate fresh-process smoke establishes lifecycle success, not cold latency.

Candidate: `data/processed/ml_persona/experiment-20260909-w1-w7-1823/model`.
Its unchanged revision is
`27ad0911014cb01e8d6d891e43dc18edf75632ae919bf3413121dbbb6a404835`;
metadata SHA-256 is
`dd9d15d0088a3a7500ed52cf095acdef1a6c03b3903779bb20cd0ec7108de604`.
The frozen NMF revision remains
`7eb2fa6f748fac32b6e987e9057004d477a45e834a457b2701060360ca78b247`;
metadata SHA-256 remains
`21e7c8848215ae203913e8d0e9dcb240c8cac370279f89c7fedada5c30d2a440`.

The candidate retains its NVIDIA/CC-BY-4.0 notices and original training-code
hash. Current runtime code differs, so strict installed-training-code checking
still rejects that drift; no manifest was resealed. Legacy NMF retains explicit
unknown creator/license/code metadata, not retroactively verified attribution.
Local manifest comparisons prove consistency, not independent publisher approval.
Hosted deployment still needs a separately trusted pin. Both artifact versions
stay frozen because no predeclared fresh relevance gate supports promotion.
MiniLM was not executed; no approved local acquisition manifest was found in
the checked registry, ML configs or ingestion metadata. No labels were invented.

## Runtime Revalidation (2026-09-10)

Earlier run, superseded for current test status by the continuation above.
Its failures and timings remain historical observations, not current blockers.

Reused the actual additional lexical fit already completed on 2026-09-09. No
new fit, hyperparameter search, dependency installation, weight/data download,
private data or test-partition evaluation was performed. The preserved
schema-3 artifact is
`data/processed/ml_persona/experiment-20260909-w1-w7-1823/model`:

- Revision: `27ad0911014cb01e8d6d891e43dc18edf75632ae919bf3413121dbbb6a404835`.
- Metadata SHA-256: `dd9d15d0088a3a7500ed52cf095acdef1a6c03b3903779bb20cd0ec7108de604`.
- Experiment fingerprint: `0be792534720e4da725ebff5a446b89dc56079d34ba9172e5f2cad98fdc1f450`.
- Recorded training-code hash: `3e1d1aa4430c75f610565e38062d09f866c4174a2c94a4fc19d1e878f01aa757`.

The existing training report
`data/metadata/ml_modernization_train_20260909T182235Z_b5c1855a3da7.json`
records exit 0, 8.7024609 seconds fitting, 26.6695754 seconds phase wall time,
380,403,712 bytes process peak working set, and zero NMF constructor calls.
It fits exactly 2,516 approved training records with the already chosen lexical
settings (8,000 features, seed 42, diversity 0.25, temperature 0.03), evaluates
539 validation records and does not evaluate the historical 539 test records.
This is a schema-3 rebuild of the prior validation winner, not another winning
search or a new statistical claim. The mixed NMF/lexical grid remains tested.

Current revalidation uses Python 3.12.9, NumPy 2.5.2, SciPy 1.18.1 and
scikit-learn 1.9.0, CPU only with all observed numerical pools at two threads.
The current report is local, ignored evidence:
`.verification/20260910T044658Z_cb445cd35968/report.json`. It completed with
exit 0 in 52.1223003 seconds, independently checked preparation/source/split
integrity, reused each archived selected model, and left all frozen experiment,
reference-model and historical split/report bytes unchanged. Fitting is blocked
by the revalidation harness. The test split is integrity-checked, never scored.

| Loaded Artifact                  | Validation MRR | Recall@1     | Recall@5     | Recall@10    |
| -------------------------------- | -------------- | ------------ | ------------ | ------------ |
| Schema-3 lexical                 | 0.7166454265   | 0.6196660482 | 0.8367346939 | 0.8979591837 |
| Unchanged schema-1 NMF reference | 0.4181169683   | 0.3320964750 | 0.4953617811 | 0.5955473098 |

All 539 validation pairs are scorable. Lexical exactly matches its TF-IDF
baseline; it does not outperform itself. Both artifacts retain full canonical
source records and attribution. Validation generation produced 32 successful
five-record batches each; lexical still selects `not_in_workforce` 47/160 times.
These are synthetic cross-view and structural proxies, not human/business labels.

| Current Local Resource Probe             | Lexical     | NMF Reference |
| ---------------------------------------- | ----------- | ------------- |
| Fresh-adapter load, seconds              | 0.6015141   | 0.7348163     |
| First adapter request, seconds           | 0.6442438   | 0.7817821     |
| Warm five-record mean, ms (32 seeds)     | 39.6199219  | 43.0128625    |
| Warm five-record p95, ms                 | 43.1823950  | 46.3726200    |
| Process working set after serving, bytes | 270,348,288 | 295,694,336   |

These run sequentially in the same process after validation: imports and
filesystem may be warm, and other agents were active. Working set is whole
process memory, not incremental model RAM; high-water marks also include
evaluation. No cold-process, HTTP latency, production SLA or reliable relative
speed improvement is claimed. An earlier revalidation had substantially slower
timings under contention; it is retained as
`.verification/20260910T043330Z_254729ef491f/report.json`, not suppressed.

The current probe checks offered concurrency 1/4/8 with adapter admission 1,
three repetitions each, and retains raw queue/worker/total times. Both models
loaded once, preserved 160/160 complete warm-probe bundles, had zero hard-age
or zero-score violations, returned ten distinct sequential excluded sources,
and explicitly abstained on out-of-vocabulary and exhausted contexts. Each
passed 20 real backend conversion checks. Lexical used zero NMF constructors,
null topics, and schema-3 full-tokenizer metadata. Unit tests separately prove
full-tail vocabulary/output retention and cancellation at admission limits 1/2.

Adapter-only p95 measurements derived with NumPy's default percentile method
from 3 / 12 / 24 samples respectively (not HTTP or sustained-load SLAs):

| Offered Concurrency | Lexical Total / Queue, ms | NMF Total / Queue, ms |
| ------------------- | ------------------------- | --------------------- |
| 1                   | 39.4457 / 0.0964          | 66.5357 / 0.1214      |
| 4                   | 158.3962 / 120.8564       | 234.1389 / 179.5653   |
| 8                   | 307.6484 / 269.7164       | 360.6171 / 314.2207   |

Readiness reports `configured`/unloaded after metadata checks, then `available`
only after real loading. The saved training-code map no longer equals current
source because runtime code changed; strict code verification still rejects
that mismatch. Neither metadata nor old provenance was rewritten to hide it.
The saved experiment's metadata pin checks integrity, not independent deployment
approval or a signature. The default NMF bundle was not replaced or promoted.

That run's scoped tests: 360 ML passed / 1 failed (95.3887% combined line/branch
coverage), 21 runtime passed, 39 adapter
passed, 5 schema passed and 6 adapter-contract passed. The ML failure was the
fresh-process provider/DB import guard, now resolved; its original path is recorded
in [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md#maintenance-runtime-readiness-2026-09-10).
Prior partial full-suite evidence (292 JUnit cases, process exit 1) remains
historical, not a passing gate. No pretrained candidate ran: the runtimes are
absent. The precise deferred R8 candidate is in
[ARCHITECTURE.md](ARCHITECTURE.md#minimal-pretrained-candidate-2026-09-10).

Fresh authorized business relevance judgments, hard student/geography checks,
cohort bias review and a genuinely untouched test set remain external gates.
The old seen 539-test results are historical only and were not used for tuning.

## Batch 1E Validation-Only Benchmark

Executed locally on 2026-09-09 after the ML unit gate passed. This is a new,
unpromoted experiment using the same approved 6,000-profile synthetic subset
and unchanged preparation: 2,516 train / 539 validation / 539 test. No new data,
model download, dependency install, human labels, or LLM fine-tuning was used.
The existing test partition was integrity-checked by the lifecycle but never
passed to evaluation or selection in this batch. Historical test measurements
below are not new test or business-quality evidence.

Configuration: [configs/modernization_lexical.json](configs/modernization_lexical.json).
Only weight 1.0 was added to the original four-candidate grid; all original
settings remain. Weight 1.0 creates one true lexical strategy, regardless of
the number of topic settings. Every candidate fits only training records and
uses the same validation queries, retrieval objective and canonical-config tie
break. The default NMF strategy and production artifact were not promoted or
replaced. New files are under `data/processed/ml_persona/modernization-lexical/`:
`model/`, `experiment.json`, `experiments/<model_version>.json`,
`evaluation.json`, `reference-validation.json`, and `example-personas.json`.

| Candidate                            | Validation MRR         | Fit Seconds   | NMF Iterations |
| ------------------------------------ | ---------------------- | ------------- | -------------- |
| NMF 16 / lexical 0.35                | 0.19710149642765074    | 8.6734085     | 114            |
| NMF 16 / lexical 0.70                | 0.36913421943750657    | 8.4582004     | 114            |
| NMF 32 / lexical 0.35                | 0.2383700341543759     | 10.5595292    | 121            |
| NMF 32 / lexical 0.70                | 0.41811696827631073    | 12.1942533    | 121            |
| Lexical TF-IDF + diversity selection | **0.7166454265071603** | **6.8162846** | Not applicable |

Total fit time was 46.7016760 s; measured training CLI wall time was 78.0080724 s,
including source/preparation checks and candidate evaluation. CPU pools were
capped at two per child process, with E: temporary storage and no global
environment changes. Python 3.12.9, NumPy 2.5.2, SciPy 1.18.1 and sklearn 1.9.0
were explicitly verified. Peak RAM, process RSS, and API latency were not measured.

Both the new saved lexical model and the unchanged historical NMF artifact
were loaded and evaluated on validation, with separate new reports:

| Reloaded Artifact   | MRR          | Recall@1     | Recall@5     | Recall@10    | Eval Seconds |
| ------------------- | ------------ | ------------ | ------------ | ------------ | ------------ |
| Lexical             | 0.7166454265 | 0.6196660482 | 0.8367346939 | 0.8979591837 | 3.7320693    |
| Saved NMF reference | 0.4181169683 | 0.3320964750 | 0.4953617811 | 0.5955473098 | 4.0214187    |

These evaluation times are inside `evaluate_model`, excluding source checks,
load, and CLI overhead. All 539 validation pairs were scorable. Reloaded lexical
model metrics exactly matched its lexical TF-IDF baseline. Both probes produced
32 successful five-profile batches; neither reported a failed batch. Lexical
mean/p95 generation was 29.7747063 / 37.3291800 ms; saved NMF was 35.7357094 /
39.5325250 ms. These single local samples are not an API SLA or throughput claim.

Lexical's 160 selections had zero recorded incomplete/underage profiles,
within-batch duplicate identities, bundle mismatches, or location rewrites.
Full normalized source reuse was 1.0, intentionally. Mean TF-IDF cosine distance
was 0.9124937390 over 320 pairs; age JS divergence was 0.0111373374.
`not_in_workforce` still accounts for 47/160 selections. Topic coverage is
`null`, not a fabricated topic metric. The separate CLI business-example export
returned five unique positive-score profiles aged 20, 20, 19, 18, 20 with NVIDIA
attribution, CC-BY-4.0 notices and `NOT_OBSERVED` status. This does not verify
student membership, geography fit, representativeness or customer demand.

### Fingerprints And Verification

- Model revision: `50ad6cf6998650f0594a234453954671b9aea0159f5ad29b1ae53b980f2f304c`.
- Model metadata SHA-256: `6b84ddc79bb165e07fa994c4181170b46e89ae7f4eed470b83b4ba11da62d0ed`.
- Experiment SHA-256: `14fba399c62948ade31ac9ed85a92672071e5ebf97f6a6768ffb9651db23ac74`.
- ML code-map SHA-256: `c3833669cd5d70b1c8fee3434a7a4493cae3dbffa1da38d240e71c887f462d3e`.
- Training-record SHA-256: `32ba49d4d7e2582cd0f452873ae2d2543cda7fb8bb4da9184371715e9cac4195`.
- Dataset SHA-256: `d0e9d8f4e9c2af263aa2c8c5ee59710468a00f7bf0be08f02466e6aa663e71c1`.

The actual bundle passed `PersonaModel.load` with the recorded metadata
expectation and `verify_training_code=True`. Lexical contains zero topics and
no NMF component/topic arrays; strict numerical pins and non-pickle loading
remain in force. The metadata pin was supplied separately during this local
check, but originated in this same run: it is not a signed attestation or an
independently trusted deployment approval. Backend pin provisioning and export
mapping remain another owner's integration work.

ML tests: **344 passed in 52.76 s**, measured branch-inclusive coverage **95.92%**
(80% gate); bug-tier Ruff and editor diagnostics passed. Interrupted terminal
attempts are excluded from successful-run counts. No backend/full-frontend
suite, service, deployment, Git operation, or independent review was performed.
Business-labelled evaluation remains an external gate. Root coordination logs
are owned by the coordinator, not this ML-only batch.

## Historical Publication

Publication verification: code commit `be92185` passed
[CI run 34299654884](https://github.com/Tayebbb/BebshaX/actions/runs/34299654884),
including the corrected ML tests on Linux. Backend/ML, frontend, migrations,
secret scanning, and Compose jobs passed; advisory typecheck remained failed.
The model and numerical results below were not retrained or retuned during
these test-compatibility follow-ups.

## Run And Evidence

Training artifacts survived the interrupted session; the selected bundle was
evaluated after resuming on 2026-09-09. Numerical results below come from the
saved experiment and the completed held-out evaluation. The recovered model
was not retrained or retuned after inspecting the test results.

| Record              | Local Path                                                   |
| ------------------- | ------------------------------------------------------------ |
| Ingestion           | `data/metadata/nemotron_personas_usa_ml.json`                |
| Preparation         | `data/processed/ml_persona/preparation.json`                 |
| Selection           | `data/processed/ml_persona/experiment.json`                  |
| Versioned selection | `data/processed/ml_persona/experiments/<model_version>.json` |
| Final test          | `data/processed/ml_persona/evaluation.json`                  |
| Fitted bundle       | `data/processed/ml_persona/model/`                           |

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

| Topics                  | Lexical Weight | Validation MRR          |
| ----------------------- | -------------- | ----------------------- |
| 16                      | 0.35           | 0.19710149642765074     |
| 16                      | 0.70           | 0.36913421943750657     |
| 32                      | 0.35           | 0.2383700341543759      |
| 32                      | 0.70           | **0.41811696827631073** |
| Lexical TF-IDF baseline | 1.00           | **0.7166454265071603**  |

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

| Method             | MRR                  | Recall@1     | Recall@5     | Recall@10    |
| ------------------ | -------------------- | ------------ | ------------ | ------------ |
| Selected model     | 0.43265430767833196  | 0.3413729128 | 0.5306122449 | 0.6141001855 |
| Lexical TF-IDF     | 0.7516210382537256   | 0.6604823748 | 0.8719851577 | 0.9294990724 |
| Expected random    | 0.012741852676724338 | 0.0018552876 | 0.0092764378 | 0.0185528757 |
| Popular occupation | 0.011943168742486186 | 0.0018552876 | 0.0092764378 | 0.0129870130 |

No tuning followed this test. The NMF blend is weaker than lexical TF-IDF on
both validation and test. This is a synthetic cross-view retrieval result,
not measured customer demand, attribute predictive accuracy, or real
business-labelled relevance. There are no real business-labelled evaluations.

## Generation Probe

Up to 32 seeded, scorable held-out queries request five training prototypes
each. Oversized contexts would be skipped rather than truncated. The recorded
test run produced 32 successful batches and 160 selected profiles.

| Check                                             | Result                                                           |
| ------------------------------------------------- | ---------------------------------------------------------------- |
| Failed batches                                    | 0                                                                |
| Incomplete / underage profiles                    | 0 / 0                                                            |
| Within-batch duplicate IDs / names / descriptions | 0 / 0 / 0                                                        |
| Bundle mismatch / location rewrite                | 0 / 0                                                            |
| Exact normalized-source reuse                     | 1.0, expected for prototype selection                            |
| Mean within-batch TF-IDF cosine distance          | 0.8779632658 over 320 pairs                                      |
| Age Jensen-Shannon divergence                     | 0.030183258935548987, base 2, against held-out synthetic records |
| Selected `not_in_workforce` occupation            | 72 / 160, a material bias                                        |
| Warm five-persona generation                      | Mean 32.971875 ms; p95 34.304875 ms, two CPU threads             |

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

| Gate                                                                 | Reported Result                                                                                                                 |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Backend offline suite                                                | 1,284 passed, 3 deselected; coverage 81.71%, floor 68%                                                                          |
| Independent ML suite                                                 | 295 passed; coverage 97%                                                                                                        |
| Frontend suite                                                       | 269 passed across 36 files after sync and the CSS token correction; final run 45.01 s                                           |
| Packaging regressions                                                | Included in the full 1,284-test backend run; earlier standalone 26-case result retained in the implementation report's baseline |
| Build / TypeScript / theme checks                                    | Latest checks PASS after the four-declaration CSS token correction; 0 theme violations; no frontend `lint` script is declared   |
| Ruff                                                                 | PASS after upstream sync; no subsequent Python changes                                                                          |
| Dependency consistency / Compose default and full syntax             | `pip check` PASS; both quiet Compose syntax checks PASS                                                                         |
| Real CLI `smoke --backend --input ml_persona/examples/business.json` | PASS: source, prepared, model, generation, backend conversion                                                                   |
| Pyright                                                              | Unavailable; remaining static-analysis debt is advisory, not a passing Pyright run                                              |

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

| Gate                                       | Reported Result                                                                                                                                                                   |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Existing PostgreSQL integration tests      | 2 passed against the isolated local database                                                                                                                                      |
| Python dependency audit                    | No known vulnerabilities; local `bebshax` and `bebshax-persona-ml` packages skipped as not on PyPI                                                                                |
| Backend Docker build and offline inference | PASS with reference-runtime constraints; five unique sources, ages 19/20/19/20/24, networking disabled                                                                            |
| Live API / database / provider flow        | 5 unique ML profiles persisted/reloaded, 22 SYNTHETIC attributes reported, zero persona-generation LLM calls; real copilot, 10 role suggestions, 2 interview turns, 4 memory rows |
| Live browser                               | Desktop 1440x1000 passed; mobile 390x844 showed clipped profile-header controls. Both had zero JS exceptions, console errors, or failed API reads                                 |

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

## Remaining External Gates

The validation-only lexical comparison is implemented and measured above;
production promotion is not. Obtain authorized held-out business-labelled
relevance judgments, including explicit student and geography mismatch review.
Freeze the next choice before a genuinely untouched test evaluation; do not
recycle the already-inspected test set for tuning. No human labels, embedding
model download, population validation, or quality certification was added.
