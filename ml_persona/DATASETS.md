# Persona ML Training Data

Last verified: 2026-09-09.

## Policy And Source Of Truth

The owner-approved 2026-09-08 exception to R9 permits only reviewed public
synthetic data for isolated **non-LLM** training. No LLM fine-tuning, real PII,
private studies, uploads, or user conversations are accepted. Existing legacy
datasets remain training-disallowed; `ml_persona` is independent of
`minimal -> development -> evaluation -> full`.

[../scripts/dataset_manifest.py](../scripts/dataset_manifest.py) owns source
metadata, license decisions, allowed fields, revision, subset size, and research
decisions. [SOURCES.json](SOURCES.json) is a deterministic generated projection,
not a second hand-maintained allowlist. The complete generated datasheet and
researched-source table are in [../data/DATASETS.md](../data/DATASETS.md).

## Approved Dataset

| Property | Value |
| --- | --- |
| Dataset | `nvidia/Nemotron-Personas-USA` |
| Creator | NVIDIA Corporation |
| Revision | `5b4cd35ab46490c1da1bd2b5a2324d6f871be180` |
| Release | v1.1, 2025-10-28; repository updated 2025-12-16 |
| License | CC-BY-4.0, checked from the pinned HF card at download time |
| Upstream | 1,000,000 synthetic adult profiles; 11 parquet shards, about 2.69 GB total |
| Download | Only `data/train-00000-of-00011.parquet`, about 245 MB, plus the pinned card |
| Selection | Lowest 6,000 SHA-256 UUID ranks across the entire selected shard |
| Role | `training`; never OBSERVED evidence, never an EvidenceStore diversity seed |

