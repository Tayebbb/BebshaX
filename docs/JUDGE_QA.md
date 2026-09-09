# Judge Q&A — the hardest questions and honest answers (2026-09-07)

> Written from the implementation, not the pitch. Where a claim is not backed by an artifact it says so. See [RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md) for the classification of every number.

Persona ML answers refreshed 2026-09-09. Older dated routing experiments retain
their original scope; seven later provider smoke responses are not a new
success-rate or cross-route benchmark. Original phase dates are unchanged.

**1. Why does BebshaX need multiple models?**
Because the project has a $0 API budget and free tiers are individually unreliable (429s, daily caps, outages, 30–120 s queues). No single free endpoint can sustain a research workflow; the union of 18 keyless/free providers plus a local model can. Multiple models are a **capacity** answer, not a quality one — we never claim a weaker model answers better.

**2. Why not simply use one strong model?**
We would, if it were free and always up. The local `llama3.2:3b` is the always-available floor (4 GB VRAM ceiling); the free pool raises quality and speed when it is reachable. The system's job is to make that switch safe: identity card immutable, context never truncated, provenance recorded, explicit failure otherwise.

**3. What exactly is being routed?**
An `LLMRequest` with a declared `TaskType` (18 fixed kinds). Task → pool (7 pools, a data table) → candidate routes in preference order → pre-flight filter (capabilities, estimated context, cooldowns) → attempt loop governed by a closed `FailureKind` policy table → fallback across adapters → `ProvenanceRecord`. The router never inspects answer quality.

The four production persona-generation paths do not enter this router: they
use `MLPersonaAdapter`. Copilot context/role suggestions, interviews, and other
LLM features are unchanged; legacy persona task enums remain for compatibility.

**4. What is the actual research contribution?**
An engineering-plus-measurement contribution: governed LLM routing with explicit failures and provenance; code-enforced claim provenance; and scoped persona/route evaluations. The maintenance continuation adds genuinely fitted TF-IDF/NMF vocabulary, IDF, topics, and profile representations with diversity-aware source selection. It is not a new foundation model or learned router, and it selects source prototypes rather than inventing identities.

**5. What is novel?**
The combination is unusual: provenance enforcement that can only downgrade, a closed failure taxonomy where quality is not a failure, memory items labelled by source so a researcher cannot author the persona's "recollections", prompt-injection defense applied to every untrusted field, and a Judge Lab that runs failure drills through the production router. Individually each is known good practice; as a whole system for synthetic-user research on free capacity it is, to our knowledge, not available off the shelf.

**6. How do you measure persona quality?**
Separate layers: ML structural/provenance checks, held-out cross-view retrieval, and existing interview/routing metrics. The selected NMF blend's test MRR is 0.432654 versus lexical TF-IDF 0.751621: it underperforms. All 160 probe profiles passed structural checks, but 72/160 were `not_in_workforce`. No real business-labelled relevance, human panel, population-validity, or demand evaluation exists. Historical LLM judging carries its own small-sample and judge-overlap caveats.

**7. How do you know personas resemble real users?**
We do not know that they do. The selector uses USA-only synthetic NVIDIA source profiles. Role/location are soft hints; a student prompt does not turn an adult into a student or move them to Bangladesh. Source occupation/location is preserved, age bounds are hard within 18–95, and missing income/budget/OCEAN stays unknown. These profiles generate hypotheses for real research, not validated customer identities.

**8. How do you prevent hallucination?**
ML generation does not ask an LLM to invent attributes: it preserves complete source bundles, with all claims `SYNTHETIC`, empty observed citations, and zero observed grounding. Source reuse is intentional, not a truth guarantee. The separate evidence pipeline checks citations and contested claims; interview fluency and retrieval scores must not be presented as customer evidence or purchase confidence.

**9. How do you handle contradictory evidence?**
`contested_slots` detects disjoint numeric values (age always; price/count when the claim asserts them) across the sources a claim cites → the claim is INFERRED with `grounding_basis = contested_evidence` and the persona carries `contested:age`. Tournament F tests it end to end; the Judge Lab `evidence_conflict` scenario shows it live.

**10. How do you prevent prompt injection?**
Every researcher/document/dataset/memory field is wrapped in an `<UNTRUSTED_*>` block whose closing tag cannot be forged from inside (case/whitespace variants neutralised), and every system prompt carries the rule that such blocks are data. Transcripts are passed as JSON rows. The identity card is placed first and is byte-identical per turn. Tournament D and the Judge Lab `prompt_injection` scenario demonstrate it. It is a defense-in-depth measure, not a proof — a sufficiently compliant model could still be talked into odd behaviour, which is why drift is also **detected** after the fact.

**11. What happens when every provider fails?**
`AllCandidatesFailed` → HTTP 503 with `error_code = all_candidates_failed`, the LLM request id, every attempt with its `FailureKind`, and the routing path. No turn is written, no template answer is produced (tournament C). The UI shows the classified reason and a copyable request id.

ML failures are independent: 503 `ml_persona_unavailable` for missing/invalid
artifacts, 422 `ml_persona_unsupported_context` for unsupported/exhausted selection.
Neither causes LLM persona fallback. A multi-role response may retain successful
roles and list `failed_roles`.

**12. Why is Ollama necessary?**
It is the availability floor: the only route that does not depend on someone else's quota. It is also the offline-venue path. It is not the quality ceiling — the pools put cloud routes first for reasoning tasks and local first for conversational ones.

**13. What happens when context exceeds the model limit?**
Pre-flight: the script-aware estimator rejects candidates whose window is too small; if none fits, `ContextWindowExceeded` → 413 **before any call** (tournament E asserts zero adapter calls). At attempt time, if every route reports a context error the same exception is raised. Nothing is ever truncated to fit.

