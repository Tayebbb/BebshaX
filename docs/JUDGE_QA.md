# Judge Q&A — the hardest questions and honest answers (2026-09-07)

> Written from the implementation, not the pitch. Where a claim is not backed by an artifact it says so. See [RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md) for the classification of every number.

**1. Why does BebshaX need multiple models?**
Because the project has a $0 API budget and free tiers are individually unreliable (429s, daily caps, outages, 30–120 s queues). No single free endpoint can sustain a research workflow; the union of 18 keyless/free providers plus a local model can. Multiple models are a **capacity** answer, not a quality one — we never claim a weaker model answers better.

**2. Why not simply use one strong model?**
We would, if it were free and always up. The local `llama3.2:3b` is the always-available floor (4 GB VRAM ceiling); the free pool raises quality and speed when it is reachable. The system's job is to make that switch safe: identity card immutable, context never truncated, provenance recorded, explicit failure otherwise.

**3. What exactly is being routed?**
An `LLMRequest` with a declared `TaskType` (18 fixed kinds). Task → pool (7 pools, a data table) → candidate routes in preference order → pre-flight filter (capabilities, estimated context, cooldowns) → attempt loop governed by a closed `FailureKind` policy table → fallback across adapters → `ProvenanceRecord`. The router never inspects answer quality.

**4. What is the actual research contribution?**
An engineering-plus-measurement contribution: (a) a routing policy layer where quality degradation is structurally impossible to hide (no truncation, no identity swap, explicit `ContextWindowExceeded`/`AllCandidatesFailed`, full provenance); (b) an evidence-grounded persona pipeline whose provenance classes (OBSERVED/INFERRED/SYNTHETIC) are **enforced in code**, not requested from the model; (c) a first deterministic cross-route persona-consistency measurement. Not a new model, not a learned router.

**5. What is novel?**
The combination is unusual: provenance enforcement that can only downgrade, a closed failure taxonomy where quality is not a failure, memory items labelled by source so a researcher cannot author the persona's "recollections", prompt-injection defense applied to every untrusted field, and a Judge Lab that runs failure drills through the production router. Individually each is known good practice; as a whole system for synthetic-user research on free capacity it is, to our knowledge, not available off the shelf.

**6. How do you measure persona quality?**
Deterministically first: grounding ratio (OBSERVED ∧ real evidence, no bonuses), schema validity, rule-based consistency, numeric self-contradiction, identity drift, cross-route retention/agreement. LLM judging exists (6-dimension rubric) but only with a judge route disjoint from every arm, and it is labelled as such. What we do **not** have: a human panel or a behavioural-plausibility metric.

**7. How do you know personas resemble real users?**
We don't claim they do. The datasets are slices, not representative samples (`data/DATASETS.md` says so). A persona is a research signal; Step 5 of the workflow lists its SYNTHETIC/INFERRED claims first under "Validate with real customers next". The honest limitation is stated in the product, not hidden in a footnote.

**8. How do you prevent hallucination?**
We cannot prevent a model from generating; we prevent the system from **believing** it. A claim becomes OBSERVED only if it cites evidence that was actually shown, shares content with it, and the cited sources do not disagree on identity facts. Everything else is INFERRED or SYNTHETIC and rendered that way. Confidence numbers are derived from citation counts, never from model self-scores.

**9. How do you handle contradictory evidence?**
`contested_slots` detects disjoint numeric values (age always; price/count when the claim asserts them) across the sources a claim cites → the claim is INFERRED with `grounding_basis = contested_evidence` and the persona carries `contested:age`. Tournament F tests it end to end; the Judge Lab `evidence_conflict` scenario shows it live.

**10. How do you prevent prompt injection?**
Every researcher/document/dataset/memory field is wrapped in an `<UNTRUSTED_*>` block whose closing tag cannot be forged from inside (case/whitespace variants neutralised), and every system prompt carries the rule that such blocks are data. Transcripts are passed as JSON rows. The identity card is placed first and is byte-identical per turn. Tournament D and the Judge Lab `prompt_injection` scenario demonstrate it. It is a defense-in-depth measure, not a proof — a sufficiently compliant model could still be talked into odd behaviour, which is why drift is also **detected** after the fact.

**11. What happens when every provider fails?**
`AllCandidatesFailed` → HTTP 503 with `error_code = all_candidates_failed`, the LLM request id, every attempt with its `FailureKind`, and the routing path. No turn is written, no template answer is produced (tournament C). The UI shows the classified reason and a copyable request id.

