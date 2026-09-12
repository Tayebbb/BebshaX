"""Local corpus-trained topic selection; scores are not customer probabilities."""

from __future__ import annotations

import hashlib
import io
import json
import platform
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import scipy
import sklearn
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.sparse import csr_matrix
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.preprocessing import normalize

from . import provenance as provenance_tools
from .data import TrainingRecord, fingerprint, normalize_text
from .provenance import ExpectedArtifactManifest, ModelProvenance, SourceAttribution

PROTECTED_FIELDS = {"sex", "religion", "race", "cultural_background"}
ALGORITHM = "tfidf-nmf-mmr-v1"
ALGORITHMS = {"nmf": ALGORITHM, "lexical": "tfidf-mmr-v1"}
FILE_LIMITS = {"config.json": 65536, "vocabulary.json": 16 * 1024**2,
               "records.json": 128 * 1024**2, "parameters.npz": 256 * 1024**2}
RUNTIME = {"numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__}
TOKENIZER_PARAMETERS = {
    "analyzer": "word", "binary": False, "decode_error": "strict", "encoding": "utf-8",
    "lowercase": True, "ngram_range": (1, 1), "norm": "l2", "smooth_idf": True,
    "stop_words": "english", "strip_accents": None, "sublinear_tf": False,
    "token_pattern": r"(?u)\b\w\w+\b", "use_idf": True,
}


def _tokenizer_contract() -> dict[str, object]:
    return {
        "implementation": "sklearn.feature_extraction.text.TfidfVectorizer",
        "parameters": {**TOKENIZER_PARAMETERS, "ngram_range": [1, 1], "dtype": "float64"},
        "stop_words_sha256": fingerprint(sorted(ENGLISH_STOP_WORDS)),
        "python_version": platform.python_version(), "unicode_version": unicodedata.unidata_version,
        "feature_projection": "complete-normalized-record/name-protected-filter-v1",
        "truncation": False, "max_input_tokens": None,
    }


def _new_vectorizer(max_features: int, vocabulary: dict[str, int] | None = None) -> TfidfVectorizer:
    return TfidfVectorizer(max_features=max_features, vocabulary=vocabulary, dtype=np.float64,
                           **TOKENIZER_PARAMETERS)


class PersonaModelError(ValueError):
    """Invalid training data, request, or local model artifact."""


class BusinessContext(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    description: str = Field(min_length=3, max_length=20000)
    target_audience: str = Field(default="", max_length=4000)
    location: str = Field(default="", max_length=512)
    price_range: str = Field(default="", max_length=512)
    product_category: str = Field(default="", max_length=512)
    features: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=100,
    )
    research: list[Annotated[str, Field(min_length=1, max_length=10000)]] = Field(
        default_factory=list, max_length=100,
    )
    role: str = Field(default="", max_length=512)
    min_age: int | None = Field(default=None, ge=18, le=95)
    max_age: int | None = Field(default=None, ge=18, le=95)

    @model_validator(mode="after")
    def validate_content(self) -> BusinessContext:
        if not self.description.strip() or any(not value.strip() for value in self.features + self.research):
            raise ValueError("Description and list entries cannot be blank")
        if self.min_age is not None and self.max_age is not None and self.min_age > self.max_age:
            raise ValueError("min_age must not exceed max_age")
        return self

    def text(self) -> str:
        return "\n".join([
            self.description, self.target_audience, self.location, self.price_range,
            self.product_category, *self.features, *self.research, self.role,
        ])


class ModelConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, allow_inf_nan=False)

    strategy: Literal["nmf", "lexical"] = "nmf"
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    n_topics: int = Field(default=24, ge=1, le=256)
    max_features: int = Field(default=8000, ge=1, le=100000)
    max_iter: int = Field(default=300, ge=1, le=5000)
    lexical_weight: float = Field(default=0.35, ge=0, le=1)
    diversity_weight: float = Field(default=0.25, ge=0, le=1)
    temperature: float = Field(default=0.03, gt=0, le=10)
    device: Literal["cpu", "auto"] = "cpu"

    @model_validator(mode="after")
    def validate_strategy(self) -> ModelConfig:
        if self.strategy == "lexical" and self.lexical_weight != 1.0:
            raise ValueError("The lexical strategy requires lexical_weight=1.0")
        return self


