# Security and Identity Continuation

## Maintenance (2026-09-10)

This is a bounded continuation of the existing security work, not a new
whole-repository audit or production sign-off. Existing dirty edits were
preserved. Production edits in this continuation are limited to
[memory/service.py](../../apps/backend/bebshax/memory/service.py) and
[interview/engine.py](../../apps/backend/bebshax/interview/engine.py).
The remaining changes are associated tests and this owned audit.

No main/configuration, ORM, migration, persona service, jobs, runtime, frontend,
or LLM implementation was changed. No dependency was added; no account,
provider, SMTP, payment, live database, deployment, commit, or push was used.
Tests use the actual Python 3.12.9 interpreter, synthetic settings, blocked
HTTP/SMTP transports, fake LLMs/mail, and local SQLite.

## Closed Gaps

### Atomic Reflection

Previously, each reflection insight was independently committed. A later
placeholder or storage failure could leave a partial batch in private memory.
The regression first failed with one committed insight remaining after the
second insight was rejected.

Reflection now validates and embeds complete accepted texts before opening the
write transaction, then passes the same session and prepared vectors to every
write. The batch commits together or rolls back together. Existing explicit
validation failures remain failures; no placeholder is persisted or replaced
with a fabricated success. SQL failure and cancellation of the later insert
both leave zero reflection rows. Existing owner-scoped dedupe is retained.

### Complete Optional Context

Deferred suggested questions previously received identity and transcript but
omitted the objective, complete study research, and recalled private memories.
The regression first failed because the objective was absent.

Suggestions now reuse the primary context composer, including the immutable
persona snapshot, evidence, objective, business/study context, complete research
history/findings, and owner-scoped memories. Retrieved memory IDs accompany
that context. Trusted owner/study identity and private classification still
flow through the existing governed LLM entry point.

No suggestion generation was added to the primary response path. Existing
background opt-in, task limit, three-second optional budget, revision/owner
checks, cancellation cleanup, and atomic primary turn/memory writes remain.
No content truncation, smaller-context fallback, or generic suggestion was
introduced.

## Regression Evidence

Eleven regression cases were added across four files:

- [Memory isolation](../../apps/backend/tests/memory/test_modernization_memory_isolation.py):
  rejecting a later reflection insight cannot leave a partial write.
- [Interview boundaries](../../apps/backend/tests/interview/test_modernization_interview_boundaries.py):
  optional context retains complete objective, study history/findings, and
  recalled owner memory, without another owner's text.
- [Session/memory round trips](../../apps/backend/tests/auth/test_security_identity_memory_roundtrip.py):
  seven cases using the shared auth fixture with SQLite foreign keys enabled,
  real persisted sessions, real shared-persona/conversation rows, and fake
  LLM/mail responses. They cover remember/retrieve/reflect/dedupe/list,
  unknown-owner quarantine, persisted retrieval audit IDs, logout/reset
  revocation, retained authorized memory after a fresh sign-in, and reflection
  rollback after SQL failure or cancellation. Database-backed developer/admin
  roles can read operational metadata but cannot read another user's private
  memories or conversation, even with forged identity/role headers.
- [Upload admission](../../apps/backend/tests/api/test_modernization_input_upload_admission.py):
  two event-gated cases prove that authentication and durable job-count awaits
  finish before the first body receive or multipart spool. The tests are
  bounded by five seconds, have no synchronization sleeps, and verify every
  authorized input byte and spool cleanup.

The shared persona remains owned by `usr_system_holder`; the private
conversation and all associated memories belong to the authenticated user.
Identical text for two users has distinct memory IDs. NULL-owner legacy data
never becomes public. Retrieval audit IDs resolve only to that user's rows.
Logout revokes the presented family while an independent family survives;
password reset rejects both existing families. Old access and refresh proof
cannot recover private memory access. Fresh authorized sessions can still read
the retained memory. Query-string bearer credentials remain rejected.

The upload helper now awaits the existing durable job-count API. This was
already present when inspected and was not changed here. The earlier synchronous
helper handoff is superseded by the current code, not implemented a second time.
Existing byte, part, header, field, and parser-chunk budgets remain unchanged.

## Verification

Focused intermediate selections passed:

| Selection | Result |
| --- | --- |
| Memory isolation and reflection | 22 passed |
| Interview context, deadlines, atomicity, revision checks, cleanup | 26 passed |
| Existing SQL memory API selection | 15 passed |
| New FK-enforced session/memory round trips | 5 passed, 7.96 seconds |
| Pre-parser upload admission | 39 passed, 0.92 seconds |
| Additional developer/admin private-data boundaries | 2 passed, 11.86 seconds |

