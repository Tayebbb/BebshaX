# Competition Audit — BebshaX vs a hostile national-level jury (2026-09-07)

> Method: fresh repository audit (git `020238c`, clean tree) → eight parallel red-team tracks (AI/persona, routing, backend/DB, security, frontend/UX, testing, research validity, demo/DevOps) → six implementation groups + an independent wiring review → end-to-end tournaments → live smoke against a from-zero-migrated PostgreSQL → a real cross-route evaluation run. Every finding below was **reproduced** before it was fixed; every fix has a regression test. Numbers are from this repository, not estimates.

## Executive verdict

```
COMPETITIVE BUT VULNERABLE
Score: 73 / 100
```

BebshaX is a real, tested, evidence-grounded system with an unusually honest failure model. Its main vulnerability in front of a national jury is **evidence volume for the research claim**: the quality-preservation-across-routing measurement now exists and is real, but at n = 16 answers it shows direction, not significance. A jury will also probe the thin evidence corpus behind the demo persona and the fact that secrets committed by a teammate on 2026-09-01 still live in git history until rotated.

## Score (every deduction cited)

| Category                            | Weight  | Score  | Why not full marks                                                                                                                                                                                                                                                 |
| ----------------------------------- | ------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Problem & Innovation                | 15      | 11     | Problem is sharp (zero-budget synthetic research); innovation is a rigorous **combination** (provenance enforcement + honest routing + judge lab), not a new algorithm                                                                                             |
| AI/ML Technical Depth               | 20      | 14     | Enforced provenance classes, source-labelled memory, deterministic drift/contradiction/conflict detectors, cross-route metric — but default embeddings are hash-based (`local-hash-384`), no learned component, LLM judging limited to one gate                    |
| Persona & Evidence Quality          | 15      | 10     | Grounding gate is lexical; demo persona's OBSERVED evidence is US office-product reviews labelled as such (`EVIDENCE_SCOPE_NOTE`); no repetition/diversity metric                                                                                                  |
| Routing / Infrastructure Innovation | 10      | 8      | Closed taxonomy, provider-scope cooldowns, script-aware estimator, `INTERNAL_ERROR` surfacing, estimate/params/ranker markers in provenance; still no persisted provenance from the eval script, quota table has two sources of truth (providers.toml vs quota.py) |
| Research / Evaluation Validity      | 10      | 6      | Real artifact exists ([RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md)) but n = 2 personas × 4 questions; CIs overlap; offline benchmark replay found unusable and withdrawn; three judged-gate runs at n = 1                                                          |
| Software Engineering                | 10      | 9      | 860+ backend tests / 247 frontend tests / migrations from zero verified on pgvector / lint clean / error envelope with request ids; pyright debt (79 errors, advisory)                                                                                             |
| Security & Reliability              | 10      | 7      | Pre-hijack, OTP, SSRF-rebind, body cap, limits, redaction fixed; **remaining:** PBKDF2 at 100k iterations (test-pinned), in-process lockouts/locks, leaked secrets in history awaiting rotation, `pip-audit` advisory only (baseline 0 vulns)                      |
| UX / Demo Quality                   | 5       | 4      | Judge Lab, provenance timeline, evaluation card, memory disclosure, template labels shipped; not re-verified in a browser during this pass (tests + build only)                                                                                                    |
| Presentation / Explainability       | 5       | 4      | Docs now match code; volume is large — a jury needs the 5-minute path (below), not the corpus                                                                                                                                                                      |
| **Total**                           | **100** | **73** |                                                                                                                                                                                                                                                                    |

## Top strengths