class Selection(BaseModel):
    record: TrainingRecord
    score: float
    topic: int | None
    warnings: list[str] = Field(default_factory=list)
    model_version: str
    strategy: Literal["nmf", "lexical"] = "nmf"
    source_attribution: SourceAttribution = Field(default_factory=lambda values: SourceAttribution.unavailable(
        values["record"].source, values["record"].revision,
    ))
    source_corpus_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    training_code_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> Selection:
        if (self.source_attribution.source, self.source_attribution.revision) != (self.record.source, self.record.revision):
            raise ValueError("Selection attribution must retain the source identity")
        if (self.strategy == "lexical") != (self.topic is None):
            raise ValueError("Selection topic must match the strategy identity")
        return self


def _feature_text(record: TrainingRecord, parts: list[str] | None = None) -> str:
    text = "\n".join(parts if parts is not None else [
        record.description, record.occupation, record.education, record.location,
        *record.goals, *record.pain_points, *record.behaviors,
        *(value for key, value in record.documents.items()
          if key not in PROTECTED_FIELDS),
    ])
    for key in PROTECTED_FIELDS:
        if value := record.documents.get(key):
            for fragment in [value, *re.split(r"(?<=[.!?])\s+", value)]:
                if fragment.strip():
                    text = re.sub(re.escape(fragment), " ", text, flags=re.I)
    name_match = re.match(r"^([A-Z][\w'-]+(?: [A-Z][\w'-]+){1,3}) (?:is|works|enjoys|has)\b", record.description)
    name = record.name or (name_match.group(1) if name_match else None)
    if name:
        for part in [name, *name.split()]:
            text = re.sub(r"(?<!\w)" + re.escape(part) + r"(?!\w)", " ", text, flags=re.I)
    return text


def _identity_keys(record: TrainingRecord) -> set[tuple[str, str]]:
    return {(field, normalize_text(value).casefold()) for field, value in (
        ("id", record.record_id), ("name", record.name), ("persona", record.description),
    ) if value}


def _complete(record: TrainingRecord) -> bool:
    return bool(
        type(record.age) is int and 18 <= record.age <= 95
        and record.record_id.strip() and record.description.strip() and record.occupation.strip()
        and any(value.strip() for value in record.goals)
        and any(value.strip() for value in record.pain_points)
    )


def _candidates(records: list[TrainingRecord]) -> list[TrainingRecord]:
    candidates, seen = [], set()
    for record in records:
        if _complete(record):
            keys = _identity_keys(record)
            if not keys & seen:
                candidates.append(record.model_copy(deep=True))
            seen.update(keys)
    return candidates


def _validate_seed(seed: int) -> int:
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise PersonaModelError("Seed must be an integer in [0, 2**32)")
    return seed


