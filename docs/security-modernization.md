# Identity and Privacy Integration Contract

Date: 2026-09-09. Implements the identity-owned portions of SEC-04/05/09/15.
SEC-10 browser callback changes, shared schema migrations, provider egress
policy, and non-owned diagnostic routers require their respective owners.
This is not production sign-off. No migration, real account, provider call,
frontend storage change, install, commit, or deployment was performed here.

## HTTP Contract

All paths below are prefixed with `/api/auth`. JSON requests reject unknown
fields. Email addresses are trimmed, lowercased, syntax checked, and capped at
254 characters. New passwords are 8-128 characters with a letter and digit;
sign-in accepts 1-128 characters for existing credentials. Names are trimmed
and 2-100 characters at signup. OTPs are exactly six ASCII digits. Neon tokens
are 1-8192 characters. A refresh credential is exactly 76 characters:
32 lowercase hexadecimal characters, a dot, and 43 base64url characters.
No query parameter is an authentication transport.

| Method / Path | Request / Authentication | Success |
| --- | --- | --- |
| POST `/signup` | `{email, full_name, password}` | Uniform 201 pending response for new, existing, and inactive accounts; no credentials or existing-account profile. A new account must prove its email. |
| POST `/verify-email` | `{email, token, purpose?: "email-verification"}` | 200 auth response plus `detail`; consumes the code once and issues a session. |
| POST `/resend-verification` | `{email}` or a current authenticated account | Uniform 200 `{"detail":"Verification email resent with 6-digit OTP code."}` regardless of eligibility/delivery. Outstanding verification codes are superseded; a locked challenge cannot be refreshed to bypass its budget. |
| POST `/forgot-password` or `/request-password-reset` | `{email, purpose?: "forget-password"}` | Uniform 200 `{"detail":"If the account is eligible, a password reset code has been sent."}`. |
| POST `/reset-password` | `{email, otp, password, purpose?: "forget-password"}` | 200 `{"detail":"Password reset successfully. Please sign in again."}`; no credentials. Changes the retained local password, proves email, and revokes all previous credentials/challenges atomically. |
| POST `/signin` | `{email, password}` | 200 auth response for an active, verified account. Wrong/unknown/passwordless/disabled accounts return generic 401. Correct password without email proof returns 403. |
| POST `/sync` | `{neon_token, auth_provider?: "email"\|"neon"\|"google"}` | 200 auth response. Identity comes only from the server-verified Neon response with `emailVerified: true`; the client's provider, role, and user ID cannot grant authority. |
| GET `/me` | Current access credential | User profile, never a refreshed credential. Checks DB account state, credential version, session generation, revocation, and expiry. |
| POST `/refresh` | Bearer transport: `{refresh_token}`. Cookie transport: cookies and Origin/CSRF headers, without a token body. | 200 rotated auth response; stable `session_id` and absolute expiry. A stale bearer header does not override an explicit refresh body. |
| GET `/session` | Cookie transport only, exact allowed Origin, HTTPS | `{user, csrf_token, session_id, session_expires_at, needs_refresh}`. Validates refresh session and host binding even when access has expired. Returns no bearer/refresh credential and does not rotate. |
| POST `/logout` | Current access bearer, explicit `{refresh_token}`, or cookie session with Origin/CSRF | 200 `{"detail":"Signed out successfully."}`; revokes the presented family and disables legacy stateless credentials for the account. Other persisted families survive. |
| POST `/logout-all` | Current access bearer, current refresh credential, or cookie session with Origin/CSRF | 200 `{"detail":"All sessions revoked."}`; advances the account credential version and revokes every family. |

Auth responses have this shape (all lifetimes are derived from actual deadlines):

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

This is the exact pending-signup shape. For authenticated responses,
`verification_required` is false and `user` contains `id`, `email`, `full_name`,
`avatar_url`, `is_active`, `is_verified`, `auth_provider`, `role`, `created_at`,
and `updated_at`. Role is read from the DB; it is not a client-supplied JWT claim.
`session_id` identifies the family, not the changing access-token `jti`.
`session_expires_at` is an ISO-8601 UTC deadline. `expires_in` and
`refresh_expires_in` are seconds; deprecated `expires_in_days` is fractional.

