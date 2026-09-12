# SEC01 Memory And Interview Workstream

Status: implementation and scoped verification in progress. No migrations,
services, live providers, live databases, commits, or full backend suite run.

## Integration Handoff

- `api/personas.py`: the raw memory listing must require a verified private
  owner and filter `MemoryItems.owner_id` even when `conversation_id` is NULL.
  Persona visibility does not grant access to its users' memories. Prefer
  `memory_service.list_for_persona(persona_id, owner_id=current_user.id)`.
- `api/personas.py`: persona generation already resolves an owner; pass that
  owner into its identity-memory `remember` call. The new service deliberately
  rejects missing ownership instead of silently using a public tenant.
- `personas/service.py`: settle the deletion policy before deleting a persona
  with foreign-owner memory references. Current persona-only memory deletion
  can remove those references. Owner filtering alone does not solve the parent
  foreign key; archive/reject the parent or authorize a distinct full purge.
- Behavioral engine currently injects memory but has no memory method calls.
  Any new call must carry its verified execution owner, never the shared
  persona's owner. No ambient context automatically filters SQL.
- Runtime must adopt the engine shutdown contract documented below when
  enabling background suggestions. Default generated suggestions remain empty;
  deterministic contradiction follow-ups remain on the answer.

The independent call-site reviewer found the first two items blocking at the
reviewed source snapshot. This workstream owns none of those files. Recheck
after the behavioral/tenancy worker lands its changes.

## Storage Contract

New nullable columns preserve unknown historical data rather than assigning a
shared default:

```sql
ALTER TABLE memory_items ADD COLUMN owner_id VARCHAR(64) NULL;
CREATE INDEX ix_memory_items_owner_id ON memory_items (owner_id);
ALTER TABLE conversations ADD COLUMN persona_snapshot JSONB NULL;
ALTER TABLE memory_items ADD CONSTRAINT uq_memory_owner_persona_content
  UNIQUE (owner_id, persona_id, content_hash);
```

The coordinator must stage these operations: add columns, audit and attribute
verifiable rows, canonicalize hashes and reconcile collisions, then create the
unique constraint. No FK to authentication is introduced: purge/retention is
not yet defined. Existing conversation turn uniqueness and CAS remain intact.

Canonical hash is SHA-256 of UTF-8 `source + U+001F + kind + U+001F + full_text`.
Never strip, redact, summarize, or truncate text when canonicalizing. NULL
owners are excluded from all ordinary memory reads, reflection, and dedupe.
NULL hashes remain a separate legacy case; exact same-owner/source/kind/text
matches can be reused without exposing unknown owners.

Backfill may attribute a row with a conversation reference only when that
conversation exists, matches the persona, and has a verifiable private owner
consistent with its parent study. A missing/mismatched reference is ambiguous,
not permission to fall back to the persona. Conversation-less rows may use a
persona owner only when it is a verifiable private owner and the complete
conversation/parent ownership inventory is unique and consistent. NULL, public
sentinel, conflicting, orphaned, or unprovable ownership stays NULL. Preserve
all ambiguous text and historical identifiers for offline reconciliation.
Do not assign the current viewer, a default user, or a shared persona owner.
Preserve colliding legacy rows/references for reconciliation; do not silently
delete them to make a constraint pass. New writes must dedupe independently
for each owner, across that owner's conversations.

New interviews capture every persona column (or the complete legacy profile),
the original rendered identity card, and the version. Historical NULL snapshots
remain unknown; do not backfill them from today's mutable persona. Existing
version-conflict checks remain: changed versions fail explicitly, not by
rewriting persona identity or discarding transcript history.

## Verification

Initial RED: six owner-isolation cases, seven engine boundary cases, five
additional memory validation/derivation cases, two snapshot/locking cases,
and five HTTP boundary cases failed for their expected behavior gaps.
Latest narrow GREEN at this checkpoint: memory 12, engine 10, API 6.
Checks use the project Python 3.12 venv, SQLite and fake LLMs. The scoped
launcher disables dotenv reads and injects test settings without changing
process-global settings in any other worker. Scratch files remain under
`.tmp` in this repository. Full/shared-suite and production claims are excluded.