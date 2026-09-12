"""Dataset persona synthesis honesty (GROUP P): the offline template is fully
SYNTHETIC and labelled, LLM claims are coerced against the record ids actually
shown, and every persona carries its real origin model."""

from copy import deepcopy
import hashlib
import json

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bebshax.interview.orm  # noqa: F401
import bebshax.memory.orm  # noqa: F401
import bebshax.persona.orm  # noqa: F401
from bebshax.config import get_settings
from bebshax.api.errors import APIError
from bebshax.auth.models import Users
from bebshax.datasets.orm import DatasetVersions
from bebshax.datasets.service import (
    DATASET_PERSONA_UNPARSEABLE,
    DatasetService,
    coerce_claim_provenance,
    record_evidence_id,
)
from bebshax.db.models import Base, DatasetPersonaRuns, DatasetSources, Personas
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.prompt_safety import UNTRUSTED_RULE
from bebshax.personas.ml_adapter import MLPersonaAdapter
from bebshax.utils.explicit_failures import UnusableModelOutput

_CLAIM_GROUPS = (
    "goals",
    "pain_points",
    "needs",
    "motivations",
    "behaviors",
    "technology_usage",
    "purchase_behavior",
    "personality_traits",
)

_RECORD = {"student_id": 1, "name": "Rahim", "role": "Student", "age": 21, "monthly_budget": 350}
_SEGMENT = {
    "id": "seg_1",
    "name": "Budget Students",
    "population_percentage": 100.0,
    "population_share": 1.0,
    "segmentation_feature": "role",
    # Observed per-group statistics keyed by the dataset's own columns.
    "constraints": {
        "rule_description": "role == 'Student' (100.0% of 1 observed records)",
        "age": {"count": 1, "min": 20, "median": 21, "max": 23, "p75": 23},
        "monthly_budget": {"count": 1, "min": 300, "median": 350, "max": 400, "p75": 400},
    },
    "sample_records": [_RECORD],
}


def _llm_persona(evidence_ids: list[str]) -> str:
    claim = {"value": "Keeps a tight monthly budget", "provenance": "OBSERVED", "evidence_ids": evidence_ids}
    return json.dumps(
        {
            "name": "Tania Rahman",
            "age": 21,
            "occupation": "Student",
            "location": "Dhaka",
            "income_range": "৳350 per month",
            "education": "Undergraduate",
            "description": "Budget-conscious student.",
            "goals": [claim],
            "pain_points": [{"value": "Fees", "provenance": "OBSERVED", "evidence_ids": ["rec_fabricated"]}],
            "needs": [{"value": "Alerts", "provenance": "TOTALLY_TRUE", "evidence_ids": []}],
            "motivations": [{"value": "Value", "provenance": "INFERRED", "evidence_ids": []}],
            "behaviors": ["plain string claim"],
            "technology_usage": [],
            "purchase_behavior": [],
            "personality_traits": [],
        }
    )


# --- pure helpers -----------------------------------------------------------------


def test_persona_hardening_no_offline_template_exists() -> None:
    import inspect

    from bebshax.datasets import service

    src = inspect.getsource(service)
    for remnant in ("_generate_offline_fallback_persona", "OFFLINE_FALLBACK_MODEL", "Dhaka, Bangladesh", "bKash", "Samiul Alam"):
        assert remnant not in src, remnant


def test_persona_hardening_record_ids_are_stable_and_content_derived() -> None:
    rid = record_evidence_id(_RECORD)
    assert rid.startswith("rec_") and len(rid) == 16
    assert rid == record_evidence_id(dict(reversed(list(_RECORD.items()))))  # key order irrelevant
    assert rid != record_evidence_id({**_RECORD, "age": 22})


def test_persona_hardening_claim_coercion_only_trusts_shown_ids() -> None:
    shown = record_evidence_id(_RECORD)
    persona = coerce_claim_provenance(json.loads(_llm_persona([shown, "rec_made_up"])), {shown})
    assert persona["goals"][0]["provenance"] == "OBSERVED"
    assert persona["goals"][0]["evidence_ids"] == [shown]
    assert persona["pain_points"][0] == {"value": "Fees", "provenance": "INFERRED", "evidence_ids": []}
    assert persona["needs"][0]["provenance"] == "SYNTHETIC"
    assert persona["motivations"][0]["provenance"] == "INFERRED"
    assert persona["behaviors"][0] == {"value": "plain string claim", "provenance": "SYNTHETIC", "evidence_ids": []}


# --- service end to end -------------------------------------------------------


