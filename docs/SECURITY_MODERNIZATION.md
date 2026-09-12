# Security Modernization Continuation

## Maintenance (2026-09-10)

This continuation owns authentication, shared auth/privacy dependencies, error
and body middleware, payments, and direct security tests only. Existing work is
preserved. No frontend, domain, router, database migration, central settings,
manifest, or other documentation is modified. No commit, deployment, external
account, email, payment, provider request, or live database verification is part
of this work. This is not external-auth or production certification.

## Implemented

- Durable auth admission stops after the first exhausted budget. An IP-denied
  request cannot allocate an arbitrary account counter or charge a victim's
  account budget. Existing PostgreSQL/SQLite upserts and HMAC keys remain.
- Logout rechecks its proof after acquiring the cooperating user-row lock.
  A concurrently revoked/rotated credential cannot authorize logout-all.
  Older valid generations can still revoke only their own session family.
- Required and optional auth dependencies bind a server-created
  `LLMRequestContext(owner_user_id=verified_user.id)` with classification
  `private`, including legacy dependency callers. Tenant wrappers retain their
  scoped behavior. Dependency cleanup resets both contexts after success or
  failure; concurrent owners remain isolated. Payload/header owner and
  classification claims never establish authority.
- Neon session verification requires a configured HTTPS URL without userinfo,
  query, fragment, control characters, invalid port, or backslashes. Requests
  send session proof only in Authorization, do not follow redirects or inherit
  HTTP proxy settings, and have a five-second timeout. Upstream 429/5xx and
  transport failures return generic 503, not invalid-credential 401.
- Billing mutations require `settings.payments_enabled is True`, fail closed
  when the field is absent, and otherwise return 503 `billing_disabled` before
  SDK calls. A configured Stripe key alone never enables payments. Disabled
  subscription responses report free/disabled/unpaid without rewriting rows.
  Expired subscriptions never report paid entitlement.
- Payment input forbids extra ownership/entitlement fields and bounds text.
  Client plan selection is purchase intent, never an entitlement update.
  Redirect validation precedes customer creation; SDK exception text is never
  returned or logged. Existing mocked Stripe success/signature tests explicitly
  select their enabled branch.
- HTTP 5xx envelopes use known public codes and static messages, excluding
  arbitrary exception detail/metadata. Public fallback reasons derive from the
  closed failure enum rather than upstream text. Validation and SQL/unhandled
  errors retain their existing sensitive-value redaction.
- Existing received-byte and pre-parse upload admission protections are retained
  and tested for typed JSON, chunked/incorrect Content-Length input, multipart
  spooling, cancellation, and exact-limit content preservation. No truncation.
- SMTP implicit TLS and STARTTLS explicitly verify hostnames and certificates
  before authentication. Recovery codes and recipient/exception text stay out
  of application logs.

## Preserved Auth Invariants

Local passwords remain the password authority, including retained local hashes
on Neon-linked accounts. Recovery changes that password, proves email, and
invalidates sessions/challenges in the same credential transaction. Passwordless
federated accounts do not acquire a local password through recovery.

OTP purposes are `email-verification` and `forget-password`. Challenges have
keyed digests, a fifteen-minute deadline, five failed guesses, account/IP
admission budgets, and transactional single use. No plaintext OTP or refresh
credential is stored.

New sign-ins create persisted, independently revocable session families. Access
lasts at most fifteen minutes; refresh lasts at most seven days; a family lasts
at most `min(max(jwt_expire_days, 1), 30)` days. Rotation retains the absolute
deadline. Valid old refresh replay revokes the family; a guessed refresh secret
cannot revoke another user. No missing/rejected credential becomes anonymous.

Existing stateless JWT compatibility is restricted to fifteen minutes from
original issue, before the account's legacy cutoff. Access-only refresh returns
the same credential/deadline and cannot mint refresh proof. Retire that
compatibility with coordinated direct-token fixture/client migration.

## Frontend Contract

All following paths begin with `/api/auth`. JSON rejects extra fields. Emails
are trimmed/lowercased and capped at 254 characters; passwords are 8-128
characters with a letter and digit (sign-in accepts 1-128). OTPs are six ASCII
digits. No URL/query bearer is accepted.

