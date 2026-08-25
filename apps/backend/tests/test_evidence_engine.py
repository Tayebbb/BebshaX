import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, Studies
from bebshax.main import app
from bebshax.research.chunker import chunk_document, clean_text
from bebshax.research.query_generator import generate_deterministic_queries
from bebshax.research.search_provider import (
    CuratedResearchProvider,
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
async def test_search_provider_and_embeddings():
    provider = CuratedResearchProvider()
    queries = generate_deterministic_queries("AI study planner for Bangladeshi students", pricing_hypothesis="250 BDT/month")
    assert len(queries) >= 4

    sources = await provider.search(queries)
    assert len(sources) >= 3
    for s in sources:
        assert s.title
        assert s.url
        assert s.content_hash
        assert s.relevance_score >= 0.6

    # Test embeddings
    engine = VectorSearchEngine()
    vectors = await engine.embed_texts([s.content for s in sources[:2]])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    sim = _cosine_similarity(vectors[0], vectors[0])
    assert pytest.approx(sim, 0.01) == 1.0


@pytest.mark.asyncio
async def test_evidence_api_lifecycle_and_user_isolation():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

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
        assert run_data["status"] == "completed"
        assert run_data["query_count"] >= 3
        assert run_data["source_count"] >= 3
        assert run_data["claim_count"] >= 3

        # 3. Get evidence summary
        res_summary = await client.get(
            f"/api/studies/{study_id}/evidence/summary",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_summary.status_code == 200
        summary = res_summary.json()
        assert summary["evidence_coverage"] > 0
        assert summary["supported_count"] >= 1
        assert summary["total_sources"] >= 3

        # 4. Get claims list
        res_claims = await client.get(
            f"/api/studies/{study_id}/evidence/claims",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_claims.status_code == 200
        claims = res_claims.json()
        assert len(claims) >= 3
        first_claim_id = claims[0]["id"]

        # Verify claim statuses are properly separated (GREEN/AMBER/RED)
        statuses = {c["status"] for c in claims}
        assert "supported" in statuses
        assert any(c["status"] in ("inference", "unsupported") for c in claims)

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

    await engine.dispose()
