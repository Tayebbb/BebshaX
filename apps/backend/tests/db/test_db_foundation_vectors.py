"""Evidence vector retrieval uses PostgreSQL SQL or isolated SQLite scoring."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from bebshax.db.models import EvidenceChunks
from bebshax.llm.adapters.embeddings import CANONICAL_DIM
from bebshax.memory.orm import MemoryItems
from bebshax.research.vector_search import VectorSearchEngine


@pytest.fixture
def foundation_embedding_backend():
    return SimpleNamespace(
        space="foundation-test-space",
        embed=AsyncMock(return_value=[[1.0] + [0.0] * (CANONICAL_DIM - 1)]),
    )


@pytest.mark.asyncio
async def test_postgresql_vector_search_executes_filtered_limited_native_sql(
    foundation_embedding_backend,
) -> None:
    chunk = EvidenceChunks(id="native-result")
    session = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(chunk, 0.25)])),
    )

    results = await VectorSearchEngine(foundation_embedding_backend).search_chunks(
        session, "foundation-study", "query", top_k=3
    )

    assert results == [(chunk, 0.75)]
    session.execute.assert_awaited_once()
    compiled = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert " <=> " in sql
    assert "WHERE evidence_chunks.study_id =" in sql
    assert "evidence_chunks.embedding_space =" in sql
    assert "ORDER BY evidence_chunks.embedding <=>" in sql
    assert "LIMIT" in sql
    assert {"foundation-study", foundation_embedding_backend.space, 3} <= {
        value for value in compiled.params.values() if isinstance(value, (str, int))
    }


@pytest.mark.asyncio
async def test_postgresql_query_failure_is_not_retried_in_aborted_transaction(
    foundation_embedding_backend, caplog,
) -> None:
    failure = RuntimeError("synthetic-private-driver-detail")
    session = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=AsyncMock(side_effect=failure),
    )

    with pytest.raises(RuntimeError) as caught:
        await VectorSearchEngine(foundation_embedding_backend).search_chunks(
            session, "foundation-study", "query"
        )

    assert caught.value is failure
    session.execute.assert_awaited_once()
    assert str(failure) not in caplog.text


@pytest.mark.asyncio
async def test_sqlite_vector_roundtrip_and_scoring_remain_isolated(
    async_session, foundation_embedding_backend,
) -> None:
    positive = [1.0] + [0.0] * (CANONICAL_DIM - 1)
    orthogonal = [0.0, 1.0] + [0.0] * (CANONICAL_DIM - 2)
    for identifier, study, space, vector in (
        ("match", "foundation-study", foundation_embedding_backend.space, positive),
        ("other-direction", "foundation-study", foundation_embedding_backend.space, orthogonal),
        ("other-study", "different-study", foundation_embedding_backend.space, positive),
        ("other-space", "foundation-study", "different-space", positive),
    ):
        async_session.add(EvidenceChunks(
            id=identifier, source_id="foundation-source", study_id=study,
            content="Synthetic evidence", embedding=vector, embedding_space=space,
        ))
    await async_session.commit()
    async_session.expire_all()

    results = await VectorSearchEngine(foundation_embedding_backend).search_chunks(
        async_session, "foundation-study", "query", top_k=1
    )

    assert [(chunk.id, score) for chunk, score in results] == [("match", 1.0)]
    assert isinstance(results[0][0].embedding, list)
    assert results[0][0].embedding == positive


def test_evidence_vector_schema_compiles_for_both_dialects() -> None:
    table = EvidenceChunks.__table__

    assert f"embedding VECTOR({CANONICAL_DIM})" in str(
        CreateTable(table).compile(dialect=postgresql.dialect())
    )
    assert "embedding JSON" in str(CreateTable(table).compile(dialect=sqlite.dialect()))


@pytest.mark.parametrize(
    ("model", "index_name"),
    [
        (EvidenceChunks, "ix_evidence_chunks_embedding_hnsw"),
        (MemoryItems, "ix_memory_items_embedding_hnsw"),
    ],
)
def test_hnsw_indexes_survive_feature_table_constraints(model, index_name: str) -> None:
    indexes = [index for index in model.__table__.indexes if index.name == index_name]

    assert len(indexes) == 1
    assert "USING hnsw (embedding vector_cosine_ops)" in str(
        CreateIndex(indexes[0]).compile(dialect=postgresql.dialect())
    )
    assert indexes[0]._ddl_if.dialect == "postgresql"