| Method / Path | JSON / Authentication | Result |
| --- | --- | --- |
| POST `/signup` | `{email, full_name, password}` | Uniform 201 pending response, no credentials or user profile. Keep the submitted email for verification. |
| POST `/verify-email` | `{email, token, purpose?: "email-verification"}` | Auth response plus `detail`, after single-use proof. |
| POST `/resend-verification` | `{email}` | Uniform 200; no disclosure of eligibility or delivery. |
| POST `/forgot-password` or `/request-password-reset` | `{email, purpose?: "forget-password"}` | Uniform 200. |
| POST `/reset-password` | `{email, otp, password, purpose?: "forget-password"}` | 200 `{"detail":"Password reset successfully. Please sign in again."}`; never signs in automatically. |
| POST `/signin` | `{email, password}` | Auth response for active, verified local credentials. |
| POST `/sync` | `{neon_token, auth_provider?: "email"\|"neon"\|"google"}` | Auth response for server-verified Neon email. The provider label does not choose the local user or grant a role. |
| GET `/me` | Access bearer or cookie | Current server-verified profile. |
| GET `/session` | Browser cookies, exact Origin, HTTPS | `{user, csrf_token, session_id, session_expires_at, needs_refresh}`; no bearer or refresh secret. |
| POST `/refresh` | Bearer: `{refresh_token}`; cookie: no token body, Origin/CSRF | Rotated auth response with stable family ID/absolute deadline. |
| POST `/logout` | Access bearer, `{refresh_token}`, or Origin/CSRF-bound cookies | Revokes that family; 200 `{"detail":"Signed out successfully."}`. |
| POST `/logout-all` | Current access/refresh proof, or Origin/CSRF-bound cookies | Revokes all families; 200 `{"detail":"All sessions revoked."}`. |

Pending signup response (exact):

```json
{
  "access_token": "",
  "token_type": "bearer",
  "expires_in": 0,
  "expires_in_days": 0,
  "refresh_token": null,
  "refresh_expires_in": 0,
  "session_id": null,
  "session_expires_at": null,
  "csrf_token": null,
  "verification_required": true,
  "user": null
}
```

Authenticated responses use these same fields with actual remaining lifetimes
in seconds, fractional deprecated `expires_in_days`, stable family `session_id`,
and ISO session expiry. `user` contains `id`, `email`, `full_name`, `avatar_url`,
`is_active`, `is_verified`, `auth_provider`, `role`, `created_at`, `updated_at`.

Browser issuance uses `X-Auth-Transport: cookie`, HTTPS, and one exact configured
Origin. Responses return `access_token: ""`, `refresh_token: null`, and a CSRF
value; JavaScript must not persist bearer/refresh secrets. Use
`credentials: "include"`; retain CSRF in memory and restore via `/session`.

| Cookie | Path | Maximum lifetime | Flags |
| --- | --- | --- | --- |
| `__Host-bebshax_access` | `/` | 15 minutes | HttpOnly, Secure, SameSite=Lax, no Domain |
| `__Secure-bebshax_refresh` | `/api/auth` | 7 days | HttpOnly, Secure, SameSite=Lax, no Domain |
| `__Host-bebshax_session` | `/` | Fixed family deadline | HttpOnly, Secure, SameSite=Lax, no Domain |

Cookie mutations require exact `Origin` plus `X-CSRF-Token`. The host binding
prevents a foreign refresh cookie switching browser identity. Rotate refresh
serially across tabs: replay revokes the family. Logout clears original cookie
paths after backend revocation. Clear identity caches and reject late responses.
Matched auth/payment responses are no-store. Cookie hosting must be same-site;
do not relax Origin/CSRF or change SameSite without a separately verified flow.

Google callback integration must consume a state-bound, one-use IdP callback,
retrieve the verified Neon session token, then POST `/sync` and use the returned
local identity/cookies. The Neon user ID is not the application's owner ID.
Do not accept URL bearer login or synthesize a fallback user. Local password
recovery must use the local endpoints above, not Neon-only reset endpoints.

## Integrator Handoffs

1. **Settings owner:** add typed `payments_enabled: bool = False`; do not enable
   it for the foreseeable release. The owned service intentionally fails closed
   until explicit configuration exists. Enablement additionally requires durable
   event IDs, authoritative subscription reconciliation, checkout idempotency,
   out-of-order/cancellation tests and signed sandbox verification. Those billing
   lifecycle guarantees are not provided by the dormant legacy enabled branch.
