"""Verify and unpack the vendored persona ML bundle during the image build.

Usage: python unpack_model.py SOURCE_DIR DESTINATION
SOURCE_DIR holds exactly one ``*.tar.gz`` plus ``SHA256SUMS``. The tarball must
match its recorded digest, contain only the five flat bundle files, and every
file must match the digest recorded in the bundle's own ``metadata.json``.
Prints the metadata.json SHA-256 (the value operators pin in
BEBSHAX_ML_PERSONA_MANIFEST_SHA256) and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path

BUNDLE_FILES = frozenset({"config.json", "metadata.json", "parameters.npz", "records.json", "vocabulary.json"})
MAX_TARBALL_BYTES = 128 * 1024 * 1024


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def recorded_digest(sums: Path, name: str) -> str:
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, _, listed = line.strip().partition("  ")
        if listed == name and len(digest) == 64:
            return digest
    raise ValueError(f"{name} is not listed in SHA256SUMS")


def main(source: Path, destination: Path) -> int:
    tarballs = sorted(source.glob("*.tar.gz"))
    if len(tarballs) != 1:
        raise ValueError("Expected exactly one vendored bundle tarball")
    tarball = tarballs[0]
    if tarball.stat().st_size > MAX_TARBALL_BYTES:
        raise ValueError("Bundle tarball exceeds the size limit")
    if sha256(tarball) != recorded_digest(source / "SHA256SUMS", tarball.name):
        raise ValueError("Bundle tarball digest does not match SHA256SUMS")
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(tarball, "r:gz") as archive:
        members = archive.getmembers()
        if {member.name for member in members} != BUNDLE_FILES or not all(member.isfile() for member in members):
            raise ValueError("Bundle must contain exactly the five flat model files")
        archive.extractall(destination, filter="data")
    metadata = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
    files = metadata.get("files")
    if not isinstance(files, dict) or set(files) != BUNDLE_FILES - {"metadata.json"}:
        raise ValueError("metadata.json does not describe the bundle files")
    for name, digest in files.items():
        if sha256(destination / name) != digest:
            raise ValueError(f"{name} does not match the digest recorded in metadata.json")
    print(sha256(destination / "metadata.json"))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: unpack_model.py SOURCE_DIR DESTINATION", file=sys.stderr)
        raise SystemExit(2)
    try:
        raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
    except (OSError, ValueError, tarfile.TarError, json.JSONDecodeError) as error:
        print(f"Model bundle rejected: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
