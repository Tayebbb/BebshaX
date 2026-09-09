# BebshaX — Project Report (AUST CSE Carnival 8.0, Software & AI)

> Draft for the official 500-word report. Persona ML scope refreshed 2026-09-09; confirm the final template's word-count rules before submission.

## BebshaX — Synthetic Research Rehearsal on a $0 AI Budget

**Problem.** User research is the most skipped step in building a product: recruiting 20 interview participants takes weeks, agencies charge thousands of dollars, and a student founder in Dhaka can afford neither. The shortcut — "just ask ChatGPT" — produces sycophantic, ungrounded answers with no way to tell real claims from invented ones.

**Solution.** A founder describes a business through an LLM copilot, explores research evidence and datasets, and selects a synthetic persona panel. A separate CPU-only TF-IDF/NMF model learns vocabulary, word weights, topics, and profile representations from approved synthetic data; diversity-aware selection returns complete source profiles, not newly invented people. All four persona-generation paths share this model and existing storage. LLM interviews, behavioral simulations, and versioned reports remain downstream. The workflow rehearses questions for real customers; it does not validate demand.

**Engineering.** The research question remains whether governed routing can aggregate legitimate free LLM capacity while preserving persona context. Eighteen declared task types map to seven pools with context checks, concurrency limits, quotas, classified failures, and full provenance. Local Ollama supports conversations when available. Persona selection bypasses those pools: it needs no LLM, API key, or GPU, and model failures surface as 503/422 rather than LLM fallback. FastAPI, PostgreSQL/pgvector, and React reuse existing contracts. ML claims are always SYNTHETIC with source/model metadata, empty observed citations, and no invented income, budget, or OCEAN scores. Cached demo fixtures remain separately labeled.

**Measurements and limits.** The approved CC-BY-4.0 NVIDIA USA-synthetic subset yields 3,594 complete unique profiles, split 2,516/539/539. Four model fits took 43.70 seconds on two CPU threads. Held-out retrieval MRR is 0.432654 versus lexical TF-IDF 0.751621: the NMF blend underperforms. All 160 probe profiles passed structural checks, but 72 were outside the workforce. Source reuse is intentional; student, Bangladesh, population, and purchasing validity are unmeasured. Warm five-profile p95 of 34.3 ms excludes API and cold-load costs. Live checks covered persistence, two LLM interview turns, and Linux loading of the Windows artifact; they are not production certification. Mobile header clipping and a full Compose rehearsal remain unresolved.

**SDG alignment.** Lower-cost research rehearsal aligns with SDG 8.3 entrepreneurship, SDG 9.b technology development, and SDG 10.2 inclusion. These are intended contributions, not measured social outcomes or proof of local-market representation.

**Complex Engineering Problem.** The work combines distributed failover, applied NLP, data licensing, and evaluation (WP1); resolves zero-budget versus context-fidelity constraints (WP2); investigates cross-provider consistency and synthetic selection (WP3–4); enforces written provenance policies through tests (WP5); balances provider, publisher, and researcher interests (WP6); and coordinates routing, persistence, memory, and evaluation (WP7). The original fifteen phases remain complete; ML is maintenance, not a sixteenth phase.

**Team.** Built by a three-member AUST team; all engineering decisions, quality gates, and audit reports are documented in the repository.
