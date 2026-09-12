# Persona ML Architecture

Last verified: 2026-09-10. Lifecycle: [README.md](README.md); recorded model and
results: [MODEL_CARD.md](MODEL_CARD.md), [EXPERIMENTS.md](EXPERIMENTS.md).

## Scope And Decision

Owner approval on 2026-09-08 permits a separate non-LLM persona model, superseding
the blanket no-training language in D6/R9 only for explicitly reviewed public
synthetic data. Existing datasets, conversations, uploads, and private studies
are not training inputs. LLM fine-tuning remains prohibited.

The existing frontend collects business context through the existing copilot.
There are four persona generators: legacy `PersonaEngine`, study
`generate_personas_for_study`, copilot role generation, and dataset generation.
Runtime wiring shares local ML inference through `MLPersonaAdapter`. Existing
`GeneratedPersona`, `PersonaProfile`, and `GeneratedPersonaDraft` contracts remain
authoritative. Existing storage, tenancy, quotas, and interview engines remain.

## Four Generation Paths

| Path                    | Owning Code                                                                                           | Mapping And Persistence                                                                                                         |
| ----------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Legacy business persona | [persona/generation.py](../apps/backend/bebshax/persona/generation.py), `PersonaEngine.generate`      | ML selection becomes `PersonaProfile`, saved through the existing persona repository                                            |
| Study/segment personas  | [personas/generator.py](../apps/backend/bebshax/personas/generator.py), `generate_personas_for_study` | Existing segment quotas; `GeneratedPersonaDraft` records saved by `PersonaGenerationService`                                    |
| Copilot role personas   | [api/copilot.py](../apps/backend/bebshax/api/copilot.py)                                              | `to_workflow_persona` preserves the existing response and study JSON/ORM storage; role suggestion/chat still use the LLM router |
| Dataset personas        | [datasets/service.py](../apps/backend/bebshax/datasets/service.py)                                    | Existing segment quotas and run storage, with source-preserving generated-persona/draft conversions                             |

Each path builds a strict `BusinessContext`, calls the same local model, and
maps selected records through [ml_adapter.py](../apps/backend/bebshax/personas/ml_adapter.py).
Explicitly injected LLM-only compatibility paths remain in code, but are not an
automatic fallback when the runtime ML path fails. The model does not route LLM
requests and does not replace business-context chat, role suggestion, interviews,
memory reflection, or other existing `LLMService` calls.

### Persistence And Identity

Source ID/revision, model version, selection score, and topic live in
`detailed_attributes.ml_provenance`; complete normalized narratives live in
`source_documents`. Existing claim/attribute fields remain `SYNTHETIC` with no
evidence IDs. Draft/workflow `dataset_refs` retain source metadata, not citations
proving customer behavior. Grounding and confidence remain zero/unset; unavailable
income, budget, structured needs, or personality measurements are not inferred.
The source identity is retained instead of rewriting occupation or geography.
Explicit minimum/maximum ages are hard; role/location hints are soft.

[active_source_exclusions](../apps/backend/bebshax/personas/service.py) reads
nonarchived source IDs and names for the owner and relevant business, study, or
dataset-run scope. Legacy, study (including regeneration), and dataset paths
forward these exclusions; study/dataset batches also accumulate exclusions
between segments. Study persona counts reflect all active owner-scoped personas,
not only the latest batch. If the requested ML batch cannot be filled, it fails
with 422 without saving a partial study/dataset persona batch.

The role workflow retains its existing cohort replacement: it archives the old
cohort on successful persistence and excludes siblings within the new request.
Its existing `failed_roles` partial-success contract across roles is unchanged;
it does not exclude the old cohort from source selection. Exclusion reads are
not a transactional uniqueness lock, so overlapping independent requests can
still select the same source. No cross-process uniqueness guarantee is claimed.

## Model Choice

