# BebshaX — Audit Remediation Assignments

> Companion to [E2E_AUDIT_2026-08-24.md](E2E_AUDIT_2026-08-24.md), which holds the full evidence for every finding.
> **This file says who fixes what. The audit says what is broken. Neither replaces the other.**
> Every one of the 41 findings appears here exactly once. Nothing is unassigned.

---

## How to update your status

1. Fix the finding.
2. Tick your box **here** and tick the matching box in the audit — in the **same commit as the fix**.
3. Add a dated entry to the audit's **Fix log** with the evidence that proved it (command output, test name — not "done").
4. Add a `### Maintenance (<date>)` entry to [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), per [AGENTS.md](../AGENTS.md).

**Nobody edits or unticks another person's finding.** Append-only, same discipline as the implementation log.

A finding is **not done** until a test fails without your fix. B1 exists precisely because `test_sink.py` never called the function it claimed to cover.

---

## Blocking decision — assign these two directories before anyone starts

`bebshax/api/**` and `bebshax/auth/**` have **no owner** in [TEAM_ASSIGNMENTS.md](TEAM_ASSIGNMENTS.md). That is not a coincidence — it is where every blocker came from. The auth feature shipped with a hardcoded secret, an unverified identity endpoint, an unapplied migration and no implementation-log entry, because no one was reviewing it.

| Directory                            | Proposed owner | Rationale                                                                                                                                       |
| ------------------------------------ | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `bebshax/auth/**` + `api/auth.py`    | **Sazid**      | The `users` table and its migration are already in his alembic territory; B6 (tenancy columns) is his. B3/B4/B6 become one coherent workstream. |
| `bebshax/api/**` (except evaluation) | **Tayeb**      | Every endpoint is a thin surface over an engine he built — routing, persona, interview.                                                         |
| `api/evaluation.py`                  | **Shehab**     | His Phase 11.                                                                                                                                   |

- [ ] All three have agreed to the ownership table above, and [TEAM_ASSIGNMENTS.md](TEAM_ASSIGNMENTS.md) has been updated to match.

---

## Progress

| Owner             | Assigned | Done |
| ----------------- | -------: | ---: |
| Joint (all three) |        5 |    0 |
| Tayeb | 8 | 8 |
| Sazid | 11 | 6 |
| Shehab | 16 | 16 |
| Already closed | 1 | 1 |
| **Total** | **41** | **31** |

🔴 = blocker · 🟠 = high · 🟡 = medium · ⚪ = low

---

## ⚠️ Joint — one session, all three, nobody touches these alone

These are contract changes. Merge rule 4 in [TEAM_ASSIGNMENTS.md](TEAM_ASSIGNMENTS.md) requires agreement from all three on anything in `types.py`, `provenance.py`, `failures.py`, `adapters/base.py` or `API_CONTRACT.md`. Two people fixing these independently will collide on the interfaces the whole parallel plan depends on.

Decide in this order, in one sitting:

- [ ] 🔴 **B2** — Canonical persona shape. Nested `demographics` or flat? One answer, then align `persona/schema.py` (Tayeb), `API_CONTRACT.md` + `types/index.ts` + `AppModal.tsx` (Shehab). Add an `ErrorBoundary` while you are in there.
- [ ] 🟠 **H4** — Canonical `FailureKind` names. Backend has 14, the contract declares 10, and `RATE_LIMITED` ≠ `RATE_LIMIT`. Align the contract to the code, not the reverse.
- [ ] 🟠 **H5** — Error envelope `{detail, error_code, request_id}`. Decide the shape together; Tayeb implements it in `api/**`.
- [ ] 🟡 **M10** — Kill the dual-shape message response. One endpoint, one contract.
- [ ] ⚪ **L13** — Docs drift. Each person fixes their own sections; Tayeb assembles the final pass.

**Exit criterion for this session:** a contract-parity test exists that fails when backend and frontend shapes drift again. Without it, B2 comes straight back.

---

## Tayeb — LLM infrastructure, `api/**`, repo-wide gates (8)

