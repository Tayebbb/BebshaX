"""Standalone, synthetic-only dataset ingestion for the opt-in non-LLM profile."""

from __future__ import annotations

import hashlib
import heapq
import json
import tempfile
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import fastparquet
import huggingface_hub
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from scripts.dataset_manifest import DatasetEntry, ML_DATASET_MANIFEST


_Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _LfsInfo(BaseModel):
    model_config = ConfigDict(strict=True, from_attributes=True)

    sha256: _Sha256
    size: int = Field(gt=0)


class _ShardInfo(BaseModel):
    model_config = ConfigDict(strict=True, from_attributes=True)

    path: str
    size: int = Field(gt=0)
    lfs: _LfsInfo


class _IntegrityMetadata(BaseModel):
    model_config = ConfigDict(strict=True)

    metadata_version: Literal[1]
    artifact_role: Literal["training"]
    actual_raw_sha256: _Sha256
    upstream_raw_sha256: _Sha256
    actual_processed_sha256: _Sha256
    actual_card_sha256: _Sha256
    metadata_sha256: _Sha256
    raw_size_bytes: int = Field(gt=0)
    processed_size_bytes: int = Field(gt=0)
    processed_record_count: int = Field(gt=0)
    inspection: dict[str, Any]
    license_check: dict[str, str]


def is_ml_dataset_entry(entry: DatasetEntry) -> bool:
    """Route ML entries to the strict path even if their permission was damaged."""
    return (
        entry.training_allowed or "ml_persona" in entry.profiles
        or any(entry.dataset_id == approved.dataset_id for approved in ML_DATASET_MANIFEST)
    )


def _validate_entry(entry: DatasetEntry) -> None:
    approved = next((candidate for candidate in ML_DATASET_MANIFEST if candidate.dataset_id == entry.dataset_id), None)
    if approved is None or entry.training_allowed is not True or entry.profiles != ["ml_persona"]:
        raise ValueError("ML source is not explicitly training-allowed in the ml_persona allowlist")
    for field_name in (
        "hf_repo_id", "pinned_revision", "files_or_patterns", "download_method", "preprocessing_fn",
        "distribution", "preprocessing", "collection",
    ):
        if getattr(entry, field_name) != getattr(approved, field_name):
            raise ValueError(f"ML source allowlist mismatch: {field_name}")
    if not 1 <= entry.composition.sample_count_estimate <= approved.composition.sample_count_estimate:
        raise ValueError("ML source subset exceeds the training allowlist limit")


