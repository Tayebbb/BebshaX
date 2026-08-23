from pathlib import Path

from bebshax.persona.evidence import EvidenceStore


def test_retrieval_ranks_matching_records_first(evidence_store) -> None:
    items = evidence_store.retrieve("late food delivery problems", k=3)
    assert items
    assert "delivery arrived late" in items[0].text
    assert items[0].relevance == 1.0  # normalized top score
    assert all(0.0 <= item.relevance <= 1.0 for item in items)


def test_retrieval_respects_k_and_source_caps(evidence_store) -> None:
    items = evidence_store.retrieve("student delivery food online", k=2, per_source_cap=1)
    assert len(items) <= 2
    sources = [item.source for item in items]
    assert len(sources) == len(set(sources))  # per-source cap of 1


def test_missing_processed_dir_degrades_gracefully(tmp_path) -> None:
    store = EvidenceStore(Path(tmp_path) / "does-not-exist")
    assert store.retrieve("anything") == []
    assert store.seed_persona("key") is None


def test_seed_persona_is_deterministic(evidence_store) -> None:
    a = evidence_store.seed_persona("same-key")
    b = evidence_store.seed_persona("same-key")
    assert a == b and a is not None


def test_nonsense_query_returns_nothing(evidence_store) -> None:
    assert evidence_store.retrieve("qqqqxyzzy zzduetp") == []
