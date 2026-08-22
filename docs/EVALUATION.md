# BebshaX — Evaluation Framework & Methodology (Phase 11)

> **Research Question:** *Can intelligent multi-model routing aggregate free LLM capacity while preserving synthetic persona quality and user experience?*

The `bebshax.evaluation` module provides a comprehensive, automated evaluation suite for synthetic persona quality, multi-model routing strategy performance under chaos, and offline benchmark dataset replays.

---

## 1. Persona Quality & Grounding Metrics

Synthetic persona quality is evaluated across four core dimensions:

1. **Schema Validity:** Ensures presence and non-null types for all required identity fields (`id`, `name`, `business_id`, `age`, `occupation`, `goals`, `pain_points`, `attributes`).
2. **Grounding Ratio ($R_{\text{grounded}}$):** Measures the proportion of persona attributes derived directly from observed data sources:
   $$\text{Grounding Ratio} = \frac{N_{\text{OBSERVED}}}{N_{\text{total}}}$$
   Attributes with provenance class `OBSERVED` or explicit evidence links contribute to grounding.
3. **Deterministic Cross-Attribute Consistency:** Rule-based verification enforcing real-world constraints (e.g., age vs occupation boundaries, income tier vs spending behavior, location vs timezone/currency).
4. **Contradiction Detection:** Scans persona descriptions and interview dialogue transcripts for self-contradictory statements (e.g., budget buyer vs luxury enthusiast).

---

## 2. Multi-Model Routing Strategy Benchmarks

`PoolRouter` supports 7 pluggable candidate ranking strategies to evaluate routing trade-offs:

| Strategy | Description | Selection Criteria |
|---|---|---|
| **`HYBRID`** *(Default)* | Balanced production order | Pool preference config order |
| **`ROUND_ROBIN`** | Equal candidate distribution | Rotates candidates statefully |
| **`LEAST_USED`** | Load balancing across routes | Ranks by lowest invocation count |
| **`QUALITY_FIRST`** | Quality prioritization | Ranks by highest model quality tier |
| **`LATENCY_FIRST`** | Speed optimization | Ranks by lowest historical response latency |
| **`CAPABILITY_FIRST`** | Maximum capability | Ranks by context window size & JSON support |
| **`QUOTA_AWARE`** | Capacity preservation | Ranks by cooling status & remaining quota |

### Chaos Simulation (`RoutingChaosSimulator`)
The chaos simulator tests `PoolRouter` resilience by injecting stochastic rate limits (429), timeouts, and server errors across simulated candidate adapters. It measures:
- **Success Rate (%)**: Percentage of requests successfully completed.
- **Fallback Count**: Total candidate failover transitions triggered.
- **P50 / P95 Latency (ms)**: Response latency percentiles across completed requests.
- **Context Failures**: Count of `CONTEXT_WINDOW_EXCEEDED` errors.

---

## 3. Offline Benchmark Replays

Evaluates routing strategies against literature benchmarks without live network overhead:
- **`router_arena`**: Evaluates strategy candidate selection against crowdsourced model win-rate distributions from LLM routing research.
- **`xroute_bench`**: Evaluates strategy model selection against pre-recorded multi-model execution logs.

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