- [x] 🟠 **H2** — Ollama is unreachable, so the local fallback tier and the offline drill are both dead. `EMERGENCY_FALLBACK` currently has no route at all. → `llm/adapters/ollama_adapter.py` + ops — **DONE 2026-08-26** (daemon up + smoke OK + startup warning `warn_if_local_tier_down`; see audit fix log)
- [x] 🟡 **M2** — `/api/routes/status` fabricates: `active_requests` hardcoded `0`, `max(count, 1)` hides empty pools, provider `type` guessed by substring match, and it reaches into the router's private `_cooling_reason`. → `api/routes.py` — **DONE 2026-08-26** (public `pool_utilization()`/`is_cooling()` on PoolRouter; measured counts; registry-table types; 4 tests)
- [x] 🟡 **M4** — Interview responses hardcode `latency_ms: 750` and invent `retrieved_memories` placeholder strings instead of the memories actually retrieved. The memory feature's only UI surface is fake. → `api/interviews.py` — **DONE 2026-08-26** (engine returns real values; API fabricated fallbacks removed; e2e asserts real latency/route/memories)
- [x] 🟡 **M5** — `industry`/`target_market` stuffed into the description string and re-parsed with `desc.startswith("Industry:")`. Any description starting with "Industry:" corrupts. Needs real columns — coordinate the migration with Sazid. → `api/personas.py` — **DONE 2026-08-26** (columns + migration `c4d5e6f7a8b9` with legacy-data extraction; **Sazid: please review the migration** — it touches your alembic territory, applied at owner instruction)
- [x] 🟡 **M6** — `CORS allow_origins=["*"]` together with `allow_credentials=True` — invalid per spec and unsafe. → `main.py` — **DONE 2026-08-26** (explicit origins via `BEBSHAX_CORS_ORIGINS`, 3 tests; see audit fix log)
- [x] 🟡 **M9** — Memories for a non-existent persona return `200 []` instead of `404`; a missing `memory_service` returns the same, so the two are indistinguishable. → `api/personas.py` — **DONE 2026-08-26** (404 for unknown persona, 503 for missing service; 2 tests)
- [x] 🟡 **M11** — CI has no lint, no standalone type-check, **no secret scan** (would have caught B4), no migration-drift check (H6), no coverage floor, and `--if-present` silently passes when a script disappears. → `.github/workflows/ci.yml` — **DONE 2026-08-26** (5 jobs; gitleaks allowlists ONLY the burned B4 literal until Sazid's fix; drift job covers H6's CI half)
- [x] ⚪ **L12** — Cross-provider reply-format drift: one free model answered in Markdown persona-script form while others used plain first person. Correctly not an infra failure per R2/D3, but an open Phase-11 normalisation gap. → `interview/` composition — **DONE 2026-08-26** (deterministic `normalize_reply` — think-blocks/fences/speaker labels only, content untouched; 11 tests)

---

## Sazid — data layer + auth (11)

**Do B3 and B4 first, today. Nothing else on anyone's list starts until they are closed** — the repo is public and these are live account takeover.

- [x] 🔴 **B3** — `/api/auth/google` accepts a `credential` field and never validates it; it trusts the client-supplied `email`. Anyone who knows a user's email owns that account, and an empty body logs you in as `google.user@example.com`. Verify the Google token properly or delete the endpoint. → `api/auth.py` — **DONE 2026-08-26** (Part 1: deleted unverified `/api/auth/google` endpoint, tests in `test_auth_google_removed.py`; Part 2: `/api/auth/sync` now requires and verifies real Neon session token server-side against Neon `/get-session`, client-supplied email rejected from lookup, tests in `test_auth_sync_verification.py`; frontend diffs for `api.ts`, `AuthPage.tsx`, `AuthModal.tsx` handed off to Shehab)

