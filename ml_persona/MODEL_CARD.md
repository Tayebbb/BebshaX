# Persona ML Model Card

Last verified: 2026-09-09. Status: locally trained synthetic-prototype selector,
not a production-readiness or customer-fit certification.

## Model And Intended Use

| Property            | Recorded Value                                                              |
| ------------------- | --------------------------------------------------------------------------- |
| Package / algorithm | `bebshax-persona-ml` 0.1.0 / `tfidf-nmf-mmr-v1`                             |
| Model version       | `7eb2fa6f748fac32b6e987e9057004d477a45e834a457b2701060360ca78b247`          |
| Training candidates | 2,516 complete, deduplicated synthetic adult profiles                       |
| Representation      | Training-fitted TF-IDF with 8,000 features and 32 NMF topics                |
| Selection           | 0.7 lexical / 0.3 topic similarity, diversity weight 0.25, temperature 0.03 |
| Reproducibility     | Seed 42, maximum 300 NMF iterations; exact numerical runtime recorded below |
| Runtime             | CPU only; no LLM, provider call, API key, PyTorch, or GPU                   |

Use the model to explore explicitly synthetic persona hypotheses for a business
and pass coherent source profiles into BebshaX's existing research workflows.
It selects whole normalized source bundles; it does not generate novel people,
predict attributes, or measure customer demand. Exact source reuse is expected,
not an originality result. Training data and user-provided context are never
automatically classified as observed evidence.

The [implementation](src/bebshax_persona_ml/model.py) learns vocabulary, IDF,
topic components, and training-profile representations. It blends lexical and
topic similarity, penalizes similarity to already selected candidates, and uses
seeded temperature sampling without replacement. It is neither an LLM nor a
prompt/template collection. MiniLM was researched but not downloaded or used;
NVIDIA Nemotron Personas is the upstream dataset, not a pretrained BebshaX model.

## Data And Provenance

Source: NVIDIA Corporation's `nvidia/Nemotron-Personas-USA`, revision
`5b4cd35ab46490c1da1bd2b5a2324d6f871be180`, CC-BY-4.0. One pinned shard is
scanned completely; the lowest 6,000 UUID-based SHA-256 ranks are projected to
17 allowlisted fields. Normalization accepts 4,694 rows and rejects 1,306 with
`invalid_schema`; completeness filtering removes 1,078 and identity deduplication
removes 22, leaving 3,594. Seed-42 identity-disjoint splits contain 2,516 training,
539 validation, and 539 test records. See [DATASETS.md](DATASETS.md) for the
normalization distinction, checksums, licenses, and selection limitations.

Raw narratives were authored synthetically upstream. Explicit sex, zipcode,
marital status, bachelors field, and list variants are dropped at ingestion.
Normalization rejects detected email/URL contact text, and feature projection
excludes selected protected fields and known name/protected-text fragments.
Narratives can still contain cultural or protected information; this is not
proof of complete PII removal or demographic neutrality.

All retained goals, pain points, and behaviors are `SYNTHETIC`, not observed
customer labels. Pain points are sentences selected by a constraint-word regex,
not annotated ground truth. No real users, uploads, conversations, or private
studies are training inputs. Source/revision/record ID, documents, model version,
topic, score, and warnings remain available in CLI output or existing backend
JSON fields. Provenance is metadata and content hashes, not signed attestation.

## Inputs And Constraints

Use the strict [business context](examples/business.json) through the
[README lifecycle](README.md). Business description, target audience, product,
features, research, price wording, role, and location affect retrieval. They
do not become validated claims about a selected profile.

- Explicit `min_age` / `max_age` are hard, inclusive integer constraints in
  18-95. The checked-in example requests 18-24.
- Role and location are soft hints. The source occupation/location is retained
  and mismatches are warned about; an adult is not relabeled as a student or
  moved to Bangladesh to satisfy a prompt.
- Income, budget, structured needs, and OCEAN/personality measurements are not
  inferred. Backend unknown strings use `Not available in training data` where
  the existing schema requires a string; personality remains unset.
- Individual model selection batches with no vocabulary overlap or insufficient
  distinct eligible candidates fail, rather than returning a smaller batch or
  using an LLM. The existing multi-role API can return successful roles alongside
  `failed_roles`; see [ARCHITECTURE.md](ARCHITECTURE.md).
- The backend reports unavailable/invalid models as 503
  `ml_persona_unavailable`, and unsupported contexts as 422
  `ml_persona_unsupported_context`. Existing chat/interview routing is unchanged.

## Evaluation And Limitations

The final held-out test has 539 queries and 539 scorable pairs. Culinary and
hobby text queries rank complementary professional, sports, arts, travel,
skills, and goal narratives from the held-out identities using training-fitted
transforms. This tests cross-view retrieval, not real business relevance.