Batch 1E (2026-09-09) adds an explicit lexical strategy without changing the
default NMF strategy or production artifact. `ModelConfig.strategy` is `nmf`
or `lexical`; lexical requires weight 1.0, fits only TF-IDF, uses lexical cosine
for relevance/redundancy, and skips all NMF construction, fitting and transforms.
Lexical selections have `topic=None`; topic coverage is unavailable. The
training grid admits weight 1.0 as exactly one lexical candidate, selected on
the same validation proxy as the NMF candidates. The new config preserves all
original grid settings. Actual unpromoted results are in [EXPERIMENTS.md](EXPERIMENTS.md#batch-1e-validation-only-benchmark).

All strategies intersect age/exclusion eligibility with `score > 0` before
sampling. Too few relevant candidates fail without a partial cohort. This is
a deterministic support gate, not a confidence threshold or a guarantee that
lexical overlap establishes business relevance. Source records remain intact.

The first model is a fitted TF-IDF representation with nonnegative latent topics
and context-conditioned, diversity-aware selection of coherent synthetic
attribute bundles. It learns corpus-specific vocabulary, inverse document
frequencies, topic components, and profile representations. It is a specialized
statistical selection model, not a text-generating language model or a collection
of prompts. It preserves profile combinations rather than predicting a person's
occupation from age or fabricating purchasing frequencies.

Training and hyperparameter selection use disjoint identities. The feature
projection excludes explicit protected document fields and removes known name
and protected-text fragments. Cultural or protected information can still occur
elsewhere in retained narratives; this is not comprehensive de-identification.
Complete source narratives are kept; feature projection is not permission to
truncate persona context in interviews. Dataset-derived text remains synthetic,
with source identifiers and model version traceable in the result. Selection
scores are not empirical confidence.

The [model implementation](src/bebshax_persona_ml/model.py) uses scikit-learn
TF-IDF with optional NMF on the CPU. `device` accepts `cpu` or `auto`; both use CPU, and
`cuda` is deliberately rejected. No GPU, PyTorch, API key, or LLM is required.
The development machine's 4 GB GPU is not used by this subsystem.

Research found no verified supervised business-to-customer persona labels.
Held-out cross-view retrieval and distribution metrics are proxy evaluations,
not evidence of customer demand or population representativeness. Retaining an
entire synthetic attribute bundle is deliberate: unrelated identities must not
be spliced into plausible-looking but contradictory profiles.

## Pretrained Alternatives Researched

- `sentence-transformers/all-MiniLM-L6-v2`: Apache-2.0, 22.7M parameters,
  384-dimensional sentence embeddings, about 91 MB of float32 weights, CPU
  compatible and offline after download. Its default 256-wordpiece truncation
  would require a full-text chunking policy. Not downloaded or used: the baseline
  can be trained locally without a transformer runtime or another artifact.
- NVIDIA Nemotron Personas is a **dataset**, not our pretrained model. Its
  synthetic narratives were authored upstream with generative models. BebshaX
  training and inference make no LLM calls.
- Rule-only templates and prompting through Freellmpool do not satisfy this task.
  Lexical retrieval, frequency sampling, and random sampling are baselines.

## Dependency Review (R8, Before Installation)

### Minimal Pretrained Candidate (2026-09-10)

Research/deferred experiment only. No runtime, model weights, tokenizer assets,
new datasets or system packages were installed/downloaded. The explicit Python
3.12.9 repository environment has none of `onnxruntime`, `tokenizers`, `torch`,
`transformers`, `sentence-transformers` or `safetensors`. Existing
`huggingface-hub==0.36.2` and numerical pins are retained. No global cache,
credential file, private study or upload was inspected.

Use the SAME previously reviewed
[`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
not a similarly named replacement. The primary API resolves revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, last modified 2026-06-01. Its
[pinned card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/README.md)
declares English, Apache-2.0 and 384-dimensional sentence embeddings. Pinned
[sentence configuration](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/sentence_bert_config.json)
caps input at 256 wordpieces;
[pooling configuration](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/1_Pooling/config.json)
specifies attention-mask mean pooling, not CLS or max pooling. The proposed
first numerical reference is that repository's `onnx/model.onnx`, not a
quantized/exported substitute assumed equivalent without testing.

| Proposed Direct Dependency      | Why / Necessity                                                                                                                                  | License And Activity                                                                                                                                                                             | Compatibility / Unverified Risk                                                                                                                                                                                   |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `onnxruntime==1.23.2` CPU wheel | Runs the frozen ONNX encoder locally without PyTorch, Transformers or an HTTP service; unnecessary for lexical serving                           | Microsoft-maintained; [tagged MIT license](https://raw.githubusercontent.com/microsoft/onnxruntime/v1.23.2/LICENSE); [release metadata](https://pypi.org/pypi/onnxruntime/1.23.2/json)           | Python >=3.10; published cp312 Windows x64 wheel, 13,470,528 bytes; requires numpy>=1.21.6, packaging, coloredlogs, flatbuffers, protobuf, sympy. No binary/runtime compatibility claimed before an isolated test |
| `tokenizers==0.22.1`            | Loads the pinned local tokenizer with token offsets, explicit no-truncation behavior and special-token accounting; avoids hand-written WordPiece | Hugging Face-maintained; [tagged Apache-2.0 license](https://raw.githubusercontent.com/huggingface/tokenizers/v0.22.1/LICENSE); [release metadata](https://pypi.org/pypi/tokenizers/0.22.1/json) | Python >=3.9; cp39-abi3 Windows x64 wheel, 2,674,684 bytes; hub>=0.16.4,<2 accepts existing 0.36.2. Import/token equivalence is untested                                                                          |

These exact versions are a bounded prospective experiment tuple, not a claim
to be latest or production-approved. The previously reviewed
sentence-transformers 6.0.1 reference path needs a separate isolated environment
because its hub>=1.3,<2 requirement conflicts with the shared backend's <1.0.
The minimal pair above avoids that direct hub conflict. It does not justify
changing the shared environment while other agents run tests. Resolve, review
licenses/security, and pin all new transitives (including Windows-only
requirements) before the parent schedules installation. No dependency manifest
or constraints file was edited, and no install command was executed.

Proposed parent-scheduled runtime options, not measured settings: use only
`CPUExecutionProvider`, `SessionOptions.intra_op_num_threads=2`,
`inter_op_num_threads=1`, `execution_mode=ORT_SEQUENTIAL`, and set
`session.intra_op.allow_spinning` / `session.inter_op.allow_spinning` to `"0"`.
One admitted inference at a time; no GPU/DirectML, process fan-out or hidden
provider fallback. [Official thread semantics](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)
confirm that intra-op=2 includes the caller thread. Disable tokenizer internal
parallelism for the experiment. Session/model loading must be lazy and local,
with all file/revision hashes checked before use.

Acquisition remains a parent-owned gate: add reviewed exact ONNX/tokenizer/
configuration/card files and their digests to the approved model pipeline,
retain license/NOTICE/source-modification records, and do not fetch through an
ad hoc global cache or `from_pretrained`. The card declares Apache-2.0 but no
local license/NOTICE bundle has been acquired or independently approved.

Full-text policy must be implemented and tested before any benchmark: tokenize
without truncation; reserve all special tokens (normally 2, verified from the
pinned tokenizer), partition at field/sentence boundaries with at most 254
content wordpieces per chunk, and prove every feature/query token span is
covered, including tails and long words. Pool each chunk using the pinned
attention-mask mean plus L2 normalization; predeclare token-weighted aggregate
and length-bias checks, cache complete record vectors, and preserve the full
canonical source bundle in all outputs. Chunking is an approximation of
whole-document representation, not permission to truncate interview content.

Compare validation-only against the strongest lexical selector with the same
inputs, ages, exclusions and attribution. Freeze aggregation/threshold choices
before fresh authorized business labels and a genuinely untouched holdout.
Do not tune on the historical 539 test records. Dense positive similarity is
not calibrated relevance: define an abstention evaluation before promotion.
Actual MiniLM quality, latency, memory, tokenizer-tail equivalence, ONNX/native
parity and Windows/Linux parity are all unmeasured. No pretrained winner or
business-quality claim is made, and no dormant/nonworking feature was added.

### W1/W7 Frozen Encoder Review (2026-09-09)

Research only; no weights, tokenizer assets, packages, or datasets were installed.
The primary [MiniLM card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
declares Apache-2.0, English sentence/short-paragraph retrieval and 384-dimensional
embeddings. Its pooling configuration enables attention-mask mean pooling; its
sentence-transformer configuration limits sequences to 256 wordpieces. The
example's `truncation=True` is unacceptable for this project's full-record
contract. The model's separate `LICENSE` URL returned 404 during this review;
the card declaration is not a checked local license/NOTICE bundle.

The [PyPI metadata](https://pypi.org/pypi/sentence-transformers/6.0.1/json)
reports sentence-transformers 6.0.1 (2026-08-31), Apache-2.0, Python >=3.10,
maintained by the Sentence Transformers/Hugging Face project. It provides the
reference tokenizer/model/pooling pipeline, but adds torch >=2.2, transformers

> =5,<6, tokenizers >=0.19 and huggingface-hub >=1.3,<2, among other scientific
> dependencies. That hub range conflicts with the backend's <1.0 requirement.
> It is unnecessary for the lexical challenger. A future reviewed install must
> be isolated under the ML workspace, with resolved dependency/license notices
> and CPU wheels reviewed before acquisition; the serving numerical pins stay
> unchanged. No package-size, RAM or inference-speed estimate is an observation.

Acquisition is blocked within this workstream: the approved dataset manifest
lists MiniLM only as `not_a_dataset`, researched/not used, and the `ml_persona`
profile admits the pinned NVIDIA synthetic source only. Weight/tokenizer
revisions, exact files, integrity hashes and license/NOTICE retention need an
owner-approved pipeline entry. Do not call `from_pretrained` or download weights
to an ad hoc cache to bypass that gate. Existing manifest/setup files belong
to the data owner and were not changed.

After that gate, the candidate should remain frozen/eval-only on CPU with two
threads. A tokenizer-aware, field/sentence-respecting chunker must disable
truncation, reserve special/instruction tokens, cover every approved feature
and the complete query, and prove end-token coverage. Predeclare aggregation
and length-bias checks, cache record representations, and keep canonical record
hashes and full source bundles intact. Actual encoder/chunking benchmarks and
Windows/Linux parity remain unmeasured. No new holdout or human relevance labels
were manufactured, and no LLM or encoder fine-tuning is authorized here.

| Dependency            | License      | Purpose And Necessity                                                                    | Maintenance                                                                                          |
| --------------------- | ------------ | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| scikit-learn >=1.7,<2 | BSD-3-Clause | Established TF-IDF, NMF, metrics; avoids hand-rolling numerical ML                       | Actively maintained official scikit-learn project; exact installed version recorded with experiments |
| scipy >=1.16,<2       | BSD-3-Clause | Sparse matrices and numerical solvers required by scikit-learn                           | Actively maintained scientific Python project                                                        |
| numpy >=2,<3          | BSD-3-Clause | Numerical arrays and safe non-pickle parameter artifacts; already installed transitively | Actively maintained scientific Python project                                                        |
| pydantic >=2.7,<3     | MIT          | Typed data/input/artifact validation; already a direct backend dependency                | Existing project standard                                                                            |

No additional datasets library, provider SDK, gateway, database, or animation
library is needed. The existing `huggingface_hub` and `fastparquet` dependencies
handle licensed, revision-pinned downloads. Recorded runtime versions, offline
checks, and live verification results are in [EXPERIMENTS.md](EXPERIMENTS.md).
The installed Python environment's vulnerability scan found no known
vulnerabilities on 2026-09-09; the two local packages were not auditable on PyPI.

Deployment pin review (2026-09-09): [constraints.txt](constraints.txt) records
`numpy==2.5.2`, `scipy==1.18.1`, and `scikit-learn==1.9.0` from the existing
trained artifact's runtime. These are version pins for the already-reviewed
dependencies above, not new dependencies. Docker applies them to both local
package installs to prevent clean-checkout builds from selecting NumPy 2.5.3
and failing the unchanged strict compatibility check. The saved artifact is
not modified.

## Artifact And Runtime Boundary

Artifacts are built locally, excluded from Git, versioned by dataset/configuration
fingerprints (plus strategy and provenance for schema 2), and loaded server-side.
The loader uses JSON and NPZ with
`allow_pickle=False`, bounded file and uncompressed archive sizes, exact numeric
shapes and dtypes, finite nonnegative values, and sparse-index validation. It
does not download anything during inference. Missing or invalid artifacts
produce an explicit persona-generation error; they do not disable chat and
never silently fall back to an LLM. Numerical inference runs off the async
request loop.

The loader checks exact NumPy/SciPy/scikit-learn versions, per-file hashes,
configuration/model fingerprints, vocabulary, and complete unique records.
Preparation validation independently re-verifies the approved source and
reconstructs canonical splits; merely rehashing edited split files is not enough.
Hashes establish local integrity, not signed authenticity or trusted attestation.

Schema 2 adds typed `ModelProvenance` and `SourceAttribution` in
[provenance.py](src/bebshax_persona_ml/provenance.py). New training records all
ML-package Python file digests, verified source artifact/manifest digests,
preparation/dataset digests and creator/license/modification notices. These
values participate in the model revision; the experiment also pins the emitted
metadata file hash. Metadata size is checked before payload writes. Lexical NPZ
archives exclude components/topics, with strategy-specific exact members and
dimensions. Schema-1 NMF fingerprint/load/resave behavior remains compatible.

`PersonaModel.load(..., expected_manifest=ExpectedArtifactManifest(...))`
compares a caller-provided metadata SHA-256 before parsing payloads. The caller
must obtain that expectation through a separate trusted channel; a self-hash is
not authenticity. `verify_training_code=True` optionally compares installed ML
source files with the training snapshot and rejects legacy/mismatched code.
Default loading retains frozen artifacts across code changes while enforcing
all existing numerical/runtime and local-integrity checks. No signature system,
download, provider, or backend configuration was introduced. Backend conversions
preserve the additive attribution/strategy/digest fields. The settings factory
consumes the configured trusted pin and rejects unpinned production/staging;
provisioning that pin from a trusted deployment channel remains the operator's
responsibility, not something an adjacent artifact file can authorize.

The 2026-09-10 continuation closes two tested release guards in the model owner.
Metadata-only readiness rejects lexical topics, topicless/excess-topic NMF and
a lexical algorithm labelled as schema 1, just as full loading does. Schemas
2/3 also require attribution for each loaded record's exact source/revision;
rehashing inconsistent attribution does not make it valid. Extra attribution
for filtered-out source records is allowed. Schema-1 unknown provenance and
all valid frozen model revisions remain unchanged. Readiness still does not
verify payload hashes or numerical state until the actual loader succeeds.

The complete ML gate passed 379 tests, with 39 adapter and 21 runtime tests
separately passing. The existing provider/DB import guard and actual lexical
five-stage fresh-process smoke both pass after the data owner's import fix;
no shared import code was changed in this continuation. Full-text TF-IDF and
tail/output retention are tested; no token-window chunker is needed for this
strategy. MiniLM chunking remains a research requirement, not an implemented
or measured encoder. Current comparison/timing limits are in
[EXPERIMENTS.md](EXPERIMENTS.md#continuation-verification-2026-09-10).

Backend settings default to `data/processed/ml_persona/model`, derived from the
processed-data root; `BEBSHAX_ML_PERSONA_ARTIFACT_DIR` overrides it. Loading is
lazy and cached per adapter; restart the API after replacing a validated bundle.
Load failure is HTTP 503 `ml_persona_unavailable`; unsupported context, age,
vocabulary, or exhausted eligible candidates is HTTP 422
`ml_persona_unsupported_context`. These are feature API errors, not additions to
the LLM failure taxonomy. The adapter bounds worker submissions and numerical
inference with a default concurrency of one, using `asyncio.to_thread` so it
does not block the event loop. This process-local bound is not a DB identity lock.

No database migration is needed. Rich structured fields and model provenance fit
the existing JSON columns and persona profile objects. Install both editable
packages using [README.md](README.md). Artifacts are not shipped by a clean
checkout and are not downloaded or trained during backend startup. No frontend,
provider, or competing storage schema is introduced by this subsystem.