All matched auth endpoints and owned private metadata routes set
`Cache-Control: no-store`, `Pragma: no-cache`, and `Vary: Origin` on normal
responses. Auth HTTP errors carry these headers; 401 includes
`WWW-Authenticate: Bearer`. 429 includes integer seconds in `Retry-After`.
The application's registered HTTP error handler remains authoritative:
the full app emits `{detail, error_code, request_id}`. Validation uses its
existing safe serializer, including sanitization of rejected field names.
Storage errors never turn a supplied credential into anonymous access.

## Browser Transport

Bearer remains the default, preserving the existing transport during frontend
integration. Credential-issuing requests opt in with `X-Auth-Transport: cookie`.
Cookie issuance requires HTTPS and one exact `Origin` from the configured
`cors_origins_list`; the permissive development origin regex is not used for
auth decisions. `null`, missing, duplicated, or untrusted origins are rejected.
Existing auth cookies also select cookie mode; no GET or URL token logs in.

Cookie mode returns `access_token: ""`, `refresh_token: null`, and a
session-bound `csrf_token`. Cookies have no Domain attribute:

| Cookie | Path | Lifetime | Flags |
| --- | --- | --- | --- |
| `__Host-bebshax_access` | `/` | Current access expiry, at most 15 minutes | HttpOnly; Secure; SameSite=Lax |
| `__Secure-bebshax_refresh` | `/api/auth` | Current refresh expiry, at most 7 days | HttpOnly; Secure; SameSite=Lax |
| `__Host-bebshax_session` | `/` | Fixed family absolute expiry | HttpOnly; Secure; SameSite=Lax |

The host-only binding is checked against the persisted family, preventing a
foreign/domain-injected refresh cookie from replacing the browser identity.
Cookie-authenticated mutations require exact `Origin` plus `X-CSRF-Token`.
CSRF values rotate with refresh; `/session` restores the current value after
reload without exposing session credentials. Logout clears all three cookies
with their original paths. Bare bearer requests do not require cookie CSRF;
ambiguous requests carrying ambient auth cookies still require trusted Origin.

Frontend owner must integrate these together, not remove storage alone:

- Keep pending signup email from the submitted form; do not dereference `user`
  until verification succeeds. Do not treat pending signup as signed in.
- Retain CSRF in memory, send `credentials: "include"`, use `/session` for
  bootstrap, and rotate via POST `/refresh` when `needs_refresh` is true.
- Serialize refresh across tabs: duplicate use intentionally returns one
  success and one rejection, then revokes that entire family. This is a replay
  defense, not a retryable refresh operation.
- Revoke at the backend before claiming logout; clear identity-scoped caches
  and use an auth epoch to reject late `/me` and refresh responses.
- Remove arbitrary URL bearer acceptance and localStorage credentials only
  as part of this coordinated flow. OAuth state/PKCE/one-use callback codes
  remain frontend/identity-provider integration responsibilities, not proved
  by the backend's Neon session verification.
- SameSite=Lax requires a same-site deployment for fetch-based cookie auth.
  Do not silently switch to SameSite=None or relax Origin/CSRF. Exact CORS
  origins, allowed headers, credential support, and trusted HTTPS termination
  must be configured by the parent/deployment owner.

## Session and OTP Invariants

Each sign-in creates an independent family with a fixed absolute lifetime of
`min(max(jwt_expire_days, 1), 30)` days. Access is capped at 15 minutes, refresh
at 7 days, and neither can outlive the family. Every rotation retains the old
generation and its digest; valid old refresh proof revokes the family, while
a guessed secret with a known ID cannot revoke it. Old access generations
cannot read private data. Older still-valid proofs may only revoke their own
family, not perform privileged logout-all.

User-row locks serialize issuance, refresh, reset, and logout across database
connections. Reset/credential changes and deactivation advance the credential
version and revoke stored sessions and outstanding challenges in the same
transaction. Lost/raced responses do not reopen a revoked family.

