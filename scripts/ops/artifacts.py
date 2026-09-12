"""Portable, bounded integrity manifests for data and immutable model releases."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_FILES = 100000
WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{number}" for number in range(1, 10)), *(f"lpt{number}" for number in range(1, 10))}


class ArtifactError(ValueError):
    pass


def storage_key(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ArtifactError("Storage key is missing or too long")
    if "\\" in value or ":" in value or value.startswith("/") or re.search(r'[\x00-\x1f<>"|?*]', value):
        raise ArtifactError("Storage keys must be relative portable POSIX paths")
    parts = value.split("/")
    if any(part in ("", ".", "..") or part.endswith((".", " ")) or len(part) > 255
           or part.split(".")[0].casefold() in WINDOWS_RESERVED for part in parts):
        raise ArtifactError("Storage key is unsafe on Windows or Linux")
    return str(PurePosixPath(value))


def legacy_storage_key(value: str, source_root: str, namespace: str) -> str:
    """Map a declared legacy root for inventory only; never rewrite database values."""
    path_type = PureWindowsPath if PureWindowsPath(source_root).drive else PurePosixPath
    try:
        relative = path_type(value).relative_to(path_type(source_root))
    except ValueError as error:
        raise ArtifactError("Legacy path is outside its explicitly declared source root") from error
    return storage_key(f"{namespace}/{relative.as_posix()}")


def safe_file(root: Path, key: str) -> Path:
    canonical = storage_key(key)
    base = root.resolve()
    candidate = base.joinpath(*canonical.split("/"))
    for component in (candidate, *candidate.parents):
        if component == base:
            break
        if component.is_symlink() or component.is_junction():
            raise ArtifactError("Symlinks and junctions are not portable release files")
    if not candidate.resolve().is_relative_to(base):
        raise ArtifactError("Artifact escapes the bundle root")
    return candidate


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ArtifactError("Manifest is missing or exceeds the size budget")
    with path.open("rb") as stream:
        content = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(content) > MAX_MANIFEST_BYTES:
        raise ArtifactError("Manifest changed beyond the size budget")
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ArtifactError("Manifest must be a JSON object")
    return result


def inventory(root: Path, namespace: str, max_bytes: int) -> list[dict[str, Any]]:
    if root.is_symlink() or root.is_junction() or not root.is_dir():
        raise ArtifactError("An explicit ordinary source directory is required")
    entries = []
    seen = set()
    total = 0
    for source in sorted(root.rglob("*")):
        relative = source.relative_to(root).as_posix()
        source = safe_file(root, relative)
        if source.is_dir():
            continue
        if not source.is_file():
            raise ArtifactError("Only regular release files are accepted")
        if source.name.startswith(".env") or source.name in {".npmrc", ".netrc"} or source.suffix.lower() in {".key", ".pem"}:
            raise ArtifactError("Secret/configuration files do not belong in release data")
        key = storage_key(f"{namespace}/{relative}")
        if key.casefold() in seen:
            raise ArtifactError("Case-colliding storage keys cannot be restored on Windows")
        seen.add(key.casefold())
        total += source.stat().st_size
        if total > max_bytes or len(entries) >= MAX_FILES:
            raise ArtifactError("Artifact inventory exceeds the declared resource budget")
        entries.append({"key": key, "size": source.stat().st_size, "sha256": sha256(source)})
    return entries


def verify_lineage(lineage: dict[str, Any], files: dict[str, dict[str, Any]]) -> None:
    if not isinstance(lineage.get("database_inventory"), dict):
        raise ArtifactError("A SQL-derived database inventory is required")
    if lineage.get("schema_version") != 1 or lineage.get("unresolved_legacy_paths") != []:
        raise ArtifactError("Lineage must explicitly contain no unresolved legacy absolute paths")
    coverage = lineage.get("coverage", {})
    if any(coverage.get(kind) is not True for kind in ("datasets", "persona_versions", "transcripts")):
        raise ArtifactError("Data-owner lineage coverage is incomplete")
    references = lineage.get("references")
    if not isinstance(references, list) or len(references) > MAX_FILES:
        raise ArtifactError("Lineage references are missing or exceed the budget")
    for reference in references:
        if not isinstance(reference, dict) or reference.get("kind") not in {"dataset", "persona_version", "transcript"}:
            raise ArtifactError("Unknown lineage reference kind")
        if not isinstance(reference.get("id"), str) or not reference["id"] or len(reference["id"]) > 256:
            raise ArtifactError("Lineage requires a bounded immutable record identity")
        key = storage_key(reference.get("storage_key", ""))
        if key not in files or reference.get("sha256") != files[key]["sha256"]:
            raise ArtifactError("Lineage reference is missing or has a different content hash")


def verify_bundle(root: Path, expected_manifest_sha256: str, max_bytes: int = 1024**3) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256):
        raise ArtifactError("An independently approved manifest SHA256 is required")
    manifest_path = safe_file(root, "manifest.json")
    if sha256(manifest_path) != expected_manifest_sha256:
        raise ArtifactError("Recovery manifest does not match its approved digest")
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != 1 or manifest.get("consistency") != "writers-paused":
        raise ArtifactError("Unknown or non-quiesced recovery format")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not 2 <= len(entries) <= MAX_FILES:
        raise ArtifactError("Recovery file inventory is incomplete or unbounded")
    files = {}
    seen = set()
    total = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ArtifactError("Invalid file entry")
        key = storage_key(entry.get("key", ""))
        if key != "database.dump" and not key.startswith(("data/", "artifacts/")):
            raise ArtifactError("Unexpected recovery namespace")
        if key.casefold() in seen or type(entry.get("size")) is not int or entry["size"] < 0:
            raise ArtifactError("Duplicate key or invalid file size")
        seen.add(key.casefold())
        total += entry["size"]
        if total > max_bytes:
            raise ArtifactError("Recovery bundle exceeds the resource budget")
        source = safe_file(root, key)
        if not source.is_file() or source.stat().st_size != entry["size"] or sha256(source) != entry.get("sha256"):
            raise ArtifactError("Recovery file is missing, changed, or corrupt")
        files[key] = entry
    model_key = storage_key(manifest.get("model_manifest_key", ""))
    if "database.dump" not in files or model_key not in files or not model_key.startswith("artifacts/"):
        raise ArtifactError("Database dump and approved model manifest are both required")
    if files[model_key]["sha256"] != manifest.get("model_manifest_sha256"):
        raise ArtifactError("Model metadata does not match the approved model release")
    lineage = manifest.get("lineage")
    if not isinstance(lineage, dict):
        raise ArtifactError("Data-owner lineage index is required")
    verify_lineage(lineage, files)
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != {*files, "manifest.json"}:
        raise ArtifactError("Unlisted files exist in the recovery bundle")
    return manifest