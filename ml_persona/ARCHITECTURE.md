# Persona ML Architecture

Last verified: 2026-09-09. Lifecycle: [README.md](README.md); recorded model and
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

| Path | Owning Code | Mapping And Persistence |
| --- | --- | --- |
| Legacy business persona | [persona/generation.py](../apps/backend/bebshax/persona/generation.py), `PersonaEngine.generate` | ML selection becomes `PersonaProfile`, saved through the existing persona repository |
| Study/segment personas | [personas/generator.py](../apps/backend/bebshax/personas/generator.py), `generate_personas_for_study` | Existing segment quotas; `GeneratedPersonaDraft` records saved by `PersonaGenerationService` |
| Copilot role personas | [api/copilot.py](../apps/backend/bebshax/api/copilot.py) | `to_workflow_persona` preserves the existing response and study JSON/ORM storage; role suggestion/chat still use the LLM router |
| Dataset personas | [datasets/service.py](../apps/backend/bebshax/datasets/service.py) | Existing segment quotas and run storage, with source-preserving generated-persona/draft conversions |

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
TF-IDF and NMF on the CPU. `device` accepts `cpu` or `auto`; both use CPU, and
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

| Dependency | License | Purpose And Necessity | Maintenance |
| --- | --- | --- | --- |
| scikit-learn >=1.7,<2 | BSD-3-Clause | Established TF-IDF, NMF, metrics; avoids hand-rolling numerical ML | Actively maintained official scikit-learn project; exact installed version recorded with experiments |
| scipy >=1.16,<2 | BSD-3-Clause | Sparse matrices and numerical solvers required by scikit-learn | Actively maintained scientific Python project |
| numpy >=2,<3 | BSD-3-Clause | Numerical arrays and safe non-pickle parameter artifacts; already installed transitively | Actively maintained scientific Python project |
| pydantic >=2.7,<3 | MIT | Typed data/input/artifact validation; already a direct backend dependency | Existing project standard |

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
fingerprints, and loaded server-side. The loader uses JSON and NPZ with
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