- [x] 🔴 **B4** — `JWT_SECRET` is a string literal in source on a public repo; a forged token was accepted by `/auth/me`. Move to `Settings` + `.env` with a startup check that fails fast, and add `iss`/`aud` validation. **The new secret must be genuinely new — the old one is in git history and is permanently burned.** → `auth/security.py`, `config.py` — **DONE 2026-08-26** (`config.py` fail-fast validation, `security.py` iss/aud + dual-key rotation, 8 regression tests in `test_jwt_secret.py`)
- [x] 🔴 **B1** — 100 % silent provenance loss. `ProvenanceRecord.task` is a `str` but the sink calls `r.task.value`; the `AttributeError` is swallowed, and the log guard `total_db_errors % 100 == 0` hides the first 99 failures. Fix is `str(r.task)` **plus** logging the first error **plus** a round-trip test asserting `total_written == 1`. → `db/sink.py`, `tests/db/test_sink.py` — **DONE 2026-08-26** (by Tayeb's agent at owner instruction; also fixed a second serialization bug — see audit fix log)
- [~] 🔴 **B6** — `Businesses` and `Personas` have no `owner_id`, so tenancy is impossible even if auth were added. Add the columns + migration; Tayeb wires `Depends(get_current_user)` row scoping in `api/**`. → `db/models.py` + migration — **Stage 1 landed 2026-08-26** (nullable `owner_id` columns + FKs on `businesses`/`personas` + migration `8d648b892fd3`, 6 tests in `test_owner_id.py`); Stage 2 gated on B4 prod deployment.
- [~] 🟠 **H3** — Demo mode is unimplemented but marked ✅. The flag is only echoed by `/api/health`; `seed_demo_data` runs unconditionally regardless of it; nothing is labelled `"cached"`; `docs/DEMO.md` does not exist. → `config.py`, `db/seed.py`, new `docs/DEMO.md` — **Pieces 1 & 3 landed 2026-08-26** (`seed_demo_data` gated behind `demo_mode`, 3 tests in `test_seed_demo_mode.py`; `docs/DEMO.md` created, `PROJECT_CONTEXT.md` corrected; Piece 2 cached labeling pending Shehab UI)

- [x] 🟠 **H6** — Migration drift. The local DB was brought to head on 2026-08-24, but **no CI guard exists**, so `/api/auth/*` still 500s on every other machine until each person runs the upgrade manually. Add `alembic current == heads` or fail. → CI + alembic — **DONE 2026-08-26** (CI guard in `ci.yml` + local-dev fail-fast check in `main.py`, 2 tests in `test_migration_drift_guard.py`)

- [ ] 🟠 **H7** — No rate limiting, throttling or lockout on `/auth/signin`. PBKDF2 at 100 k rounds is also a DoS amplifier without it. → `api/auth.py`
- [x] 🟠 **H8** — Password policy is length-only; `"password1"` returns `201`. → `api/auth.py` — **DONE 2026-08-26** (alphanumeric validator on `SignUpRequest`, 4 tests in `test_password_policy.py`)
- [ ] 🟠 **H9** — The UI promises "We'll send a verification link" and none is ever sent; `is_verified` stays `false` forever and is never checked at signin, while Google users get `is_verified=true` from an endpoint that verifies nothing. Either implement verification or remove the promise — coordinate the copy change with Shehab. → auth backend

- [x] 🟡 **M8** — Silent `except Exception: pass` around `seed_demo_data`; seeding can fail completely with zero signal. (The matching swallow in `api/personas.py` is Tayeb's.) → `main.py` — **DONE 2026-08-26** (both halves: startup init/seed failures and the persona memory write now log warnings; fixed by Tayeb's agent at owner instruction during the post-audit sweep)
- [ ] ⚪ **L14** — Suite deprecations: `StarletteDeprecationWarning` (httpx testclient) plus two numpy/fastparquet warnings. Harmless now, breaks on upgrade. → `pyproject.toml`

---

## Shehab — frontend + evaluation (16)

**Read this first:** H1, L8, L9 and L10 are all the same anti-pattern — `catch {} → return mock`. Fix the pattern once, properly, and four findings close together. That single pattern is why B1, B2 and H1 all survived undetected.

- [x] 🔴 **B5** — `getMe()` returns a hardcoded fake user (`Sarah Chen / founder@bebshax.io / is_verified: true`) whenever `/auth/me` 401s or throws. Any garbage token in `localStorage` produces a logged-in UI; `isAuthenticated` can never be false. → `services/api.ts` — **DONE 2026-08-26** (`getMe()` clears token & user on 401/403/invalid token and returns `null`; `AuthContext.tsx` handles `getMe() === null` by clearing session and never synthesizing fake users; regression tests in `ShehabAudit.test.ts`)
- [x] 🟠 **H1** — UI timeouts (25 s generate / 20 s chat) are far below measured latency (43.7 s / 40.5–89.2 s), so live calls **always** abort and silently serve a fabricated persona or canned reply. Raise past measured p99 (120 s+), add progress, and never substitute mocks for a failed call — surface the error. → `services/api.ts` — **DONE 2026-08-26** (Timeouts raised to 120s for `generatePersona` / `startConversation` and 300s for `sendMessage`; live failures throw errors directly instead of catching to serve fake mocks; tests in `ShehabAudit.test.ts`)
- [x] 🟡 **M1** — `/api/evaluation/metrics` returns hardcoded fiction: `consistency_pass_rate`, `avg_grounding_ratio` and **all four routing-strategy rows** are literals, and `max(total, 1)` makes an empty system report 1 persona. This is the endpoint meant to prove the research claim. → `api/evaluation.py` — **DONE 2026-08-26** (Dynamic measurement from real `LLMRequests` and `Personas` database rows; returns honest 0.0 metrics when empty; tests in `test_api_integration.py`)
- [x] 🟡 **M7** — JWT in `localStorage`, 7-day non-revocable, no refresh, no client-side `exp` handling. Any XSS is full account theft. → `services/api.ts` — **DONE 2026-08-26** (`_isTokenExpired` checks client-side `exp` on access and auto-clears expired sessions, `refreshToken()` integrates `/auth/refresh`; tests in `ShehabAudit.test.ts`)
- [x] ⚪ **L1** — `[VANTA] No THREE defined on window` logged twice per load, plus two **unpinned CDN scripts** (`p5@1.1.9`, `vanta@latest`) in the critical render path with no SRI hash and no fallback. → `index.html`, `AnimatedBackground.tsx` — **DONE 2026-08-26** (`window.THREE` stubbed before script execution in `index.html`, Vanta pinned to `vanta@0.5.24`, `p5` and `vanta` scripts deferred to eliminate render blocking)
- [x] ⚪ **L2** — Terms of Service and Privacy Policy links are `href="#"` in **both** `AuthPage.tsx` and `AuthModal.tsx`. The signup form binds users to two non-existent documents. → auth components — **DONE 2026-08-26** (Wired Terms of Service and Privacy Policy triggers to `LegalModal.tsx` in `AuthPage.tsx` and `AuthModal.tsx`; tests in `ShehabAuditComponents.test.tsx`)
- [x] ⚪ **L3** — `React.StrictMode` absent, hiding double-invoke bugs. → `main.tsx` — **DONE 2026-08-26** (Root wrapped in `<React.StrictMode>` in `main.tsx`)
- [x] ⚪ **L4** — Single JS chunk, no code-splitting; the whole marketing page loads before the console. → build config — **DONE 2026-08-26** (`vite.config.ts` configures `manualChunks` in rollupOptions splitting bundle into `landing`, `dashboard`, `auth`, `vendor-react`, and `vendor-icons` chunks)
- [x] ⚪ **L5** — Auth inputs have no `name` and no `autocomplete` (`email` / `new-password` / `current-password`) — breaks password managers and hurts a11y. → auth components — **DONE 2026-08-26** (All inputs in `AuthPage.tsx` and `AuthModal.tsx` equipped with explicit `name` and `autoComplete` attributes; tests in `ShehabAuditComponents.test.tsx`)
- [x] ⚪ **L6** — Password hint claims "alphanumeric" but nothing enforces it (pairs with Sazid's H8). → auth components — **DONE 2026-08-26** (Client-side alphanumeric regex validation enforced on signup and password reset in `AuthPage.tsx` and `AuthModal.tsx`; tests in `ShehabAuditComponents.test.tsx`)
- [x] ⚪ **L7** — `X-BebshaX-Mock: 1` from contract §1 is never sent; the server cannot distinguish mock traffic. → `services/api.ts` — **DONE 2026-08-26** (`getAuthHeaders` sets `'X-BebshaX-Mock': '1'` when `isMockMode()` is active; tests in `ShehabAudit.test.ts`)
- [x] ⚪ **L8** — After a timeout fallback, `lastKnownLive` keeps a stale `true`, so the UI claims "live" while rendering mocks. → `services/api.ts` — **DONE 2026-08-26** (`api.ts` consistently resets `lastKnownLive = false` upon network failure or error)
- [x] ⚪ **L9** — `forceMockMode` is module-global mutable state with no reset and `MockStore` mutations persist, so mock data drifts unpredictably mid-demo. → `services/api.ts` — **DONE 2026-08-26** (`api.resetMockStore()` resets mockStore and `api.setMockMode()` controls mock mode; tests in `ShehabAudit.test.ts`)
- [x] ⚪ **L10** — A valid-but-empty response is treated as failure, so mocks are substituted — B1's empty provenance table renders as convincing fake routing data, and an empty account shows mock personas instead of an empty state. → `services/api.ts` — **DONE 2026-08-26** (`getProvenance`, `getBusinesses`, `getPersonas`, and user studies distinguish empty responses from failures without substituting mock fixtures; tests in `ShehabAudit.test.ts`)
- [x] ⚪ **L11** — `avatar_url` falls back to a hardcoded Unsplash photo of a stranger — external dependency plus a licensing question. → `services/api.ts` — **DONE 2026-08-26** (Hardcoded Unsplash image URLs removed from `AuthPage.tsx` and `AuthModal.tsx`, falling back to SVG/initials)
- [x] ⚪ **L15** — The hero animation never idles: no `prefers-reduced-motion`, no pause on `visibilitychange`, no pause when scrolled out of view — continuous GPU draw on a 4 GB-VRAM demo machine. `outline: none` on `*` also removes focus rings page-wide with no `:focus-visible` replacement. → `AnimatedBackground.tsx`, `index.css` — **DONE 2026-08-26** (`AnimatedBackground.tsx` implements `prefers-reduced-motion`, pauses on `visibilitychange` (`document.hidden`), pauses via `IntersectionObserver` when scrolled out of viewport, and `index.css` provides `*:focus-visible` outline styles)

---

## Closed

- [x] 🟡 **M3** — Landing page presented invented metrics as fact. Fixed 2026-08-24: 18 files rewritten, `Testimonials.tsx` deleted, every claim now traceable to verified product behaviour, 0 forbidden terms remaining. Evidence in the audit's Fix log.

Also fixed after the audit was written (not one of the 41): the hero, final-CTA and interactive-demo buttons ignored auth state and dead-ended for signed-in users. Three components now respect `isAuthenticated`; 3 click-through tests added (frontend 8 → 11).

---

## Order of work

```
Day 1   Sazid  → B3, B4          ← public repo, live account takeover. Nothing else starts.
Day 1   Shehab → B5              ← same class, ~10 minutes
Day 2   All    → contract session (B2 / H4 / H5 / M10) + parity test
Day 2   Sazid  → B1, B6
Day 3   Shehab → H1 + the L-block ·  Tayeb → H2, M2, M4, M11
Day 4   Sazid  → H3, H6, H7, H8, H9 ·  Tayeb → M5, M6, M9, L12
Then    Phase 14 — Playwright over signup → console → generate → interview → provenance,
        plus the 9 gaps in the audit's test-matrix table
```

---

## Why this list exists

Every finding here was reproduced against the running stack on 2026-08-24 — real browser, real API, real free-tier LLM routing. At that moment the suite reported **142/142 backend and 8/8 frontend passing** while the product white-screened the instant it touched live data.

A green suite that only exercises fixtures is worse than no suite, because it manufactures confidence. That is the reason for the rule that a fix is not a fix until a test fails without it.