1. **Nothing is faked when infrastructure fails.** Total failure → 503 with every attempt classified, zero turns written, no template answer (tournament C, live smoke). Context overflow refuses before any call and proves it (`adapter.calls == []`).
2. **Provenance can only be downgraded.** OBSERVED requires a shown citation **and** lexical grounding **and** no identity conflict; confidences derive from citations; templates carry `source`/`fallback_reason` and render as "not AI-generated".
3. **Judge Lab.** Seven scripted drills run through the production router code (throwaway `PoolRouter`, `FakeAdapter`, never the app's router or sink) and show REQUEST → ROUTING → FAILURE → CLASSIFICATION → FALLBACK → PROVENANCE on demand.
4. **Memory that cannot be poisoned by the interviewer.** Source-labelled items; researcher text never rendered as recollection, never reflected, never listed by default; dedupe; relevance floor.
5. **Engineering discipline.** Error envelope + `X-Request-ID` on every response; migrations from zero → single head verified on pgvector; from-scratch demo seed with no fabricated provenance; CI gates lint, coverage, migrations, frontend, gitleaks.

## Top weaknesses

1. Research evidence is small-n (see score table). The pipeline is ready; the runs are not.
2. Evidence corpus for the flagship demo persona is a US review slice; Bangladesh-context corpora are illustrative or absent.
3. Free-tier latency is real: 0.7–6 s on the pool, up to 26 s on a cold local model, 30–120 s historically on some routes — the UI is honest about it, the experience is still slow.
4. Secrets committed on 2026-09-01 remain in git history (source scrubbed). **Rotation is a human action still outstanding.**
5. Default embeddings are hash-based; semantic retrieval quality is deliberately traded for offline determinism.

## Critical vulnerabilities found (all fixed unless marked)

| Severity | Finding                                                                                                                 | Fix                                                                                |
| -------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| CRITICAL | Copilot keyword-template replies rendered as AI; a template goal card could be approved                                 | `served_by`/`fallback_reason` read; amber "Template reply" chip; approval disabled |
| HIGH     | Interview system prompt interpolated study goal/objective/segment **undelimited** → identity override via a study field | every field in `<UNTRUSTED_*>` blocks + identity rule (prompt_safety)              |
| HIGH     | Interviewer messages stored as persona memory (poisoning + forgery)                                                     | `source` column, filtered retrieval/reflection/listing, dedupe, floor              |
| HIGH     | Account pre-hijack: signup unverified → victim's Neon sign-in linked to attacker's password                             | password revoked on link                                                           |
| HIGH     | Concurrent turns duplicated turn numbers                                                                                | per-conversation lock + `MAX(turn_number)` + DB unique constraint                  |
| HIGH     | Estimator under-counted Bangla → local model silently dropped history (R2)                                              | script-aware shared estimator; `num_ctx ≥ estimate`                                |
| HIGH     | Quota ranker demoted a provider after one request                                                                       | bucketed demotion, local pinned                                                    |
| HIGH     | Anonymous GET spent real OpenRouter calls                                                                               | config-only GET                                                                    |
| HIGH     | `/behavioral-tests/compare` shadowed → feature dead                                                                     | route order + generic shadow test                                                  |
| HIGH     | Seeded provenance row fabricated; demo case incoherent (US fintech persona in BDT study)                                | seed rewritten (ShomoySuchi / Nusrat Jahan), no `llm_requests` rows                |
| HIGH     | No request id / error envelope; 500s leaked `text/plain`                                                                | envelope + middleware (inside CORS)                                                |
| HIGH     | Study delete orphaned personas/conversations                                                                            | metadata-driven cascade                                                            |
| MEDIUM   | OTP global lookup, no invalidation, no lockout                                                                          | scoped, invalidated, 5-strike lockout                                              |
| MEDIUM   | `INTERNAL_ERROR` never stamped; bugs became template personas                                                           | stamped + surfaced; generator re-raises                                            |
| MEDIUM   | Offline benchmark "100 % alignment" was a tautology                                                                     | evaluator reports `unusable`; docs withdrawn                                       |
| MEDIUM   | Constant `avg_tokens_per_sec = 120.5` in eval artifacts                                                                 | `null`                                                                             |
| MEDIUM   | Judge model overlapped arm B                                                                                            | judge disjointness enforced                                                        |
| MEDIUM   | Contradiction detector false positives on restated budgets (found in the real run)                                      | budget restatement excluded; regression test                                       |
| MEDIUM   | Cross-route agreement paired by requested route (would count within-model repeatability)                                | pairs by served route; `None` when one route served                                |
| **OPEN** | Leaked secrets in git history                                                                                           | **human: rotate Neon/Resend/Brevo/gmail creds**                                    |
| **OPEN** | PBKDF2 100 000 iterations                                                                                               | flip to 600 000 once `tests/test_auth.py` pin is relaxed                           |

## AI quality findings

- Identity card immutable per turn (test-enforced, tournament G over 20 turns with attacks).
- Deterministic drift + contradiction flags now exposed on every turn payload and rendered as chips (quality signals, never infra failures).
- Real cross-route run: identity retention 16/16 across `llama3.2:3b`, `codestral-latest` (llm7), `Llama-3.3-70B` (ovh); budget divergence 0; agreement ratio 1.15 (CIs overlap).
- Grounding gate is cheap and conservative; Bangla tokenisation fixed; claim-scoped contested slots avoid downgrading unrelated claims.

## Routing findings

- Fallback chain, cooldowns (provider scope), pre-flight CWE, attempt-time CWE, INTERNAL_ERROR surfacing, attempt budget, Ollama negative-discovery cache, ranker bucketing — all tested with `FakeAdapter`; B/C/E/H verified over HTTP.
- Live: 2/8 free-pool requests fell back to local in the same request and were recorded as not honoured.
- Remaining: quota caps duplicated between `providers.toml` and `quota.py`; OpenRouter context-compression plugin not disabled explicitly (only free models used).

## Security findings

Fixed: pre-hijack, OTP scope/lockout, body cap, limits on every LLM route + job cap, SSRF DNS-rebind pinning, provenance detail redaction, SPA security headers + CSP, envelope on 500 inside CORS, raw exception text never persisted, client-supplied study ids ignored. Open: PBKDF2 cost, secrets in history (rotate), single-process lockout counters, `pip-audit` advisory (baseline 0).

## UX findings

Shipped: template-reply labelling, request ids in every error surface, Routing & Provenance inspector (attempts timeline, skipped markers, tokens, cached), Evaluation card fed by real metrics, Judge Lab panel, memory disclosure + persona Memory tab (source-badged), consistency chips, honest "—/Not measured" for absent numbers, mock/demo banners, dialog a11y on 8 modals, enum sync (13 kinds / 18 tasks). Not done: browser screenshot verification in this pass; behavioural test-type cards still `div onClick`.

## Research validity findings

See [RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md). Verified: availability behaviour; provenance completeness; grounding semantics. Small-n verified: cross-route persona consistency. Not verified: significance, generality, human resemblance, cost savings, latency SLO.

## Judge attack results (live smoke, demo mode, from-zero PostgreSQL)

| Scenario              | Outcome               | error_code              | Steps                      |
| --------------------- | --------------------- | ----------------------- | -------------------------- |
| all_providers_down    | explicit_failure      | all_candidates_failed   | 4                          |
| context_overflow      | explicit_failure      | context_window_exceeded | 3 (all skipped pre-flight) |
| provider_429_fallback | served_after_fallback | —                       | 2                          |
| prompt_injection      | claims_downgraded     | —                       | 1                          |
| evidence_conflict     | claims_downgraded     | —                       | 1                          |

Envelope checks: 404 and 422 bodies carried `error_code` + `request_id` = `X-Request-ID`; `/api/health` reported `db=ok`; `GET /api/demo-lab/scenarios` without a token → 401.

## Fixed issues (counts)

- Backend: 6 implementation groups + integration fixes; **~120 changed files**, new migration `e1f2a3b4c5d6`, +~330 backend tests (548 → 860+), +62 frontend tests (185 → 247).
- Documentation drift corrected in 14 docs (provider counts, model names, withdrawn claims, all three gate runs).

## Remaining issues (prioritised)

1. Rotate leaked credentials; consider `git filter-repo` with the team.
2. Run the larger cross-route evaluation (`--personas 6 --questions 5 --repeats 3`) and, if possible, a disjoint-judge scoring; report CIs.
3. Bangladesh-context evidence corpus for the demo persona (or keep the labelled US slice and say so on stage).
4. PBKDF2 → 600k; lockouts/locks to DB for multi-process deployments.
5. Persist eval-script provenance to `llm_requests`; unify quota caps; disable OpenRouter context compression explicitly.
6. Real-embedding memory backend as an opt-in (`auto`) with a migration story for the embedding space.
7. Browser-level E2E (Playwright) for the 5-minute path.

## Judge questions

Twenty-five hostile questions with implementation-grounded answers: [JUDGE_QA.md](JUDGE_QA.md).

## Recommended demo sequence (5 minutes)

1. **0:00 — Problem (30 s).** Landing → "Synthetic user research with a $0 API budget": the pitch is capacity aggregation _without_ quality degradation.
2. **0:30 — Demo study.** Sign in (`founder@bebshax.ai`), open _Customer Discovery Study_ (ShomoySuchi, BDT student planner). Show Nusrat Jahan's card: `CACHED`, grounding ratio, chips.
3. **1:00 — Evidence → claim.** Click an OBSERVED chip → the exact review record (US slice, labelled). Show an INFERRED one — no evidence, said so.
4. **1:45 — Interview (live).** Ask one question; open _Recalled N memories_ and _Route_ under the reply; point at the consistency chips (none, hopefully — or one, honestly).
5. **2:45 — Routing & Provenance.** Expand the latest trace: estimate marker, attempts, served-by, tokens. Evaluation card: "computed from N logged requests".
6. **3:30 — Judge Lab.** Run `all_providers_down` (explicit failure, every attempt classified, nothing fabricated) then `context_overflow` (refused before any call — nothing truncated). Optionally `prompt_injection`.
7. **4:30 — Honesty close.** Step 5 "Validate with real customers next" + the cross-route artifact: 16/16 identity retention across three real models, ratio 1.15, "n is small and we say so".
