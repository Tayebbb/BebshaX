"""Measure the frozen lexical challenger through the approved local lifecycle."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
import re
import sys
import time
import uuid
import xml.etree.ElementTree as element_tree
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml_persona.tools.verify_modernization import (
    NUMERICAL_VERSIONS, THREAD_VARIABLES, frozen_snapshot, memory_bytes,
)


def experiment_path(name: str) -> Path:
    if not re.fullmatch(r"experiment-[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("Use a new experiment-* directory name, not an arbitrary artifact path")
    directory = ROOT / "data/processed/ml_persona" / name
    if any(path.is_symlink() or path.is_junction() for path in (directory, *directory.parents)):
        raise ValueError("Experiment paths cannot traverse links or junctions")
    return directory


def write_evidence(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def cli_step(arguments: list[str]) -> dict[str, Any]:
    from bebshax_persona_ml.cli import main

    output = io.StringIO()
    started = time.perf_counter()
    with contextlib.redirect_stdout(output):
        exit_code = main(["--root", str(ROOT), *arguments])
    response = json.loads(output.getvalue())
    result = {"command": ["python", "-B", "-m", "bebshax_persona_ml", "--root", str(ROOT), *arguments],
              "exit_code": exit_code, "wall_seconds": time.perf_counter() - started,
              "response": response}
    if exit_code != 0 or not response.get("ok"):
        raise ValueError(f"Local {arguments[0]} lifecycle failed with exit {exit_code}: {response.get('error')}")
    return result


def train(directory: Path) -> dict[str, Any]:
    if directory.exists():
        raise FileExistsError("Experiment already exists; frozen runs are never overwritten")
    with patch("bebshax_persona_ml.model.NMF", side_effect=AssertionError("Lexical invoked NMF")) as nmf:
        result = cli_step([
            "train", "--config", "ml_persona/configs/modernization_lexical.json",
            "--lexical-weights", "1.0", "--experiment-dir", directory.relative_to(ROOT).as_posix(),
            "--threads", "2",
        ])
        result["nmf_constructor_calls"] = nmf.call_count
    report = result["response"]["result"]
    if len(report["candidates"]) != 1 or report["selected_config"]["strategy"] != "lexical":
        raise ValueError("Only the already-selected lexical configuration may be fitted")
    result["purpose"] = "Schema-3 rebuild of the prior validation winner; no new hyperparameter search or test evaluation"
    return result


def evaluate(directory: Path, label: str, *, report_path: Path | None = None) -> dict[str, Any]:
    if label == "lexical":
        arguments = ["--experiment-dir", directory.relative_to(ROOT).as_posix()]
    else:
        arguments = ["--model", "data/processed/ml_persona/model",
                     "--report", (report_path or directory / "reference-validation.json").relative_to(ROOT).as_posix()]
    if label == "lexical" and report_path is not None:
        arguments.extend(["--report", report_path.relative_to(ROOT).as_posix()])
    return cli_step(["evaluate", *arguments, "--split", "validation", "--threads", "2"])


def resources(
    directory: Path, label: str, *, verify_recorded_code: bool = True, fresh_process: bool = True,
) -> dict[str, Any]:
    import_started = time.perf_counter()
    import numpy as np
    from bebshax_persona_ml.cli import _check_backend_conversion
    from bebshax_persona_ml.data import fingerprint
    from bebshax_persona_ml.model import BusinessContext, PersonaModel
    from bebshax_persona_ml.provenance import ExpectedArtifactManifest, training_code_snapshot
    from threadpoolctl import threadpool_info, threadpool_limits

    with patch("pydantic_settings.BaseSettings.__init__", side_effect=AssertionError("Settings reads forbidden in ML measurement")):
        from bebshax.api.errors import APIError
        from bebshax.personas.ml_adapter import (
            MLPersonaAdapter, to_generated_persona, to_persona_draft, to_persona_profile, to_workflow_persona,
        )
    import_seconds = time.perf_counter() - import_started
    artifact = directory / "model" if label == "lexical" else ROOT / "data/processed/ml_persona/model"
    metadata_bytes = (artifact / "metadata.json").read_bytes()
    metadata_sha = hashlib.sha256(metadata_bytes).hexdigest()
    selected_directory = directory if label == "lexical" else ROOT / "data/processed/ml_persona"
    selection_report = json.loads((selected_directory / "experiment.json").read_text(encoding="utf-8"))
    expected = ExpectedArtifactManifest(metadata_sha256=selection_report.get("artifact_manifest_sha256", metadata_sha))
    context = BusinessContext.model_validate_json((ROOT / "ml_persona/examples/business.json").read_text(encoding="utf-8"))

    class MeasuredAdapter(MLPersonaAdapter):
        load_seconds = 0.0
        load_count = 0

        def _load(self) -> PersonaModel:
            if self._model is not None:
                return super()._load()
            started = time.perf_counter()
            loaded = super()._load()
            self.load_seconds += time.perf_counter() - started
            self.load_count += 1
            return loaded

        def _generate(self, context, num_personas, seed, exclude_ids, exclude_names):
            started = time.perf_counter()
            try:
                return super()._generate(context, num_personas, seed, exclude_ids, exclude_names)
            finally:
                worker_times[seed] = (started, time.perf_counter())

    worker_times: dict[int | None, tuple[float, float]] = {}
    verify_code = label == "lexical" and verify_recorded_code
    adapter = MeasuredAdapter(artifact, expected_manifest=expected, verify_training_code=verify_code)

    async def measure() -> dict[str, Any]:
        if context.min_age is None or context.max_age is None:
            raise ValueError("Resource probes require explicit age bounds")
        readiness_before = await adapter.readiness()
        if readiness_before["status"] != "configured" or readiness_before["model_loaded"]:
            raise ValueError("Unloaded artifact did not report honest manifest-only readiness")
        cold_started = time.perf_counter()
        first = await adapter.generate(context, 5, seed=42)
        cold_seconds = time.perf_counter() - cold_started
        cold_memory = memory_bytes()
        model = adapter._load()
        readiness_after = await adapter.readiness()
        if readiness_after["status"] != "available" or not readiness_after["model_loaded"]:
            raise ValueError("Loaded artifact did not report available readiness")
        source = {record.record_id: record for record in model.records}
        warm_samples, source_mismatches, age_violations, zero_scores = [], 0, 0, 0
        for seed in range(32):
            started = time.perf_counter()
            batch = model.generate(context, 5, seed=seed)
            warm_samples.append((time.perf_counter() - started) * 1000)
            for selection in batch:
                source_mismatches += int(selection.record != source[selection.record.record_id])
                age_violations += int(selection.record.age is None
                                      or not context.min_age <= selection.record.age <= context.max_age)
                zero_scores += int(selection.score <= 0)
        if source_mismatches or age_violations or zero_scores:
            raise ValueError("The real artifact violated a source, age, or positive-relevance constraint")

        queue_samples: dict[str, list[dict[str, Any]]] = {}

        async def queued_request(seed: int) -> dict[str, Any]:
            started = time.perf_counter()
            batch = await adapter.generate(context, 5, seed=seed)
            finished = time.perf_counter()
            worker_started, worker_finished = worker_times[seed]
            return {"seed": seed, "total_ms": (finished - started) * 1000,
                    "queue_ms": (worker_started - started) * 1000,
                    "worker_ms": (worker_finished - worker_started) * 1000,
                    "record_ids": [selection.record.record_id for selection in batch],
                    "model_versions": sorted({selection.model_version for selection in batch})}

        for concurrency in (1, 4, 8):
            samples = []
            for repetition in range(3):
                samples.extend(await asyncio.gather(*(
                    queued_request(concurrency * 100 + repetition * concurrency + offset)
                    for offset in range(concurrency)
                )))
            queue_samples[str(concurrency)] = samples
        serving_memory = memory_bytes()
        if adapter.load_count != 1:
            raise ValueError("Runtime cache unexpectedly reloaded the artifact")
        if fingerprint([record.model_dump(mode="json") for record in model.records]) != json.loads(
            (ROOT / "data/processed/ml_persona/preparation.json").read_text(encoding="utf-8")
        )["splits"]["train"]["records_sha256"]:
            raise ValueError("Loaded records differ from the frozen canonical training records")
        if label == "lexical" and (model._nmf is not None or model._topics.shape[1] != 0):
            raise ValueError("Lexical artifact contains NMF state")

        second = await adapter.generate(context, 5, seed=42,
                                        exclude_ids={selection.record.record_id for selection in first},
                                        exclude_names={selection.record.name for selection in first if selection.record.name})
        distinct = len({selection.record.record_id for selection in [*first, *second]}) == 10
        if not distinct:
            raise ValueError("Sequential requests repeated an excluded source")
        abstentions = []
        for probe, query, excluded in (
            ("no_vocabulary_overlap", BusinessContext(description="qzxwvyplm"), None),
            ("source_exhausted", context, set(source)),
        ):
            try:
                await adapter.generate(query, 1, seed=42, exclude_ids=excluded)
            except APIError as error:
                if error.status_code != 422 or error.error_code != "ml_persona_unsupported_context":
                    raise
                abstentions.append({"probe": probe, "status": error.status_code, "error_code": error.error_code})
            else:
                raise ValueError("Unsupported/exhausted context was accepted")

        conversions: dict[str, list[dict[str, Any]]] = {name: [] for name in ("generated", "profile", "draft", "workflow")}
        for selection in first:
            generated = to_generated_persona(selection).model_dump(mode="json")
            profile = to_persona_profile(selection, "ml-smoke").model_dump(mode="json")
            draft = to_persona_draft(selection).model_dump(mode="json")
            workflow = to_workflow_persona(selection, role_id="ml-smoke", role_title=context.role)
            _check_backend_conversion(selection, generated, profile, draft, workflow, context.role)
            for name, value in zip(conversions, (generated, profile, draft, workflow), strict=True):
                conversions[name].append(value)
        payload_bytes = {name: len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
                         for name, value in conversions.items()}
        return {
            "model_version": model.version, "strategy": model.config.strategy,
            "artifact": artifact.relative_to(ROOT).as_posix(), "metadata_sha256": metadata_sha,
            "manifest_pin_origin": "Same-run integrity check, not independent publisher authentication",
            "schema_version": json.loads(metadata_bytes)["schema_version"],
            "training_code_verified": verify_code,
            "training_code_matches_current": model.provenance.training_code == training_code_snapshot() if model.provenance else None,
            "record_count": len(model.records), "readiness_before": readiness_before, "readiness_after": readiness_after,
            "cold_load_seconds": adapter.load_seconds, "cold_first_adapter_request_seconds": cold_seconds,
            "cold_import_and_first_request_seconds": import_seconds + cold_seconds,
            "cold_definition": ("Fresh process; interpreter startup excluded, filesystem cache uncontrolled" if fresh_process else
                                "Fresh adapter after validation; imports and filesystem may be warm, interpreter startup excluded"),
            "fresh_process_measurement": fresh_process,
            "memory_after_cold_request": cold_memory, "memory_after_serving_probes": serving_memory,
            "warm_generation": {"query": "ml_persona/examples/business.json", "seeds": list(range(32)),
                                "batch_size": 5, "milliseconds": warm_samples,
                                "mean_ms": float(np.mean(warm_samples)), "p95_ms": float(np.percentile(warm_samples, 95))},
            "queue_probes": {"inference_concurrency": 1, "offered_concurrency": [1, 4, 8],
                             "repetitions": 3, "samples": queue_samples,
                             "scope": "Adapter only; no HTTP, DB, network or cross-process uniqueness measurement"},
            "load_count": adapter.load_count, "full_canonical_training_records_verified": True,
            "structural": {"bundle_mismatches": source_mismatches, "age_violations": age_violations,
                           "zero_score_selections": zero_scores, "sequential_ten_distinct_sources": distinct},
            "explicit_abstentions": abstentions, "full_backend_conversions": 20,
            "five_persona_serialized_bytes": payload_bytes,
            "bundle_files": {path.name: path.stat().st_size for path in sorted(artifact.iterdir()) if path.is_file()},
            "tokenizer_contract": json.loads(metadata_bytes).get("tokenizer_contract"),
            "numerical_pools": [{key: pool.get(key) for key in ("internal_api", "num_threads", "version")}
                                for pool in threadpool_info()],
        }

    with threadpool_limits(limits=2):
        if label == "lexical":
            with patch("bebshax_persona_ml.model.NMF", side_effect=AssertionError("Lexical invoked NMF")) as nmf:
                result = asyncio.run(measure())
                result["nmf_constructor_calls"] = nmf.call_count
        else:
            result = asyncio.run(measure())
    return result


def revalidate(directory: Path, output: Path) -> dict[str, Any]:
    def snapshot() -> dict[str, str]:
        return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(directory.rglob("*")) if path.is_file()}

    artifact_before = snapshot()
    checks = {}
    with patch("bebshax_persona_ml.model.PersonaModel.fit", side_effect=AssertionError("Revalidation cannot retrain")):
        for label in ("lexical", "reference"):
            evaluation = evaluate(directory, label, report_path=output / f"{label}-validation.json")
            measured = resources(directory, label, verify_recorded_code=False, fresh_process=False)
            if evaluation["response"]["result"]["model_version"] != measured["model_version"]:
                raise ValueError("Validation and serving measurements use different models")
            checks[label] = {"evaluation": evaluation, "resources": measured}
    if artifact_before != snapshot():
        raise ValueError("Revalidation changed the frozen experimental artifact or evidence")
    return {
        "purpose": "Revalidate existing artifacts without fitting or changing any saved model or historical report",
        "training_performed": False, "test_split_evaluated": False,
        "training_code_policy": "Recorded code hashes remain intact; current source drift is reported, not resealed or bypassed in the strict loader",
        "experimental_files_unchanged": True, "experimental_file_sha256": artifact_before,
        "candidates": checks,
    }


def summarize(directory: Path, full_run_id: str, full_exit_code: int) -> dict[str, Any]:
    import numpy as np

    if not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", full_run_id):
        raise ValueError("Expected the recorded full-suite run ID")
    reports = {}
    origins = {}
    incomplete = []
    for phase in ("train", "evaluate-lexical", "evaluate-reference", "lexical", "reference"):
        paths = [*(ROOT / "data/metadata").glob(f"ml_modernization_{phase}_*.json"),
                 *(ROOT / "ml_persona/.verification").glob("*/report.json")]
        for path in sorted(paths):
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("phase") != phase or report.get("experiment") != directory.relative_to(ROOT).as_posix():
                continue
            if report["exit_code"] != 0:
                incomplete.append(path.relative_to(ROOT).as_posix())
                continue
            reports[phase], origins[phase] = report, path.relative_to(ROOT).as_posix()
        if phase not in reports:
            raise ValueError(f"No completed evidence for {phase}")
    candidates = {}
    for label in ("lexical", "reference"):
        report = reports[label]
        resource = report["result"]
        evaluation = reports[f"evaluate-{label}"]["result"]["response"]["result"]["metrics"]
        if resource["model_version"] != evaluation["model_version"]:
            raise ValueError("Resource and validation reports describe different models")
        candidates[label] = {
            "model_version": resource["model_version"], "artifact": resource["artifact"],
            "metadata_sha256": resource["metadata_sha256"], "schema_version": resource["schema_version"],
            "validation": evaluation["retrieval"], "validation_generation": evaluation["generation"],
            "evaluation_ms": evaluation["latency_ms"]["total"],
            "cold_load_seconds": resource["cold_load_seconds"],
            "cold_import_and_first_request_seconds": resource["cold_import_and_first_request_seconds"],
            "warm_mean_ms": resource["warm_generation"]["mean_ms"], "warm_p95_ms": resource["warm_generation"]["p95_ms"],
            "rss_before_bytes": report["memory_before_phase"]["rss_bytes"],
            "rss_after_cold_bytes": resource["memory_after_cold_request"]["rss_bytes"],
            "rss_after_serving_bytes": resource["memory_after_serving_probes"]["rss_bytes"],
            "peak_serving_bytes": resource["memory_after_serving_probes"]["peak_rss_bytes"],
            "peak_entire_phase_bytes": report["memory_after_phase"]["peak_rss_bytes"],
            "bundle_files": resource["bundle_files"], "bundle_bytes": sum(resource["bundle_files"].values()),
            "payload_bytes": resource["five_persona_serialized_bytes"], "load_count": resource["load_count"],
            "numerical_pools": resource["numerical_pools"],
            "queue_p95": {level: {"samples": len(samples), **{
                name: float(np.percentile([sample[name] for sample in samples], 95))
                for name in ("total_ms", "queue_ms", "worker_ms")
            }} for level, samples in resource["queue_probes"]["samples"].items()},
        }
    local_verification = ROOT / "ml_persona/.verification" / full_run_id / "report.json"
    if local_verification.exists():
        verification = json.loads(local_verification.read_text(encoding="utf-8"))
        if (not verification.get("full_ml_suite_requested") or verification["exit_code"] != full_exit_code
                or not verification["frozen_files_unchanged"]):
            raise ValueError("Full-suite scope, exit code or frozen artifact verification mismatch")
        junit = ROOT / verification["junit"]
    else:
        junit = ROOT / "data/metadata" / f"ml_modernization_full_ml_{full_run_id}.xml"
    suites = list(element_tree.parse(junit).getroot().iter("testsuite"))
    counts = {name: sum(int(suite.get(name, "0")) for suite in suites)
              for name in ("tests", "failures", "errors", "skipped")}
    training = reports["train"]["result"]["response"]["result"]
    return {
        "origins": origins, "incomplete_phase_reports": incomplete, "candidates": candidates,
        "training_seconds": training["training_seconds"], "training_phase_wall_seconds": reports["train"]["wall_seconds"],
        "training_peak_rss_bytes": reports["train"]["memory_after_phase"]["peak_rss_bytes"],
        "training_code_sha256": training["provenance"]["training_code_sha256"],
        "dataset_sha256": training["dataset_sha256"], "source_notices": training["provenance"]["source_attributions"],
        "full_ml_attempt": {"junit": junit.relative_to(ROOT).as_posix(), "counts": counts,
                            "junit_seconds": sum(float(suite.get("time", "0")) for suite in suites),
                            "observed_process_exit_code": full_exit_code,
                            "exit_origin": "Matching terminal execution, not inferred from partial JUnit",
                            "complete_pass": full_exit_code == 0 and counts["failures"] == counts["errors"] == 0},
        "promotion_decision": "Unpromoted lexical proxy challenger; parent approval and unmet release/label gates required",
        "fresh_business_labels": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--phase", required=True, choices=("train", "evaluate-lexical", "evaluate-reference", "lexical", "reference", "summarize", "revalidate"))
    parser.add_argument("--full-run-id")
    parser.add_argument("--full-exit-code", type=int)
    arguments = parser.parse_args()
    directory = experiment_path(arguments.experiment)
    if arguments.phase == "summarize" and (arguments.full_run_id is None or arguments.full_exit_code is None):
        parser.error("Summaries require the actual full-suite run ID and observed terminal exit code")
    versions = {name: importlib.metadata.version(name) for name in NUMERICAL_VERSIONS}
    if versions != NUMERICAL_VERSIONS or sys.version_info[:3] != (3, 12, 9):
        parser.error("Use the frozen repository Python 3.12.9 and exact numerical versions")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]
    temporary = ROOT / "ml_persona/.verification" / run_id / "tmp"
    temporary.mkdir(parents=True, exist_ok=False)
    for name in THREAD_VARIABLES:
        os.environ[name] = "2"
    os.environ.update({"TEMP": str(temporary), "TMP": str(temporary), "PYTHONDONTWRITEBYTECODE": "1"})
    sys.dont_write_bytecode = True
    os.chdir(ROOT)
    frozen_before = frozen_snapshot()
    memory_before = memory_bytes()
    started = time.perf_counter()
    exit_code, result, problem = 0, None, None
    try:
        if arguments.phase == "train":
            result = train(directory)
        elif arguments.phase == "revalidate":
            result = revalidate(directory, temporary.parent)
        elif arguments.phase.startswith("evaluate-"):
            result = evaluate(directory, arguments.phase.removeprefix("evaluate-"))
        elif arguments.phase == "summarize":
            result = summarize(directory, arguments.full_run_id, arguments.full_exit_code)
        else:
            result = resources(directory, arguments.phase)
    except (AssertionError, ValueError, OSError, RuntimeError, ImportError) as error:
        exit_code = 1
        problem = {"type": type(error).__name__, "message": str(error)}
    except KeyboardInterrupt:
        exit_code = 130
        problem = {"type": "KeyboardInterrupt", "message": "Measurement interrupted; not successful evidence"}
    elapsed = time.perf_counter() - started
    final_memory = memory_bytes()
    frozen_after = frozen_snapshot()
    unchanged = frozen_before == frozen_after
    if not unchanged:
        exit_code = 1
    report = {
        "phase": arguments.phase, "run_id": run_id, "experiment": directory.relative_to(ROOT).as_posix(),
        "command": [str(Path(sys.executable).relative_to(ROOT)), *sys.argv], "exit_code": exit_code,
        "wall_seconds": elapsed, "python": sys.version.split()[0], "numerical_versions": versions,
        "numerical_threads": 2, "memory_before_phase": memory_before, "memory_after_phase": final_memory,
        "frozen_files_before": frozen_before, "frozen_files_after": frozen_after, "frozen_files_unchanged": unchanged,
        "application_environment_overrides": [], "result": result, "error": problem,
        "test_split_evaluated": False, "fresh_business_labels": 0, "production_promoted": False,
    }
    report_path = temporary.parent / "report.json"
    write_evidence(report_path, report)
    print(json.dumps({"report": report_path.relative_to(ROOT).as_posix(), "exit_code": exit_code,
                      "wall_seconds": elapsed, "frozen_files_unchanged": unchanged, "error": problem}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())