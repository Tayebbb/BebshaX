"""Local preparation and experiment lifecycle for approved synthetic sources."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import warnings
from itertools import product
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

from .data import TrainingRecord, fingerprint, normalize_text, prepare_records, split_records
from .evaluation import evaluate_model
from .model import FILE_LIMITS, RUNTIME, ModelConfig, PersonaModel, _candidates, _complete, _identity_keys
from .provenance import ModelProvenance, SourceAttribution

DEFAULT_OUTPUT = Path("data/processed/ml_persona")
SPLITS = ("train", "validation", "test")
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
VERIFY_SOURCE = """import json
from pathlib import Path
from scripts.dataset_manifest import ML_DATASET_MANIFEST
from scripts.persona_ml_dataset import verify_ml_dataset
root = Path.cwd()
approved = [entry for entry in ML_DATASET_MANIFEST
            if entry.training_allowed is True and entry.profiles == ['ml_persona']]
if len(approved) != 1:
    raise ValueError('Expected one approved ml_persona source')
entry = approved[0]
raw_sha256, processed_sha256 = verify_ml_dataset(
    entry, root / 'data/raw', root / 'data/processed', root / 'data/metadata')
print(json.dumps({'entry': entry.to_dict(), 'raw_sha256': raw_sha256,
                  'processed_sha256': processed_sha256}, allow_nan=False))
