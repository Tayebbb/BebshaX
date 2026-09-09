# BebshaX — Evaluation Framework & Methodology (Phase 11)

> **Research Question:** _Can intelligent multi-model routing aggregate free LLM capacity while preserving synthetic persona quality and user experience?_

The `bebshax.evaluation` module provides persona metrics, routing control-flow experiments under chaos, and replay scaffolding. The withdrawn offline replay results are not valid routing benchmarks (section 3).

The isolated non-LLM persona model has a separate package and lifecycle; its
2026-09-09 results are in section 5 below. Its retrieval scores are not grounding
scores and do not replace the original Phase-11 routing research question.

---

## 1. Persona Quality & Grounding Metrics

Synthetic persona quality is evaluated across four core dimensions:

1. **Schema Validity:** Ensures presence and non-null types for all required identity fields (`id`, `name`, `business_id`, `age`, `occupation`, `goals`, `pain_points`, `attributes`).
2. **Grounding Ratio ($R_{\text{grounded}}$):** Measures the proportion of persona attributes derived directly from observed data sources:
   $$\text{Grounding Ratio} = \frac{N_{\text{OBSERVED}}}{N_{\text{total}}}$$
   Attributes with provenance class `OBSERVED` or explicit evidence links contribute to grounding.
3. **Deterministic Cross-Attribute Consistency:** Rule-based verification enforcing real-world constraints (e.g., age vs occupation boundaries, income tier vs spending behavior, location vs timezone/currency).
4. **Contradiction Detection:** Scans persona descriptions and interview dialogue transcripts for self-contradictory statements (e.g., budget buyer vs luxury enthusiast).

Current ML profiles deliberately carry zero observed grounding and unknown
income/OCEAN. These older metrics do not establish predictive accuracy or
business relevance; a `SYNTHETIC` profile is not an infrastructure failure.

---

## 2. Multi-Model Routing Strategy Benchmarks

`PoolRouter` supports 7 pluggable candidate ranking strategies to evaluate routing trade-offs:

| Strategy                 | Description                  | Selection Criteria                          |
| ------------------------ | ---------------------------- | ------------------------------------------- |
| **`HYBRID`** _(Default)_ | Balanced production order    | Pool preference config order                |
| **`ROUND_ROBIN`**        | Equal candidate distribution | Rotates candidates statefully               |
| **`LEAST_USED`**         | Load balancing across routes | Ranks by lowest invocation count            |
| **`QUALITY_FIRST`**      | Quality prioritization       | Ranks by highest model quality tier         |
| **`LATENCY_FIRST`**      | Speed optimization           | Ranks by lowest historical response latency |
| **`CAPABILITY_FIRST`**   | Maximum capability           | Ranks by context window size & JSON support |
| **`QUOTA_AWARE`**        | Capacity preservation        | Ranks by cooling status & remaining quota   |

### Chaos Simulation (`RoutingChaosSimulator`)

The chaos simulator tests `PoolRouter` resilience by injecting stochastic rate limits (429), timeouts, and server errors across simulated candidate adapters. It measures:

- **Success Rate (%)**: Percentage of requests successfully completed.
- **Fallback Count**: Total candidate failover transitions triggered.
- **P50 / P95 Latency (ms)**: Response latency percentiles across completed requests.
- **Context Failures**: Count of `CONTEXT_WINDOW_EXCEEDED` errors.

---

## 3. Offline Benchmark Replays

The retained scaffolding was intended to compare routing strategies without live network overhead:

- **`router_arena`**: intended candidate comparison, but the available slice does not supply usable per-model score evidence.
- **`xroute_bench`**: intended execution-log comparison, but the downloaded slice lacks candidate executions.

> **Status (2026-09-06): results withdrawn, scaffolding kept.** The 2026-08 replay reports (`eval_report_20260822_*`, `eval_report_20260828_*`) claimed 100 % alignment, but nonexistent RouterArena column names and absent xRouteBench candidate executions made the evaluator agree with its own default. Do not cite those numbers. The [evidence inventory](RESEARCH_EVIDENCE.md) records the separate [cross-route measurement](../scripts/run_cross_route_eval.py) and its small-sample limits. Neither replay nor cross-route results measure the new ML selector's business relevance.

---

## 4. Running Evaluations

Run the evaluation CLI script from the repository root:

```bash
# Run all evaluation suites (personas, routing chaos simulation, offline datasets)
python scripts/run_evaluation.py --suite all

# Run specific suite
python scripts/run_evaluation.py --suite routing

# Save reports to custom directory
python scripts/run_evaluation.py --suite all --output-dir data/metadata
```

Output artifacts are generated in `data/metadata/`:

- Markdown Report: `eval_report_<timestamp>.md`
- JSON Report: `eval_report_<timestamp>.json`

---

## 5. Isolated Persona ML Evaluation (2026-09-09)