Transitional JWTs without `jti` authenticate for at most 15 minutes from their
original `iat`, only before `legacy_tokens_revoked_at` is set. Bearer-only
`POST /refresh` without refresh proof returns the same access credential and
remaining deadline; it cannot extend expiry or mint refresh proof. Signed
`jti` without a DB row is always invalid. New API issuers never mint stateless
credentials. Integration must retire this bounded compatibility path once
all clients and direct-token test fixtures use stored sessions.

OTPs use HMAC-SHA256 over purpose, owner, challenge ID and code. Only digests
are stored. They last 15 minutes, allow five failed guesses per challenge,
and compare-and-set consumption is transactional. Account/IP budgets are
independent of challenge replacement. Password reset acts on any retained
local hash, even for a Neon-linked account; passwordless federated accounts
receive no local reset code. Unverified local-password pre-hijacking remains
blocked when a verified Neon identity is linked.

PBKDF2 remains the existing 600,000-round format, with bounded legacy hash
verification and equivalent work for malformed/unknown/passwordless records.
Hash work runs off the event loop. Recovery/delivery replies do not disclose
eligibility, and auth mail logs omit recipient addresses and exception bodies.
Verification messages link to the entry page without URL credentials.

## Database Handoff

The migration owner must integrate these before enabling the new auth runtime.
Existing rows must not be deleted or ownership invented.

- `users`: existing `session_version INTEGER NOT NULL DEFAULT 0` remains.
  Add `role VARCHAR(32) NOT NULL DEFAULT 'user'` with `ck_users_role` allowing
  only `user`, `developer`, `admin`. Add nullable UTC
  `legacy_tokens_revoked_at`. Nullable typing corrections to `hashed_password`
  and `avatar_url` do not themselves require physical column changes.
- `email_verification_tokens`: integrate existing in-progress `purpose
  VARCHAR(32) NOT NULL DEFAULT 'email-verification'` and `failed_attempts
  INTEGER NOT NULL DEFAULT 0`, plus new `session_version INTEGER NOT NULL
  DEFAULT 0`. Existing unique indexed `token VARCHAR(64)` now stores keyed
  digests, not plaintext. Older plaintext challenges intentionally fail closed;
  users request fresh codes. Keep history rather than making a plaintext
  compatibility bypass.
- New `auth_sessions`: `id VARCHAR(64)` PK; indexed `family_id VARCHAR(64)`;
  indexed `user_id VARCHAR(64)` FK to users with ON DELETE CASCADE;
  `session_version INTEGER`; unique `refresh_token_hash VARCHAR(64)`;
  `transport VARCHAR(16)` (application default `bearer`);
  UTC `created_at`, `access_expires_at`, `refresh_expires_at`,
  `absolute_expires_at`; nullable UTC `rotated_at`, `revoked_at`.
  All fields except the last two are non-null. `id` is each access JWT's `jti`;
  one family has multiple retained generations. No session-secret plaintext.
- New `auth_rate_limits`: `key VARCHAR(64)` PK; `attempts INTEGER NOT NULL`;
  indexed UTC `expires_at NOT NULL`. Keys are HMACs, not raw emails or IPs.
  Uses native PostgreSQL/SQLite transactional upserts, not process memory.
- Shared `llm_requests.owner_id` and its owner/time index are already present
  in the shared model. It must remain immutable and have no entity-deletion
  cascade or owner-inference fallback. NULL remains private unknown.

Retain rotated session rows at least through their family's absolute expiry
to detect replay. Any expiry cleanup or auth-audit retention job is a separate
owner-approved task; none is implemented or run here. All workers must use the
same signing configuration for consistent HMAC budgets; coordinate key rotation
as an operational boundary, not an implicit counter-reset mechanism.

## Durable Admission and Proxy Contract

Policies live in `AUTH_RATE_POLICIES` in the existing limiter module. Every
admitted attempt consumes both applicable budgets, including unknown accounts;
successful login does not erase the durable counter.