def _file_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _metadata_sha256(metadata: dict[str, Any]) -> str:
    payload = {key: value for key, value in metadata.items() if key != "metadata_sha256"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_hash(actual: str, expected: str | None, artifact: str) -> None:
    if expected is not None and actual != expected:
        raise ValueError(f"ML {artifact} SHA-256 checksum mismatch")


def _verify_file(path: Path, expected_hash: str, expected_size: int | None = None) -> None:
    if not path.is_file():
        raise ValueError(f"ML local artifact missing: {path.name}")
    if expected_size is not None and path.stat().st_size != expected_size:
        raise ValueError(f"ML local artifact size mismatch: {path.name}")
    _require_hash(_file_sha256(path), expected_hash, path.name)


def _check_card(entry: DatasetEntry, card_path: Path) -> dict[str, str]:
    from yaml import YAMLError

    try:
        card = huggingface_hub.DatasetCard(card_path.read_text(encoding="utf-8"))
    except (YAMLError, TypeError, ValueError) as error:
        raise ValueError("ML dataset card license metadata is malformed") from error
    license_name = card.data.to_dict().get("license")
    if license_name != entry.distribution.license_claimed_hf or not isinstance(license_name, str):
        raise ValueError("ML dataset card license is missing or differs from the reviewed license")
    return {"license": license_name, "revision": entry.pinned_revision, "card_path": "README.md"}


def _download_inputs(entry: DatasetEntry, raw_target: Path, force: bool) -> tuple[Path, Path, _ShardInfo]:
    raw_target.mkdir(parents=True, exist_ok=True)

    def download(filename: str) -> Path:
        downloaded = Path(huggingface_hub.hf_hub_download(
            repo_id=entry.hf_repo_id, filename=filename, repo_type="dataset",
            revision=entry.pinned_revision, local_dir=str(raw_target), token=False, force_download=force,
        ))
        if downloaded.resolve() != (raw_target / filename).resolve():
            raise ValueError("ML download path does not match the approved source path")
        return downloaded

    card_path = download("README.md")
    _check_card(entry, card_path)
    paths = huggingface_hub.HfApi(token=False).get_paths_info(
        repo_id=entry.hf_repo_id, paths=entry.files_or_patterns, repo_type="dataset",
        revision=entry.pinned_revision, token=False,
    )
    if len(paths) != 1:
        raise ValueError("ML source requires exactly one pinned LFS file")
    try:
        info = _ShardInfo.model_validate(paths[0])
    except ValidationError as error:
        raise ValueError("ML source has invalid or missing LFS SHA-256 metadata") from error
    if info.path != entry.files_or_patterns[0]:
        raise ValueError("ML upstream path differs from the approved shard path")
    if info.size != info.lfs.size:
        raise ValueError("ML upstream file size differs from its LFS size")
    _require_hash(info.lfs.sha256, entry.raw_sha256, "upstream raw")
    raw_path = download(info.path)
    _verify_file(raw_path, info.lfs.sha256, info.size)
    return raw_path, card_path, info


@dataclass
class _RankedRow:
    """Reverse ordering keeps the worst retained hash at the heap root."""

    key: tuple[str, str]
    record: dict[str, Any]

    def __lt__(self, other: _RankedRow) -> bool:
        return self.key > other.key


def _write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False,
        ) as output:
            temporary_path = Path(output.name)
            for line in lines:
                output.write(line + "\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _inspect_record(record: dict[str, Any], schema: dict[str, str], report: dict[str, Any]) -> None:
    for name, expected_type in schema.items():
        value = record[name]
        if value is None or (isinstance(value, str) and not value.strip()):
            report["missing_values"][name] += 1
            continue
        valid = isinstance(value, str) if expected_type == "str" else (
            isinstance(value, int) and not isinstance(value, bool)
        )
        if not valid:
            report["invalid_values"][name] += 1
        if isinstance(value, str):
            report["max_text_characters"][name] = max(report["max_text_characters"][name], len(value))


def preprocess_nemotron_personas(entry: DatasetEntry, raw_file: Path, output_file: Path) -> dict[str, Any]:
    """Hash-rank the whole shard; preserve complete allowed values for later normalization."""
    _validate_entry(entry)
    requested_rows = entry.composition.sample_count_estimate
    if requested_rows < 1:
        raise ValueError("ML subset size must be positive")
    parquet = fastparquet.ParquetFile(str(raw_file))
    schema = entry.preprocessing.normalized_jsonl_schema
    available = set(parquet.columns)
    if "uuid" not in available:
        raise ValueError("ML source is missing the uuid column")
    columns = [name for name in schema if name in available]
    report: dict[str, Any] = {
        "rows_scanned": 0,
        "row_groups_scanned": 0,
        "rows_selected": 0,
        "available_columns": sorted(available),
        "excluded_columns": sorted(available - set(schema)),
        "missing_columns": sorted(set(schema) - available),
        "missing_values": dict.fromkeys(schema, 0),
        "invalid_values": dict.fromkeys(schema, 0),
        "max_text_characters": dict.fromkeys(schema, 0),
        "selection": {
            "method": "sha256_rank_v1",
            "key": "<hf_repo_id>@<pinned_revision>:<uuid>",
            "encoding": "utf-8",
            "ordering": "sha256_then_uuid",
            "requested_rows": requested_rows,
            "scope": entry.files_or_patterns[0],
        },
    }
    selected: list[_RankedRow] = []
    seen: set[str] = set()
    for group in parquet.iter_row_groups(columns=columns):
        report["row_groups_scanned"] += 1
        group = group.astype(object).where(group.notna(), None)
        for values in group.itertuples(index=False, name=None):
            report["rows_scanned"] += 1
            available_record = dict(zip(columns, values, strict=True))
            record = {name: available_record.get(name) for name in schema}
            identifier = record["uuid"]
            if not isinstance(identifier, str) or not identifier:
                raise ValueError(f"Invalid uuid at source row {report['rows_scanned']}")
            try:
                canonical_uuid = str(uuid.UUID(identifier))
            except ValueError as error:
                raise ValueError(f"Invalid uuid at source row {report['rows_scanned']}") from error
            if canonical_uuid in seen:
                raise ValueError(f"ML source contains a duplicate uuid at row {report['rows_scanned']}")
            seen.add(canonical_uuid)
            _inspect_record(record, schema, report)
            digest = hashlib.sha256(
                f"{entry.hf_repo_id}@{entry.pinned_revision}:{identifier}".encode("utf-8")
            ).hexdigest()
            candidate = _RankedRow((digest, identifier), record)
            if len(selected) < requested_rows:
                heapq.heappush(selected, candidate)
            elif candidate.key < selected[0].key:
                heapq.heapreplace(selected, candidate)
    if not selected:
        raise ValueError("ML source shard is empty")
    ordered = sorted(selected, key=lambda candidate: candidate.key)
    _write_lines(
        output_file,
        (json.dumps(candidate.record, ensure_ascii=False, sort_keys=True, allow_nan=False) for candidate in ordered),
    )
    report["rows_selected"] = len(ordered)
    return report


def verify_ml_dataset(
    entry: DatasetEntry, raw_dir: Path, processed_dir: Path, metadata_dir: Path,
) -> tuple[str, str]:
    """Verify local metadata, pinned source, card, raw and output without any network call."""
    _validate_entry(entry)
    metadata_path = metadata_dir / f"{entry.dataset_id}.json"
    if not metadata_path.is_file():
        raise ValueError("ML local metadata is missing; run ingestion first or --force to repair")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    try:
        integrity = _IntegrityMetadata.model_validate(metadata)
    except ValidationError as error:
        raise ValueError("Invalid ML local metadata") from error
    _require_hash(_metadata_sha256(metadata), integrity.metadata_sha256, "metadata")
    for name, expected in entry.to_dict().items():
        if name not in {"raw_sha256", "processed_sha256"} and metadata.get(name) != expected:
            raise ValueError(f"ML metadata source/revision mismatch: {name}")
    raw_path = raw_dir / entry.dataset_id / entry.files_or_patterns[0]
    card_path = raw_dir / entry.dataset_id / "README.md"
    output_path = processed_dir / f"{entry.dataset_id}.jsonl"
    _require_hash(integrity.actual_raw_sha256, integrity.upstream_raw_sha256, "raw LFS")
    _require_hash(integrity.actual_raw_sha256, entry.raw_sha256, "manifest raw")
    _require_hash(integrity.actual_processed_sha256, entry.processed_sha256, "manifest output")
    _verify_file(raw_path, integrity.actual_raw_sha256, integrity.raw_size_bytes)
    _verify_file(output_path, integrity.actual_processed_sha256, integrity.processed_size_bytes)
    _verify_file(card_path, integrity.actual_card_sha256)
    if _check_card(entry, card_path) != integrity.license_check:
        raise ValueError("ML metadata license verification mismatch")
    with output_path.open(encoding="utf-8") as output:
        output_count = sum(1 for line in output if line.strip())
    if output_count != integrity.processed_record_count or output_count != integrity.inspection.get("rows_selected"):
        raise ValueError("ML metadata record count mismatch")
    return integrity.actual_raw_sha256, integrity.actual_processed_sha256


def process_ml_dataset(
    entry: DatasetEntry, raw_dir: Path, processed_dir: Path, metadata_dir: Path, *, force: bool = False,
) -> tuple[str, str, str]:
    """Download the approved shard, verify integrity, and publish a reproducible training artifact."""
    _validate_entry(entry)
    output_path = processed_dir / f"{entry.dataset_id}.jsonl"
    metadata_path = metadata_dir / f"{entry.dataset_id}.json"
    if not force and (output_path.exists() or metadata_path.exists()):
        raw_sha, output_sha = verify_ml_dataset(entry, raw_dir, processed_dir, metadata_dir)
        return "SKIPPED", raw_sha, output_sha

    raw_path, card_path, info = _download_inputs(entry, raw_dir / entry.dataset_id, force)
    processed_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ml-ingest-", dir=processed_dir) as staging_directory:
        staged_output = Path(staging_directory) / output_path.name
        inspection = preprocess_nemotron_personas(entry, raw_path, staged_output)
        output_sha = _file_sha256(staged_output)
        _require_hash(output_sha, entry.processed_sha256, "processed output")
        metadata = entry.to_dict()
        metadata.update(
            metadata_version=1,
            artifact_role="training",
            actual_raw_sha256=info.lfs.sha256,
            upstream_raw_sha256=info.lfs.sha256,
            actual_processed_sha256=output_sha,
            actual_card_sha256=_file_sha256(card_path),
            raw_size_bytes=raw_path.stat().st_size,
            processed_size_bytes=staged_output.stat().st_size,
            processed_record_count=inspection["rows_selected"],
            license_check=_check_card(entry, card_path),
            inspection=inspection,
        )
        metadata["metadata_sha256"] = _metadata_sha256(metadata)
        staged_output.replace(output_path)
        _write_lines(metadata_path, [json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)])
    return "PROCESSED", info.lfs.sha256, output_sha