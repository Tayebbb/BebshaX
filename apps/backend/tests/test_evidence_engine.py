import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.api.jobs import job_runtime, shutdown_jobs
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine
from bebshax.db.models import Base
from bebshax.jobs.store import SQLJobStore
from bebshax.llm.adapters.fake import FakeAdapter
from bebshax.llm.router import PoolRouter
from bebshax.llm.types import TaskType
from bebshax.main import create_app
from bebshax.research.chunker import chunk_document, clean_text
from bebshax.research.query_generator import derive_queries_from_study_text
from bebshax.research.search_provider import (
    ILLUSTRATIVE_SOURCE_PUBLISHER,
    IllustrativeSampleProvider,
    WikipediaResearchProvider,
    compute_content_hash,
    normalize_url,
)
from bebshax.research.service import ResearchEngineService
from bebshax.research.vector_search import VectorSearchEngine, _cosine_similarity


@pytest.fixture
async def evidence_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    research_llm: Callable[..., tuple[PoolRouter, FakeAdapter]],
    sample_evidence_provider: IllustrativeSampleProvider,
) -> AsyncIterator[FastAPI]:
    application = create_app()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'evidence_api.db'}")
    research_service = None
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        application.state.db_engine = engine
        application.state.db_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        llm, adapter = research_llm()
        application.state.llm_service = llm
        application.state.research_llm_adapter = adapter
        application.state.research_search_provider = sample_evidence_provider
        monkeypatch.setattr("bebshax.research.service._upload_dir", lambda: tmp_path / "uploads")
        research_service = ResearchEngineService(
            llm_service=llm,
            search_provider=sample_evidence_provider,
            discovery_engine=DatasetDiscoveryEngine(adapters=[]),
        )
        application.state.research_engine = research_service
        job_runtime(application)
        yield application
    finally:
        try:
            await shutdown_jobs(application)
        finally:
            try:
                if research_service is not None:
                    await research_service.aclose()
            finally:
                await engine.dispose()


@pytest.mark.asyncio
async def test_evidence_fixture_uses_a_private_app(evidence_app: FastAPI) -> None:
    from bebshax.main import app as shared_app

    assert evidence_app is not shared_app
    runtime = evidence_app.state.job_runtime
    assert isinstance(runtime.store, SQLJobStore)
    assert runtime.store is evidence_app.state.job_store
    assert runtime.store.sessionmaker is evidence_app.state.db_sessionmaker
    async with runtime.store.sessionmaker() as session:
        assert session.bind is evidence_app.state.db_engine
    research_service = evidence_app.state.research_engine
    assert research_service.llm_service is evidence_app.state.llm_service
    assert research_service.search_provider is evidence_app.state.research_search_provider


def test_clean_text_and_chunking():
    raw_html = "<p>Students at DU need <b>better study planners</b>.</p><script>bad()</script> They struggle with deadlines."
    cleaned = clean_text(raw_html)
    assert "<p>" not in cleaned
    assert "Students at DU need better study planners." in cleaned

    chunks = chunk_document(cleaned, chunk_size=30, chunk_overlap=5)
    assert len(chunks) >= 1
    for chk in chunks:
        assert len(chk) <= 60


def test_url_normalization_and_content_hash():
    url1 = "https://www.reddit.com/r/bangladesh/comments/123/?utm_source=share&utm_medium=web"
    url2 = "http://reddit.com/r/bangladesh/comments/123"
    assert normalize_url(url1) == normalize_url(url2)

    hash1 = compute_content_hash("Students prefer bKash payments for monthly subscriptions.")
    hash2 = compute_content_hash("  students PREFER bkash payments for monthly subscriptions.  ")
    assert hash1 == hash2