@pytest_asyncio.fixture
async def dataset_session_maker(tmp_path, monkeypatch):
    monkeypatch.setenv("BEBSHAX_UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    records = json.dumps([_RECORD]).encode("utf-8")
    digest = hashlib.sha256(records).hexdigest()
    file_path = upload_root / f"ds_test.v_0123456789abcdef.{digest}.json"
    file_path.write_bytes(records)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add(Users(id="usr_test", email="persona-hardening@example.test", full_name="Synthetic owner"))
        await session.flush()
        session.add(
            DatasetSources(
                id="ds_test",
                user_id="usr_test",
                name="Student survey",
                source_type="upload",
                file_type="csv",
                status="ready",
                row_count=1,
                column_count=5,
                segments=[deepcopy(_SEGMENT)],
                file_path=str(file_path),
                content_hash=digest,
                persona_count_generated=0,
            )
        )
        await session.flush()
        session.add(DatasetVersions(
            id="ds_test_version", dataset_id="ds_test", owner_id="usr_test", version=1,
            content_hash=digest, records_hash=digest, file_path=str(file_path), file_type="csv",
            row_count=1, column_count=5, schema_metadata={}, statistics={}, segments=[deepcopy(_SEGMENT)],
        ))
        await session.commit()
    yield maker
    await engine.dispose()
    get_settings.cache_clear()


async def test_persona_hardening_missing_ml_model_fails_explicitly(dataset_session_maker, tmp_path) -> None:
    service = DatasetService(dataset_session_maker, ml_generator=MLPersonaAdapter(tmp_path / "missing-model"))
    with pytest.raises(APIError) as raised:
        await service.generate_personas_from_dataset(
            "ds_test", requested_count=2, user_id="usr_test", business_description="Food delivery for students",
        )
    assert raised.value.status_code == 503
    assert raised.value.error_code == "ml_persona_unavailable"

    async with dataset_session_maker() as session:
        assert list((await session.execute(select(Personas))).scalars()) == []
        assert list((await session.execute(select(DatasetPersonaRuns))).scalars()) == []


async def test_persona_hardening_llm_claims_are_coerced_against_shown_records(dataset_session_maker) -> None:
    shown = record_evidence_id(_RECORD)
    adapter = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m9"), replies=[_llm_persona([shown, "rec_made_up"])])]
    )
    service = DatasetService(dataset_session_maker, llm=SingleAdapterLLMService(adapter))
    result = await service.generate_personas_from_dataset("ds_test", requested_count=1, user_id="usr_test")

    [persona] = result["personas"]
    assert persona["model_used"] == "m9" and persona["served_by"] == "fake/m9"
    assert result["served_by"] == ["fake/m9"] and result["failed"] == []
    assert persona["goals"][0]["provenance"] == "OBSERVED" and persona["goals"][0]["evidence_ids"] == [shown]
    assert persona["pain_points"][0]["provenance"] == "INFERRED" and persona["pain_points"][0]["evidence_ids"] == []

    # the prompt shows the record under its stable id, inside an untrusted block,
    # and only the OBSERVED per-group statistics — no assumed defaults
    request = adapter.requests[0]
    assert UNTRUSTED_RULE in request.messages[0].content
    prompt = request.messages[1].content
    assert f"[{shown}]" in prompt
    assert "<UNTRUSTED_DATASET_RECORDS" in prompt and prompt.count("</UNTRUSTED_DATASET_RECORDS>") == 1
    assert '- monthly_budget: {"count": 1, "min": 300' in prompt and "- age: " in prompt
    for assumed in ("৳", "Medium", "Core functionality", "[18, 50]"):
        assert assumed not in prompt, assumed

    async with dataset_session_maker() as session:
        [row] = list((await session.execute(select(Personas))).scalars())
    assert row.generation_model == "fake/m9"
    assert row.country_code is None  # not stated by the model -> not assumed


async def test_persona_hardening_unusable_reply_is_recorded_not_replaced(dataset_session_maker) -> None:
    shown = record_evidence_id(_RECORD)
    adapter = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m9"), replies=['{"name": ""}', '{"goals": []}', _llm_persona([shown])])]
    )
    service = DatasetService(dataset_session_maker, llm=SingleAdapterLLMService(adapter))
    result = await service.generate_personas_from_dataset("ds_test", requested_count=2, user_id="usr_test")

    # persona #1: two unusable replies -> recorded as failed; persona #2 succeeds.
    assert result["failed_count"] == 1 and result["generated_count"] == 1
    assert result["failed"][0]["error_code"] == DATASET_PERSONA_UNPARSEABLE
    assert len(adapter.requests) == 3
    async with dataset_session_maker() as session:
        rows = list((await session.execute(select(Personas))).scalars())
    assert len(rows) == 1 and rows[0].generation_model == "fake/m9"


async def test_persona_hardening_all_unusable_raises(dataset_session_maker) -> None:
    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="m9"), reply='{"name": ""}')])
    service = DatasetService(dataset_session_maker, llm=SingleAdapterLLMService(adapter))
    with pytest.raises(UnusableModelOutput) as info:
        await service.generate_personas_from_dataset("ds_test", requested_count=1, user_id="usr_test")
    assert info.value.error_code == DATASET_PERSONA_UNPARSEABLE
    async with dataset_session_maker() as session:
        assert list((await session.execute(select(Personas))).scalars()) == []


async def test_dataset_persona_prompt_retains_every_supplied_evidence_record(dataset_session_maker):
    tail = {**_RECORD, "student_id": 3, "name": "Synthetic tail evidence"}
    async with dataset_session_maker() as session, session.begin():
        dataset = await session.get(DatasetSources, "ds_test")
        dataset.segments = [{**_SEGMENT, "sample_records": [_RECORD, {**_RECORD, "student_id": 2}, tail]}]
    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="m9"), reply=_llm_persona([record_evidence_id(tail)]))])
    service = DatasetService(dataset_session_maker, llm=SingleAdapterLLMService(adapter))
    await service.generate_personas_from_dataset("ds_test", requested_count=1, user_id="usr_test")
    prompt = adapter.requests[0].messages[1].content
    assert record_evidence_id(tail) in prompt
    assert "Synthetic tail evidence" in prompt


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_persona_hardening_coercion_tolerates_non_list_groups(bad) -> None:
    persona = {"goals": bad, "needs": "not a list"}
    assert coerce_claim_provenance(persona, set()) == {"goals": bad, "needs": "not a list"}
