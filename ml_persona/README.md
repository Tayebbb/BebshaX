# Persona ML

Last verified: 2026-09-10.

An isolated, CPU-only, non-LLM subsystem for selecting coherent synthetic persona
prototypes from an approved public corpus. It fits TF-IDF vocabulary/IDF with
optional NMF topics, then uses business-context similarity and diversity-aware sampling to
select complete source profiles. It does not invent new identities, call an LLM,
fine-tune an LLM, or establish customer demand. Exact source reuse is intentional.

The backend adapts selections to existing persona schemas and persistence. Chat,
interviews, and the business-context copilot continue through the existing LLM
router; they are not replaced by this model. No new DB migration, frontend,
provider, or competing persona schema is required.

## Local Lifecycle

Run from the repository root with an existing Python 3.12+ virtual environment.
The installation command installs both editable packages; the independent CLI
does not require a running API, database, provider, or API key. Only `download`
needs network access to the public, revision-pinned source. No GPU or PyTorch is
needed; `device: "cuda"` deliberately fails validation, while `cpu` and `auto`
both use CPU. The development machine's 4 GB GPU is untouched.

```powershell
	.venv/Scripts/pip.exe install -c ml_persona/constraints.txt -e ml_persona -e "apps/backend[dev]"
.venv/Scripts/python.exe -m bebshax_persona_ml download
.venv/Scripts/python.exe -m bebshax_persona_ml prepare
.venv/Scripts/python.exe -m bebshax_persona_ml validate
.venv/Scripts/python.exe -m bebshax_persona_ml train --config ml_persona/configs/training.json
.venv/Scripts/python.exe -m bebshax_persona_ml evaluate
.venv/Scripts/python.exe -m bebshax_persona_ml generate --input ml_persona/examples/business.json --num-personas 5
.venv/Scripts/python.exe -m bebshax_persona_ml smoke --backend --input ml_persona/examples/business.json
```

`download` delegates to the existing dataset setup script with
`--profile ml_persona`; it does not introduce another downloader or allowlist.
Training selects on validation only. Evaluate the frozen selection on test once;
do not retune against that test result.

| Command    | Default Output Or Check                                                                                                                                                                 |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `download` | Pinned card/shard in `data/raw/nemotron_personas_usa_ml/`, projected `data/processed/nemotron_personas_usa_ml.jsonl`, ingestion record in `data/metadata/nemotron_personas_usa_ml.json` |
| `prepare`  | `data/processed/ml_persona/{train,validation,test}.jsonl` and `preparation.json`                                                                                                        |
| `validate` | Read-only approved-source, normalization, fingerprint, canonical-split, and identity-disjointness checks                                                                                |
| `train`    | `data/processed/ml_persona/model/`, latest `experiment.json`, and `experiments/<model_version>.json`                                                                                    |
| `evaluate` | `data/processed/ml_persona/evaluation.json`; checks model/experiment/preparation correspondence before test evaluation                                                                  |
| `generate` | Structured JSON on stdout; optional `--output data/processed/ml_persona/example_personas.json` also saves the result                                                                    |
| `smoke`    | Local checks of source presence, prepared data, model load, and five-persona generation; `--backend` adds real backend conversion/schema/provenance checks                              |

Paths in the table are artifact locations, not download links. Raw data,
prepared data, and model artifacts are ignored by Git and must be built locally;
the repository does not globally ignore ingestion metadata. Keep the experiment
and preparation records alongside the model for reproducible evaluation, even
though serving loads only the model directory.

Common options are `--root`, `--data-dir`, `--model`, `--seed`, `--threads`,
`--force`, and `--help`. Relative paths resolve against the explicit root
(default: current directory). CLI inputs/outputs must stay inside that root;
parent traversal, symlinks, and junctions are rejected. `--data-dir` defaults to
`data/processed/ml_persona`; the model defaults to `<data-dir>/model`.

`prepare --output` chooses a prepared directory. `train --report` and
`evaluate --report` choose report files. Use a separate data/model/report location
for a new experiment and pass the same paths to subsequent commands. Existing
outputs fail with `output_exists` unless replacement is explicitly authorized
with `--force`. A valid download is reused after verification; a corrupt download
is not silently repaired. `download --force` re-fetches the pinned source.
`--force` never bypasses validation or authorizes overwriting protected inputs.

The CLI emits a JSON envelope with `ok`, `command`, and `result` or `error`.
Exit status is `0` for success, `2` for usage/schema errors, and `1` for lifecycle,
I/O, dependency, or failed smoke checks. `smoke --backend` uses no LLM, network,
settings initialization, or DB connection; it is not a live API or persistence
test. Inspect every stage's `ok` value.