[Pinned source card](https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA/blob/5b4cd35ab46490c1da1bd2b5a2324d6f871be180/README.md)
and [CC-BY-4.0 license](https://creativecommons.org/licenses/by/4.0/).
Attribute NVIDIA Corporation, retain license and attribution notices, and
identify the hash-ranked subset and field projection as BebshaX modifications.
Source-derived bundles also retain attribution and notices of normalization or
other changes. The source license does not assign a license to BebshaX software
or its dependencies. Names are intended to be synthetic identifiers; retained
narratives may still contain cultural or protected information. Neither the
allowlist nor synthetic origin proves complete PII removal. This is a synthetic
prior, **not empirical consumer data**.

The manifest records its license review on 2026-09-08. The pinned upstream card
was fetched again and its CC-BY-4.0 license confirmed on 2026-09-09.

## Commands And Artifacts

From the repository root on the configured Windows development machine:

```powershell
.venv/Scripts/python.exe scripts/setup_datasets.py --profile ml_persona
.venv/Scripts/python.exe scripts/setup_datasets.py --profile ml_persona --verify-only
.venv/Scripts/python.exe scripts/setup_datasets.py --profile ml_persona --force
```

The approved download, preparation, and local training have completed; the saved
test evaluation was produced on the 2026-09-09 resume. The independent
[CLI lifecycle](README.md) wraps the same downloader with
`python -m bebshax_persona_ml download`, then provides `prepare`, `validate`,
`train`, `evaluate`, `generate`, and `smoke`.

Ingestion creates:

- `data/raw/nemotron_personas_usa_ml/README.md` and the selected shard under its
  upstream `data/` path. The Hub may also create its own local download metadata.
- `data/processed/nemotron_personas_usa_ml.jsonl`, one raw-shaped synthetic
  profile per UTF-8/LF line, with only allowlisted fields.
- `data/metadata/nemotron_personas_usa_ml.json`, the manifest projection and
  ingestion verification/inspection record described below.

No downloader imports the `ml_persona` package. The existing `huggingface_hub`,
`fastparquet`, and pydantic dependencies suffice; no `datasets`, `pyarrow`,
provider SDK, or new dependency installation is introduced. The existing Hub
dependency PyYAML is used only to classify structured-card parse failures.
Splits and model artifacts are produced by the independent package under
`data/processed/ml_persona/`; ingestion itself does not create them. Local raw,
processed, and model artifacts are ignored by Git and are not distributed with
a clean checkout.

## Recorded Ingestion

| Measurement | Saved Value |
| --- | --- |
| Shard scan | 90,910 rows, all 5 row groups |
| Selected profiles | 6,000, hash-ranked across the shard |
| Raw shard bytes | 244,151,718 |
| Projected JSONL bytes | 30,146,176 |
| Raw SHA-256 | `af5d3e1c0ca2ca9cd12b5bcfc6ca5a850cdc6b7d6c24eb89ce948b23bed9c7e7` |
| Processed SHA-256 | `02e5db3063fa79c5cbcf61fbb3419dd3cf62c368cc98cbb8745495f8cb80b0a2` |
| Projected fields | 17; no missing columns; scalar missing/invalid counters all zero |

The counters cover ingestion type/presence inspection across scanned rows.
They are not the later `TrainingRecord` schema or candidate-completeness checks.
The full per-location distributions remain in local reports rather than this
summary; the subset is not a population-representative sample.

## Determinism And Verification

Download calls use official `hf_hub_download` with `repo_type="dataset"`, the
exact manifest revision, and `token=False`. The pinned card must declare the
single license `cc-by-4.0`. Missing, malformed, ambiguous, or mismatched licenses
fail before the shard download. `HfApi(token=False).get_paths_info` obtains the
selected file's upstream LFS SHA-256 and byte size. Missing LFS metadata, a wrong
path, a size mismatch, or a checksum mismatch is fatal. `--force` passes
`force_download=True` to both ML file downloads; it does not change legacy
profile behavior.

Every parquet row group is scanned. For each UUID the selector hashes UTF-8
`<hf_repo_id>@<pinned_revision>:<uuid>`, keeps the lowest 6,000 ranks, and emits
records sorted by hash then UUID. It is not a prefix, randomized sample, or
representative sample of the million-profile corpus. Memory is bounded by one
decoded row group, selected complete row payloads, and the scanned UUID set.
Tiny fixture shards emit all their rows; the actual selected count is recorded.
Duplicate or invalid UUIDs and empty shards fail instead of silently dropping
identities. Full field values and narrative whitespace are preserved; no
persona text is truncated, compressed, or relabeled.

`--verify-only` is entirely local and read-only for this profile. It verifies the
manifest source and revision, metadata digest, card hash/license, raw hash
against the persisted LFS hash, output hash, sizes, and output record count.
Missing or mismatched artifacts return a nonzero exit code. A normal rerun skips
only after the same checks pass; it never silently skips or repairs mismatches.
Use explicit `--force` to rebuild corrupted artifacts from the pinned source.

The metadata contains all fields from the manifest entry plus:

| Field | Meaning |
| --- | --- |
| `metadata_version`, `artifact_role` | `1`, `training` |
| `actual_raw_sha256`, `upstream_raw_sha256` | Exact primary raw-file checksum verified against upstream LFS |
| `actual_processed_sha256`, `actual_card_sha256` | SHA-256 of emitted JSONL and locally retained pinned README |
| `metadata_sha256` | SHA-256 of canonical UTF-8 JSON excluding this field; sorted keys, compact separators |
| `raw_size_bytes`, `processed_size_bytes`, `processed_record_count` | Observed artifact sizes and selected count |
| `license_check` | `license`, `revision`, and `card_path` (`README.md`) |
| `inspection` | Scanned/selected counts, row groups, selection recipe, available/excluded/missing columns, missing/invalid value counts, maximum string lengths |

Inspection counters cover all scanned rows, not only the selected subset.
Missing values remain `null` or their original empty text; invalid non-UUID
values remain visible for strict normalization to reject. No values are
imputed. The metadata hash detects corruption, not adversarial coordinated
rewrites of local metadata and artifacts. Manifest `raw_sha256` and
`processed_sha256` remain `null`; the recorded actual digests above are verified
against retained upstream LFS/local metadata, not checked-in checksum pins or
cryptographically signed source attestation.

## Normalization And Splits

[data.py](src/bebshax_persona_ml/data.py) owns
`prepare_records(rows, source, revision)`;
[pipeline.py](src/bebshax_persona_ml/pipeline.py) owns completeness filtering,
split persistence, and re-verification. Ingestion does not import either one.

| Upstream Fields | Meaning At The Handoff |
| --- | --- |
| `uuid` | Stable synthetic source identity |
| `age`, `occupation`, `education_level` | Source demographic and professional values; normalization validates complete types |
| `city`, `state`, `country` | Source location; not a target population claim |
| `persona`, `professional_persona`, `sports_persona`, `arts_persona`, `travel_persona`, `culinary_persona` | Complete synthetic narratives |
| `cultural_background`, `skills_and_expertise`, `hobbies_and_interests` | Complete synthetic background and interest text |
| `career_goals_and_ambitions` | Goal candidates, not measured customer objectives |

Explicit sex, zipcode, bachelors field, marital status, and the hobbies/skills
list variants are not emitted. Cultural background is retained as source text;
protected information may also occur elsewhere in narratives.
Downstream regex extraction of `pain_points` produces candidate hypotheses,
**not ground truth labels**. Income is absent and remains unknown. Never infer
income, purchasing power, or budget from age or occupation. No supervised
business-to-customer or customer-demand labels are supplied by this corpus.

Normalization applies Unicode NFKC and whitespace collapse to strings, but does
not summarize or truncate narratives. It requires a source UUID and identity
description, hashes source/UUID for the stable record ID, preserves revision and
documents, extracts a name only when the source text supports it, and rejects
detected email/URL contact text. Goals come from source career-goal text;
behaviors retain source hobby/identity text; pain points are whole matching
sentences. Missing values are not imputed and source locations are not rewritten.

| Preparation Stage | Recorded Result |
| --- | --- |
| Projected input | 6,000 |
| Normalization accepted | 4,694 |
| Normalization rejected | 1,306, all labelled `invalid_schema` |
| Initial ID/content duplicates | 0 |
| Incomplete candidates removed | 1,078 |
| Duplicate identities/names removed | 22 |
| Usable candidates | 3,594 |
| Train / validation / test | 2,516 / 539 / 539; seed 42, 70/15/15 |

`invalid_schema` is the `TrainingRecord` pydantic-validation branch, not a
missing-input or scalar-ingestion error. In particular, age must be a strict
integer in 18-95 when present; the saved aggregate does not retain per-row
validation details. Completeness separately requires an adult age, source ID,
description, occupation, at least one goal, and at least one extracted pain
point. Zero scalar-ingestion missingness therefore does not mean every profile
is schema-valid or complete for selection.

The pipeline deterministically orders candidates, deduplicates IDs, normalized
names, and descriptions, and groups related identities before the seeded split.
Training, validation, and test never share those identities. `validate`, `train`,
and `evaluate` re-verify the approved source through `_verify_source`, check
source/split/record/preparation digests, and reconstruct normalized records and
canonical split membership from that source. Rehashed forged preparation/split
files still fail this source comparison; local hashes are not an independent
trust anchor against coordinated replacement of all source metadata.

The model fits only training records, selects hyperparameters on validation,
and evaluates the frozen model on test. See [EXPERIMENTS.md](EXPERIMENTS.md) for
the recorded results and [MODEL_CARD.md](MODEL_CARD.md) for intended use/limits.

## Research Decisions And Limits

- **Used: Nemotron-Personas-USA (CC-BY-4.0).** Synthetic adult profiles with the
  needed structured fields; only the bounded pinned subset is approved.
- **Researched, not used for ML: Google Synthetic-Persona-Chat (CC-BY-4.0).**
  Conversation-centric and missing required demographics; its legacy
  dialogue-example use stays unchanged.
- **Researched, not used for ML: PersonaHub (CC-BY-NC-SA-4.0).** NC/share-alike
  restrictions and insufficient structured fields; its legacy seed use stays
  unchanged and does not grant training permission.
- **Researched, NOT downloaded: UCI Restaurant Consumer Data (CC-BY-4.0).**
  Historical 2012 data for 138 people and 1,161 ratings. Coordinates and religion
  raise privacy concerns, real-person records violate the synthetic-only
  training constraint, and restaurant-only coverage is too narrow.
- **MiniLM is a model, not a dataset.**
  `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0) was researched but not
  downloaded or used for this ingestion slice.

The approved source covers USA adults and inherits upstream generation,
cultural, demographic, and selection biases. It supports no Bangladesh
population claims and is not empirical research into any customer segment.
Model selection scores and synthetic profiles cannot establish consumer demand
or substitute for real-user validation.