2. **Data owner:** integrate the existing auth ORM schema, including user role
   and legacy cutoff, OTP purpose/attempt/session version, `auth_sessions`, and
   `auth_rate_limits`. Use the existing shared Base/import contract. No migration
   was added here. Retain rotated generations through absolute expiry for replay
   detection; never backfill plaintext challenges into a compatibility bypass.
3. **Upload/job integrator:** `UploadAdmission.admit` currently calls synchronous
   `running_jobs_for_user`, which rejects SQLJobStore. Change that unowned caller
   to await the durable admission/count API and validate shared admission. The
   middleware tests explicitly use the existing MemoryJobStore; their passing
   result does not certify SQL job/upload integration or process-wide slots.
4. **Router/domain owners:** HTTP auth dependencies now provide private owner
   context for their callers. Attach study identity only after server-side
   ownership validation. Deferred jobs must capture/reconstruct the immutable
   context from trusted stored job/owner data; never use request claims to mark
   content synthetic. No approved private providers means refusal, not synthetic
   fallback, truncation, or remote disclosure.
5. **Frontend/deployment owners:** integrate the complete contract together with
   same-site HTTPS, exact credentialed CORS and allowed headers, trusted proxy
   termination, callback state/PKCE, refresh coordination, and cache invalidation.
   Proxy identity still requires explicit trusted CIDRs. None of these deployed
   guarantees was exercised against a real account here.
6. **Parent:** copy the maintenance outcome to the append-only implementation
   log and execution ledger. Those shared documents are outside this ownership.

## Verification

The owned launcher requires the explicit project Python 3.12 interpreter,
suppresses dotenv reads, sets synthetic configuration, disables real HTTP/SMTP
transports, and keeps test/coverage artifacts under the auth test directory.
MockTransport, mocked Stripe, and isolated SQLite are used for behavior checks.

Focused TDD results so far: durable throttle 8 passed; session edges 12 passed;
all-caller context 8 passed; payment containment plus existing SDK tests 34
passed; Neon transport 14 passed; email security 4 passed; redaction 36 passed;
body streaming 29 passed; upload middleware 37 passed; launcher isolation 1
passed. Selections overlap and must not be summed as unique tests.

The final combined gate passed **346 tests in 233.68 seconds**, with zero
failures/errors and **90.33% line coverage** across 1,716 statements in the
selected owned modules (1,550 covered; required gate 80%). This includes all
direct-auth unit files, the existing payment SDK tests, and the three input
middleware/error test files. **86 added regression cases** are present in that
completed XML report. The separate, non-overlapping offline SSRF URL selection
passed **2 tests**; dataset parser tests were not selected. The final hosted-auth
and launcher check also passed 5 tests, already included in the combined count.

The first combined run also passed all 346 tests but its default coverage core
reported 74.77%, below the gate. An identical single-test comparison showed
that core omitting executed async session continuations; Python 3.12
`sys.monitoring` recorded them. The owned launcher now explicitly selects
`COVERAGE_CORE=sysmon`, and the same combined selection passes the unchanged
coverage threshold. This is a measurement correction, not a claimed coverage
improvement from additional production behavior. A before-change coverage delta
was not measured in the pre-existing dirty worktree. Branch coverage was not
measured. Mail-module line coverage is 69% overall; the newly changed verified
TLS branches are exercised using mocked SMTP, not real delivery.

Scoped bug-tier Ruff, editor diagnostics on the touched paths, and owned
`git diff --check` passed. No packaging/frontend build or whole-repo type check
was performed. No new dependencies or manifests were introduced. Independent
code/security review could not be delegated with the available tools and remains
a gate, not a self-certification.

The complete backend suite, real PostgreSQL contention/migrations, live
SMTP/Neon/Google/Stripe, browser journeys, deployment/key rotation, and CI were
not run. Billing lifecycle, central settings/schema integration, and the SQL
upload/job caller remain the explicit handoffs above. This is not production
or external-auth sign-off.

One stalled owned upload test run was interrupted and its terminal cleaned up:
`14fd708d-8cce-415d-9741-8bae82cf3acb`. Subsequent bounded-fixture upload tests
passed. A stalled full-app auth-fixture inventory was also stopped using only
its unique owned command filter (PIDs 9744/11832), then replaced by the scoped
auth fixture. No owned verification processes remained at the final process
check. No other agents' processes were intentionally stopped.