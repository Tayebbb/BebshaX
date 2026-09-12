"""Request-time owner capture is task-local and resets on every exit."""

import asyncio
from types import SimpleNamespace

import pytest

from bebshax.tenancy_context import capture_provenance_owner, get_tenant_owner_id, tenant_scope
from bebshax.persona.context import private_persona_context
from bebshax.llm.governance import LLMRequestContext, get_llm_request_context, llm_request_context


def test_nested_owner_scopes_reset_after_exception() -> None:
    assert get_tenant_owner_id() is None
    with tenant_scope("outer-owner"):
        with pytest.raises(RuntimeError):
            with tenant_scope("inner-owner"):
                assert get_tenant_owner_id() == "inner-owner"
                raise RuntimeError("test exit")
        assert get_tenant_owner_id() == "outer-owner"
    assert get_tenant_owner_id() is None


async def test_concurrent_request_owners_do_not_leak() -> None:
    arrived = asyncio.Queue()
    release = asyncio.Event()

    async def request(owner_id: str) -> str | None:
        with tenant_scope(owner_id):
            await arrived.put(owner_id)
            await release.wait()
            return capture_provenance_owner(SimpleNamespace())

    first = asyncio.create_task(request("first-owner"))
    second = asyncio.create_task(request("second-owner"))
    await arrived.get()
    await arrived.get()
    release.set()
    assert await asyncio.gather(first, second) == ["first-owner", "second-owner"]
    assert get_tenant_owner_id() is None


def test_submission_capture_outlives_request_and_unknown_stays_private() -> None:
    assert capture_provenance_owner(SimpleNamespace()) is None
    with tenant_scope("submitted-owner"):
        captured = capture_provenance_owner(SimpleNamespace())
    assert captured == "submitted-owner"
    assert get_tenant_owner_id() is None
    assert capture_provenance_owner(SimpleNamespace(owner_id="explicit-owner")) == "explicit-owner"


def test_conflicting_explicit_owner_is_rejected() -> None:
    with tenant_scope("request-owner"):
        with pytest.raises(ValueError, match="owner"):
            capture_provenance_owner(SimpleNamespace(owner_id="foreign-owner"))


@pytest.mark.parametrize("owner", ["", " owner ", "usr_system_holder", "x" * 65])
def test_private_persona_context_rejects_ambiguous_owners(owner):
    with pytest.raises(ValueError, match="verified owner"):
        with private_persona_context(owner):
            raise AssertionError("Invalid owner entered private processing")


def test_private_persona_context_cannot_replace_verified_caller():
    with tenant_scope("first-owner"):
        with pytest.raises(ValueError, match="ownership"):
            with private_persona_context("second-owner"):
                raise AssertionError("Conflicting owner entered private processing")
    with llm_request_context(LLMRequestContext(owner_user_id="first-owner", study_id="first-study")):
        before = get_llm_request_context()
        with pytest.raises(ValueError, match="study"):
            with private_persona_context("first-owner", "second-study"):
                raise AssertionError("Conflicting study entered private processing")
        assert get_llm_request_context() is before


def test_private_persona_context_restores_scope_on_failure():
    with tenant_scope("first-owner"), llm_request_context(LLMRequestContext(owner_user_id="first-owner")):
        before = get_llm_request_context()
        with pytest.raises(RuntimeError, match="synthetic failure"):
            with private_persona_context("first-owner", "private-study"):
                assert get_llm_request_context().study_id == "private-study"
                raise RuntimeError("synthetic failure")
        assert get_llm_request_context() is before
        assert get_tenant_owner_id() == "first-owner"