## Business Input And Output

The strict [BusinessContext schema](src/bebshax_persona_ml/model.py) rejects
unknown fields. The checked-in [business example](examples/business.json)
requests five profiles aged 18-24 when used with the command above.

| Field                                                                    | Contract                                                                                                             |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| `description`                                                            | Required, nonblank, 3-20,000 characters                                                                              |
| `target_audience`, `location`, `price_range`, `product_category`, `role` | Optional relevance text, not verified demographic or purchasing constraints                                          |
| `features`, `research`                                                   | Optional lists of nonblank strings; providing research text does not turn model selections into evidence             |
| `min_age`, `max_age`                                                     | Optional integer bounds in 18-95, inclusive; minimum must not exceed maximum; these are hard eligibility constraints |

`--num-personas` accepts 1-50. A context with no vocabulary overlap, or too few
unique eligible candidates with strictly positive retrieval scores, fails
rather than returning a partial batch or filling it with zero-score sources.
The deterministic `score > 0` gate is not calibrated confidence. Role
and location are soft hints: source occupation and location remain unchanged,
with mismatch warnings. A student-oriented prompt does not establish that the
selected adults are students. USA synthetic profiles do not establish fit for
Bangladesh or any real customer population.

The complete-batch rule applies to each model call. The existing multi-role
HTTP workflow can return successful roles alongside `failed_roles`; it retains
its own per-role count cap and cohort replacement behavior.

CLI results carry source/revision/record ID, source documents, a record digest,
model version, topic, selection score, and warnings. They declare
`synthetic: true` and `NOT_OBSERVED`. Backend conversions use `SYNTHETIC` claims,
empty evidence IDs/citations, and zero grounding; scores are retrieval similarity,
not confidence or purchase probability. Unknown income/budget remains unknown;
there is no invented OCEAN score, location rewrite, or student relabeling.

## Reproducibility And Serving