The independent [evaluation implementation](../ml_persona/src/bebshax_persona_ml/evaluation.py)
measures synthetic cross-view retrieval and generation structure. It does not
measure customer demand, real business-labelled relevance, or attribute
predictive accuracy. All source-derived claims stay `SYNTHETIC`; empty evidence
and zero grounding are correct, not reasons to fall back to an LLM.

### Protocol

The approved 6,000-record subset yields 3,594 usable normalized identities.
Seed-42 splits are 2,516 training, 539 validation, and 539 test records. TF-IDF
vocabulary/IDF and NMF components fit training only. A four-point search over
16/32 topics and lexical weights 0.35/0.7 selects on validation MRR, with
canonical-config tie breaking. The frozen 32-topic/0.7 selection was evaluated
on test after the interrupted session resumed; no tuning followed that test.

Culinary and hobby narratives query complementary professional, sports, arts,
travel, skills, and goal narratives for the same held-out identities. Rankings
are among held-out records using training-fitted transforms. Missing/OOV views
count as misses rather than being dropped; this run had 539/539 valid test pairs.
Random is exact expected uniform ranking; popularity uses training occupation
frequencies and seeded tie breaking. These are proxies, not supervised
business-to-persona labels or direct MMR batch-quality comparisons.

| Method | Validation MRR | Test MRR |
| --- | --- | --- |
| Selected TF-IDF + NMF | 0.41811696827631073 | 0.43265430767833196 |
| Lexical TF-IDF | 0.7166454265071603 | 0.7516210382537256 |
| Expected random | Not reproduced here | 0.012741852676724338 |
| Popular occupation | Not reproduced here | 0.011943168742486186 |

**The custom model underperforms lexical TF-IDF on validation and test.** It is
not established as a superior production selector. Full recall tables and all
four candidate measurements are in [EXPERIMENTS.md](../ml_persona/EXPERIMENTS.md).

### Generation And Timing

The test probe generated 32 batches of five training prototypes: 160 selections,
zero failed batches, and zero incomplete/underage profiles, within-batch duplicate
IDs/names/descriptions, bundle mismatches, or location rewrites. Exact normalized
source reuse is 1.0 by design, not novel identity synthesis. Within-batch TF-IDF
cosine distance is 0.8779632658 over 320 pairs; age Jensen-Shannon divergence
against the held-out synthetic reference is 0.03018325894. `not_in_workforce`
accounts for 72/160 selections, exposing bias despite those structural checks.

Warm five-persona generation measured mean 32.971875 ms and p95 34.304875 ms with
two CPU threads. This is loaded-model timing, not cold-load latency, API queuing,
DB persistence, or an SLA. The 4 GB GPU is unused. Source coverage is USA-only
synthetic data; no Bangladesh or student fit, income/budget prediction, OCEAN
accuracy, or real-business relevance is established.

### Reproduction And Status

After the [ML installation/download/preparation steps](../ml_persona/README.md),
run from the repository root:

```powershell
.venv/Scripts/python.exe -m bebshax_persona_ml train --config ml_persona/configs/training.json
.venv/Scripts/python.exe -m bebshax_persona_ml evaluate
.venv/Scripts/python.exe -m bebshax_persona_ml smoke --backend --input ml_persona/examples/business.json
```

Training writes local `data/processed/ml_persona/experiment.json` and
`experiments/<model_version>.json`; evaluation writes
`data/processed/ml_persona/evaluation.json`. Existing outputs require a different
path or explicit `--force`, not silent overwrite. These ignored artifacts are
not linked as distributed files. Model/source/preparation fingerprints and
exact numerical-runtime compatibility are checked; they are not signatures.

The [post-sync local verification record](../ml_persona/IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09)
reports passing backend/ML/frontend suites, all five trained-artifact smoke
stages, Ruff, `pip check`, and both quiet Compose syntax checks. The full backend
run includes the packaging regressions. The verified frontend suite preceded
the CSS token correction; the latest TypeScript/Vite build and theme check
passed after it. Exact counts, timing, and the pre-sync baseline are in that record.

Earlier PostgreSQL integration tests passed 2/2; live persistence, Freellmpool
chat/roles/interviews, and network-disabled Linux-container inference also
passed, but were not repeated after sync. Desktop rendering passed before
upstream styling; mobile profile-header clipping remains unfixed and was not
reverified after the styling or token-only correction. Pyright was unavailable.

These scoped results are not a provider success rate or proof of production
readiness. Full Compose app/web and cross-conversation memory retrieval
rehearsals were not repeated. The probe's zero
within-batch duplicates do not prove concurrent uniqueness: production source
exclusions are owner-scoped reads without a transactional identity lock.
Commit, push, and CI results are tracked separately in the
[implementation log](IMPLEMENTATION_PLAN.md), not claimed successful here.

Next work is a validation-only comparison of TF-IDF with equivalent diversity
selection, plus authorized held-out business-labelled relevance judgments.
These are proposals, not implemented features or permission to retune against
the already-inspected test set.