class _Metadata(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    schema_version: int = Field(ge=1, le=3)
    algorithm: Literal["tfidf-nmf-mmr-v1", "tfidf-mmr-v1"]
    model_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime: dict[str, str]
    files: dict[str, str]
    n_records: int = Field(ge=1, le=100000)
    n_features: int = Field(ge=1, le=100000)
    n_topics: int = Field(ge=0, le=256)
    nnz: int = Field(ge=1, le=20000000)
    provenance: ModelProvenance | None = None
    tokenizer_contract: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_strategy_dimensions(self) -> _Metadata:
        if self.schema_version == 1 and self.algorithm != ALGORITHMS["nmf"]:
            raise ValueError("Legacy schema requires the NMF strategy")
        if ((self.algorithm == ALGORITHMS["lexical"]) != (self.n_topics == 0)
                or self.n_topics > min(self.n_records, self.n_features)):
            raise ValueError("Inconsistent artifact strategy topic dimensions")
        return self


def _check_file(path: Path, limit: int) -> None:
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise PersonaModelError(f"Missing or unsafe artifact file: {path.name}")
    if not 0 < path.stat().st_size <= limit:
        raise PersonaModelError(f"Artifact size limit exceeded: {path.name}")


def _read_bytes(path: Path, limit: int) -> bytes:
    _check_file(path, limit)
    # read(n) preallocates n bytes: sizing by the checked file instead of the
    # 128-256 MiB limits keeps a model load from transiently claiming ~400 MiB.
    size = path.stat().st_size
    with path.open("rb") as stream:
        payload = stream.read(min(size, limit) + 1)
    if len(payload) > limit:
        raise PersonaModelError(f"Artifact size limit exceeded: {path.name}")
    return payload


def _read_metadata(
    path: Path, expected_manifest: ExpectedArtifactManifest | None, verify_training_code: bool,
) -> _Metadata:
    if path.is_symlink() or path.is_junction():
        raise PersonaModelError("Unsafe artifact directory")
    if expected_manifest is not None and not isinstance(expected_manifest, ExpectedArtifactManifest):
        raise PersonaModelError("expected_manifest must be ExpectedArtifactManifest")
    if type(verify_training_code) is not bool:
        raise PersonaModelError("verify_training_code must be boolean")
    payload = _read_bytes(path / "metadata.json", 65536)
    if expected_manifest is not None and hashlib.sha256(payload).hexdigest() != expected_manifest.metadata_sha256:
        raise PersonaModelError("Expected artifact manifest checksum mismatch")
    metadata = _Metadata.model_validate_json(payload)
    if metadata.runtime != RUNTIME or set(metadata.files) != set(FILE_LIMITS):
        raise PersonaModelError("Incompatible runtime version or artifact files")
    if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in metadata.files.values()):
        raise PersonaModelError("Invalid artifact file checksum")
    if ((metadata.schema_version >= 3 and metadata.tokenizer_contract is None)
            or (metadata.tokenizer_contract is not None
                and fingerprint(metadata.tokenizer_contract) != fingerprint(_tokenizer_contract()))):
        raise PersonaModelError("Incompatible or missing tokenizer contract")
    if ((metadata.schema_version >= 2) != (metadata.provenance is not None)
            or (metadata.provenance is not None
                and metadata.provenance.source_records_sha256 != metadata.corpus_fingerprint)):
        raise PersonaModelError("Invalid artifact provenance or source digest")
    if verify_training_code:
        if metadata.provenance is None:
            raise PersonaModelError("Legacy artifact has no recorded training code")
        provenance_tools.verify_training_code(metadata.provenance)
    return metadata


