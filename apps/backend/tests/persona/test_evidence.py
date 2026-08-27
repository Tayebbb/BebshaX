import json
from pathlib import Path

from bebshax.persona.evidence import EvidenceStore


def test_retrieval_ranks_matching_records_first(evidence_store) -> None:
    items = evidence_store.retrieve("late food delivery problems", k=3)
    assert items
    assert "delivery arrived late" in items[0].text
    assert items[0].relevance == 1.0  # normalized top score
    assert all(0.0 <= item.relevance <= 1.0 for item in items)


def test_retrieval_respects_k_and_source_caps(evidence_store) -> None:
    # the fixture has TWO matching amazon records — with the cap deleted,
    # amazon would appear twice in the top-3
    items = evidence_store.retrieve("student delivery food online", k=3, per_source_cap=1)
    sources = [item.source for item in items]
    assert len(sources) == len(set(sources))  # per-source cap of 1
    assert sources.count("amazon_reviews_office_products") == 1


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


def test_seed_datasets_are_never_citable_evidence(evidence_store) -> None:
    """PersonaHub sketches are synthetic — retrieving one as evidence would
    let an invented fact wear an OBSERVED badge (dataset role table)."""
    # query built from the personahub fixture rows' own vocabulary
    items = evidence_store.retrieve("budget-conscious university student Dhaka organic groceries", k=6)
    assert all(item.source != "personahub_sample" for item in items)
    # …while the same rows still power diversity seeds
    assert evidence_store.seed_persona("any-key") is not None


def test_probe_datasets_never_load_as_evidence(tmp_path) -> None:
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "gsm8k_micro.jsonl").write_text(
        json.dumps({"text": "Natalia sold clips to 48 friends in April and half as many in May."}),
        encoding="utf-8",
    )
    store = EvidenceStore(processed)
    assert store.retrieve("Natalia sold clips April friends") == []
    assert store.available_sources() == {}


def test_unknown_datasets_default_to_grounding(tmp_path) -> None:
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "my_uploaded_survey.jsonl").write_text(
        json.dumps({"text": "Respondents complained about weekly delivery delays across Dhaka."}),
        encoding="utf-8",
    )
    store = EvidenceStore(processed)
    items = store.retrieve("delivery delays Dhaka respondents")
    assert items and items[0].source == "my_uploaded_survey"


def test_noise_records_are_filtered(tmp_path) -> None:
    """Duplicates and one-liners dilute idf statistics — both are dropped."""
    processed = tmp_path / "processed"
    processed.mkdir()
    review = "The delivery packaging was damaged and support never replied to my complaint."
    rows = [
        {"text": review},
        {"text": review},  # exact duplicate
        {"text": "  " + review + " "},  # whitespace-variant duplicate
        {"text": "Great!"},  # below the noise floor
    ]
    (processed / "amazon_reviews_office_products.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )
    store = EvidenceStore(processed)
    assert store.available_sources() == {"amazon_reviews_office_products": 1}


def test_every_managed_dataset_has_an_explicit_role() -> None:
    """New manifest datasets must not ship without a role decision — the
    fail-open grounding default exists for USER-dropped corpora only."""
    from bebshax.persona.evidence import DATASET_ROLES
    from scripts.dataset_manifest import DATASET_MANIFEST

    manifest_ids = {entry.dataset_id for entry in DATASET_MANIFEST}
    missing = manifest_ids - set(DATASET_ROLES)
    assert not missing, f"datasets without a DATASET_ROLES entry: {missing}"