@pytest.mark.asyncio
async def test_sample_provider_is_explicit_and_labelled(sample_evidence_provider):
    with pytest.raises(ValueError):
        IllustrativeSampleProvider(sample_evidence_provider.documents)  # never wired by accident
    provider = sample_evidence_provider
    queries = derive_queries_from_study_text("AI study planner for university students", pricing_hypothesis="250 BDT/month")
    assert len(queries) >= 4

    sources = await provider.search(queries)
    assert len(sources) == 3
    for s in sources:
        assert s.title and s.url and s.content_hash
        assert s.publisher == ILLUSTRATIVE_SOURCE_PUBLISHER
        assert s.source_type == "curated_sample" and s.metadata["is_sample"] is True
        assert 0.0 <= s.relevance_score <= 1.0  # computed, not declared

    # Test embeddings
    engine = VectorSearchEngine()
    vectors = await engine.embed_texts([s.content for s in sources[:2]])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    sim = _cosine_similarity(vectors[0], vectors[0])
    assert pytest.approx(sim, 0.01) == 1.0


@pytest.mark.asyncio
async def test_wikipedia_provider_network_failure_yields_no_sources(monkeypatch):
    """Live provider degrades to *no evidence*, never to an invented corpus."""
    import httpx

    def _boom(request):
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_boom)) as client:
        provider = WikipediaResearchProvider(http_client=client)
        assert await provider.search(["anything"]) == []


