# Competition Audit — BebshaX vs a hostile national-level jury (2026-09-07)

> **Re-audit 2026-09-08 — "nothing pre-coded" pass: see [§ Re-audit (2026-09-08)](#re-audit-2026-09-08--nothing-pre-coded-live-ai-verified) at the end of this file for the current score.** Everything between here and that section is the 2026-09-07 baseline, kept verbatim as the record the re-audit is measured against.

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
| Software Engineering                | 10      | 9      | 865 backend tests / 247 frontend tests / migrations from zero verified on pgvector / lint clean / error envelope with request ids; pyright debt (79 errors, advisory)                                                                                             |
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

- Backend: 6 implementation groups + integration fixes; **~180 changed files**, new migration `e1f2a3b4c5d6`, +317 backend tests (548 → 865), +62 frontend tests (185 → 247).
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

---

## Re-audit (2026-09-08) — nothing pre-coded, live AI-verified

> Mission brief from the owner: _"nothing should be static, nothing pre-coded, results must vary from one study to another, verified and analysed by AI; production-ready test."_ Method: 8 read-only audit tracks over the whole codebase → every template/heuristic/default fallback removed feature by feature (each with tests) → an independent AI judge added → a **live end-to-end audit through the real API, real routes and real database** (`scripts/live_ai_audit.py`, 4 runs; each failure diagnosed from provenance and fixed before the next). Numbers below are from this repository and from `data/metadata/live_ai_audit_20260908_040247.{json,md}`.

### Verdict

```
COMPETITIVE — DYNAMIC END TO END
Score: 86 / 100   (2026-09-07 baseline: 73)
```

### What was pre-coded before this pass (all removed — see [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) § Maintenance 2026-09-08)

| Area                | Static/pre-coded behaviour found                                                                                                    | Now                                                                                                             |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Copilot             | canned replies, goal-card skeleton, hard-coded role list, template backfill of persona fields                                       | model-written or `copilot_reply_unparseable` / `roles_unparseable`; partial failures reported per role         |
| Personas            | keyword tables, domain anchors, deterministic fallback persona, `country_code` default `BD`, `"US"` example anchor in the prompt    | LLM-only, country inferred from the brief (live: `NO` for Norway, `US` for Chicago), duplicates regenerated     |
| Interview script    | fixed 5-question questionnaire seeded in the UI and used by batch interviews                                                        | model-written with provenance (`studies.script_meta`); no script → `script_required`                            |
| Research            | deterministic plans/queries/claims/report text with Bangladesh literals; curated sample corpus in production                        | Wikipedia live search, LLM-only planning/queries/claims/synthesis, `summary` per run step, ISO3 target countries |
| Datasets            | fabricated BBS/Kaggle catalogues, 100 invented CSV rows, offline fallback persona, invented constraints                              | World Bank + CKAN (HDX, data.gov) discovery, real downloads, observed-only constraints                           |
| Segmentation        | "Strategy C" with invented BDT budgets and canned segment names                                                                     | categorical grouping / quantile bands over real rows or `segmentation_requires_data`; LLM-only interpretation   |
| Behavioral          | rule-based decision heuristics, invented defaults and locale                                                                        | parameter-only simulators, `simulation_unparseable`                                                             |
| Interviews          | template synthesis, hard-coded follow-up suggestions, BDT-only consistency checks                                                   | LLM synthesis or `source:"unavailable"` + `error_code`; model-written suggestions; currency-neutral checks       |

### Live audit (real routes, real database) — 56/56 checks

Two unrelated ideas (a Norwegian sea-angling bait subscription; a Chicago piano-teacher scheduling/billing app), each run signup → study → copilot → roles → personas → script → batch interview → report → **independent AI review**:

| Evidence                                                                              | Run A (Norway bait box)                                                       | Run B (Chicago piano teachers)                                            |
| ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Roles suggested (10 / 9, all idea-specific)                                           | RECREATIONAL SEA ANGLER, LOCAL BAIT SUPPLIER, COASTAL RETIREE, WINTER ANGLER… | INDEPENDENT PIANO TEACHER, PARENT PAYOR, RECITAL COORDINATOR…             |
| Personas (country inferred, never defaulted)                                          | Magnus Halvorsen, Magnus Nordahl — `NO`                                       | Maria Chen ×2 — `US` (duplicate name → now regenerated, see below)        |
| Script specificity (Jaccard between the two scripts)                                  | 0.07                                                                          |                                                                           |
| Report summaries (Jaccard)                                                            | 0.14                                                                          |                                                                           |
| Cross-idea leakage                                                                    | none                                                                          | none                                                                      |
| AI review (dimension scores, written per study)                                       | overall 42 — grounding 20 · specificity 60 · consistency 70 · honesty 90 · actionability 75 | overall 45 — grounding 55 · specificity 60 · consistency 30 · honesty 70 · actionability 75 |
| Route attribution at every stage                                                      | `openrouter/dots-studio/dots-3-note-preview:free` (discovered live)           | same                                                                      |
| Wall clock (3-question script, 1 interview)                                           | 201 s                                                                         | 175 s                                                                     |

The judge's own findings are the honest part of this table: it flagged the empty evidence layer ("zero evidence claims recorded"), a report that generalised from one interview, and — in run B — two personas sharing a name with incompatible bios. That last finding became a fix in the same session (sibling-aware persona prompts + one regeneration of duplicate names, remaining duplicates flagged in `validation_warnings`). The evidence-layer finding is real: the audit script does not run the research step, so the judge is right that these two studies had no claims.

### What the live audit found in the routing layer (each fixed, tested, documented in [ROUTING.md](ROUTING.md))

1. All three hard-coded OpenRouter `:free` models had been delisted → 3 dead attempts + 3 cooldowns per request. **Live catalogue discovery.**
2. One 75 s freellmpool timeout benched the only keyless route → every feature failed in 0 ms for 30 s. **Half-open cooldown probe.**
3. Free reasoning models spent the whole output budget thinking and returned empty replies. **`reasoning: {enabled:false}` on routes that expose the toggle**; empty-after-reasoning failures explain themselves.
4. An upstream per-model 429 benched every OpenRouter route. **Route-scoped `MODEL_UNAVAILABLE`** for upstream-pool limits.
5. The free-tier **day cap (50 requests)** was hit after three runs and re-probed every minute. **`QUOTA_EXHAUSTED` + Retry-After / reset-timestamp-aware cooldown** (bounded to 24 h).
6. `json_object` mode forbids a top-level array, so a model returned one role object instead of the list → `roles_unparseable`. **Prompts ask for the object wrapper; `unwrap_list` recovers the list from any shape without adding content.**
7. A single transient exhaustion failed a whole background interview. **One recorded retry per turn after a pause.**
8. `docker compose --profile full up --wait` could never pass: nginx listened on IPv4 only while busybox resolved `localhost` to `::1`. **Fixed; from-zero migration to `f2a3b4c5d6e7` verified in the container.**

### Score (every change from the baseline cited)

| Category                            | Weight  | 09-07  | 09-08  | Why                                                                                                                                                                          |
| ----------------------------------- | ------- | ------ | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Problem & Innovation                | 15      | 11     | 12     | The honesty model now covers every feature (explicit coded failures, never templates) and an independent AI judge closes the loop                                             |
| AI/ML Technical Depth               | 20      | 14     | 17     | All artefacts model-written with provenance; AI review rubric; adaptive routing learned from live failures (catalogue discovery, probes, reasoning control, quota hints)       |
| Persona & Evidence Quality          | 15      | 10     | 12     | Country/currency inferred, duplicates regenerated, observed-only constraints; **still** lexical grounding and thin evidence unless the research step runs                     |
| Routing / Infrastructure Innovation | 10      | 8      | 9      | Eight live-found routing defects fixed with tests; remaining: freellmpool keyless routes are slow (75 s timeouts observed)                                                     |
| Research / Evaluation Validity      | 10      | 6      | 8      | Live end-to-end audit artefact with variability and specificity checks (n = 2 ideas, 4 runs); cross-route study unchanged (still small-n)                                     |
| Software Engineering                | 10      | 9      | 9      | 929 backend tests / 249 frontend tests, migration from zero verified in compose, lint clean; pyright debt unchanged                                                           |
| Security & Reliability              | 10      | 7      | 8      | Compose health fixed, quota-aware cooldowns, batch retry; leaked-secret rotation is **still** a pending human action                                                           |
| UX / Demo Quality                   | 5       | 4      | 5      | No seeded questionnaire, partial-failure notices, observed-fact segmentation, AI review card; verified by tests and build (not by a browser session in this pass)              |
| Presentation / Explainability       | 5       | 4      | 4      | Docs match code; the corpus is larger again — use the 5-minute path                                                                                                          |
| **Total**                           | **100** | **73** | **86** |                                                                                                                                                                              |

### Remaining issues (prioritised, honest)

1. **Free-tier capacity is the exhibition risk, not the code.** OpenRouter's key allows 50 free requests/day (one full study ≈ 15–20 calls); keyless freellmpool routes timed out at 75 s several times. Run Ollama (`llama3.2:3b`) at the venue so `conversation`/`fast` pools always have a local route, and treat OpenRouter as a bonus.
2. Rotate the credentials leaked on 2026-09-01 (unchanged, human action).
3. The AI judge is right that studies without the research step have no evidence claims — run research before personas in the demo, or say so on stage.
4. Cross-route evaluation is still small-n; the live audit adds variability evidence, not statistical power.
5. Browser-level E2E for the 5-minute path is still missing.
