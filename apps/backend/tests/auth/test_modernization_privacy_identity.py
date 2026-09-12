"""Immutable provenance ownership, server-only diagnostic roles, and typed study gates."""

import asyncio
from typing import get_type_hints

import pytest
from fastapi import Depends, HTTPException
from sqlalchemy import select

from bebshax.api import auth as auth_api, deps, routes
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import LLMRequests, Personas, Studies
from bebshax.llm.governance import get_llm_request_context
from bebshax.llm.types import TaskType
from bebshax.tenancy_context import get_tenant_owner_id


def _headers(owner_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(owner_id)}"}


@pytest.mark.parametrize("path", ["/api/routes/status", "/api/routing/capacity"])
async def test_operational_metadata_requires_auth_and_database_developer_role(identity_state, path):
    state = identity_state
    state.app.include_router(routes.router, prefix="/api")
    assert (await state.client.get(path)).status_code == 401
    supplied = {**_headers("usr_identity"), "X-Role": "developer", "X-User-ID": "usr_other"}
    assert (await state.client.get(path, headers=supplied)).status_code == 403
    async with state.sessions() as session:
        user = await session.get(Users, "usr_identity")
        user.role = "developer"
        await session.commit()
    assert (await state.client.get(path, headers=supplied)).status_code == 200
    async with state.sessions() as session:
        user = await session.get(Users, "usr_identity")
        user.role = "user"
        await session.commit()
    assert (await state.client.get(path, headers=supplied)).status_code == 403


async def test_provenance_visibility_is_unchanged_by_entity_deletion(identity_state):
    state = identity_state
    state.app.include_router(routes.router, prefix="/api")
    async with state.sessions() as session:
        session.add(Studies(id="std_private", title="Synthetic study", user_id="usr_identity", is_demo=False))
        session.add(Personas(id="per_private", name="Synthetic persona", owner_id="usr_identity", study_id="std_private"))
        session.add_all([
            LLMRequests(request_id=request_id, owner_id=owner, persona_id=persona_id, task=TaskType.PERSONA_RESPONSE)
            for request_id, owner, persona_id in (
                ("req_owned", "usr_identity", "per_private"),
                ("req_unlinked", "usr_identity", None),
                ("req_orphan", "usr_identity", "per_never_saved"),
                ("req_foreign", "usr_other", "per_private"),
                ("req_unknown", None, "per_private"),
                ("req_unknown_unlinked", None, None),
            )
        ])
        await session.commit()
    before = await state.client.get("/api/provenance", headers=_headers("usr_identity"))
    assert before.status_code == 200
    expected = {"req_owned", "req_unlinked", "req_orphan"}
    assert {item["request_id"] for item in before.json()["items"]} == expected
    async with state.sessions() as session:
        persona = await session.get(Personas, "per_private")
        await session.delete(persona)
        await session.delete(await session.get(Studies, "std_private"))
        await session.commit()
    after = await state.client.get("/api/provenance", headers=_headers("usr_identity"))
    assert {item["request_id"] for item in after.json()["items"]} == expected
    assert after.json()["total"] == 3
    assert after.headers["cache-control"] == "no-store"
    foreign = await state.client.get("/api/provenance", headers=_headers("usr_other"))
    assert {item["request_id"] for item in foreign.json()["items"]} == {"req_foreign"}
    assert (await state.client.get("/api/provenance")).status_code == 401
    async with state.sessions() as session:
        assert len((await session.scalars(select(LLMRequests))).all()) == 6


async def test_provenance_ownership_cannot_be_reassigned(identity_state):
    async with identity_state.sessions() as session:
        record = LLMRequests(request_id="req_immutable", owner_id="usr_identity", task=TaskType.PERSONA_RESPONSE)
        session.add(record)
        await session.commit()
        record.owner_id = "usr_other"
        with pytest.raises(ValueError, match="immutable"):
            await session.commit()
        await session.rollback()
    async with identity_state.sessions() as session:
        assert (await session.get(LLMRequests, "req_immutable")).owner_id == "usr_identity"


@pytest.mark.parametrize("owner_id", [None, "", "usr_default", "anonymous", "usr_other"])
@pytest.mark.parametrize("write", [False, True])
def test_non_demo_studies_never_become_anonymous_resources(owner_id, write):
    study = Studies(id="std_legacy", title="Private by default", user_id=owner_id, is_demo=False)
    with pytest.raises(HTTPException) as error:
        deps.require_study_access(study, None, write=write)
    assert error.value.status_code == 404


