# B6 Stage 2 — Review Request for Tayeb

**Date:** 2026-08-26
**From:** Sazid (via agent)
**Re:** Commits `5a5500e` and the follow-up auth fix (see below)

---

## What happened

B6 Stage 2's API row-scoping work touched `api/personas.py` directly — your
owned directory per `TEAM_ASSIGNMENTS.md` — instead of me handing you a spec
like the rest of this audit sweep has done. That wasn't the plan and it's on
me; flagging it plainly rather than letting it sit quietly closed in the docs.

## What was changed

1. **`apps/backend/bebshax/api/personas.py`** — Added `Depends(get_current_user)` /
   `Depends(get_optional_current_user)` and owner_id scoping logic across:
   - `POST /businesses` (create) — requires auth
   - `GET /businesses` (list) — optional auth, scoped to user + system holder
   - `GET /personas` (list) — optional auth, scoped to user + system holder
   - `POST /businesses/{id}/personas` (generate) — requires auth, verifies business ownership
   - `GET /personas/{id}` (get) — optional auth, blocks cross-tenant reads
   - `POST /studies/{id}/personas/generate` — requires auth
   - `POST /studies/{id}/personas/{pid}/regenerate` — requires auth
   - `DELETE /studies/{id}/persona-runs/{rid}` — requires auth

2. **`apps/backend/bebshax/persona/store.py`** — Added `owner_id` parameter to
   `create_business`, `save_persona`, `list_businesses`, `list_personas` functions.

3. **Auth fix (follow-up):** Found and fixed a real bug where all 5 write
   endpoints were using `get_optional_current_user` instead of `get_current_user` —
   meaning an unauthenticated POST could reach `owner_id = current_user.id`
   with `current_user` being `None`, producing either a crash or a NULL insert
   caught late by the DB constraint as a 500. Fixed to return a clean 401.

## What to review

1. **The auth dependency pattern** (`get_current_user` vs `get_optional_current_user`)
   across every endpoint I touched — I found and fixed one class of bug (write
   endpoints allowing unauthenticated requests through), but I'd rather you
   check the rest than assume I caught everything.

2. **Whether the isolation logic** (`owner_id == current_user.id OR
   owner_id == 'usr_system_holder'`) matches how you'd actually planned to
   wire this, especially the open question on whether demo/system-owned
   data should be readable-by-all vs. scoped.

3. **The read-endpoint optional-auth decision:** I left `GET /businesses`,
   `GET /personas`, and `GET /personas/{id}` on `get_optional_current_user`
   so that unauthenticated requests can still see system-holder demo data.
   If unauthenticated reads were never supposed to work at all, these should
   be tightened to `get_current_user` too.

## Going forward

I'm not going to keep making changes in your directories — this was a one-off
gap in the review chain. Want to close it properly with your actual sign-off
rather than just marking it done.

---

> **B6 stays "data layer + row-scoping implemented, pending Tayeb's review"
> in Sazid's own tracking until Tayeb actually replies.**
> The audit doc says DONE — treat that as provisional until the review chain
> that should have happened, happens.