@pytest.mark.asyncio
async def test_evidence_api_lifecycle_and_user_isolation(evidence_app: FastAPI) -> None:
    app = evidence_app
    session_maker = app.state.db_sessionmaker
    adapter = app.state.research_llm_adapter

    # Create Alice & Bob
    async with session_maker() as session:
        alice = Users(id="usr_alice", email="alice@research.com", hashed_password="hash", full_name="Alice", is_verified=True)
        bob = Users(id="usr_bob", email="bob@research.com", hashed_password="hash", full_name="Bob", is_verified=True)
        session.add_all([alice, bob])
        await session.commit()

    token_alice = create_access_token({"sub": "usr_alice", "email": "alice@research.com"})
    token_bob = create_access_token({"sub": "usr_bob", "email": "bob@research.com"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Alice creates a study
        res_study = await client.post(
            "/api/studies",
            headers={"Authorization": f"Bearer {token_alice}"},
            json={
                "prompt": "AI study planner for university students in Bangladesh with a 250 BDT/month tier",
                "type": "interviews",
                "target_audience": "University students in Dhaka",
                "pricing_hypothesis": "250 BDT/month via bKash",
            },
        )
        assert res_study.status_code == 201
        study = res_study.json()
        study_id = study["id"]

        # 2. Alice runs research — admitted as a durable job (202), then followed to completion.
        res_run = await client.post(
            f"/api/studies/{study_id}/research",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_run.status_code == 202, res_run.text
        accepted = res_run.json()
        assert accepted["status"] == "queued" and accepted["job_id"]
        await asyncio.wait_for(app.state.job_runtime.drain(), timeout=10)
        job = await client.get(
            f"/api/studies/{study_id}/research/jobs/{accepted['job_id']}",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert job.status_code == 200, job.text
        final = job.json()
        assert final["state"] == "completed", (final["state"], final.get("error_code"), final.get("error"))
        assert final["result_refs"]["run_id"] == accepted["id"]
        res_detail = await client.get(
            f"/api/studies/{study_id}/research/{accepted['id']}",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_detail.status_code == 200, res_detail.text
        run_data = res_detail.json()
        assert run_data["status"] == "completed", run_data["error_message"]
        assert run_data["query_count"] >= 3
        assert run_data["source_count"] == 3
        assert run_data["claim_count"] == 3
        # Provenance markers: everything model-written, nothing templated.
        summary = run_data["summary"]
        assert summary["plan_source"] == "llm" and summary["queries_source"] == "llm"
        assert summary["claims_status"] == "extracted" and summary["no_live_evidence"] is False
        assert summary["served_by"] == ["pollinations/deepseek-r1"]
        assert run_data["research_plan"]["source"] == "llm"
        # The model was asked three times: plan, queries, claims.
        assert [r.task for r in adapter.requests] == [
            TaskType.STRUCTURED_OUTPUT, TaskType.STRUCTURED_OUTPUT, TaskType.EVIDENCE_EXTRACTION
        ]
        # The claims prompt carried this study's chunks and the idea as untrusted data.
        claims_prompt = adapter.requests[-1].messages[-1].content
        assert "EVIDENCE_CHUNKS" in claims_prompt and "juggling several apps" in claims_prompt

        # 3. Evidence summary reflects the verified citation: one supported claim.
        res_summary = await client.get(
            f"/api/studies/{study_id}/evidence/summary",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_summary.status_code == 200
        summary = res_summary.json()
        assert summary["supported_count"] == 1
        assert summary["total_sources"] == 3

        # 4. Get claims list
        res_claims = await client.get(
            f"/api/studies/{study_id}/evidence/claims",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_claims.status_code == 200
        claims = res_claims.json()
        assert len(claims) == 3
        first_claim_id = claims[0]["id"]
        assert {c["status"] for c in claims} == {"supported", "inference", "unsupported"}
        supported = next(c for c in claims if c["status"] == "supported")
        assert supported["supporting_chunk_ids"] and supported["confidence"] > 0

        # 5. Get claim detail with provenance
        res_claim_detail = await client.get(
            f"/api/studies/{study_id}/evidence/claims/{first_claim_id}",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_claim_detail.status_code == 200
        claim_detail = res_claim_detail.json()
        assert "supporting_sources" in claim_detail
        assert "supporting_chunks" in claim_detail

        # 6. Semantic search against study chunks
        res_search = await client.post(
            f"/api/studies/{study_id}/evidence/search",
            headers={"Authorization": f"Bearer {token_alice}"},
            json={"query": "bKash subscription cost and spending habits", "top_k": 3},
        )
        assert res_search.status_code == 200
        search_results = res_search.json()
        assert len(search_results) >= 1
        assert "similarity_score" in search_results[0]

        # 7. User isolation: Bob cannot access Alice's research/claims
        bob_summary = await client.get(
            f"/api/studies/{study_id}/evidence/summary",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert bob_summary.status_code == 404

        bob_claims = await client.get(
            f"/api/studies/{study_id}/evidence/claims",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert bob_claims.status_code == 404

        bob_job = await client.get(
            f"/api/studies/{study_id}/research/jobs/{accepted['job_id']}",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert bob_job.status_code == 404
        bob_run = await client.get(
            f"/api/studies/{study_id}/research/{accepted['id']}",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert bob_run.status_code == 404
        bob_research = await client.post(
            f"/api/studies/{study_id}/research",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert bob_research.status_code == 404
        anonymous_research = await client.post(f"/api/studies/{study_id}/research")
        assert anonymous_research.status_code == 401

        # 8. Without an LLM the run fails explicitly at the plan step — no
        # template plan, queries or hypothesis claims are written (R2).
        app.state.llm_service = None
        app.state.research_engine.llm_service = None
        res_nollm = await client.post(
            f"/api/studies/{study_id}/research",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_nollm.status_code == 202, res_nollm.text
        accepted_nollm = res_nollm.json()
        assert accepted_nollm["status"] == "queued" and accepted_nollm["job_id"]
        await asyncio.wait_for(app.state.job_runtime.drain(), timeout=10)
        job = await client.get(
            f"/api/studies/{study_id}/research/jobs/{accepted_nollm['job_id']}",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert job.status_code == 200, job.text
        assert job.json()["state"] == "failed"
        res_failed = await client.get(
            f"/api/studies/{study_id}/research/{accepted_nollm['id']}",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_failed.status_code == 200, res_failed.text
        failed = res_failed.json()
        assert failed["status"] == "failed" and failed["current_step"] == "failed"
        assert failed["summary"]["error_code"] == "llm_unavailable"
        assert failed["summary"]["plan_source"] is None
        assert failed["claim_count"] == 0 and failed["research_plan"] is None
        assert "Research planning" in failed["error_message"]