def _arrays(payload: bytes, metadata: _Metadata) -> dict[str, np.ndarray]:
    expected = {
        "idf": ((metadata.n_features,), "<f8"),
        "lexical_data": ((metadata.nnz,), "<f8"),
        "lexical_indices": ((metadata.nnz,), "<i8"),
        "lexical_indptr": ((metadata.n_records + 1,), "<i8"),
    }
    if metadata.algorithm == ALGORITHMS["nmf"]:
        expected.update({
            "components": ((metadata.n_topics, metadata.n_features), "<f8"),
            "topics": ((metadata.n_records, metadata.n_topics), "<f8"),
        })
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if len(entries) != len(expected) or {entry.filename for entry in entries} != {name + ".npy" for name in expected}:
            raise PersonaModelError("Invalid numeric archive members")
        if sum(entry.file_size for entry in entries) > FILE_LIMITS["parameters.npz"]:
            raise PersonaModelError("Uncompressed artifact size limit exceeded")
        for entry in entries:
            with archive.open(entry) as stream:
                if np.lib.format.read_magic(stream) != (1, 0):
                    raise PersonaModelError("Unsupported numeric array version")
                shape, _fortran, dtype = np.lib.format.read_array_header_1_0(stream)
                expected_shape, expected_dtype = expected[entry.filename[:-4]]
                if shape != expected_shape or dtype != np.dtype(expected_dtype):
                    raise PersonaModelError("Invalid numeric dimensions or dtype")
                if entry.file_size != stream.tell() + int(np.prod(shape)) * dtype.itemsize:
                    raise PersonaModelError("Invalid numeric array size")
    with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in expected}
    if any(not np.isfinite(array).all() or (array < 0).any() for array in arrays.values()):
        raise PersonaModelError("Numeric parameters must be finite and nonnegative")
    pointers, indices = arrays["lexical_indptr"], arrays["lexical_indices"]
    if pointers[0] != 0 or pointers[-1] != metadata.nnz or (np.diff(pointers) < 0).any() or (indices >= metadata.n_features).any():
        raise PersonaModelError("Invalid sparse matrix indices")
    if ((arrays["idf"] < 1).any() or not arrays["lexical_data"].any()
            or ("components" in arrays and not arrays["components"].any())):
        raise PersonaModelError("Invalid fitted weights")
    return arrays