**14. How do you prevent silent degradation?**
Quality is not a `FailureKind` (test-enforced), so it never causes infrastructure fallback. LLM attempts carry provenance. ML selection either preserves a complete supported source batch or fails; no template/skeleton/LLM fills gaps. Full source narratives are retained, and feature filtering is not claimed as complete PII removal or demographic neutrality.

**15. How do you prove routing improves the system?**
The historical 2026-09-07 evidence record reports 2/8 free-pool requests falling back locally, identity retention 16/16 across three real models, zero budget overspend, and agreement 0.41 versus cross-persona 0.36 (ratio 1.15). The CIs overlap; no significance is claimed. These are not evaluations of the new ML personas. The continuation's seven successful Freellmpool responses are a separate smoke sample, not a reliability estimate or controlled cost/UX study.

**16. How reproducible are your experiments?**
Offline pipeline checks are deterministic (`--fake`, seeded, CI-tested). Real runs are reproducible in procedure (`scripts/run_cross_route_eval.py … --seed 42`) but not in output: free providers drift, temperature 0 is not deterministic across vendors. Every artifact stores the raw answers and per-answer provenance so a reviewer can re-score them.

**17. How much does the system actually cost?**
$0 in API spend by design: keyless freellmpool providers, OpenRouter free models only (the paid `openrouter/auto` default was removed), local Ollama. There is no cost ledger artifact; the quota ledger tracks request counts per provider per day.

**18. What happens at 100 concurrent users?**
We have not load-tested that scale. LLM pools use concurrency limits; ML inference is bounded separately. The old 20-generation acceptance test predates this selector and is not a cross-process identity guarantee. Sequential owner-scoped source exclusions exist, but independent overlapping requests have no transactional uniqueness lock. End-to-end capacity remains unvalidated.

**19. What happens if a provider changes its API?**
Only `bebshax/llm/adapters/` may import provider SDKs (AST-enforced). freellmpool absorbs most provider churn; an adapter failure becomes a classified `FailureKind` and the route cools down; our own bug becomes `INTERNAL_ERROR` and surfaces instead of being swallowed.

**20. Why is this better than an ordinary RAG system?**
RAG retrieves; it does not decide what may be asserted. BebshaX enforces provenance classes on every claim, detects contested evidence, remembers only the persona's own statements, and evaluates consistency across models. RAG is one component (evidence retrieval), not the system.

**21. Why is this better than a normal multi-model router?**
A generic router optimises cost/latency and may truncate or retry on "bad output". Ours refuses to truncate, refuses to treat quality as a routing signal, cools down at the right scope, records estimate/params/ranker decisions in provenance, and exposes all of it — because the research question is about _preserving_ persona quality, not just serving tokens.

**22. Why should anyone trust a synthetic persona?**
They shouldn't, blindly — and the product says so at Step 5. Trust is scoped: an OBSERVED claim links to the evidence record; INFERRED and SYNTHETIC are labelled; grounding is a ratio computed from real evidence, never a default. Personas are for generating hypotheses to test with real people.

**23. What are the limitations?**
USA-only synthetic coverage, weak student/geographic fit, selection bias, and an NMF blend that loses to lexical TF-IDF. No customer-demand or learned purchasing/OCEAN claims. Hash embeddings, provider latency, process-local constraints, and small LLM evaluation samples remain. Desktop passed before upstream styling, but mobile persona-header clipping remains unfixed and was not reverified after styling or the token-only correction. Full Compose app/web and cross-conversation retrieval rehearsals were not repeated; Pyright was unavailable. Passing local checks is not a production-readiness verdict.

**24. What ethical risks exist?**
Mistaking synthetic signals for real research, inheriting corpus/protected-trait biases, and over-trusting fluent interviews. R9 permits only reviewed public synthetic data for non-LLM training (owner-approved 2026-09-08); private studies/uploads/conversations are excluded, and LLM fine-tuning is still forbidden. Attribution and synthetic labels are mandatory. Filtering selected fields/contact text is not proof that narratives are PII-free or unbiased.

**25. What happens when the synthetic persona is wrong?**
Synthetic labels and warnings expose the evidence limit, not every factual error. Structural checks cannot determine whether an upstream narrative is true or a selected profile suits a business. Researchers must test hypotheses with real people; no UI chip or zero-grounding score makes a persona reliable.

**26. What was trained, and how fast is it?**
Six thousand pinned NVIDIA Nemotron-Personas-USA rows (CC-BY-4.0) became 3,594 complete unique profiles, split 2,516/539/539 with seed 42. Four 16/32-topic × 0.35/0.7 lexical-weight fits took 43.70 s on two CPU threads. Warm five-profile p95 was 34.3 ms, excluding cold loading, API, DB, and network. The ignored ~32.54 MiB artifact requires exact pinned numerical versions; see [MODEL_CARD.md](../ml_persona/MODEL_CARD.md).

**27. What was checked live after ML integration?**
Five unique age-bounded profiles persisted/read back with 22 synthetic claims reported and zero LLM generation calls. Seven Freellmpool responses covered context, ten role suggestions, and two interview turns with four 384-dimensional memories. Linux loaded the Windows artifact and selected five profiles with networking disabled. The cloud DB was untouched. These earlier live checks were not repeated after sync. The [post-sync local checks](../ml_persona/IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09) passed at the documented scopes; commit, push, and CI results are tracked separately in the [implementation log](IMPLEMENTATION_PLAN.md), not implied by local passes.
