# Research Evidence — what BebshaX can and cannot claim (2026-09-07)

> Companion to [EVALUATION.md](EVALUATION.md) and [COMPETITION_AUDIT.md](COMPETITION_AUDIT.md). Every statement below is classified. A claim is **VERIFIED** only when an artifact in this repository (a stored run, a test that executes the code path, or a schema) backs it; **SUPPORTED** when the code computes it but no stored run exists; **EXPERIMENTAL** when it is a pipeline check on scripted data; **NOT VERIFIED** when the repository contains no evidence. Numbers are quoted with their `n`.

## 1. The research question, decomposed

> _Can intelligent multi-model routing aggregate legitimately available free LLM capacity while preserving synthetic persona quality and user experience?_

The question bundles five separable claims. They are **not** interchangeable and this document never lets one stand in for another:

| Dimension | What would count as evidence | Status |
| --- | --- | --- |
| **Availability** — requests are served when a provider fails | fallback recorded in provenance; explicit failure when nothing serves | **VERIFIED** (code + tests + live run, §3) |
| **Quality preservation across routes** — the persona stays the same person whichever model answers | identity facts retained, numeric claims stable, cross-route answer agreement above the cross-persona baseline | **VERIFIED at very small n** (§4) — direction positive, not statistically separable |
| **Cost** — the system runs on $0 of API spend | keyless providers, no paid default routes | **SUPPORTED** (config; no cost ledger artifact) |
| **Latency** — acceptable interaction time | measured per request in provenance; local 1–3 s, free pool 0.7–6 s, worst case 26 s on cold Ollama | **VERIFIED for the runs stored**; no SLO claimed |
| **User experience** — a researcher can complete the workflow without picking models | one "Generate" button; routing only in the developer view; failures explicit with request ids | **SUPPORTED** (UI + tests); no user study |

## 2. Stored artifacts (all under `data/metadata/`)

| Artifact | Produced by | What it measures | Honest scope |
| --- | --- | --- | --- |
| `cross_route_<ts>.json/.md` (latest `cross_route_20260907_034932`) | `scripts/run_cross_route_eval.py` — real routes, `simulated: false` | identity-fact retention, numeric divergence, cross-route vs cross-persona agreement, contradiction count, per-answer provenance | **n = 2 personas × 4 questions × 2 requested routes × 1 repeat = 16 answers.** Three concrete models actually served (`ollama/llama3.2:3b` ×10, `llm7/codestral-latest` ×5, `ovh/Meta-Llama-3_3-70B-Instruct` ×1). Two of the eight free-pool requests fell back to the local model and are reported as **not honoured**, never relabelled. |
| `local_3b_gate_2026082{6,7}_*.json` (3 runs) | `scripts/judge_local_interview.py` | LLM-judged 6-dimension rubric, local 3B vs free pool | n = 1 persona × 5 questions per arm; judge model overlapped with arm B in runs 1–2 (flagged; the script now refuses a non-disjoint judge) |
| `eval_report_20260828_035252.json/.md` | `scripts/run_evaluation.py --suite all` | PoolRouter control flow under scripted failure probabilities (7 strategies × n=35) | **router control-flow simulation on FakeAdapter** — says nothing about real providers; `avg_tokens_per_sec` is `null` (a former constant 120.5 was removed) |
| `ollama_benchmark.json` | `scripts/benchmark_ollama.py` | tok/s, TTFT for local candidates on the 4 GB GPU | n = 3 runs per model, one machine |
| `router_arena.json`, `xroute_bench.json` | dataset manifest | dataset descriptors only | the offline "benchmark replay" was found **unusable** (RouterArena ships no per-model scores; column case mismatch fixed) — the evaluator now reports `unusable: true`, never a default winner |

## 3. Availability — what is verified

- **Fallback sequence** `A 429 → B serves`, `A 5xx → B timeout → local serves`, `all fail → AllCandidatesFailed`: unit-tested with `FakeAdapter` ([tests/llm/test_fallback.py](../apps/backend/tests/llm/test_fallback.py), [test_pool_router.py](../apps/backend/tests/llm/test_pool_router.py)) **and** end-to-end over HTTP with provenance assertions ([tests/api/test_tournaments_e2e.py](../apps/backend/tests/api/test_tournaments_e2e.py) — tournaments B, C, H). The 503 body lists every attempt with its `FailureKind`.
- **Explicit failure, no fabrication:** tournament C asserts the transcript is unchanged and no reply text exists anywhere after total failure; the copilot/script/insight/plan fallbacks that _do_ template carry structural markers (`served_by=bebshax/copilot-engine`, `source=fallback_static|fallback_mechanical|deterministic_template`, `fallback_reason`) that the UI renders as "Template — not AI-generated".
- **Context pre-flight:** tournament E asserts a 413 `context_window_exceeded` with `estimated_tokens`, every adapter `.calls == []` (nothing sent, nothing truncated). The token estimator is now script-aware (Bangla counted ≥1 token/char) so the local model's `num_ctx` can no longer silently drop history.
- **Live observation (this repo, 2026-09-07):** in the cross-route run 2/8 free-pool requests fell back to the local model within the same request; earlier the cold Ollama daemon produced one `AllCandidatesFailed` after 9 attempts / 145 s — surfaced as a failed row, not as an answer.
- **Cooldown scope:** RATE_LIMITED / QUOTA_EXHAUSTED / AUTH_INVALID now cool the whole provider, not just one model ([test_routing_hardening_cooldown_scope.py](../apps/backend/tests/llm/test_routing_hardening_cooldown_scope.py)).

