"""Backend forwarding for immutable ML selection identity and trusted artifacts."""

import hashlib
import json
from pathlib import Path

import pytest
from bebshax_persona_ml.data import TrainingRecord, fingerprint
from bebshax_persona_ml.model import BusinessContext, ModelConfig, PersonaModel, Selection
from bebshax_persona_ml.provenance import ExpectedArtifactManifest, SourceAttribution

from bebshax.api.errors import APIError
from bebshax.personas.ml_adapter import (
    MLPersonaAdapter, to_generated_persona, to_persona_draft, to_persona_profile, to_workflow_persona,
)


@pytest.fixture
def adapter_records() -> list[TrainingRecord]:
    return [
        TrainingRecord(
            record_id=f"source-{index}", source="synthetic-test-source", revision="fixture-v1",
            name=f"Fixture Person {index}", age=30 + index, occupation=occupation,
            description=description, location="Austin", education="College",
            goals=[goal, "Organize a schedule"], pain_points=[pain, "Limited time"],
        )
        for index, (occupation, description, goal, pain) in enumerate([
            ("Farmer", "Maintains apple orchard irrigation and harvest systems.", "Conserve irrigation", "Crop pests"),
            ("Astronomer", "Observes distant galaxies with telescopes.", "Schedule observations", "Cloudy skies"),
            ("Baker", "Prepares sourdough bread recipes and pastries.", "Perfect baking", "Oven repairs"),
            ("Engineer", "Designs bridge structures and concrete beams.", "Build bridges", "Structural constraints"),
        ])
    ]


@pytest.mark.parametrize("strategy,topic", [("lexical", None), ("nmf", 1)])
def test_all_converters_preserve_complete_selection_identity(adapter_records, strategy, topic) -> None:
    record = adapter_records[0]
    attribution = SourceAttribution.unavailable(record.source, record.revision)
    selection = Selection(
        record=record, score=0.5, topic=topic, model_version="fixture-version", strategy=strategy,
        source_attribution=attribution, source_corpus_sha256="a" * 64, training_code_sha256="b" * 64,
    )
    expected = {
        "source": record.source, "revision": record.revision, "record_id": record.record_id,
        "model_version": selection.model_version, "selection_score": selection.score, "topic": topic,
        "strategy": strategy, "source_attribution": attribution.model_dump(mode="json"),
        "source_corpus_sha256": "a" * 64, "training_code_sha256": "b" * 64,
    }
    generated = to_generated_persona(selection)
    profile = to_persona_profile(selection, "business")
    draft = to_persona_draft(selection)
    workflow = to_workflow_persona(selection, role_id="farmer", role_title="Farmer")
    for output in (generated, profile, draft):
        assert output.detailed_attributes["ml_provenance"] == expected
    assert workflow["detailed_attributes"]["ml_provenance"] == expected
    assert workflow["dataset_refs"] == draft.dataset_refs == [expected]
    assert attribution.metadata_status == "unavailable"


async def test_trusted_manifest_rejects_replacement_before_inference(tmp_path: Path, adapter_records) -> None:
    artifact = tmp_path / "trusted-model"
    PersonaModel.fit(adapter_records, ModelConfig(strategy="lexical", lexical_weight=1.0)).save(artifact)
    expected = ExpectedArtifactManifest(metadata_sha256=hashlib.sha256((artifact / "metadata.json").read_bytes()).hexdigest())
    adapter = MLPersonaAdapter(artifact, expected_manifest=expected)
    selected = await adapter.generate(BusinessContext(description="orchard"), 1, seed=1)
    assert selected[0].record.record_id == "source-0"
    rejected = MLPersonaAdapter(artifact, expected_manifest=ExpectedArtifactManifest(metadata_sha256="0" * 64))
    with pytest.raises(APIError) as error:
        await rejected.generate(BusinessContext(description="orchard"), 1)
    assert error.value.status_code == 503
    assert error.value.error_code == "ml_persona_unavailable"
    assert str(artifact) not in error.value.detail


async def test_cached_artifact_does_not_auto_promote(tmp_path: Path, adapter_records) -> None:
    artifact = tmp_path / "frozen-model"
    original = PersonaModel.fit(adapter_records, ModelConfig(strategy="lexical", lexical_weight=1.0, seed=1))
    original.save(artifact)
    expected = ExpectedArtifactManifest(metadata_sha256=hashlib.sha256((artifact / "metadata.json").read_bytes()).hexdigest())
    adapter = MLPersonaAdapter(artifact, expected_manifest=expected)
    context = BusinessContext(description="orchard")
    first = await adapter.generate(context, 1, seed=1)
    PersonaModel.fit(adapter_records, ModelConfig(strategy="lexical", lexical_weight=1.0, seed=2)).save(artifact)
    second = await adapter.generate(context, 1, seed=1)
    assert first[0].model_version == second[0].model_version == original.version
    with pytest.raises(APIError) as error:
        await MLPersonaAdapter(artifact, expected_manifest=expected).generate(context, 1)
    assert error.value.status_code == 503


async def test_zero_relevance_and_capacity_errors_are_deterministic(tmp_path: Path, adapter_records) -> None:
    artifact = tmp_path / "capacity-model"
    PersonaModel.fit(adapter_records, ModelConfig(strategy="lexical", lexical_weight=1.0)).save(artifact)
    adapter = MLPersonaAdapter(artifact)
    for seed in (0, 1, 42):
        selection = await adapter.generate(BusinessContext(description="orchard"), 1, seed=seed)
        assert selection[0].record.record_id == "source-0"
        for description, count, exclusions in (("orchard", 2, set()), ("orchard", 1, {"source-0"}), ("qzxwvyplm", 1, set())):
            with pytest.raises(APIError) as error:
                await adapter.generate(BusinessContext(description=description), count, seed=seed, exclude_ids=exclusions)
            assert error.value.status_code == 422
            assert error.value.error_code == "ml_persona_unsupported_context"


async def test_old_schema_baseline_stays_nmf_without_inventing_training_digest(tmp_path: Path, adapter_records) -> None:
    artifact = tmp_path / "legacy-baseline"
    PersonaModel.fit(adapter_records, ModelConfig(n_topics=2, max_iter=1000)).save(artifact)
    config_path = artifact / "config.json"
    configuration = json.loads(config_path.read_text(encoding="utf-8"))
    configuration.pop("strategy")
    config_bytes = json.dumps(configuration).encode("utf-8")
    config_path.write_bytes(config_bytes)
    metadata_path = artifact / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["schema_version"] = 1
    metadata.pop("provenance", None)
    metadata["files"]["config.json"] = hashlib.sha256(config_bytes).hexdigest()
    version = fingerprint({"corpus": metadata["corpus_fingerprint"], "config": configuration, "algorithm": "tfidf-nmf-mmr-v1"})
    metadata["model_version"] = version
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    adapter = MLPersonaAdapter(artifact)
    first = await adapter.generate(BusinessContext(description="orchard"), 1, seed=42)
    second = await adapter.generate(BusinessContext(description="orchard"), 1, seed=42)
    assert first == second
    provenance = to_persona_draft(first[0]).detailed_attributes["ml_provenance"]
    assert provenance["model_version"] == version
    assert provenance["strategy"] == "nmf"
    assert provenance["topic"] is not None
    assert provenance["training_code_sha256"] is None