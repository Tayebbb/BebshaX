"""Explicit-consent PG16 backup/restore rehearsal; no .env or default database."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops.artifacts import ArtifactError, inventory, read_json, safe_file, sha256, storage_key, verify_bundle, verify_lineage


@dataclass(frozen=True)
class DatabaseTarget:
    host: str
    port: int
    database: str
    username: str
    password: str = field(repr=False)
    sslmode: str = "verify-full"

    @property
    def identity(self) -> str:
        return f"{self.host}:{self.port}/{self.database}"

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.identity.encode("utf-8")).hexdigest()

    def environment(self) -> dict[str, str]:
        safe_names = {"PATH", "Path", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "TMP", "TEMP"}
        environment = {name: value for name, value in os.environ.items() if name in safe_names}
        environment.update({
            "PGHOST": self.host, "PGPORT": str(self.port), "PGDATABASE": self.database,
            "PGUSER": self.username, "PGPASSWORD": self.password, "PGSSLMODE": self.sslmode,
            "PGPASSFILE": os.devnull, "PGCONNECT_TIMEOUT": "5", "PGAPPNAME": "bebshax-recovery-rehearsal",
            "PGOPTIONS": "-c statement_timeout=300000 -c lock_timeout=10000",
        })
        return environment


def database_target(url: str, confirmation: str, *, restore: bool, allow_remote: bool = False) -> DatabaseTarget:
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, strict_parsing=True)
        if parsed.scheme not in {"postgresql", "postgres", "postgresql+asyncpg"} or parsed.fragment or set(query) - {"sslmode"}:
            raise ValueError
        host = parsed.hostname or ""
        database = unquote(parsed.path.removeprefix("/"))
        username, password = unquote(parsed.username or ""), unquote(parsed.password or "")
        port = parsed.port or 5432
        if not host or not username or not password or not re.fullmatch(r"[A-Za-z0-9_]{1,63}", database):
            raise ValueError
        if any(ord(character) < 32 for value in (host, username, password) for character in value):
            raise ValueError
        local = host in {"localhost", "127.0.0.1", "::1"}
        sslmode = query.get("sslmode", ["prefer" if local else "verify-full"])[0]
        if sslmode not in {"disable", "prefer", "require", "verify-ca", "verify-full"} or (not local and sslmode != "verify-full"):
            raise ValueError
    except (ValueError, TypeError) as error:
        raise ArtifactError("Invalid explicit PostgreSQL URL or insufficient remote TLS verification") from error
    target = DatabaseTarget(host, port, database, username, password, sslmode)
    if confirmation != target.identity:
        raise ArtifactError("Confirmation must exactly match the selected host:port/database")
    if restore and (not re.fullmatch(r"bebshax_rehearsal_[a-z0-9_]{1,40}", database) or (not local and not allow_remote)):
        raise ArtifactError("Restore requires a rehearsal-named database; remote targets require separate consent")
    return target


def pg(tool: str, arguments: list[str], target: DatabaseTarget, pg_bin: Path | None) -> str:
    executable = str(pg_bin / tool) if pg_bin else tool
    result = subprocess.run([executable, *arguments], env=target.environment(), capture_output=True,
                            text=True, check=False, timeout=900)
    if result.returncode:
        raise ArtifactError(f"{tool} failed; credentials and server diagnostics are intentionally not logged")
    return result.stdout.strip()


def scalar(sql: str, target: DatabaseTarget, pg_bin: Path | None) -> str:
    return pg("psql", ["-X", "-q", "-A", "-t", "--no-password", "-v", "ON_ERROR_STOP=1", "-c", sql], target, pg_bin)


def check_pg16(target: DatabaseTarget, pg_bin: Path | None) -> None:
    if scalar("SELECT current_setting('server_version_num')::integer / 10000", target, pg_bin) != "16":
        raise ArtifactError("The recovery contract requires PostgreSQL 16")
    for tool in ("pg_dump", "pg_restore"):
        if not re.search(r"\b16\.", pg(tool, ["--version"], target, pg_bin)):
            raise ArtifactError("Use reviewed PostgreSQL 16 dump/restore clients")


def selected_target(arguments: argparse.Namespace, *, restore: bool) -> DatabaseTarget:
    name = arguments.target_url_env if restore else arguments.source_url_env
    if not name or not re.fullmatch(r"[A-Z][A-Z0-9_]*_URL", name):
        raise ArtifactError("Select an explicit URL environment variable by name")
    value = os.environ.get(name)
    if not value:
        raise ArtifactError("The explicitly selected URL variable is empty; no default database will be used")
    return database_target(value, arguments.confirm_target if restore else arguments.confirm_source,
                           restore=restore, allow_remote=getattr(arguments, "allow_remote_target", False))


def new_output(path: Path, sources: list[Path]) -> Path:
    resolved = path.resolve()
    if path.exists() or path.is_symlink() or path.is_junction():
        raise ArtifactError("Output must not exist; existing work is never overwritten")
    if any(resolved.is_relative_to(source.resolve()) or source.resolve().is_relative_to(resolved) for source in sources):
        raise ArtifactError("Recovery output and source trees must be disjoint")
    resolved.mkdir(parents=True, mode=0o700)
    return resolved


def copy_files(entries: list[dict], sources: dict[str, Path], output: Path) -> None:
    for entry in entries:
        namespace, relative = entry["key"].split("/", 1)
        source = safe_file(sources[namespace], relative)
        destination = safe_file(output, entry["key"])
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with source.open("rb") as reader, destination.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        destination.chmod(0o600)
        if destination.stat().st_size != entry["size"] or sha256(destination) != entry["sha256"]:
            raise ArtifactError("A file changed during recovery copying; the incomplete output was retained")


def backup(arguments: argparse.Namespace) -> str:
    if not arguments.writers_paused:
        raise ArtifactError("Backup requires explicit confirmation that all database/blob writers are paused")
    target = selected_target(arguments, restore=False)
    check_pg16(target, arguments.pg_bin)
    revision = scalar("SELECT version_num FROM alembic_version", target, arguments.pg_bin)
    if not re.fullmatch(r"[a-zA-Z0-9_]+", revision):
        raise ArtifactError("Backup requires one explicit Alembic revision")
    entries = inventory(arguments.data_root, "data", arguments.max_bytes) + inventory(arguments.artifact_root, "artifacts", arguments.max_bytes)
    estimated_database_bytes = int(scalar("SELECT pg_database_size(current_database())", target, arguments.pg_bin))
    estimated_bytes = sum(entry["size"] for entry in entries) + estimated_database_bytes
    if estimated_bytes > arguments.max_bytes:
        raise ArtifactError("Database plus artifacts exceed the declared backup budget")
    files = {entry["key"]: entry for entry in entries}
    model_key = storage_key(f"artifacts/{arguments.model_manifest_key}")
    if model_key not in files or files[model_key]["sha256"] != arguments.model_manifest_sha256:
        raise ArtifactError("Model metadata must match the independently approved release hash")
    lineage = read_json(arguments.lineage_index)
    verify_lineage(lineage, files)
    output = new_output(arguments.output, [arguments.data_root, arguments.artifact_root])
    if shutil.disk_usage(output).free < estimated_bytes * 2 + 64 * 1024 * 1024:
        raise ArtifactError("Insufficient free space for a bounded backup")
    copy_files(entries, {"data": arguments.data_root, "artifacts": arguments.artifact_root}, output)
    dump = output / "database.dump"
    pg("pg_dump", ["--no-password", "--format=custom", "--compress=6", "--no-owner", "--no-acl", "--file", str(dump)], target, arguments.pg_bin)
    dump.chmod(0o600)
    after = inventory(arguments.data_root, "data", arguments.max_bytes) + inventory(arguments.artifact_root, "artifacts", arguments.max_bytes)
    if after != entries:
        raise ArtifactError("Source files changed during backup; the incomplete output was retained")
    entries.append({"key": "database.dump", "size": dump.stat().st_size, "sha256": sha256(dump)})
    manifest = {
        "schema_version": 1, "consistency": "writers-paused", "created_at": datetime.now(timezone.utc).isoformat(),
        "database_fingerprint": target.fingerprint, "alembic_revision": revision,
        "model_manifest_key": model_key, "model_manifest_sha256": arguments.model_manifest_sha256,
        "files": entries, "lineage": lineage,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    digest = sha256(manifest_path)
    verify_bundle(output, digest, arguments.max_bytes)
    return digest


def restore(arguments: argparse.Namespace) -> str:
    started = time.monotonic()
    manifest = verify_bundle(arguments.bundle, arguments.manifest_sha256, arguments.max_bytes)
    target = selected_target(arguments, restore=True)
    if target.fingerprint == manifest.get("database_fingerprint"):
        raise ArtifactError("Restoring into the source database is forbidden")
    check_pg16(target, arguments.pg_bin)
    count = scalar("SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')", target, arguments.pg_bin)
    if count != "0":
        raise ArtifactError("Restore target is not empty; no clean/drop/overwrite operation is supported")
    output = new_output(arguments.output, [arguments.bundle])
    entries = [entry for entry in manifest["files"] if entry["key"] != "database.dump"]
    copy_files(entries, {"data": arguments.bundle / "data", "artifacts": arguments.bundle / "artifacts"}, output)
    pg("pg_restore", ["--no-password", "--exit-on-error", "--single-transaction", "--no-owner", "--no-acl",
                      "--dbname", target.database, str(arguments.bundle / "database.dump")], target, arguments.pg_bin)
    if scalar("SELECT version_num FROM alembic_version", target, arguments.pg_bin) != manifest["alembic_revision"]:
        raise ArtifactError("Restored schema revision differs from the snapshot")
    pg("psql", ["-X", "--no-password", "-v", "ON_ERROR_STOP=1", "-f", str(ROOT / "deploy/recovery_checks.sql")], target, arguments.pg_bin)
    receipt = {
        "manifest_sha256": arguments.manifest_sha256, "target_fingerprint": target.fingerprint,
        "alembic_revision": manifest["alembic_revision"], "model_manifest_sha256": manifest["model_manifest_sha256"],
        "restored_files": len(entries), "elapsed_seconds": round(time.monotonic() - started, 3),
        "scope": "PG16 restore, schema/extension/constraint checks and supplied lineage files; not an authenticated product journey",
    }
    (output / "rehearsal.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return arguments.manifest_sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operations = parser.add_subparsers(dest="operation", required=True)
    backup_parser = operations.add_parser("backup")
    backup_parser.add_argument("--source-url-env", required=True)
    backup_parser.add_argument("--confirm-source", required=True)
    backup_parser.add_argument("--writers-paused", action="store_true")
    backup_parser.add_argument("--data-root", type=Path, required=True)
    backup_parser.add_argument("--artifact-root", type=Path, required=True)
    backup_parser.add_argument("--lineage-index", type=Path, required=True)
    backup_parser.add_argument("--model-manifest-key", default="ml_persona/model/metadata.json")
    backup_parser.add_argument("--model-manifest-sha256", required=True)
    backup_parser.add_argument("--output", type=Path, required=True)
    restore_parser = operations.add_parser("restore")
    restore_parser.add_argument("--target-url-env", required=True)
    restore_parser.add_argument("--confirm-target", required=True)
    restore_parser.add_argument("--allow-remote-target", action="store_true")
    restore_parser.add_argument("--output", type=Path, required=True)
    verify_parser = operations.add_parser("verify")
    for subparser in (restore_parser, verify_parser):
        subparser.add_argument("--bundle", type=Path, required=True)
        subparser.add_argument("--manifest-sha256", required=True)
    for subparser in (backup_parser, restore_parser, verify_parser):
        subparser.add_argument("--max-bytes", type=int, default=1024**3)
    for subparser in (backup_parser, restore_parser):
        subparser.add_argument("--pg-bin", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.max_bytes <= 0:
            raise ArtifactError("The resource budget must be positive")
        if arguments.operation == "backup":
            digest = backup(arguments)
        elif arguments.operation == "restore":
            digest = restore(arguments)
        else:
            verify_bundle(arguments.bundle, arguments.manifest_sha256, arguments.max_bytes)
            digest = arguments.manifest_sha256
        print(f"PASS: {arguments.operation}; manifest_sha256={digest}")
        return 0
    except ArtifactError as error:
        print(f"Recovery blocked: {error}", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f"Recovery blocked: {type(error).__name__}; existing data was not removed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())