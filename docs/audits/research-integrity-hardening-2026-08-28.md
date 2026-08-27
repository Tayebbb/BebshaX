# Research Integrity Hardening — Final Audit Report (2026-08-28)

Companion to [research-integrity-baseline.md](research-integrity-baseline.md). Protocol: baseline → independent auditor agents → prioritized implementation → second-wave verification audit → fix round → gates. Two independent audit waves ran: Agent B+C (research integrity + persona quality, researcher agent) and a consolidated verifier covering fix verification + Agents E–I (code-reviewer agent). Agent J/K (UX/showcase) was performed live in the embedded browser. Repository state at close: all gates green (428 backend + 79 frontend tests, tsc build, theme drift 0).

## Scores

| Area | Before | After | Notes |
| --- | :-: | :-: | --- |
| Architecture | 9 | 9 | Untouched by design — no new infra, boundaries intact (R1 test-enforced) |
| Persona generation | 5 | 8 | Measured grounding, honest citations, BD-template guard; legacy engine was already solid |
| Dataset analysis | 6 | 7 | Upload security hardened (SSRF), representativeness statement added; profiler depth unchanged |
| Interview simulation | 8 | 8 | Per-turn identity composition verified; long-horizon drift eval remains a gap |
| Memory | 8 | 8 | Kinds/scoping verified, no contamination path; no turn back-reference (gap) |
| Evidence / trust | **3** | **8** | The core of this pass — see below |
| Evaluation | 7 | 8 | Grounding conflation fixed (schema-validity ≠ grounding; INFERRED+string ≠ grounded) |
| Routing | 9 | 9 | Verified against the Phase-14 acceptance matrix; no changes needed |
| Reproducibility | 7 | 7 | Pinned datasets + runs + provenance verified; prompt-version ids still missing (documented) |
| Security | 6 | 8 | SSRF redirect bypass closed, delimiter escape stripped; DNS-rebinding TOCTOU documented |
| UX | 8 | 8 | Honest-state banner, honest percentages, provenance chips; no blockers in walkthrough |
| Visual design | 9 | 9 | Untouched (established direction maintained) |
| Showcase readiness | 6 | 8 | The product now shows its uncertainty instead of decorating it |

## What the audits found (headline)

Wave-1 verdict: *"The traceability chain doesn't break — it terminates in fiction."* Six critical fabrication paths existed between the honest legacy persona engine and the UI:

1. **C1** — the curated research corpus wore real publisher brands (The Daily Star, TechRadar, Product Hunt, Reddit, Facebook) with invented statistics and fake URLs.
2. **C2** — study-path claim extraction stored model-cited evidence ids **unverified**; invalid statuses even defaulted to "supported".
3. **C3** — the deterministic claim fallback fabricated domain-specific "supported" claims at 0.88 confidence on any LLM exception, silently.
4. **C4** — the copilot prompt *instructed* the model to output `"provenance_class": "OBSERVED"` and self-scores (0.96/0.94), which were persisted verbatim with no evidence retrieval.
5. **C5** — dataset-run personas shipped with constant `grounding_score=0.92, confidence=0.88`, `evidence_citations=[]`.
6. **C6** — the template report asserted an "85% aggregate demand index" it never computed.

Plus: grounding score was "arithmetic theater" (base 0.85 + bonuses including **+0.03 for missing data**), citations were decorative (`claims[:3]` attached to every persona), the UI never rendered per-claim provenance, missing values rendered as fabricated defaults (`'88%'`, `|| 0.95`, `?? 68`, `?? 60/20/20`, `|| 0.8`), the ORM defaulted scores to 0.88/0.85 at the column level, and a US-market persona could inherit bKash habits from Bangladeshi templates.

Wave-2 additionally found: an **SSRF redirect bypass** in dataset URL fetching (validation ran only on the original URL; a 302 could reach metadata endpoints), a delimiter-escape in the behavioral engine's untrusted-scenario block, and an evaluator that granted grounding 1.0 to zero-attribute personas.

## Implemented