| Action | IP budget | Account/family budget |
| --- | --- | --- |
| signup | 20/hour | 5/hour |
| signin | 30/minute | 5/15 minutes |
| verify | 30/hour | 5/15 minutes |
| resend | 10/hour | 5/15 minutes |
| forgot | 10/hour | 5/hour |
| reset | 10/hour | 10/15 minutes, plus five guesses/challenge |
| sync | 20/minute | 20/minute after verified identity |
| refresh/bootstrap | 60/minute | 30/minute |
| logout | 60/minute | 30/minute |

The pre-existing SlowAPI decorators remain additional local guards; these DB
budgets remain enforced when that local limiter is disabled or restarted.
Database admission failure is 503, never a fallback to an in-memory allowance.

Forwarded IPs require both `BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR=true` and
`BEBSHAX_TRUSTED_PROXY_CIDRS` containing explicit comma-separated networks.
Without them the socket peer wins. Only an allowlisted socket peer can supply
a chain; walk right-to-left past trusted hops and use the first untrusted IP.
Invalid configuration, malformed/oversized chains, and invalid addresses fall
back to the socket peer. The new CIDR variable is read only in the owned limiter;
central settings/deployment documentation and ASGI server proxy handling remain
integrator-owned. The server must preserve the actual socket peer here, or
validate and strip forwarding itself with the same trusted network boundary.

## Privacy and Remaining Handoffs

- `/api/provenance` requires auth and filters only immutable request owner.
  Unlinked, missing-persona, and deleted-entity records stay private; NULL-owner
  records are never returned. Filter lengths and page size are bounded.
- `/api/routes/status` and `/api/routing/capacity` require DB role
  `developer` or `admin`, and retain the prior development/loopback gate.
  The reusable `require_developer_user` dependency is in
  [deps.py](../apps/backend/bebshax/api/deps.py).
- **Unowned integration required:** apply `Depends(require_developer_user)`
  to GET `/api/health/openrouter` and POST `/api/health/openrouter/test` in
  the health router (and any other fleet diagnostic route). Those endpoints
  were inspected but not edited or invoked here. Public basic liveness may
  remain public only without configuration/quota/route details.
- `require_study_access(...) -> Studies` remains the typed parent guard:
  missing/foreign/anonymous non-demo access is 404; explicit demo mutation is
  403; authorized reads/writes return the non-optional study. Parent study
  handlers must use the returned value instead of ignoring it.
- `get_tenant_user` / `get_optional_tenant_user` bind verified DB identity with
  `tenant_scope` through request cleanup, including concurrent requests.
  Missing auth can mean anonymous reads; rejected supplied credentials cannot.
  Client owner IDs/role headers never set this context.
- This context supplies provenance ownership only, **not** data classification,
  consent, or destination approval. The LLM owner still enforces egress policy
  on every adapter/fallback and must capture the trusted context before
  deferred work. No LLM policy/model/memory/interview files were edited here.

## Verification Scope

The owned tests use synthetic SQLite (FK enforcement where deletion is tested),
mock mail/IdP delivery, and no application startup that contacts providers.
The launcher [run_modernization_checks.py](../apps/backend/tests/auth/run_modernization_checks.py)
disables dotenv reads and sets synthetic auth/database/delivery configuration;
temporary files stay under the owned auth test directory. It runs ordinary
pytest selections and does not install dependencies.

The final scoped run passed **104 tests in 109.66 seconds**: the owned auth
tests, `tests/test_auth.py`, and the pre-existing modernization session and
password-reset tests. The configured bug-tier Ruff check passed on all owned
source/test paths; editor diagnostics were clear, and scoped `git diff --check`
and documentation-link validation passed. No remaining failures were observed
in that selection. The complete backend suite was intentionally not run.
SQLite transaction races are tested; real
PostgreSQL isolation/contention, migration upgrade, live email/Neon callback,
multi-tab frontend/cache behavior, same-site hosting, proxy/CORS enforcement,
and deployed key rotation remain external integration gates.