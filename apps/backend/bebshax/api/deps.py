"""Shared FastAPI dependencies and row-level access helpers.

Extracted from ``api/studies.py`` so sibling routers stop importing
underscore-private names across module boundaries. ``studies.py`` re-exports
``_user_owns_study`` / ``_owner_accessible`` aliases (and ``get_session`` by
name) for back-compat importers — notably ``api/payments.py``, which is a
frozen path.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.db.models import Studies
from bebshax.tenancy import STUDY_ANON_OWNER_IDS
from bebshax.tenancy import owner_accessible as _tenancy_owner_accessible


def user_owns_study(study: Studies, current_user: Optional[Users]) -> bool:
    """Return True if the current user owns the study, or it is a public demo / default study."""
    if study.is_demo:
        return True
    if current_user and study.user_id == current_user.id:
        return True
    if current_user is None and (not study.user_id or study.user_id in STUDY_ANON_OWNER_IDS):
        return True
    return False


def owner_accessible(owner_id: Optional[str], current_user: Optional[Users]) -> bool:
    """Row-level access rule for owner-stamped rows (audiences, businesses,
    personas, conversations): shared/system rows are readable by every caller;
    owned rows require the owner's token. NOTE the deliberate delta from
    `user_owns_study`: studies use the `is_demo` flag and do not grant
    authenticated users the anonymous tenant — see bebshax/tenancy.py."""
    return _tenancy_owner_accessible(owner_id, current_user.id if current_user else None)


async def get_session(request: Request) -> AsyncSession:
    sessionmaker = getattr(request.app.state, "db_sessionmaker", None)
    if not sessionmaker:
        raise HTTPException(status_code=500, detail="Database not configured")
    async with sessionmaker() as session:
        yield session