| Method                                | Test MRR | Recall@1 | Recall@5 | Recall@10 |
| ------------------------------------- | -------- | -------- | -------- | --------- |
| Selected TF-IDF + NMF                 | 0.432654 | 0.341373 | 0.530612 | 0.614100  |
| Lexical TF-IDF                        | 0.751621 | 0.660482 | 0.871985 | 0.929499  |
| Expected random ranking               | 0.012742 | 0.001855 | 0.009276 | 0.018553  |
| Training occupation-frequency ranking | 0.011943 | 0.001855 | 0.009276 | 0.012987  |

**The custom NMF blend underperforms lexical TF-IDF on both validation and
test.** Selection among the four NMF configurations is not a claim that the
selected model is better than the baseline. No tuning followed the final test.
Exact values and protocol are in [EXPERIMENTS.md](EXPERIMENTS.md).

In the test generation probe, 32 batches of five selected 160 profiles, with no
failed batches, incomplete/underage profiles, within-batch duplicate IDs/names/
descriptions, bundle mismatches, or location rewrites. Exact source reuse was
1.0. Within-batch TF-IDF cosine diversity was 0.877963 over 320 pairs; age
Jensen-Shannon divergence from the held-out synthetic reference was 0.030183.
These checks do not measure truth, predictive accuracy, or novelty.

The probe selected `not_in_workforce` 72 times out of 160, a visible selection
bias. USA-only synthetic source coverage and upstream model/cultural biases
remain. Age-bounded student-oriented generation may return distinct adults who
are not students. There are zero real business-labelled relevance evaluations
and no validated population, income, purchasing-power, OCEAN, or demand claims.

Sequential backend requests exclude active source IDs/names within their owner
scope. Independent overlapping requests do not have a transactional uniqueness
lock, so cross-process uniqueness is not guaranteed. Reported duplicate counts
above apply within evaluated batches, not all future requests.

## Runtime And Artifacts

Recorded runtime: Python 3.12.9, NumPy 2.5.2, SciPy 1.18.1, scikit-learn 1.9.0.
The loader demands exact numerical-library versions, not merely compatible
major versions. [constraints.txt](constraints.txt) pins this numerical runtime
for local installation and the backend image. Train a fresh validated model
after deliberate dependency changes; never bypass the artifact checks.

Training used two numerical threads on Windows 11, Intel64 Family 6 Model 154,
with 16 logical CPUs. The four fits took 43.6982491 seconds cumulatively,
excluding preparation and validation/evaluation overhead. The 4 GB GPU was not
used. Warm five-persona generation measured mean 32.971875 ms and p95
34.304875 ms with two CPU threads. This excludes cold loading, API queuing,
database work, and network time; it is not an API SLA. Peak RAM was not measured.

The default local bundle is `data/processed/ml_persona/model/`:

| File              | Recorded Bytes                                      |
| ----------------- | --------------------------------------------------- |
| `config.json`     | 154                                                 |
| `metadata.json`   | 779                                                 |
| `parameters.npz`  | 14,525,542                                          |
| `records.json`    | 19,458,538                                          |
| `vocabulary.json` | 137,597                                             |
| Total             | 34,122,610 (about 32.54 MiB; not runtime RAM usage) |

Bundles are ignored by Git and built locally. The backend override is
`BEBSHAX_ML_PERSONA_ARTIFACT_DIR`; loading is lazy and cached. JSON/NPZ loading
uses `allow_pickle=False`, bounded compressed/uncompressed sizes, checked file
hashes, schema, array dimensions/dtypes, finite nonnegative values, sparse
indices, vocabulary, record completeness, and identity uniqueness. Config and
metadata are each limited to 64 KiB; vocabulary to 16 MiB, records to 128 MiB,
and numeric archive/uncompressed payload to 256 MiB. Hashes detect corruption;
they do not authenticate a bundle supplied by an untrusted actor.

## Licensing And Verification Status

The source profiles are CC-BY-4.0. Redistribution of source-derived bundles or
profiles must retain NVIDIA attribution, source/revision and license notices,
and notices describing subset, normalization, and other changes. NumPy, SciPy,
and scikit-learn are BSD-3-Clause; pydantic is MIT, as recorded in the existing
[R8 review](ARCHITECTURE.md). Dependency licenses do not license the whole model
or repository. No root or ML-specific LICENSE/LICENCE/COPYING file was found,
and the ML package manifest declares no project software license; this card
does not assign one or grant redistribution rights for project code.

Post-sync local verification on 2026-09-09 passed the offline suites and all
five trained-artifact backend-smoke stages. Exact timing, including the passing
build/theme checks after the approved CSS token correction, is in
[Post-Sync Verification](IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09).
Earlier real PostgreSQL persistence/pgvector, Freellmpool chat/roles/two interview
turns, and Linux loading/inference from the Windows artifact with networking
disabled passed but were not repeated after sync. Before upstream styling,
desktop rendering passed and mobile profile-header controls clipped; the
token-only correction neither fixes that defect nor constitutes re-verification.
Local passes do not establish publication, an all-green UI, or production
readiness. See [EXPERIMENTS.md](EXPERIMENTS.md) for the research limitations.
