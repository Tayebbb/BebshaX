# Persona ML

Last verified: 2026-09-09.

An isolated, CPU-only, non-LLM subsystem for selecting coherent synthetic persona
prototypes from an approved public corpus. It fits TF-IDF vocabulary/IDF and NMF
topics, then uses business-context similarity and diversity-aware sampling to
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

| Command | Default Output Or Check |
| --- | --- |
| `download` | Pinned card/shard in `data/raw/nemotron_personas_usa_ml/`, projected `data/processed/nemotron_personas_usa_ml.jsonl`, ingestion record in `data/metadata/nemotron_personas_usa_ml.json` |
| `prepare` | `data/processed/ml_persona/{train,validation,test}.jsonl` and `preparation.json` |
| `validate` | Read-only approved-source, normalization, fingerprint, canonical-split, and identity-disjointness checks |
| `train` | `data/processed/ml_persona/model/`, latest `experiment.json`, and `experiments/<model_version>.json` |
| `evaluate` | `data/processed/ml_persona/evaluation.json`; checks model/experiment/preparation correspondence before test evaluation |
| `generate` | Structured JSON on stdout; optional `--output data/processed/ml_persona/example_personas.json` also saves the result |
| `smoke` | Local checks of source presence, prepared data, model load, and five-persona generation; `--backend` adds real backend conversion/schema/provenance checks |

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

| Field | Contract |
| --- | --- |
| `description` | Required, nonblank, 3-20,000 characters |
| `target_audience`, `location`, `price_range`, `product_category`, `role` | Optional relevance text, not verified demographic or purchasing constraints |
| `features`, `research` | Optional lists of nonblank strings; providing research text does not turn model selections into evidence |
| `min_age`, `max_age` | Optional integer bounds in 18-95, inclusive; minimum must not exceed maximum; these are hard eligibility constraints |

`--num-personas` accepts 1-50. A context with no vocabulary overlap, or too few
unique eligible candidates, fails rather than returning a partial batch. Role
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

The [training configuration](configs/training.json) searches 16/32 topics and
lexical weights 0.35/0.7 with seed 42, 8,000 maximum features, 300 maximum NMF
iterations, diversity weight 0.25, temperature 0.03, and two numerical threads.
The recorded selection is 32 topics/0.7. Splits use seed 42 and 70/15/15 shares.
The saved experiment records Python 3.12.9, NumPy 2.5.2, SciPy 1.18.1, and
scikit-learn 1.9.0. [constraints.txt](constraints.txt) pins those three numerical
dependencies for reference-bundle compatibility; the backend Docker image uses
the same constraints. It does not freeze every transitive application dependency.

The loader requires exact NumPy/SciPy/scikit-learn version matches with its
metadata. Use the recorded numerical environment to load this bundle, or train
and validate a fresh bundle after changing numerical dependencies. Python is
recorded for reproducibility but is not part of that exact numerical-version
comparison. Do not edit metadata to bypass compatibility checks. Repeatability
depends on the same source, split, config, seed, and numerical environment;
cross-platform bit-for-bit equality is not promised.

API serving lazily loads `data/processed/ml_persona/model` by default, derived 
from the configured processed-data directory. `BEBSHAX_ML_PERSONA_ARTIFACT_DIR`
overrides it; relative backend paths resolve from the server's working directory.
The adapter caches the loaded model, so restart the API after deliberately
replacing a validated bundle. Keep the bundle writable only by trusted operators.
The standalone CLI selects its model with `--model`, not that backend variable.

| Symptom | Action |
| --- | --- |
| Missing package or `dependency_error` | Install both editable packages with the command above in the interpreter used to run the CLI/API |
| `missing_input` | Check root and paths; run the missing download/preparation/training stage in order |
| `output_exists` | Use a new output location, or explicitly use `--force` only when replacement is intended |
| Integrity, split, or runtime mismatch | Preserve the old report; verify the source and rebuild affected downstream stages in a compatible environment, never rehash edited files to suppress failure |
| API 503 `ml_persona_unavailable` | Check the configured bundle, its permissions, integrity, and recorded numerical versions; no LLM fallback is attempted |
| API 422 `ml_persona_unsupported_context` | Check schema, vocabulary overlap, hard ages, and remaining source identities; role/location wording cannot guarantee population fit |

See [architecture](ARCHITECTURE.md) for the adapter boundary and dependency
review, [training data](DATASETS.md) for provenance and preparation,
[MODEL_CARD.md](MODEL_CARD.md) for intended use and limits, and
[EXPERIMENTS.md](EXPERIMENTS.md) for measurements and reported verification.