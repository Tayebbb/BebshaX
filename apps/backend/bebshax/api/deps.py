"""Shared FastAPI dependencies and row-level access helpers.

Extracted from ``api/studies.py`` so sibling routers stop importing
underscore-private names across module boundaries. ``studies.py`` re-exports
``_user_owns_study`` / ``_owner_accessible`` aliases (and ``get_session`` by
name) for back-compat importers — notably ``api/payments.py``, which is a
frozen path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import nullcontext
from ipaddress import ip_address
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_current_user, get_optional_current_user
from bebshax.auth.models import Users
from bebshax.config import get_settings
from bebshax.db.models import Studies
from bebshax.llm.governance import LLMRequestContext, llm_request_context
from bebshax.tenancy import STUDY_ANON_OWNER_IDS
from bebshax.tenancy import owner_accessible as _tenancy_owner_accessible
from bebshax.tenancy import owner_can_write as _tenancy_owner_can_write
from bebshax.tenancy_context import tenant_scope


async def get_tenant_user(current_user: Users = Depends(get_current_user)) -> AsyncIterator[Users]:
    """Keep a required authenticated identity bound through the route and its cleanup."""
    with tenant_scope(current_user.id), llm_request_context(LLMRequestContext(owner_user_id=current_user.id)):
        yield current_user


async def get_optional_tenant_user(
    current_user: Optional[Users] = Depends(get_optional_current_user),
) -> AsyncIterator[Optional[Users]]:
    """Bind only the identity verified by the auth dependency, never a payload owner."""
    processing_scope = (
        llm_request_context(LLMRequestContext(owner_user_id=current_user.id))
        if current_user else nullcontext()
    )
    with tenant_scope(current_user.id if current_user else None), processing_scope:
        yield current_user


def user_owns_study(study: Studies, current_user: Optional[Users]) -> bool:
    """Only explicit demos are public; legacy or missing ownership stays private."""
    if study.is_demo:
        return True
    return bool(
        current_user and current_user.id not in STUDY_ANON_OWNER_IDS
        and study.user_id and study.user_id == current_user.id
    )


def user_can_write_study(study: Studies, current_user: Optional[Users]) -> bool:
    """Write gate for study mutations.

    Deliberately stricter than ``user_owns_study``: the ``is_demo`` allowance
    exists so anyone can *read* the shared demo, not so any unauthenticated
    caller can overwrite it. Every mutation requires the owner's token —
    unauthenticated callers all share the ``usr_default`` anonymous identity,
    so granting them writes would let any visitor edit or delete any other
    visitor's study.
    """
    if current_user is None or study.is_demo or current_user.id in STUDY_ANON_OWNER_IDS:
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


async def require_developer_user(current_user: Users = Depends(get_tenant_user)) -> Users:
    """Roles are read from the verified user's DB row, never JWT or client claims."""
    if current_user.role not in {"developer", "admin"}:
        raise HTTPException(status_code=403, detail="Developer access required.")
    return current_user


def require_development_environment(request: Request) -> None:
    """404 outside development or off-loopback, before any credential is examined."""
    settings = getattr(request.app.state, "settings", None) or get_settings()
    if settings.environment != "development" or request.client is None:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        local_peer = ip_address(request.client.host).is_loopback
    except ValueError:
        local_peer = False
    if not local_peer:
        raise HTTPException(status_code=404, detail="Not found")


def require_development_diagnostics(
    _environment: None = Depends(require_development_environment),
    current_user: Users = Depends(require_developer_user),
) -> None:
    """Development-only diagnostics: existence check first, then developer identity."""
    return None


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