class PersonaModel:
    config: ModelConfig
    records: list[TrainingRecord]
    provenance: ModelProvenance | None
    version: str
    _schema_version: int
    _tokenizer_contract: dict[str, object] | None
    _corpus_fingerprint: str
    _vectorizer: TfidfVectorizer
    _lexical: csr_matrix
    _topics: np.ndarray
    _nmf: NMF | None

    @classmethod
    def fit(
        cls, records: list[TrainingRecord], config: ModelConfig | None = None,
        *, provenance: ModelProvenance | None = None,
    ) -> PersonaModel:
        if not isinstance(records, list) or not all(isinstance(record, TrainingRecord) for record in records):
            raise PersonaModelError("Training candidates must be a list of TrainingRecord")
        if config is not None and not isinstance(config, ModelConfig):
            raise PersonaModelError("config must be ModelConfig")
        if provenance is not None and not isinstance(provenance, ModelProvenance):
            raise PersonaModelError("provenance must be ModelProvenance")
        model = cls()
        model.config = config or ModelConfig()
        model._schema_version = 3
        model._tokenizer_contract = _tokenizer_contract()
        model.records = _candidates(records)
        if not model.records:
            raise PersonaModelError("No complete adult training candidates")
        model._corpus_fingerprint = fingerprint([record.model_dump(mode="json") for record in records])
        model.provenance = (ModelProvenance.model_validate(provenance.model_dump(mode="json"))
                            if provenance is not None else ModelProvenance.from_records(records))
        if (model.provenance.source_records_sha256 != model._corpus_fingerprint
                or {(item.source, item.revision) for item in model.provenance.source_attributions}
                != {(record.source, record.revision) for record in records}):
            raise PersonaModelError("Training provenance source digest or identities mismatch")
        try:
            provenance_tools.verify_training_code(model.provenance)
        except ValueError as error:
            raise PersonaModelError(f"Invalid training provenance: {error}") from error
        model.version = model._revision()
        model._vectorizer = _new_vectorizer(model.config.max_features)
        try:
            model._lexical = model._vectorizer.fit_transform([_feature_text(record) for record in model.records])
        except ValueError as error:
            raise PersonaModelError(f"Cannot fit training vocabulary: {error}") from error
        model._nmf = None
        model._topics = np.empty((len(model.records), 0), dtype=np.float64)
        if model.config.strategy == "lexical":
            return model
        model._nmf = NMF(
            n_components=min(model.config.n_topics, *model._lexical.shape),
            init="nndsvda", random_state=model.config.seed, max_iter=model.config.max_iter,
        )
        model._topics = normalize(model._nmf.fit_transform(model._lexical))
        return model

    def _configuration(self) -> dict[str, object]:
        return self.config.model_dump(
            mode="json", exclude={"strategy"} if self._schema_version == 1 else set(),
        )

    def _revision(self) -> str:
        identity = {"corpus": self._corpus_fingerprint, "config": self._configuration(),
                    "algorithm": ALGORITHMS[self.config.strategy]}
        if self.provenance is not None:
            identity["provenance"] = self.provenance.model_dump(mode="json")
        if self._schema_version >= 3:
            identity["tokenizer_contract"] = self._tokenizer_contract
        return fingerprint(identity)

    def _transform(self, texts: list[str]) -> tuple[csr_matrix, np.ndarray]:
        lexical = self._vectorizer.transform(texts)
        topics = (normalize(self._nmf.transform(lexical)) if self._nmf is not None
                  else np.empty((len(texts), 0), dtype=np.float64))
        return lexical, topics

    def _scores(
        self, lexical: csr_matrix, topics: np.ndarray,
        index: tuple[csr_matrix, np.ndarray] | None = None,
    ) -> np.ndarray:
        candidates_lexical, candidates_topics = index if index is not None else (self._lexical, self._topics)
        lexical_scores = (candidates_lexical @ lexical.T).toarray().ravel()
        if self.config.strategy == "lexical":
            return np.clip(lexical_scores, 0, 1)
        return np.clip(
            self.config.lexical_weight * lexical_scores
            + (1 - self.config.lexical_weight) * (candidates_topics @ topics[0]), 0, 1,
        )

    def generate(
        self, context: BusinessContext, num_personas: int = 5, seed: int | None = None,
        exclude_ids: set[str] | None = None, exclude_names: set[str] | None = None,
    ) -> list[Selection]:
        if not isinstance(context, BusinessContext):
            raise PersonaModelError("context must be BusinessContext")
        if type(num_personas) is not int or not 1 <= num_personas <= 50:
            raise PersonaModelError("num_personas count must be an integer in [1, 50]")
        random = np.random.default_rng(_validate_seed(self.config.seed if seed is None else seed))
        for excluded in (exclude_ids, exclude_names):
            if excluded is not None and (not isinstance(excluded, set) or not all(isinstance(value, str) for value in excluded)):
                raise PersonaModelError("Exclusions must be sets of strings")
        names = {normalize_text(name).casefold() for name in exclude_names or set()}
        eligible = np.array([
            record.record_id not in (exclude_ids or set()) and normalize_text(record.name).casefold() not in names
            and (context.min_age is None or record.age >= context.min_age)
            and (context.max_age is None or record.age <= context.max_age)
            for record in self.records
        ])
        if eligible.sum() < num_personas:
            raise PersonaModelError("Insufficient unique candidates satisfying age and exclusions")
        lexical, topics = self._transform([context.text()])
        if not lexical.nnz:
            raise PersonaModelError("Context has no overlap with the training vocabulary")
        scores, redundancy, selected = self._scores(lexical, topics), np.zeros(len(self.records)), []
        eligible &= scores > 0
        if eligible.sum() < num_personas:
            raise PersonaModelError("Insufficient relevant candidates satisfying age and exclusions")
        for _ in range(num_personas):
            available = np.flatnonzero(eligible)
            utility = scores[available] - self.config.diversity_weight * redundancy[available]
            with np.errstate(over="ignore"):
                probabilities = np.exp((utility - utility.max()) / self.config.temperature)
            chosen = int(random.choice(available, p=probabilities / probabilities.sum()))
            record, warnings = self.records[chosen], []
            if context.location.strip() and normalize_text(context.location).casefold() not in normalize_text(record.location).casefold():
                warnings.append(f"Source location {record.location!r} retained; requested location {context.location!r} is not established.")
            attribution = next((item for item in self.provenance.source_attributions
                                if (item.source, item.revision) == (record.source, record.revision)), None) if self.provenance else None
            selected.append(Selection(
                record=record.model_copy(deep=True), score=float(scores[chosen]), warnings=warnings,
                topic=int(self._topics[chosen].argmax()) if self._nmf is not None else None,
                model_version=self.version, strategy=self.config.strategy,
                source_attribution=(attribution.model_copy(deep=True) if attribution else
                                    SourceAttribution.unavailable(record.source, record.revision)),
                source_corpus_sha256=self._corpus_fingerprint,
                training_code_sha256=self.provenance.training_code_sha256 if self.provenance else None,
            ))
            eligible[chosen] = False
            redundancy = np.maximum(redundancy, self._scores(
                self._lexical[chosen], self._topics[chosen:chosen + 1],
            ))
        return selected

    def save(self, path: Path) -> None:
        """Write a local artifact. Checksums provide integrity, not authenticity."""
        try:
            if path.is_symlink() or path.is_junction():
                raise PersonaModelError("Unsafe artifact directory")
            path.mkdir(parents=True, exist_ok=True)
            for name in [*FILE_LIMITS, "metadata.json"]:
                if (path / name).is_symlink() or (path / name).is_junction():
                    raise PersonaModelError("Unsafe artifact destination")
            records = [record.model_dump(mode="json") for record in self.records]
            parameters = io.BytesIO()
            arrays = {"idf": self._vectorizer.idf_, "lexical_data": self._lexical.data,
                      "lexical_indices": self._lexical.indices.astype("<i8"),
                      "lexical_indptr": self._lexical.indptr.astype("<i8")}
            if self._nmf is not None:
                arrays.update(components=self._nmf.components_, topics=self._topics)
            np.savez(parameters, **arrays)
            payloads = {name: json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
                        for name, value in {"config.json": self._configuration(),
                                            "vocabulary.json": {word: int(index) for word, index in self._vectorizer.vocabulary_.items()},
                                            "records.json": records}.items()}
            payloads["parameters.npz"] = parameters.getvalue()
            metadata = _Metadata(
                schema_version=self._schema_version, algorithm=ALGORITHMS[self.config.strategy],
                model_version=self.version,
                corpus_fingerprint=self._corpus_fingerprint, training_fingerprint=fingerprint(records),
                runtime=RUNTIME, n_records=len(records), n_features=self._lexical.shape[1],
                n_topics=self._topics.shape[1], nnz=self._lexical.nnz,
                files={name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()},
                provenance=self.provenance,
                tokenizer_contract=self._tokenizer_contract if self._schema_version >= 3 else None,
            )
            if any(len(payload) > FILE_LIMITS[name] for name, payload in payloads.items()):
                raise PersonaModelError("Artifact size limit exceeded")
            metadata_bytes = metadata.model_dump_json(
                exclude=({"provenance"} if self.provenance is None else set())
                | ({"tokenizer_contract"} if self._schema_version < 3 else set()),
            ).encode("utf-8")
            if len(metadata_bytes) > 65536:
                raise PersonaModelError("Artifact metadata size limit exceeded")
            for name, payload in payloads.items():
                (path / name).write_bytes(payload)
            (path / "metadata.json").write_bytes(metadata_bytes)
        except (OSError, ValueError, TypeError) as error:
            raise PersonaModelError(f"Cannot save model artifact: {error}") from error

    @classmethod
    def validate_manifest(
        cls, path: Path, *, expected_manifest: ExpectedArtifactManifest | None = None,
        verify_training_code: bool = False,
    ) -> None:
        """Check metadata and payload sizes only; weights and payload hashes remain unchecked."""
        try:
            _read_metadata(path, expected_manifest, verify_training_code)
            for name, limit in FILE_LIMITS.items():
                _check_file(path / name, limit)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            raise PersonaModelError(f"Cannot validate model manifest: {error}") from error

    @classmethod
    def load(
        cls, path: Path, *, expected_manifest: ExpectedArtifactManifest | None = None,
        verify_training_code: bool = False,
    ) -> PersonaModel:
        """Load validated JSON/numeric state without imports or pickle from the artifact."""
        try:
            metadata = _read_metadata(path, expected_manifest, verify_training_code)
            payloads = {name: _read_bytes(path / name, limit) for name, limit in FILE_LIMITS.items()}
            if any(hashlib.sha256(payload).hexdigest() != metadata.files[name] for name, payload in payloads.items()):
                raise PersonaModelError("Artifact checksum mismatch")
            model = cls()
            model.config = ModelConfig.model_validate_json(payloads["config.json"])
            model._schema_version = metadata.schema_version
            model.provenance = metadata.provenance
            model._tokenizer_contract = metadata.tokenizer_contract
            if (metadata.algorithm != ALGORITHMS[model.config.strategy]
                    or (metadata.schema_version == 1
                        and (model.config.strategy != "nmf"
                             or "strategy" in json.loads(payloads["config.json"])))):
                raise PersonaModelError("Inconsistent artifact strategy identity")
            model._corpus_fingerprint = metadata.corpus_fingerprint
            model.version = model._revision()
            if model.version != metadata.model_version:
                raise PersonaModelError("Model version fingerprint mismatch")
            records, vocabulary = json.loads(payloads["records.json"]), json.loads(payloads["vocabulary.json"])
            if not isinstance(records, list) or len(records) != metadata.n_records or fingerprint(records) != metadata.training_fingerprint:
                raise PersonaModelError("Invalid training record fingerprint or count")
            model.records = [TrainingRecord.model_validate(record, strict=True) for record in records]
            if len(_candidates(model.records)) != len(records):
                raise PersonaModelError("Invalid or duplicate training candidates")
            if model.provenance is not None:
                attributed_sources = {(item.source, item.revision)
                                      for item in model.provenance.source_attributions}
                if any((record.source, record.revision) not in attributed_sources for record in model.records):
                    raise PersonaModelError("Artifact provenance is missing source attribution for a training record")
            if (not isinstance(vocabulary, dict) or len(vocabulary) != metadata.n_features
                    or any(not isinstance(word, str) or not word or type(index) is not int for word, index in vocabulary.items())
                    or set(vocabulary.values()) != set(range(metadata.n_features))):
                raise PersonaModelError("Invalid vocabulary indices")
            expected_topics = (min(model.config.n_topics, metadata.n_features, metadata.n_records)
                               if model.config.strategy == "nmf" else 0)
            if metadata.n_features > model.config.max_features or metadata.n_topics != expected_topics:
                raise PersonaModelError("Inconsistent model dimensions")
            arrays = _arrays(payloads["parameters.npz"], metadata)
            model._vectorizer = _new_vectorizer(model.config.max_features, vocabulary=vocabulary)
            model._vectorizer.idf_ = arrays["idf"]
            model._nmf = None
            if model.config.strategy == "nmf":
                model._nmf = NMF(n_components=metadata.n_topics, init="nndsvda",
                                 random_state=model.config.seed, max_iter=model.config.max_iter)
                model._nmf.components_ = arrays["components"]
                model._nmf.n_components_, model._nmf.n_features_in_ = metadata.n_topics, metadata.n_features
            model._lexical = csr_matrix((arrays["lexical_data"], arrays["lexical_indices"], arrays["lexical_indptr"]),
                                        shape=(metadata.n_records, metadata.n_features))
            model._topics = arrays.get("topics", np.empty((metadata.n_records, 0), dtype=np.float64))
            return model
        except (OSError, ValueError, TypeError, KeyError, EOFError, zipfile.BadZipFile, RuntimeError) as error:
            raise PersonaModelError(f"Cannot load model artifact: {error}") from error