def test_typed_study_guard_returns_owned_study_and_demo_remains_read_only():
    owner = Users(id="usr_identity")
    private = Studies(id="std_owned", user_id=owner.id, is_demo=False)
    demo = Studies(id="std_demo", user_id=None, is_demo=True)
    assert get_type_hints(deps.require_study_access)["return"] is Studies
    assert deps.require_study_access(private, owner, write=True) is private
    assert deps.require_study_access(demo, None) is demo
    with pytest.raises(HTTPException) as error:
        deps.require_study_access(demo, owner, write=True)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        deps.require_study_access(None, owner, write=True)
    assert error.value.status_code == 404


async def test_tenant_context_is_verified_and_isolated_across_concurrent_requests(identity_state):
    barrier = asyncio.Barrier(2)

    @identity_state.app.post("/trusted-context")
    async def trusted_context(payload: dict, user=Depends(deps.get_tenant_user)):
        before = get_tenant_owner_id()
        await barrier.wait()
        return {"before": before, "after": get_tenant_owner_id(), "user_id": user.id}

    assert get_tenant_owner_id() is None
    results = await asyncio.gather(*[
        identity_state.client.post("/trusted-context", json={"owner_id": "usr_forged"}, headers={
            **_headers(owner_id), "X-Tenant-ID": "usr_forged",
        })
        for owner_id in ("usr_identity", "usr_other")
    ])
    for owner_id, response in zip(("usr_identity", "usr_other"), results):
        assert response.status_code == 200
        assert response.json() == {"before": owner_id, "after": owner_id, "user_id": owner_id}
    assert get_tenant_owner_id() is None


async def test_invalid_optional_credentials_do_not_install_anonymous_context(identity_state):
    @identity_state.app.post("/optional-context")
    async def optional_context(user=Depends(deps.get_optional_tenant_user)):
        return {"owner_id": get_tenant_owner_id()}

    missing = await identity_state.client.post("/optional-context", headers={"X-User-ID": "usr_forged"})
    assert missing.status_code == 200
    assert missing.json() == {"owner_id": None}
    invalid = await identity_state.client.post("/optional-context", headers={"Authorization": "Bearer invalid"})
    assert invalid.status_code == 401
    assert get_tenant_owner_id() is None


@pytest.mark.parametrize("dependency", [
    deps.get_tenant_user, deps.get_optional_tenant_user,
    auth_api.get_current_user, auth_api.get_optional_current_user,
])
async def test_llm_context_is_private_and_owned_by_verified_identity(
    identity_state, dependency,
) -> None:
    barrier = asyncio.Barrier(2)

    @identity_state.app.post("/private-processing-context")
    async def processing_context(payload: dict, user=Depends(dependency)):
        before = get_llm_request_context()
        await barrier.wait()
        after = get_llm_request_context()
        return {
            "before": before.model_dump() if before else None,
            "after": after.model_dump() if after else None,
        }

    assert get_llm_request_context() is None
    responses = await asyncio.gather(*[
        identity_state.client.post("/private-processing-context", json={
            "owner_user_id": "usr_forged", "study_id": "std_foreign",
            "data_classification": "synthetic", "synthetic": True,
        }, headers={**_headers(owner_id), "X-Data-Classification": "synthetic"})
        for owner_id in ("usr_identity", "usr_other")
    ])
    for owner_id, response in zip(("usr_identity", "usr_other"), responses):
        assert response.status_code == 200
        expected = {"owner_user_id": owner_id, "study_id": None, "data_classification": "private"}
        assert response.json() == {"before": expected, "after": expected}
    assert get_llm_request_context() is None


@pytest.mark.parametrize("dependency", [auth_api.get_current_user, auth_api.get_optional_current_user])
async def test_private_context_cleans_up_after_endpoint_error(identity_state, dependency) -> None:
    observed = []

    @identity_state.app.get("/context-error")
    async def context_error(user=Depends(dependency)):
        observed.append(get_llm_request_context())
        raise HTTPException(409, "Synthetic test conflict")

    response = await identity_state.client.get("/context-error", headers=_headers("usr_identity"))

    assert response.status_code == 409
    assert observed[0] is not None
    assert observed[0].owner_user_id == "usr_identity"
    assert observed[0].data_classification == "private"
    assert get_llm_request_context() is None
    assert get_tenant_owner_id() is None