- **Honest evidence source labeling**: curated corpus → `BebshaX Illustrative Sample` / `source_type="curated_sample"` / internal sample URLs; SAMPLE badge in the Evidence Lab; header copy no longer claims "verified public sources".
- **Citation verification at extraction**: model-cited ids intersected with the chunks actually shown; unverifiable "supported" downgraded to "inference" with an audit note (mirrors `coerce_provenance`); unknown statuses → "inference"; LLM failures logged, never silently swallowed.
- **Deterministic fallback honesty**: hypothesis-framed claims, `inference`/`unsupported` only, confidence ≤ 0.5.
- **Copilot path**: prompt example is INFERRED-only with no self-scores; all attribute provenance forced INFERRED (no evidence shown); `grounding_score` persisted as 0.0.
- **Measured grounding**: `grounding_score = OBSERVED claims / total claims`, `confidence = (OBSERVED+INFERRED)/total`, from per-claim provenance; all bonuses deleted; "ready" status decoupled (renamed "Passed checks" in UI). Citations rebuilt from what personas actually cite. ORM + draft defaults → 0.0 with migration `b1c2d3e4f5a6` (existing rows preserved as audit trail).
- **Report honesty**: no demand index, hypothesis-framed findings, unscored pricing signals labeled as such, limitations name curated samples and require real-user validation.
- **UI truthfulness**: OBSERVED/INFERRED/SYNTHETIC chips (with explanatory tooltips) on every goal/need/pain point; all fabricated display defaults removed (`n/a`/0 instead); grounding filters re-banded to meaningful thresholds (≥50% observed / >0%); "Showing sample data — backend unreachable" banner when mock fixtures serve; methodology lines ("synthetic participants — hypotheses to validate with real users") in the persona library, report note, and generated DATASETS.md (§ Coverage & Representativeness).
- **Security**: dataset fetches no longer follow redirects (each hop would evade IP validation); `</UNTRUSTED_SCENARIO>` stripped from untrusted behavioral scenario text.
- **Evaluator**: grounding counts only evidence-cited OBSERVED attributes; zero attributes = 0.0, never 1.0.
- **Tests**: 5 new/updated modules — `test_claim_extractor.py` (4 tests: downgrade, intersection, unknown-status, deterministic honesty), validator ratio tests, template-draft honesty assertions, evidence-lifecycle contract updated to the honest statuses.

## Already existed and verified (left alone)

`coerce_provenance` downgrade-only enforcement; `_coerce_claim_list` alias-verified citations; SYNTHETIC-labeled template fallbacks with honest model labels; dataset role table excluding synthetic corpora from citable evidence; one-refinement budget with explicit failure; infra failures never template-ized; `data_source` live/cached labeling; per-turn identity composition (byte-identical, test-enforced); memory scoping by persona + embedding space; infra/quality separation in the failure taxonomy; SSRF IP-range validation, size caps, safe parsers; pinned dataset revisions + checksums; `PersonaGenerationRuns` snapshots; complete LLM provenance.

## Rejected as unnecessary (with reasons)

- **Inline NLI/entailment claim verification** — an ML judge in the request path violates the lean-infrastructure rule (R10); citation-existence + downgrade-only is the declared, test-enforced contract. Belongs offline in Phase-11 evaluation if ever.
- **Calibrated numeric per-claim confidence** — no calibration data exists; would swap one decorative number for another. The three-class provenance system is the defensible unit.
- **Removing template/skeleton fallbacks** — zero-key operation is a supported configuration; fallbacks are now honestly labeled and scored.
- **Hard grounding-score gates** — gating on the old fake metric would have institutionalized it; `needs_review` status already gates on real warnings.
- **New "low grounding" failure kinds** — R6 taxonomy is closed; low quality is not an infrastructure failure (R2).
- **UNKNOWN provenance class** — the schema's three classes plus absent-provenance (rendered as no chip) already express every state the pipeline produces; a fourth enum member would add surface without information.
- **A new Research Run abstraction** — `PersonaGenerationRuns` + `ProvenanceRecord` + pinned dataset manifest already cover run reproducibility; duplicating them fails the prompt's own §10 test.
- **Redis/queues/another vector DB/LiteLLM/LangChain** — nothing in this pass needed any of them.

## Remaining limitations (documented, not hidden)

- Legacy personas keep their pre-hardening scores (audit trail); regenerate to get measured scores.
- No prompt-version identifiers on generation/interview/evaluation prompts (reproducibility gap; prompt text is recoverable from git history).
- No automated 20+-turn identity-drift evaluation (5-turn live cross-provider consistency verified manually 2026-08-23).
- Memory items lack a conversation/turn back-reference; retrieval is Python-scored full scan, not pgvector ANN (scale, not integrity).
- DNS-rebinding TOCTOU between URL validation and fetch (low likelihood; redirect hole closed).
- `StudyReports.confidence_score` / `EvidenceClaims.confidence` column defaults (0.85/0.75) are fabrication traps if a future writer omits them — current writers all set them explicitly.
- The shared Neon database's alembic version points at `a1b2c3d4e5f6`, a revision not in this repository (a teammate's unpushed migration). Migration `b1c2d3e4f5a6` applies cleanly once that file lands; flag at next sync.
- Free-tier latency (30–190 s) unchanged; mock fixtures still show optimistic demo numbers but are now banner-labeled whenever they serve.

## Known risks

Regenerated personas will now show low grounding percentages when studies lack evidence runs — this is the truth the product previously hid; the UI explains it (chips, tooltips, filter labels) rather than apologizing for it.

## Final confidence

**8/10 — defensible showcase-ready.** Not 10/10, per protocol §20: two auditor-identified structural gaps remain open by choice (prompt versioning, long-horizon drift evals) and are documented above rather than papered over. Every critical and major finding from both audit waves is either fixed (verified by the second wave and by 428 green tests) or explicitly accepted with rationale. The product's honesty is now enforced by code and tests, not by copy.