These selections overlap the combined gate and must not be summed as unique
tests. Both production fixes were driven by observed failing tests before
implementation. No existing assertion was weakened.

The final combined focused gate passed **503 tests**, with **2 integration
tests deselected**, in **389.55 seconds**. The two developer/admin cases were
added after that run was collected and passed separately. De-duplicating the
actual JUnit case identifiers confirms **505 unique passing tests**, zero
failures/errors, including all eleven added regressions.

The combined gate selected auth, memory, interview, the three input-security
files, the SQL memory API file, and the existing SQL upload admission file.
It did not select the whole backend suite. Auth selections include local-password
recovery, cookie/CSRF/session boundaries, persisted throttles, private
identity/provenance, operational roles, and disabled billing.

Line coverage across the selected memory/interview packages was **91.45%**
(1,144 of 1,251 statements), above the unchanged 80% threshold. The modified
production modules measured:

| Module | Covered Statements | Line Coverage |
| --- | --- | --- |
| Memory service | 184 / 198 | 92.93% |
| Interview engine | 761 / 844 | 90.17% |

Branch coverage and a before-change coverage delta were not measured. The
pre-existing dirty worktree was not reverted to manufacture a baseline.

Coverage collection with importable module-name targets twice stopped before
collection with NumPy's `cannot load module more than once per process` error.
A single-memory-test coverage probe passed. The final run uses filesystem
coverage targets for the memory/interview packages and explicitly enables only
`pytest_asyncio.plugin` and `pytest_cov.plugin`. The 80% gate is unchanged.
No dependency or application import code was modified for this tooling issue.

Reproduce the current focused selection, including both additional role cases,
from the repository root:

```powershell
.venv\Scripts\python.exe -B apps\backend\tests\auth\run_modernization_checks.py `
  --disable-plugin-autoload -p pytest_asyncio.plugin -p pytest_cov.plugin `
  apps/backend/tests/auth apps/backend/tests/memory apps/backend/tests/interview `
  apps/backend/tests/api/test_modernization_memory_tenants.py `
  apps/backend/tests/api/test_modernization_input_upload_admission.py `
  apps/backend/tests/api/test_modernization_input_body_streaming.py `
  apps/backend/tests/api/test_modernization_input_error_redaction.py `
  apps/backend/tests/jobs/test_upload_sql_job_admission.py `
  -q --tb=short --cov=apps/backend/bebshax/memory `
  --cov=apps/backend/bebshax/interview --cov-report=term-missing --cov-fail-under=80
```

Scoped bug-tier Ruff and tracked-file `git diff --check` passed. Editor
diagnostics were clear for both modified production files and the newly added
code. The existing independent-writer memory test still has four SQLAlchemy
`sessionmaker(AsyncEngine)` typing diagnostics outside the added regression;
they were not changed or presented as a clean whole-workspace type check.

## API and Frontend Contract

There are no new endpoints, request fields, response fields, or authentication
transport changes in this continuation. Suggested questions remain optional
after primary completion; clients must not wait for them before displaying the
durably saved primary result. Memory remains authenticated and owner-private
even when the persona itself is shared.

The existing backend session contract remains authoritative: opt-in secure
HttpOnly cookies, exact Origin and CSRF checks for cookie mutations, serialized
refresh, backend logout revocation, and local password-recovery endpoints.
No query/URL bearer login bypass was added. Frontend callback state/PKCE,
credential storage removal, cache invalidation, refresh coordination, and
same-site HTTPS/CORS integration remain the frontend/deployment owners' work;
these changes do not certify their implementation.

Billing remains disabled/unpaid by default. A provider key or a client-selected
plan cannot grant paid entitlement. This continuation does not enable billing
or certify the dormant enabled checkout/webhook lifecycle.

## Residual Gates

- Governance owner: preserve default denial of private content to unapproved
  remote destinations across primary, optional, and fallback calls. The identity
  tests prove trusted private context propagation, not remote-provider approval.
  No LLM policy file was changed or live egress attempted.
- Data owner: tests use the current owner/session/challenge/rate-limit columns
  and constraints. No additional column is requested for these fixes. Live
  PostgreSQL migrations, locking, and multi-process contention were not tested.
- Jobs/runtime owner: the selected SQL upload tests and bounded middleware
  checks do not establish deployed cross-worker upload reservations or runtime
  wiring. Existing durable-job ownership remains with that workstream.
- Independent code and security review could not be delegated with the
  available tools. No self-review approval is claimed.
- Real email/IdP/browser/payment/provider journeys, deployment key rotation,
  full-suite verification, commit/push, and CI were not run.
- Parent integrator: copy this maintenance outcome into the shared append-only
  implementation log and execution ledger. Those files are outside this task's
  explicit ownership.