## 4. Quality preservation across routes — the crux, measured honestly

**Metric definitions** (`bebshax/evaluation/cross_route_consistency.py`, deterministic, no LLM judge):

- `identity_fact_retention` — share of probed identity facts (name, age, occupation, location) restated correctly by the answering model.
- `numeric_divergence_mean_bdt` — |claimed monthly amount − stated budget| on the budget probe.
- `cross_route_agreement` — mean pairwise HashEmbedding cosine between answers to the same question by the **same persona served by different models** (pairing uses the route that **served**, never the route requested — a first run that paired by requested route was discarded because one model had served everything).
- `baseline_agreement` — the same cosine between **different personas** on the same question. `agreement_ratio > 1` ⇒ the persona signal dominates the provider signal.
- `contradiction_count` — the interview engine's numeric self-contradiction detector over each answer sequence.

**Result (`cross_route_20260907_034932`, real routes):**

| Metric | Value | 95% bootstrap CI | n |
| --- | --- | --- | --- |
| identity_fact_retention | **1.000** | [1.000, 1.000] | 16 facts |
| numeric_divergence_mean_bdt | **0.0** | — | 4 probes |
| cross_route_agreement | 0.411 | [0.355, 0.456] | 6 pairs |
| baseline_agreement | 0.358 | [0.303, 0.410] | 16 pairs |
| agreement_ratio | **1.145** | — | — |
| contradiction_count | 0 | — | 16 sequences |

**What may be claimed:** _On this run, every identity fact survived a switch between a 3B local model, Codestral (llm7) and Llama-3.3-70B (ovh); no persona overspent its stated budget; same-persona answers across models agreed more with each other than different personas did (ratio 1.15)._

**What may NOT be claimed:** statistical significance (the two CIs overlap at n = 6/16 pairs), generality (2 personas, 4 questions, one afternoon, one region of the provider catalog), or anything about interviews longer than one turn (the 20-turn identity-attack tournament G is a **scripted** FakeAdapter test of the prompt-side invariants, not a model measurement).

**Known metric limitation found during this work:** the numeric self-contradiction detector produced 3/3 false positives on the first real run by comparing a restated _total_ budget ("800 BDT for apps") with an _allocation_ ("200 BDT for this app"). Fixed and regression-tested ([test_numeric_consistency.py](../apps/backend/tests/interview/test_numeric_consistency.py) `test_restating_the_known_budget_is_not_a_spend_claim`); the stored artifact was regenerated with the shipped detector.

**To strengthen (documented, not done):** `--personas 6 --questions 5 --repeats 3` (≈180 calls, ~1–2 h on free tiers) gives ≥45 same-persona pairs; add an LLM judge with a route disjoint from every arm (the judge script already enforces disjointness); persist provenance to `llm_requests` from the script.

## 5. Claims audit — corrected in this pass

| Claim (where it lived) | Before | Now |
| --- | --- | --- |
| "~24 providers / 222 routes" (PROJECT_CONTEXT, ROUTING, AI plan) | asserted | "18 providers in the freellmpool 0.11.4 catalog (verified)" |
| "100 % alignment on RouterArena/xRouteBench" (FINAL report, SUMMARY) | tautology on a hard-coded default model | withdrawn; evaluator reports `unusable` |
| `avg_tokens_per_sec: 120.5` in eval JSON | constant | `null` / "not measured" |
| "Local 3B scored 9.65/10" | one run quoted | all three runs quoted (9.65 / 9.05 / 9.2 vs 8.25 / 8.05 / 8.2), n = 1 × 5, judge overlap noted |
| "identity held across 4 providers mid-interview" | unstored smoke observation | labelled as such; replaced by the stored cross-route artifact (§4) |
| "~100 personas/day validated as feasible" | asserted | "planned target; `measure_capacity.py` exists, no stored artifact" |
| Seeded demo provenance row (pollinations/deepseek-r1, 1180 ms) | fabricated, rendered as real | deleted; demo mode seeds **no** `llm_requests` rows |

## 6. Reproduce

```bash
# offline pipeline check (scripted replies; the report says simulated: true)
python scripts/run_cross_route_eval.py --fake --personas 3 --questions 5 --routes fakeA/m1,fakeB/m2 --repeats 2 --seed 42

# real routes (network + Ollama running); ~2-3 min for 16 calls
python scripts/run_cross_route_eval.py --personas 2 --questions 4 --routes ollama/llama3.2:3b,freellmpool/auto --repeats 1 --seed 42

# router control-flow simulation + persona validator suite
python scripts/run_evaluation.py --suite all

# judged gate (refuses a judge that shares a route with an arm)
python scripts/judge_local_interview.py
```

Metrics endpoints computed from real provenance rows: `GET /api/evaluation/metrics` (per-pool success/fallback/local-serve/latency, grounding, schema validity) — rendered in the Routing & Provenance view's Evaluation card with `n` and "not yet measured" for nulls.
