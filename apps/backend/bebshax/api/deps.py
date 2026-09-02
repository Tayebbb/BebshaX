"""Shared FastAPI dependencies and row-level access helpers.

Extracted from ``api/studies.py`` so sibling routers stop importing
underscore-private names across module boundaries. ``studies.py`` re-exports
``_user_owns_study`` / ``_owner_accessible`` aliases (and ``get_session`` by
name) for back-compat importers — notably ``api/payments.py``, which is a
frozen path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.db.models import Studies
from bebshax.tenancy import STUDY_ANON_OWNER_IDS
from bebshax.tenancy import owner_accessible as _tenancy_owner_accessible
from bebshax.tenancy import owner_can_write as _tenancy_owner_can_write


def user_owns_study(study: Studies, current_user: Optional[Users]) -> bool:
    """Return True if the current user owns the study, or it is a public demo / default study."""
    if study.is_demo:
        return True
    if current_user and study.user_id == current_user.id:
        return True
    if current_user is None and (not study.user_id or study.user_id in STUDY_ANON_OWNER_IDS):
        return True
    return False


def user_can_write_study(study: Studies, current_user: Optional[Users]) -> bool:
    """Write gate for study mutations.

    Deliberately stricter than ``user_owns_study``: the ``is_demo`` allowance
    exists so anyone can *read* the shared demo, not so any unauthenticated
    caller can overwrite it. Every mutation requires the owner's token —
    unauthenticated callers all share the ``usr_default`` anonymous identity,
    so granting them writes would let any visitor edit or delete any other
    visitor's study.
    """
    if current_user is None:
        return False
    return bool(study.user_id) and study.user_id == current_user.id


def owner_accessible(owner_id: Optional[str], current_user: Optional[Users]) -> bool:
    """Row-level access rule for owner-stamped rows (audiences, businesses,
    personas, conversations): shared/system rows are readable by every caller;
    owned rows require the owner's token. NOTE the deliberate delta from
    `user_owns_study`: studies use the `is_demo` flag and do not grant
    authenticated users the anonymous tenant — see bebshax/tenancy.py."""
    return _tenancy_owner_accessible(owner_id, current_user.id if current_user else None)


def owner_can_write(owner_id: Optional[str], current_user: Optional[Users]) -> bool:
    """Write/destroy gate for owner-stamped rows: the shared pool is readable
    by everyone but writable by nobody but its owner (see bebshax/tenancy.py)."""
    return _tenancy_owner_can_write(owner_id, current_user.id if current_user else None)


READ_ONLY_STUDY_DETAIL = (
    "This is a read-only example study — create your own study to make changes."
)


def require_study_access(
    study: Optional[Studies],
    current_user: Optional[Users],
    *,
    write: bool = False,
    not_found_detail: str = "study not found",
    read_only_detail: str = READ_ONLY_STUDY_DETAIL,
) -> Studies:
    """Shared study gate: 404 when the study is missing or the caller cannot
    read it (existence never leaks); 403 when the caller can read it but may
    not mutate it. A reader backtracking into a write action on the shared
    demo must see "read-only", never a false "not found"."""
    if study is None or not user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=not_found_detail)
    if write and not user_can_write_study(study, current_user):
        raise HTTPException(
            status_code=403,
            detail=read_only_detail if study.is_demo else "Not authorized to modify this study",
        )
    return study


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker = getattr(request.app.state, "db_sessionmaker", None)
    if not sessionmaker:
        raise HTTPException(status_code=500, detail="Database not configured")
    async with sessionmaker() as session:
        yield session
