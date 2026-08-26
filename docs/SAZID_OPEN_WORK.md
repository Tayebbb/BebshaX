# Sazid — Open Work

**Status: 3 of 11 closed (B4, B1, M8) · 8 remaining · 2 of those partially landed.**

Working brief derived from [AUDIT_ASSIGNMENTS.md](AUDIT_ASSIGNMENTS.md) (lines 80–113) and
[E2E_AUDIT_2026-08-24.md](E2E_AUDIT_2026-08-24.md) (lines 105–200), plus a read of the current
code on `main` as of 2026-08-26. Where this document disagrees with the audit, the disagreement
is called out explicitly below.

Of the 3 closed items, only **B4** was Sazid's own work — **B1** and **M8** were fixed by Tayeb's
agent at owner instruction during the post-audit sweep.

---

## ⚠️ First: a finding that changes the plan

**B3 is not actually blocked — and the recorded unblock plan does not close the hole.**

The audit records B3 as gated on Shehab migrating the frontend from `/auth/google` to
`/auth/sync`. But `/auth/sync` ([`api/auth.py:253-280`](../apps/backend/bebshax/api/auth.py))
has **the identical bypass**: it reads `payload.email`, looks up or creates that user, and mints
a token. No credential, no verification of any kind. Migrating the caller relocates the account
takeover; it does not fix it.

Worse: `/auth/sync` is already live and already called at
[`services/api.ts:781`](../apps/frontend/src/services/api.ts), so the hole is reachable **today**
regardless of what Shehab does.

Two further details in [`api/auth.py:200-250`](../apps/backend/bebshax/api/auth.py):

- When a `credential` *is* supplied, the code base64-decodes the JWT payload segment and reads
  `email` / `name` / `picture` out of it **without verifying the signature**. Decoding is not
  validating.
- The `email or "google.user@example.com"` fallback survives at line 227, so an empty body still
  logs in.

**Therefore the real task is "make token issuance require proof of identity", covering `/google`
and `/sync` as one job.** This needs to be agreed before B3 is scheduled.

---

## The 8 open items

### 🔴 B3 — Auth bypass on Google sign-in — *listed blocked, actually actionable*

Anyone who knows an email owns that account; an empty body logs in as `google.user@example.com`.
Fix is either real Google token verification (`google-auth`: signature + `aud` + `iss` + `exp`)
or deletion of both unverified paths. Adding the library needs an R8 dependency review.

Note that [`tests/test_auth.py`](../apps/backend/tests/test_auth.py) covers the service and crypto
layers only — there are **no HTTP-layer auth tests**, which is precisely why B3 shipped undetected.
Whatever lands here must come with endpoint-level tests.

### 🔴 B6 Stage 2 — tenancy enforcement — *Stage 1 done*

Stage 1 landed 2026-08-26: nullable `owner_id` + FK on `businesses`/`personas`, migration
`8d648b892fd3`, 6 tests in [`tests/db/test_owner_id.py`](../apps/backend/tests/db/test_owner_id.py).
Stage 2 — row scoping via `Depends(get_current_user)` in `api/**` — is Tayeb's, gated on B4
reaching prod.

**Open question owned by Sazid:** the columns are nullable, so pre-existing rows have
`owner_id IS NULL`. Whether those become invisible, admin-only, or backfilled is a data-layer
decision, and Stage 2 cannot be written until it is made.

### 🟠 H6 — Migration drift guard — *CI half already done, by someone else*

[`.github/workflows/ci.yml:81-86`](../.github/workflows/ci.yml) already runs `alembic upgrade head`
and asserts `current == heads`. That arrived with Tayeb's M11 work.

What remains is the **local-dev** half: teammates still silently run behind head. A startup check
or a `make check`-style guard closes it. Cheapest win on the list — confirm what CI covers, close
the gap, tick the item.

### 🟠 H7 — No rate limiting or lockout on `/auth/signin`

Freely brute-forceable, and PBKDF2 at 100k rounds makes it a DoS amplifier. Nothing in
[`pyproject.toml`](../apps/backend/pyproject.toml) covers this today, so `slowapi` or a
hand-rolled limiter both need an R8 review.

Decision needed: in-process limiter (simple, resets on restart, incorrect under multiple workers)
vs. DB- or Redis-backed. The audit also asks for a failed-attempt audit log — don't drop that half.

### 🟠 H8 — Password policy is length-only

`min_length=8` at [`api/auth.py:18`](../apps/backend/bebshax/api/auth.py) and nothing else;
`"password1"` returns `201` (verified in the audit). Smallest item here: a validator plus tests.

Pairs with Shehab's **L6** — the UI already claims "At least 8 characters, alphanumeric". Agree
the exact rule with him first, or copy and enforcement diverge again.

### 🟠 H9 — Email verification promised, never implemented

`is_verified` stays `false` forever and is never checked at signin, while Google users get
`is_verified=true` from an endpoint that verifies nothing.

**This is a scope fork, not a bug fix.** Implementing verification means a mail provider, a token
table, and an expiry flow. Removing the promise is two lines of Shehab's copy. Get an owner
decision before starting — don't build a mail pipeline for a demo if the answer is "remove the
sentence".

### 🟠 H3 — Demo mode marked ✅ but unimplemented

Three distinct pieces:

1. `seed_demo_data` runs unconditionally on every startup regardless of the flag.
2. Nothing is labelled `"cached"` in any API response or UI surface — the spec's core honesty
   requirement.
3. `docs/DEMO.md` does not exist, despite being a named Phase 13 exit criterion referenced from
   [PHASES.md](PHASES.md) and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

The `"cached"` labelling crosses into API responses and UI, so it needs Shehab. Related: **L13**
notes that [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) still marks Phase 13 ✅ — that doc claim
should be corrected as part of this fix.

### ⚪ L14 — Suite deprecation warnings

`StarletteDeprecationWarning` (httpx testclient) plus two numpy/fastparquet `DeprecationWarning`s.
There are currently **no `filterwarnings`** in [`pyproject.toml`](../apps/backend/pyproject.toml),
so nothing is suppressed or tracked. Harmless until an upgrade breaks it. Do last.

---

## Suggested order

| # | Item | Why here |
| - | ---- | -------- |
| 1 | **B3** | Resolve the `/sync` finding, then fix both endpoints as one job. Only live account takeover left on the board. |
| 2 | **H6** | Verify what CI already covers, close the local half. Fast. |
| 3 | **H8** | Small, self-contained; needs only a quick rule agreement with Shehab. |
| 4 | **H9 + H3** | Both need an owner decision on scope before any code. Raise as questions, not tasks. |
| 5 | **H7** | Needs an R8 dependency review; decide limiter strategy first. |
| 6 | **B6 Stage 2 · L14** | The null-`owner_id` policy call, then the warnings cleanup. |

**Cross-team blockers to raise early, not mid-implementation:**

- H8 / L6 and H3's `"cached"` labelling both need Shehab.
- H9 needs an owner ruling on implement-vs-remove.
- B3's dependency choice and H7's limiter both need R8 reviews.
