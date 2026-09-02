"""Single source of truth for the shared-owner tenancy policy (B6 stage 3).

Rows stamped with one of PUBLIC_OWNER_IDS (or NULL, where the column is
nullable) form the shared pool: the system demo tenant and the anonymous
tenant. Every row-scoping rule in the API derives from this table.

Deliberate deltas (documented so they are not "fixed" into bugs):
- Study access (`api.studies._user_owns_study`): the `is_demo` flag governs
  demo visibility, and authenticated users do NOT inherit anonymous-tenant
  studies into their own view — their list mirrors their token identity.
- Owner-stamped rows (`owner_accessible`): the shared pool is readable by
  every caller, authenticated or not; owned rows require the owner's token.
"""

from __future__ import annotations

from typing import Optional

PUBLIC_OWNER_IDS = ("usr_system_holder", "usr_default", "anonymous")

# Study-access delta: anonymous callers reach the anonymous tenant but NOT
# system-holder studies (demo visibility is governed by Studies.is_demo).
STUDY_ANON_OWNER_IDS = tuple(o for o in PUBLIC_OWNER_IDS if o != "usr_system_holder")


def allowed_owner_ids(current_user_id: Optional[str]) -> list[str]:
    """Owner ids visible to a caller: shared pool plus their own, if any."""
    return [*PUBLIC_OWNER_IDS, current_user_id] if current_user_id else list(PUBLIC_OWNER_IDS)


def owner_accessible(owner_id: Optional[str], current_user_id: Optional[str]) -> bool:
    """READ rule for owner-stamped rows (audiences, businesses, personas,
    conversations, datasets). The shared pool is world-readable."""
    if owner_id is None or owner_id in PUBLIC_OWNER_IDS:
        return True
    return current_user_id is not None and owner_id == current_user_id


def owner_can_write(owner_id: Optional[str], current_user_id: Optional[str]) -> bool:
    """WRITE/DESTROY rule for owner-stamped rows.

    Deliberately NOT `owner_accessible`: a shared-pool row being world-readable
    must never make it a world-writable target. Every unauthenticated caller
    shares one anonymous identity, so letting them mutate the shared pool lets
    any visitor destroy another visitor's dataset, audience or conversation —
    and letting an authenticated user inherit the pool lets them destroy rows
    that are not theirs. Mirrors `api.deps.user_can_write_study` for studies:
    mutations require the owner's own token.
    """
    return current_user_id is not None and owner_id == current_user_id
