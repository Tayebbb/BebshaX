import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base
from bebshax.llm.types import TaskType
from bebshax.main import app
from bebshax.research.chunker import chunk_document, clean_text
from bebshax.research.query_generator import derive_queries_from_study_text
from bebshax.research.search_provider import (
    ILLUSTRATIVE_SOURCE_PUBLISHER,
    IllustrativeSampleProvider,
    WikipediaResearchProvider,
    compute_content_hash,
    normalize_url,
)
from bebshax.research.vector_search import VectorSearchEngine, _cosine_similarity


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

    provider = WikipediaResearchProvider(http_client=httpx.AsyncClient(transport=httpx.MockTransport(_boom)))
    assert await provider.search(["anything"]) == []


@pytest.mark.asyncio
async def test_evidence_api_lifecycle_and_user_isolation(research_llm, sample_evidence_provider):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker
    llm, adapter = research_llm(app)
    app.state.llm_service = llm
    app.state.research_search_provider = sample_evidence_provider

    # Create Alice & Bob
    async with session_maker() as session:
        alice = Users(id="usr_alice", email="alice@research.com", hashed_password="hash", full_name="Alice")
        bob = Users(id="usr_bob", email="bob@research.com", hashed_password="hash", full_name="Bob")
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

        # 2. Alice runs research
        res_run = await client.post(
            f"/api/studies/{study_id}/research",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_run.status_code == 201
        run_data = res_run.json()
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

        # 8. Without an LLM the run fails explicitly at the plan step — no
        # template plan, queries or hypothesis claims are written (R2).
        app.state.llm_service = None
        res_nollm = await client.post(
            f"/api/studies/{study_id}/research",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_nollm.status_code == 201
        failed = res_nollm.json()
        assert failed["status"] == "failed" and failed["current_step"] == "failed"
        assert failed["summary"]["error_code"] == "llm_unavailable"
        assert failed["summary"]["plan_source"] is None
        assert failed["claim_count"] == 0 and failed["research_plan"] is None
        assert "Research planning" in failed["error_message"]

    app.state.llm_service = None
    app.state.research_search_provider = None
    await engine.dispose()