"""


class PipelineError(ValueError):
    """A lifecycle contract failed; messages never echo external input."""


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)


class SplitConfig(_Strict):
    seed: int = Field(default=42, ge=0, lt=2**32)
    validation_fraction: float = Field(default=0.15, gt=0, lt=1)
    test_fraction: float = Field(default=0.15, gt=0, lt=1)

    @model_validator(mode="after")
    def check_fractions(self) -> SplitConfig:
        if self.validation_fraction + self.test_fraction >= 1:
            raise PipelineError("Split fractions leave no training data")
        return self


class _Source(_Strict):
    dataset_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,100}$")
    hf_repo_id: str = Field(min_length=1, max_length=200)
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    manifest_sha256: Sha256
    raw_file: str = Field(min_length=1, max_length=500)
    files: dict[str, Sha256]


class TrainingConfig(_Strict):
    model: ModelConfig = Field(default_factory=ModelConfig)
    topics: list[Annotated[int, Field(ge=1, le=256)]] = Field(default_factory=lambda: [16, 32], min_length=1, max_length=8)
    lexical_weights: list[Annotated[float, Field(ge=0, le=1)]] = Field(default_factory=lambda: [0.35, 0.7], min_length=1, max_length=8)
    threads: int = Field(default=2, ge=1, le=64)


class _Partition(_Strict):
    count: int = Field(gt=0, le=100000)
    file_sha256: Sha256
    records_sha256: Sha256
    record_sha256: list[Sha256] = Field(min_length=1, max_length=100000)


class _Preparation(SplitConfig):
    schema_version: Literal[1]
    source: _Source
    statistics: dict[str, Any]
    dataset_sha256: Sha256
    splits: dict[Literal["train", "validation", "test"], _Partition]
    preparation_sha256: Sha256


def resolve_path(root: Path, path: Path) -> Path:
    root = root.absolute()
    candidate = path if path.is_absolute() else root / path
    if ".." in candidate.parts or not candidate.is_relative_to(root):
        raise PipelineError("Paths must stay inside the explicit root")
    if any(part.is_symlink() or part.is_junction() for part in (candidate, *candidate.parents)):
        raise PipelineError("Symlinks and junctions are not permitted")
    return candidate


def _output_path(root: Path, path: Path) -> Path:
    target = resolve_path(root, path)
    _check(not any(target.is_relative_to(root.absolute() / reserved) for reserved in ("data/raw", "data/metadata", "data/uploads", "scripts", ".git")),
           "Output would overwrite protected source or project files")
    return target


def read_json(path: Path, limit: int = 64 * 1024**2) -> Any:
    if not 0 < path.stat().st_size <= limit:
        raise PipelineError("JSON file is empty or exceeds the size limit")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise PipelineError(message)


def _available(paths: list[Path], force: bool) -> None:
    for path in paths:
        if path.exists() and not force:
            raise FileExistsError("Output exists; choose another path or use --force")


def _write(path: Path, payload: bytes, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb" if force else "xb") as stream:
        stream.write(payload)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _source_paths(root: Path, source: _Source) -> dict[str, Path]:
    relative = PurePosixPath(source.raw_file)
    _check(not relative.is_absolute() and not {".", ".."} & set(relative.parts)
           and "\\" not in source.raw_file and ":" not in source.raw_file, "Unsafe source metadata path")
    return {name: resolve_path(root, Path(path)) for name, path in {
        "raw": f"data/raw/{source.dataset_id}/{source.raw_file}",
        "card": f"data/raw/{source.dataset_id}/README.md",
        "processed": f"data/processed/{source.dataset_id}.jsonl",
        "metadata": f"data/metadata/{source.dataset_id}.json",
    }.items()}


def _verify_source(root: Path) -> _Source:
    for name in ("setup_datasets.py", "dataset_manifest.py", "persona_ml_dataset.py"):
        _check(resolve_path(root, Path("scripts") / name).is_file(), "Root does not own the dataset scripts")
    completed = subprocess.run([sys.executable, "-c", VERIFY_SOURCE], cwd=root,
                               capture_output=True, text=True, encoding="utf-8", check=False)
    _check(completed.returncode == 0, "Approved source verification failed")
    result = json.loads(completed.stdout)
    entry = result["entry"]
    _check(entry.get("training_allowed") is True and entry.get("profiles") == ["ml_persona"],
           "Source is not explicitly training-allowed")
    _check(len(entry["files_or_patterns"]) == 1, "Expected one approved source shard")
    source = _Source(dataset_id=entry["dataset_id"], hf_repo_id=entry["hf_repo_id"],
                     revision=entry["pinned_revision"], manifest_sha256=fingerprint(entry),
                     raw_file=entry["files_or_patterns"][0], files={})
    paths = _source_paths(root, source)
    metadata = read_json(paths["metadata"])
    _check(metadata.get("actual_raw_sha256") == result["raw_sha256"]
           and metadata.get("actual_processed_sha256") == result["processed_sha256"],
           "Verified source checksum mismatch")
    hashes = {str(path.relative_to(root)).replace("\\", "/"): _sha256(path) for path in paths.values()}
    _check(hashes[paths["processed"].relative_to(root).as_posix()] == result["processed_sha256"]
           and hashes[paths["raw"].relative_to(root).as_posix()] == result["raw_sha256"],
           "Source checksum mismatch after verification")
    return source.model_copy(update={"files": hashes})


def _source_records(root: Path, source: _Source) -> tuple[list[TrainingRecord], dict[str, Any]]:
    source_path = _source_paths(root, source)["processed"]
    _check(source_path.stat().st_size <= 256 * 1024**2, "Source exceeds the size limit")
    with source_path.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    _check(all(isinstance(row, dict) for row in rows), "Source rows must be JSON objects")
    rows.sort(key=lambda row: (fingerprint([source.hf_repo_id, normalize_text(row.get("uuid"))]), fingerprint(row)))
    records, statistics = prepare_records(rows, source=source.hf_repo_id, revision=source.revision)
    complete = sorted((record for record in records if _complete(record)), key=lambda record: record.record_id)
    candidates = _candidates(complete)
    statistics.update(incomplete=len(records) - len(complete), identity_duplicates=len(complete) - len(candidates),
                      duplicate_names=sum(bool(record.name) for record in complete) - len({normalize_text(record.name).casefold() for record in complete if record.name}),
                      candidate_count=len(candidates))
    return candidates, statistics


def _partition(records: list[TrainingRecord], payload: bytes) -> dict[str, Any]:
    values = [record.model_dump(mode="json") for record in records]
    return {"count": len(records), "file_sha256": hashlib.sha256(payload).hexdigest(),
            "records_sha256": fingerprint(values), "record_sha256": [fingerprint(value) for value in values]}


def prepare(
    root: Path, output: Path | None = None, *, seed: int = 42,
    validation_fraction: float = 0.15, test_fraction: float = 0.15, force: bool = False,
) -> dict[str, Any]:
    root = root.absolute()
    config = SplitConfig(seed=seed, validation_fraction=validation_fraction, test_fraction=test_fraction)
    directory = _output_path(root, output or DEFAULT_OUTPUT)
    destinations = [resolve_path(root, directory / name) for name in [*(f"{split}.jsonl" for split in SPLITS), "preparation.json"]]
    _available(destinations, force)
    source = _verify_source(root)
    candidates, statistics = _source_records(root, source)
    splits = {name: sorted(values, key=lambda record: record.record_id)
              for name, values in split_records(candidates, **config.model_dump()).items()}
    payloads = {name: b"".join(_json_bytes(record.model_dump(mode="json")) for record in splits[name]) for name in SPLITS}
    report = {"schema_version": 1, **config.model_dump(), "source": source.model_dump(), "statistics": statistics,
              "dataset_sha256": fingerprint([record.model_dump(mode="json") for record in candidates]),
              "splits": {name: _partition(splits[name], payloads[name]) for name in SPLITS}}
    report["preparation_sha256"] = fingerprint(report)
    _Preparation.model_validate(report)
    for name in SPLITS:
        _write(directory / f"{name}.jsonl", payloads[name], force)
    _write(directory / "preparation.json", _json_bytes(report), force)
    return report


def _load_prepared(root: Path, output: Path | None) -> tuple[dict[str, Any], dict[str, list[TrainingRecord]]]:
    root = root.absolute()
    directory = resolve_path(root, output or DEFAULT_OUTPUT)
    report = _Preparation.model_validate(read_json(resolve_path(root, directory / "preparation.json")))
    values = report.model_dump(mode="json")
    _check(report.preparation_sha256 == fingerprint({key: value for key, value in values.items() if key != "preparation_sha256"}),
           "Preparation fingerprint mismatch")
    source = _verify_source(root)
    _check(report.source == source, "Approved source metadata or checksum mismatch")
    _check(set(report.splits) == set(SPLITS), "All three splits are required")
    partitions, seen, descriptions = {}, set(), {}
    for name in SPLITS:
        path = resolve_path(root, directory / f"{name}.jsonl")
        _check(_sha256(path) == report.splits[name].file_sha256, "Split file checksum mismatch")
        with path.open(encoding="utf-8") as stream:
            records = [TrainingRecord.model_validate_json(line, strict=True) for line in stream]
        _check(_partition(records, path.read_bytes()) == report.splits[name].model_dump(), "Record fingerprint mismatch")
        _check([record.record_id for record in records] == sorted(record.record_id for record in records), "Records must be ID-ordered")
        for record in records:
            _check(_complete(record) and record.source == report.source.hf_repo_id and record.revision == report.source.revision,
                   "Incomplete record or source mismatch")
            keys = _identity_keys(record)
            content_key = " ".join(re.findall(r"\w+", record.description.casefold()))
            _check(not keys & seen and descriptions.get(content_key, name) == name, "Duplicate or overlapping split identities")
            seen.update(keys)
            descriptions[content_key] = name
        partitions[name] = records
    records = sorted((record for partition in partitions.values() for record in partition), key=lambda record: record.record_id)
    _check(fingerprint([record.model_dump(mode="json") for record in records]) == report.dataset_sha256, "Dataset fingerprint mismatch")
    candidates, _statistics = _source_records(root, source)
    expected = {name: sorted(records, key=lambda record: record.record_id)
                for name, records in split_records(candidates, seed=report.seed,
                                                   validation_fraction=report.validation_fraction,
                                                   test_fraction=report.test_fraction).items()}
    _check(partitions == expected, "Prepared records or split membership mismatch with approved source")
    return values, partitions


def validate(root: Path, output: Path | None = None) -> dict[str, Any]:
    return _load_prepared(root, output)[0]


def protect_output(root: Path, directory: Path, target: Path, source: dict[str, Any], model: Path | None = None) -> Path:
    target = _output_path(root, target)
    protected = [resolve_path(root, Path(name)) for name in source["files"]]
    protected.extend(directory / name for name in [*(f"{split}.jsonl" for split in SPLITS), "preparation.json"])
    _check(target not in protected and not any(path.is_relative_to(target) for path in protected),
           "Output would overwrite protected inputs")
    _check(model is None or not target.is_relative_to(model), "Output would overwrite protected model files")
    return target


def _training_provenance(
    root: Path, preparation: dict[str, Any], records: list[TrainingRecord],
) -> ModelProvenance:
    source = _Source.model_validate(preparation["source"])
    path = _source_paths(root, source)["metadata"]
    _check(_sha256(path) == source.files[path.relative_to(root).as_posix()], "Source metadata changed before attribution")
    metadata = read_json(path)
    sections = [metadata.get(name, {}) for name in ("collection", "distribution", "composition", "preprocessing")]
    _check(all(isinstance(section, dict) for section in sections), "Invalid source attribution metadata")
    collection, distribution, composition, preprocessing = sections
    creator, source_url = collection.get("upstream_creator"), collection.get("source_url")
    license_name, license_reference = distribution.get("license_verified_upstream"), distribution.get("license_verification_url")
    known = all((creator, source_url, license_name, license_reference))
    modifications = [value for value in (composition.get("slice_description"), preprocessing.get("cleaning_applied")) if value]
    modifications.extend([
        "BebshaX applies Unicode NFKC and whitespace normalization without summarizing or truncating narratives.",
        "Complete adult records are filtered and identity-deduplicated into seeded, disjoint splits; only the training split is fitted.",
        "Goals and regex-derived constraint sentences remain synthetic hypotheses, not human relevance labels.",
        "TF-IDF feature projection excludes known names and protected fields; selections retain the complete normalized source bundle.",
    ])
    if not known:
        modifications.append("Some upstream attribution details are unavailable; no redistribution permission is inferred.")
    attribution = SourceAttribution(
        source=source.hf_repo_id, revision=source.revision, creator=creator, source_url=source_url,
        license=license_name, license_reference_url=license_reference, license_notice=distribution.get("license_notes"),
        modifications=modifications, metadata_status="verified_ingestion_metadata" if known else "unavailable",
    )
    values = ModelProvenance.from_records(records).model_dump(mode="json")
    return ModelProvenance.model_validate({
        **values, "source_attributions": [attribution.model_dump(mode="json")], "source_files": source.files,
        "source_manifest_sha256": source.manifest_sha256, "preparation_sha256": preparation["preparation_sha256"],
        "dataset_sha256": preparation["dataset_sha256"],
    })


def _fit_grid(
    partitions: dict[str, list[TrainingRecord]], config: TrainingConfig,
    provenance: ModelProvenance | None = None,
) -> tuple[PersonaModel, list[dict[str, Any]]]:
    best_model, best_key, candidates = None, None, []
    settings = [ModelConfig(**{**config.model.model_dump(), "strategy": "nmf",
                              "n_topics": topics, "lexical_weight": weight})
                for topics, weight in product(sorted(set(config.topics)), sorted(set(config.lexical_weights)))
                if weight < 1.0]
    if 1.0 in config.lexical_weights:
        settings.append(ModelConfig(**{**config.model.model_dump(), "strategy": "lexical", "lexical_weight": 1.0}))
    with threadpool_limits(limits=config.threads):
        for setting in settings:
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always", ConvergenceWarning)
                started = perf_counter()
                fitted = PersonaModel.fit(partitions["train"], setting, provenance=provenance)
                seconds = perf_counter() - started
                metrics = evaluate_model(fitted, partitions["validation"], seed=setting.seed)
            candidate = {"config": setting.model_dump(), "model_version": fitted.version,
                         "training_seconds": seconds,
                         "iterations": int(fitted._nmf.n_iter_) if fitted._nmf is not None else None,
                         "convergence_warnings": list(dict.fromkeys(str(item.message) for item in captured
                                                                   if issubclass(item.category, ConvergenceWarning))),
                         "warnings": list(dict.fromkeys(str(item.message) for item in captured)), "validation": metrics}
            candidates.append(candidate)
            key = (-metrics["retrieval"]["model"]["mrr"], json.dumps(setting.model_dump(), sort_keys=True))
            if best_key is None or key < best_key:
                best_model, best_key = fitted, key
    if best_model is None:
        raise PipelineError("No training candidates configured")
    return best_model, candidates


def train(
    root: Path, output: Path | None = None, *, config: TrainingConfig | None = None,
    model_path: Path | None = None, report_path: Path | None = None, force: bool = False,
    experiment_dir: Path | None = None,
) -> dict[str, Any]:
    root = root.absolute()
    config = config or TrainingConfig()
    _check(isinstance(config, TrainingConfig), "Training configuration must be TrainingConfig")
    preparation, partitions = _load_prepared(root, output)
    directory = resolve_path(root, output or DEFAULT_OUTPUT)
    experiment_directory = _output_path(root, experiment_dir or directory)
    model_path = protect_output(root, directory, model_path or experiment_directory / "model", preparation["source"])
    latest = protect_output(root, directory, report_path or experiment_directory / "experiment.json", preparation["source"], model_path)
    _check(latest.suffix == ".json", "Experiment output must be JSON")
    _available([model_path, latest], force)
    for name in [*FILE_LIMITS, "metadata.json"]:
        protect_output(root, directory, model_path / name, preparation["source"])
    provenance = _training_provenance(root, preparation, partitions["train"])
    selected, candidates = _fit_grid(partitions, config, provenance)
    archive = protect_output(root, directory, experiment_directory / "experiments" / f"{selected.version}.json", preparation["source"], model_path)
    _available([archive], force)
    report = {
        "schema_version": 1, "model_version": selected.version, "seed": selected.config.seed,
        "selected_config": selected.config.model_dump(), "search_config": config.model_dump(), "candidates": candidates,
        "selection": {"objective": "retrieval.model.mrr", "split": "validation", "tie_break": "canonical config JSON ascending"},
        "test_evaluated": False, "sizes": {name: len(records) for name, records in partitions.items()},
        "runtime": {"python": platform.python_version(), **RUNTIME},
        "hardware": {"platform": platform.platform(), "machine": platform.machine(), "processor": platform.processor(),
                     "cpu_count": os.cpu_count(), "threads": config.threads, "device": "cpu"},
        "training_seconds": sum(candidate["training_seconds"] for candidate in candidates),
        "source": preparation["source"], "dataset_sha256": preparation["dataset_sha256"],
        "preparation_sha256": preparation["preparation_sha256"], "splits": preparation["splits"],
        "provenance": selected.provenance.model_dump(mode="json"),
    }
    selected.save(model_path)
    report["artifact_manifest_sha256"] = _sha256(model_path / "metadata.json")
    report["experiment_sha256"] = fingerprint(report)
    for target in dict.fromkeys([archive, latest]):
        _write(target, _json_bytes(report), force)
    return report


def evaluate(
    root: Path, output: Path | None = None, *, model_path: Path | None = None,
    report_path: Path | None = None, seed: int = 42, threads: int = 2, force: bool = False,
    experiment_dir: Path | None = None, split: Literal["validation", "test"] = "test",
) -> dict[str, Any]:
    root = root.absolute()
    TrainingConfig(model=ModelConfig(seed=seed), threads=threads)
    _check(split in ("validation", "test"), "Evaluation split must be validation or test")
    preparation, partitions = _load_prepared(root, output)
    directory = resolve_path(root, output or DEFAULT_OUTPUT)
    experiment_directory = resolve_path(root, experiment_dir or directory)
    model_path = resolve_path(root, model_path or experiment_directory / "model")
    target = protect_output(root, directory, report_path or experiment_directory / "evaluation.json", preparation["source"], model_path)
    _check(target.suffix == ".json" and all(target != scope / "experiment.json"
           and not target.is_relative_to(scope / "experiments") for scope in (directory, experiment_directory)),
           "Evaluation output would overwrite experiment records")
    _available([target], force)
    fitted = PersonaModel.load(model_path)
    experiment = read_json(resolve_path(root, experiment_directory / "experiments" / f"{fitted.version}.json"))
    _check(experiment["experiment_sha256"] == fingerprint({key: value for key, value in experiment.items() if key != "experiment_sha256"}),
           "Experiment fingerprint mismatch")
    _check(experiment["model_version"] == fitted.version and ModelConfig.model_validate(experiment["selected_config"]) == fitted.config
           and experiment["preparation_sha256"] == preparation["preparation_sha256"]
           and fitted.records == partitions["train"], "Model was not selected on these train/validation splits")
    if fitted.provenance is not None:
        _check(experiment.get("artifact_manifest_sha256") == _sha256(model_path / "metadata.json"),
               "Artifact manifest does not match the experiment")
        _check(experiment.get("provenance") == fitted.provenance.model_dump(mode="json")
               and fitted.provenance.source_files == preparation["source"]["files"]
               and fitted.provenance.source_manifest_sha256 == preparation["source"]["manifest_sha256"]
               and fitted.provenance.preparation_sha256 == preparation["preparation_sha256"]
               and fitted.provenance.dataset_sha256 == preparation["dataset_sha256"],
               "Artifact provenance does not match the verified preparation")
    with threadpool_limits(limits=threads), warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ConvergenceWarning)
        metrics = evaluate_model(fitted, partitions[split], seed=seed)
    report = {"schema_version": 1, "model_version": fitted.version, "seed": seed, "split": split, "metrics": metrics,
              "limitation": "Synthetic heldout retrieval proxy; not population truth, customer demand, or measured business relevance.",
              "dataset_sha256": preparation["dataset_sha256"], "experiment_sha256": experiment["experiment_sha256"],
              "warnings": list(dict.fromkeys(str(item.message) for item in captured))}
    _write(target, _json_bytes(report), force)
    return report