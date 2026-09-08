# Persona ML Architecture

## Scope And Decision

Owner approval on 2026-09-08 permits a separate non-LLM persona model, superseding
the blanket no-training language in D6/R9 only for explicitly reviewed public
synthetic data. Existing datasets, conversations, uploads, and private studies
are not training inputs. LLM fine-tuning remains prohibited.

The existing frontend collects business context through the existing copilot.
There are four persona generators: legacy `PersonaEngine`, study
`generate_personas_for_study`, copilot role generation, and dataset generation.
They must share local ML inference through a backend adapter. Existing
`GeneratedPersona`, `PersonaProfile`, and `GeneratedPersonaDraft` contracts remain
authoritative. Existing storage, tenancy, quotas, and interview engines remain.

## Model Choice

The first model is a fitted TF-IDF representation with nonnegative latent topics
and context-conditioned, diversity-aware selection of coherent synthetic
attribute bundles. It learns corpus-specific vocabulary, inverse document
frequencies, topic components, and profile representations. It is a specialized
statistical selection model, not a text-generating language model or a collection
of prompts. It preserves profile combinations rather than predicting a person's
occupation from age or fabricating purchasing frequencies.

Training and hyperparameter selection use disjoint identities. Text features do
not include protected demographic fields. Complete source narratives are kept;
feature projection is not permission to truncate persona context in interviews.
Dataset-derived text remains synthetic, with source identifiers and model
version traceable in the result. Selection scores are not empirical confidence.

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
handle licensed, revision-pinned downloads. Dependency auditing and exact runtime
versions are recorded in the final verification report, not assumed here.

## Artifact And Runtime Boundary

Artifacts are built locally, excluded from Git, versioned by dataset/configuration
fingerprints, and loaded server-side. They must not execute pickled code or
download anything during inference. Missing or invalid artifacts produce an
explicit persona-generation error; they do not disable chat and never silently
fall back to an LLM. Numerical inference runs off the async request loop.

No database migration is needed. Rich structured fields and model provenance fit
the existing JSON columns and persona profile objects. Installation must cover
the independent package in local setup, CI, and Docker.