Current continuation evidence (2026-09-10) is in
[EXPERIMENTS.md](EXPERIMENTS.md#continuation-verification-2026-09-10). The full
ML gate passed 379 tests with 95.45% branch-inclusive coverage; 39 adapter and
21 runtime tests also passed. The data owner's import fix passes the unchanged
fresh-process regression. The actual schema-3 lexical candidate passed all five
fresh-process backend smoke stages and remains explicitly configured, not
promoted. Neither frozen artifact nor any historical split/report was rewritten.
See [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md#maintenance-artifact-release-guards-2026-09-10).

Exercise the existing candidate without changing backend settings or the default
model directory:

```powershell
.venv/Scripts/python.exe -B -m bebshax_persona_ml --root E:/BebshaX smoke --backend --model data/processed/ml_persona/experiment-20260909-w1-w7-1823/model --input ml_persona/examples/business.json --threads 2
```

The NMF default remains the frozen historical reference, not a claim that it
beats lexical retrieval. Repeated validation on already-used synthetic records
is not fresh relevance evidence. No predeclared fresh business-quality gate has
been met, so this continuation does not authorize a production default switch.

The [training configuration](configs/training.json) searches 16/32 topics and
lexical weights 0.35/0.7 with seed 42, 8,000 maximum features, 300 maximum NMF
iterations, diversity weight 0.25, temperature 0.03, and two numerical threads.
The recorded selection is 32 topics/0.7. Splits use seed 42 and 70/15/15 shares.
The saved experiment records Python 3.12.9, NumPy 2.5.2, SciPy 1.18.1, and
scikit-learn 1.9.0. [constraints.txt](constraints.txt) pins those three numerical
dependencies for reference-bundle compatibility; the backend Docker image uses
the same constraints. It does not freeze every transitive application dependency.

The loader requires exact NumPy/SciPy/scikit-learn version matches with its
metadata. Schema 3 also verifies the complete TF-IDF tokenizer contract,
including the Python patch and Unicode versions. Use the recorded numerical environment to load this bundle, or train
and validate a fresh bundle after changing numerical dependencies. Python is
recorded for legacy reproducibility but is not part of the legacy numerical-version
comparison. Do not edit metadata to bypass compatibility checks. Repeatability
depends on the same source, split, config, seed, and numerical environment;
cross-platform bit-for-bit equality is not promised.

API serving lazily loads `data/processed/ml_persona/model` by default, derived
from the configured processed-data directory. `BEBSHAX_ML_PERSONA_ARTIFACT_DIR`
overrides it; relative backend paths resolve from the server's working directory.
The adapter caches the loaded model, so restart the API after deliberately
replacing a validated bundle. Keep the bundle writable only by trusted operators.
The standalone CLI selects its model with `--model`, not that backend variable.

| Symptom                                  | Action                                                                                                                                                       |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Missing package or `dependency_error`    | Install both editable packages with the command above in the interpreter used to run the CLI/API                                                             |
| `missing_input`                          | Check root and paths; run the missing download/preparation/training stage in order                                                                           |
| `output_exists`                          | Use a new output location, or explicitly use `--force` only when replacement is intended                                                                     |
| Integrity, split, or runtime mismatch    | Preserve the old report; verify the source and rebuild affected downstream stages in a compatible environment, never rehash edited files to suppress failure |
| API 503 `ml_persona_unavailable`         | Check the configured bundle, its permissions, integrity, and recorded numerical versions; no LLM fallback is attempted                                       |
| API 422 `ml_persona_unsupported_context` | Check schema, vocabulary overlap, hard ages, and remaining source identities; role/location wording cannot guarantee population fit                          |

See [architecture](ARCHITECTURE.md) for the adapter boundary and dependency
review, [training data](DATASETS.md) for provenance and preparation,
[MODEL_CARD.md](MODEL_CARD.md) for intended use and limits, and
[EXPERIMENTS.md](EXPERIMENTS.md) for measurements and reported verification.

## Batch 1E: Lexical Capability, No Promotion

The 2026-09-09 benchmark adds genuine `strategy="lexical"` alongside the default
`strategy="nmf"`. Lexical requires `lexical_weight=1.0` and never constructs,
fits, transforms, or serializes NMF. `Selection.topic` is `None`, and evaluation
topic coverage is unavailable. NMF remains the default even if its lexical
weight is 1.0; old schema-1 artifacts retain their original model versions.

[configs/modernization_lexical.json](configs/modernization_lexical.json) keeps
the original settings and adds weight 1.0 to the four NMF candidates. The grid
creates one lexical candidate, not one duplicate per topic count, and chooses
by the same validation MRR and canonical-config tie break. No business-labelled
quality or fresh untouched-test result is claimed. The saved test is not used
for selection. See [EXPERIMENTS.md](EXPERIMENTS.md#batch-1e-validation-only-benchmark).

These commands used the existing approved preparation and a new ignored output
directory. They now refuse existing outputs; use a different unused experiment
directory for another run, not `--force` on the recorded run.

```powershell
.venv/Scripts/python.exe -B -m bebshax_persona_ml train --config ml_persona/configs/modernization_lexical.json --experiment-dir data/processed/ml_persona/modernization-lexical --threads 2
.venv/Scripts/python.exe -B -m bebshax_persona_ml evaluate --experiment-dir data/processed/ml_persona/modernization-lexical --split validation --threads 2
.venv/Scripts/python.exe -B -m bebshax_persona_ml evaluate --model data/processed/ml_persona/model --split validation --report data/processed/ml_persona/modernization-lexical/reference-validation.json --threads 2
```

`--experiment-dir` changes model/report/archive defaults, not prepared-data
inputs. `evaluate --split validation` is explicit; the historical default is
still `test`. This run capped BLAS/OpenMP thread pools at two in each child
process, used Python 3.12.9 explicitly and E: temporary storage, and changed no
global environment, dependencies, downloads, or application configuration.

### Artifact And Integration APIs

Schema-2 and schema-3 manifests record source-file, source-record, preparation, dataset,
and ML-package Python-code digests, plus typed source attribution. Provenance
and strategy are included in new model revisions. All numerical compatibility,
bounded JSON/NPZ, non-pickle, dimensions, and checksum checks remain strict.
Metadata-only validation now rejects impossible strategy/topic combinations,
including lexical topics and a lexical algorithm labelled as legacy schema 1.
Full loading additionally requires attribution for every loaded record's exact
source/revision in schemas 2/3, even when inconsistent metadata was rehashed.
Attribution for a source filtered out of the candidate set remains valid.
Schema-1 unknown attribution remains explicit; no legacy license or training-code
metadata is invented. These consistency checks do not replace a trusted pin.

- `ModelConfig(strategy="lexical", lexical_weight=1.0)` enables lexical fitting.
- `PersonaModel.fit(records, config=None, *, provenance=None)` accepts a typed
  `ModelProvenance`; pipeline training supplies verified ingestion metadata.
  Direct fixture fits have explicit unknown creator/license metadata.
- `PersonaModel.provenance` is `ModelProvenance | None`; `None` denotes a legacy
  artifact without a recorded code/source manifest, not verified provenance.
- `PersonaModel.load(path, *, expected_manifest=None, verify_training_code=False)`
  accepts `ExpectedArtifactManifest(metadata_sha256=...)` from
  `bebshax_persona_ml.provenance`. Supply its hash from a separately trusted
  deployment channel. Recomputing it from the same untrusted directory adds no
  authenticity. Optional installed-code matching fails for legacy artifacts.
- `Selection` adds `strategy`, `source_attribution`, `source_corpus_sha256`,
  `training_code_sha256`; `topic` is now `int | None`. CLI exports retain the
  attribution, code/source digests, source identity, full documents, and
  `NOT_OBSERVED` status. Scores are not confidence.
- `pipeline.train(..., experiment_dir=None)` and
  `pipeline.evaluate(..., experiment_dir=None, split="test")` support isolated
  experiments; evaluation accepts only `validation` or `test`.

Backend conversions preserve these selection fields, null lexical topics,
full narratives and synthetic attribution in the existing schemas. The default
artifact path is unchanged. The lexical winner is an experimental artifact,
not an automatic deployment. Real-business relevance labels and independent
review remain external gates; higher proxy MRR does not establish customer fit.

### Readiness And Parent Integration

`MLPersonaAdapter(artifact_dir: Path, *, max_concurrency: int = 1,
expected_manifest: ExpectedArtifactManifest | None = None,
verify_training_code: bool = False)` preserves the constructor expected by
startup. `await adapter.readiness()` returns the typed `MLPersonaReadiness`
mapping with `status`, `reason`, `validation`, `model_loaded`, and
`expected_manifest_matched`. Statuses are:

- `configured`, `lazy_model_load_pending`, `validation="manifest"`: bounded
  metadata/schema/runtime/tokenizer/trusted-pin checks and payload existence/size
  checks passed. Numerical arrays and payload hashes have NOT been loaded or
  validated; `model_loaded=False`.
- `available`, `model_loaded`, `validation="loaded"`: the actual strict loader
  succeeded and the model is cached; `model_loaded=True`.
- `unavailable`, `artifact_unavailable`, `validation="unavailable"`: metadata
  failed, or a real load failed. No local paths or exception details are exposed.

`PersonaModel.validate_manifest(path, *, expected_manifest=None,
verify_training_code=False) -> None` owns the same schema checks as the loader,
including schemas 1, 2 and 3. It never reads weight/record/vocabulary payloads
or claims that their hashes have been validated. Both adapter readiness and
generation use bounded, cancellation-safe thread submission. Cancelling an
already running request does not free its slot until its worker actually ends;
cancelled queued waiters never enter the thread pool. Limits are per adapter
process, not distributed admission or a throughput guarantee.

`MLPersonaAdapter.from_settings(settings=None, *, expected_manifest=None,
verify_training_code=False, max_concurrency=1)` now consumes
`settings.expected_ml_persona_manifest`, honors `ml_persona_enabled=False`, and
fails closed with `expected_manifest_required` when production/staging has no
trusted pin. An explicitly passed typed expectation overrides settings. The
parent supplies `BEBSHAX_ML_PERSONA_MANIFEST_SHA256` through a trusted deployment
channel, not from an untrusted adjacent file. No environment/config changes
were made here.

Existing `_persona_capability` introspection accepts this mapping and needs no
new argument or domain schema. It currently keeps only `status` and `reason`;
to expose the full distinction later, the parent can also retain `validation`,
`model_loaded`, and `expected_manifest_matched` in its capability mapping. No
startup or shared API files were changed here.

The new runtime code intentionally differs from the frozen lexical training
code map. `verify_training_code=True` still rejects that difference; do not
reseal metadata or pretend the artifact was fitted by current code. Normal
trusted-manifest loading preserves the original recorded training provenance.

Scoped, single-process checks with all generated test evidence under the ignored
ML verification directory and dotenv loading disabled:

```powershell
.venv/Scripts/python.exe -B ml_persona/tools/verify_modernization.py --scope ml --coverage
.venv/Scripts/python.exe -B ml_persona/tools/verify_modernization.py --scope runtime
.venv/Scripts/python.exe -B ml_persona/tools/verify_modernization.py --scope adapter
.venv/Scripts/python.exe -B ml_persona/tools/verify_modernization.py --scope schema
.venv/Scripts/python.exe -B ml_persona/tools/modernization_experiment.py --experiment experiment-20260909-w1-w7-1823 --phase revalidate
```

The last command refuses fitting, validates only the validation partition, and
writes new reports under `.verification/<run-id>/`. It checks frozen reference
and experiment files before/after. Resource timings use a fresh adapter after
evaluation, not a cold interpreter or controlled cold filesystem.