**12. Why is Ollama necessary?**
It is the availability floor: the only route that does not depend on someone else's quota. It is also the offline-venue path. It is not the quality ceiling — the pools put cloud routes first for reasoning tasks and local first for conversational ones.

**13. What happens when context exceeds the model limit?**
Pre-flight: the script-aware estimator rejects candidates whose window is too small; if none fits, `ContextWindowExceeded` → 413 **before any call** (tournament E asserts zero adapter calls). At attempt time, if every route reports a context error the same exception is raised. Nothing is ever truncated to fit.

**14. How do you prevent silent degradation?**
Structurally: quality is not a `FailureKind` (test-enforced), so the router has no code path that "falls back because the answer was bad"; templates carry `source`/`fallback_reason` markers the UI renders as "Template — not AI-generated"; provenance is written in a `finally` block, failures included.

**15. How do you prove routing improves the system?**
Availability: yes — fallback and explicit-failure behaviour are tested and observed live (2/8 free-pool requests fell back to local in the stored run). Quality preservation: **a first, small measurement** — identity retention 16/16 across three real models, zero budget overspend, cross-route agreement 0.41 vs cross-persona baseline 0.36 (ratio 1.15). The CIs overlap; we do not claim significance. Cost, latency and UX improvements are supported by design and logs, not by a controlled study.

**16. How reproducible are your experiments?**
Offline pipeline checks are deterministic (`--fake`, seeded, CI-tested). Real runs are reproducible in procedure (`scripts/run_cross_route_eval.py … --seed 42`) but not in output: free providers drift, temperature 0 is not deterministic across vendors. Every artifact stores the raw answers and per-answer provenance so a reviewer can re-score them.

**17. How much does the system actually cost?**
$0 in API spend by design: keyless freellmpool providers, OpenRouter free models only (the paid `openrouter/auto` default was removed), local Ollama. There is no cost ledger artifact; the quota ledger tracks request counts per provider per day.

**18. What happens at 100 concurrent users?**
It degrades explicitly, not silently: per-pool semaphores (2–5 concurrent per pool) queue requests; free-tier caps trigger provider-level cooldowns; the local model serialises. A test drives 20 concurrent generations successfully; 100 real users would mostly wait and see honest latency. We have not load-tested at that scale and say so.

**19. What happens if a provider changes its API?**
Only `bebshax/llm/adapters/` may import provider SDKs (AST-enforced). freellmpool absorbs most provider churn; an adapter failure becomes a classified `FailureKind` and the route cools down; our own bug becomes `INTERNAL_ERROR` and surfaces instead of being swallowed.

**20. Why is this better than an ordinary RAG system?**
RAG retrieves; it does not decide what may be asserted. BebshaX enforces provenance classes on every claim, detects contested evidence, remembers only the persona's own statements, and evaluates consistency across models. RAG is one component (evidence retrieval), not the system.

**21. Why is this better than a normal multi-model router?**
A generic router optimises cost/latency and may truncate or retry on "bad output". Ours refuses to truncate, refuses to treat quality as a routing signal, cools down at the right scope, records estimate/params/ranker decisions in provenance, and exposes all of it — because the research question is about *preserving* persona quality, not just serving tokens.

**22. Why should anyone trust a synthetic persona?**
They shouldn't, blindly — and the product says so at Step 5. Trust is scoped: an OBSERVED claim links to the evidence record; INFERRED and SYNTHETIC are labelled; grounding is a ratio computed from real evidence, never a default. Personas are for generating hypotheses to test with real people.

**23. What are the limitations?**
Small evaluation n; hash-based embeddings by default (offline, stable, weak semantics); LLM judging only for one gate; no human validation; free-tier latency (up to minutes); single-process locks/lockouts; provenance from the eval script is not written to the DB; datasets are English-centric slices; the demo evidence corpus is US product reviews labelled as such.

**24. What ethical risks exist?**
Mistaking synthetic signals for real user research; personas inheriting dataset biases; researchers over-trusting fluent output; free-tier providers that train on prompts (we send only synthetic data, never PII). Mitigations: explicit provenance, "validate with real customers" card, no PII ingestion rule, no fine-tuning, honest limitation notes in every report.

**25. What happens when the synthetic persona is wrong?**
It is wrong visibly: the claim is INFERRED/SYNTHETIC, the identity-drift or contradiction chip appears on the turn, the grounding ratio is low, and the report tells the researcher what to validate. What we cannot do is know it is wrong when the evidence itself is wrong — which is why sources are cited and conflicts are flagged rather than resolved by fiat.
