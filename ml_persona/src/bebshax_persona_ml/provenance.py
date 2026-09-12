"""Local integrity and attribution records; hashes are not signatures."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .data import TrainingRecord, fingerprint

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, Field(min_length=1, max_length=20000)]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class SourceAttribution(_Strict):
    source: Text
    revision: Text
    creator: Text | None
    source_url: Text | None
    license: Text | None
    license_reference_url: Text | None
    license_notice: Text | None = None
    modifications: list[Text] = Field(min_length=1, max_length=30)
    metadata_status: Literal["unavailable", "verified_ingestion_metadata"]

    @model_validator(mode="after")
    def validate_attribution(self) -> SourceAttribution:
        details = (self.creator, self.source_url, self.license, self.license_reference_url, self.license_notice)
        if any(value is not None and not value.strip()
               for value in (self.source, self.revision, self.license_notice, *details, *self.modifications)):
            raise ValueError("Attribution text cannot be blank")
        if self.metadata_status == "verified_ingestion_metadata" and any(value is None for value in details):
            raise ValueError("Verified attribution requires creator, source and license metadata including a license notice")
        return self

    @classmethod
    def unavailable(cls, source: str, revision: str) -> SourceAttribution:
        return cls(
            source=source, revision=revision, creator=None, source_url=None,
            license=None, license_reference_url=None, metadata_status="unavailable",
            modifications=[
                "Creator, source URL, license and upstream modification history were not supplied; no redistribution permission is inferred.",
                "BebshaX selects complete, deduplicated adult records without rewriting source narratives.",
                "TF-IDF feature projection excludes known names and protected fields; retained source documents are unchanged.",
            ],
        )


def training_code_snapshot() -> dict[str, str]:
    directory = Path(__file__).parent
    snapshot = {}
    for path in sorted(directory.rglob("*.py")):
        with path.open("rb") as stream:
            snapshot[path.relative_to(directory).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return snapshot


class ModelProvenance(_Strict):
    source_records_sha256: Sha256
    source_attributions: list[SourceAttribution] = Field(min_length=1, max_length=100)
    source_files: dict[str, Sha256] = Field(default_factory=dict, max_length=100)
    source_manifest_sha256: Sha256 | None = None
    preparation_sha256: Sha256 | None = None
    dataset_sha256: Sha256 | None = None
    training_code: dict[str, Sha256] = Field(min_length=1, max_length=100)
    training_code_sha256: Sha256

    @model_validator(mode="after")
    def validate_digests(self) -> ModelProvenance:
        if fingerprint(self.training_code) != self.training_code_sha256:
            raise ValueError("Training code digest mismatch")
        identities = [(item.source, item.revision) for item in self.source_attributions]
        if len(set(identities)) != len(identities):
            raise ValueError("Duplicate source attribution identities")
        return self

    @classmethod
    def from_records(cls, records: list[TrainingRecord]) -> ModelProvenance:
        code = training_code_snapshot()
        return cls(
            source_records_sha256=fingerprint([record.model_dump(mode="json") for record in records]),
            source_attributions=[SourceAttribution.unavailable(source, revision)
                                 for source, revision in sorted({(record.source, record.revision) for record in records})],
            training_code=code, training_code_sha256=fingerprint(code),
        )


class ExpectedArtifactManifest(_Strict):
    metadata_sha256: Sha256


def verify_training_code(provenance: ModelProvenance) -> None:
    if provenance.training_code != training_code_snapshot():
        raise ValueError("Installed training code differs from the recorded training code")