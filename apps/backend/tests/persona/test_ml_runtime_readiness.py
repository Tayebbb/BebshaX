import asyncio
import hashlib
import json
import threading
from pathlib import Path

import pytest
from bebshax_persona_ml.model import BusinessContext, PersonaModel
from bebshax_persona_ml.provenance import ExpectedArtifactManifest

from bebshax.api.errors import APIError
from bebshax.main import _persona_capability
from bebshax.personas.ml_adapter import MLPersonaAdapter


def expected_manifest(artifact: Path) -> ExpectedArtifactManifest:
    return ExpectedArtifactManifest(
        metadata_sha256=hashlib.sha256((artifact / "metadata.json").read_bytes()).hexdigest(),
    )


async def test_schema3_startup_is_configured_without_loading_weights(
    ml_artifact: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_load(*args, **kwargs):
        pytest.fail("Readiness must not load model weights")

    assert json.loads((ml_artifact / "metadata.json").read_bytes())["schema_version"] == 3
    monkeypatch.setattr(PersonaModel, "load", forbidden_load)
    expected = expected_manifest(ml_artifact)
    adapter = MLPersonaAdapter(ml_artifact, expected_manifest=expected)

    assert await _persona_capability(adapter, expected) == {
        "status": "configured", "reason": "lazy_model_load_pending",
    }
    assert adapter._model is None


async def test_readiness_reports_manifest_only_and_runs_off_event_loop(
    ml_artifact: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = Path.open
    manifest_threads = []

    def tracked_open(path, *args, **kwargs):
        if path.parent == ml_artifact:
            assert path.name == "metadata.json", "Readiness must not read model payloads"
            manifest_threads.append(threading.get_ident())
        return original_open(path, *args, **kwargs)

    expected = expected_manifest(ml_artifact)
    adapter = MLPersonaAdapter(ml_artifact, expected_manifest=expected)
    monkeypatch.setattr(Path, "open", tracked_open)
    status = await adapter.readiness()

    assert status == {
        "status": "configured", "reason": "lazy_model_load_pending",
        "validation": "manifest", "model_loaded": False,
        "expected_manifest_matched": True,
    }
    assert manifest_threads and all(worker != threading.get_ident() for worker in manifest_threads)
    assert adapter._model is None


@pytest.mark.parametrize("corruption", ["missing", "malformed", "oversized", "runtime", "tokenizer", "digest", "payload"])
async def test_readiness_rejects_bad_manifests_without_disclosing_paths(
    ml_artifact: Path, corruption: str,
) -> None:
    manifest = ml_artifact / "metadata.json"
    metadata = json.loads(manifest.read_bytes())
    if corruption == "missing":
        manifest.unlink()
    elif corruption == "malformed":
        manifest.write_text("{}", encoding="utf-8")
    elif corruption == "oversized":
        manifest.write_text(" " * 65537, encoding="utf-8")
    elif corruption == "payload":
        (ml_artifact / "parameters.npz").unlink()
    else:
        if corruption == "runtime":
            metadata["runtime"]["numpy"] = "0.0.0"
        elif corruption == "tokenizer":
            metadata["tokenizer_contract"] = None
        else:
            metadata["files"]["config.json"] = "not-a-digest"
        manifest.write_text(json.dumps(metadata), encoding="utf-8")
    adapter = MLPersonaAdapter(ml_artifact)

    status = await adapter.readiness()

    assert status["status"] == "unavailable"
    assert status["model_loaded"] is False
    assert str(ml_artifact) not in json.dumps(status)
    assert adapter._model is None


async def test_readiness_rejects_expected_manifest_mismatch(ml_artifact: Path) -> None:
    adapter = MLPersonaAdapter(ml_artifact, expected_manifest=ExpectedArtifactManifest(metadata_sha256="0" * 64))

    status = await adapter.readiness()

    assert status["status"] == "unavailable"
    assert status["expected_manifest_matched"] is False
    assert adapter._model is None
    with pytest.raises(APIError) as raised:
        await adapter.generate(BusinessContext(description="Food delivery"), 1)
    assert raised.value.error_code == "ml_persona_unavailable"


async def test_readiness_only_claims_available_after_successful_loader(ml_artifact: Path) -> None:
    adapter = MLPersonaAdapter(ml_artifact, expected_manifest=expected_manifest(ml_artifact))
    await adapter.generate(BusinessContext(description="Food delivery"), 1, seed=42)

    status = await adapter.readiness()

    assert status == {
        "status": "available", "reason": "model_loaded", "validation": "loaded",
        "model_loaded": True, "expected_manifest_matched": True,
    }


async def test_failed_weight_validation_stays_unavailable(ml_artifact: Path) -> None:
    parameters = ml_artifact / "parameters.npz"
    parameters.write_bytes(b"invalid numeric payload")
    adapter = MLPersonaAdapter(ml_artifact)
    assert (await adapter.readiness())["status"] == "configured"
    with pytest.raises(APIError):
        await adapter.generate(BusinessContext(description="Food delivery"), 1)

    status = await adapter.readiness()

    assert status["status"] == "unavailable"
    assert status["model_loaded"] is False
    assert adapter._model is None


@pytest.mark.parametrize("environment", ["production", "staging"])
async def test_settings_factory_rejects_hosted_without_a_trusted_pin(
    ml_artifact: Path, environment: str,
) -> None:
    from bebshax.config import Settings

    settings = Settings.model_construct(environment=environment, ml_persona_artifact_dir=str(ml_artifact))
    adapter = MLPersonaAdapter.from_settings(settings)

    assert (await adapter.readiness())["status"] == "unavailable"
    with pytest.raises(APIError) as raised:
        await adapter.generate(BusinessContext(description="Food delivery"), 1)
    assert raised.value.error_code == "ml_persona_unavailable"
    assert adapter._model is None


@pytest.mark.parametrize("environment", ["production", "staging", "development"])
async def test_settings_factory_uses_configured_manifest_pin(
    ml_artifact: Path, environment: str,
) -> None:
    from bebshax.config import Settings

    settings = Settings.model_construct(
        environment=environment, ml_persona_artifact_dir=str(ml_artifact),
        ml_persona_manifest_sha256="0" * 64,
    )
    adapter = MLPersonaAdapter.from_settings(settings)

    assert (await adapter.readiness())["status"] == "unavailable"
    with pytest.raises(APIError) as raised:
        await adapter.generate(BusinessContext(description="Food delivery"), 1)
    assert raised.value.error_code == "ml_persona_unavailable"
    assert adapter._model is None


async def test_settings_factory_respects_disabled_feature(ml_artifact: Path) -> None:
    from bebshax.config import Settings

    settings = Settings.model_construct(ml_persona_enabled=False, ml_persona_artifact_dir=str(ml_artifact))
    adapter = MLPersonaAdapter.from_settings(settings)

    assert (await adapter.readiness())["reason"] == "feature_disabled"
    with pytest.raises(APIError):
        await adapter.generate(BusinessContext(description="Food delivery"), 1)
    assert adapter._model is None


async def test_cancelled_readiness_keeps_admission_until_worker_finishes(
    ml_artifact: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    scheduled = asyncio.Event()
    release = threading.Event()
    original_validate = PersonaModel.validate_manifest
    worker_calls = []

    def controlled_validate(*args, **kwargs):
        worker_calls.append(threading.get_ident())
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10), "Readiness worker was not released"
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(PersonaModel, "validate_manifest", controlled_validate)
    adapter = MLPersonaAdapter(ml_artifact)
    first = asyncio.create_task(adapter.readiness())
    tasks = [first]
    try:
        await asyncio.wait_for(started.wait(), 10)
        waiting = asyncio.create_task(adapter.readiness())
        next_request = asyncio.create_task(adapter.generate(BusinessContext(description="Food delivery"), 1))
        tasks.extend([waiting, next_request])
        loop.call_soon(scheduled.set)
        await scheduled.wait()
        waiting.cancel()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        with pytest.raises(asyncio.CancelledError):
            await first
        assert len(worker_calls) == 1
        assert adapter._model is None
        assert not next_request.done()
        release.set()
        assert len(await asyncio.wait_for(next_request, 10)) == 1
        assert (await adapter.readiness())["status"] == "available"
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("limit", [1, 2])
async def test_cancelled_requests_never_exceed_configured_worker_admission(
    ml_artifact: Path, monkeypatch: pytest.MonkeyPatch, limit: int,
) -> None:
    loop = asyncio.get_running_loop()
    saturated = asyncio.Event()
    release = threading.Event()
    guard = threading.Lock()
    active = 0
    peak = 0
    seeds = []
    original_generate = PersonaModel.generate

    def controlled_generate(model, context, count, seed, exclude_ids, exclude_names):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
            seeds.append(seed)
            if active == limit:
                loop.call_soon_threadsafe(saturated.set)
        try:
            assert release.wait(10), "Inference workers were not released"
            return original_generate(model, context, count, seed, exclude_ids, exclude_names)
        finally:
            with guard:
                active -= 1

    monkeypatch.setattr(PersonaModel, "generate", controlled_generate)
    adapter = MLPersonaAdapter(ml_artifact, max_concurrency=limit)
    context = BusinessContext(description="Food delivery")
    tasks = [asyncio.create_task(adapter.generate(context, 1, seed=seed)) for seed in range(8)]
    try:
        await asyncio.wait_for(saturated.wait(), 10)
        tasks[0].cancel()
        tasks[-1].cancel()
        for cancelled in (tasks[0], tasks[-1]):
            with pytest.raises(asyncio.CancelledError):
                await cancelled
        assert len(seeds) == limit
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 10)
        assert peak == limit
        assert active == 0
        assert 7 not in seeds
        assert sum(isinstance(result, list) for result in results) == 6
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)