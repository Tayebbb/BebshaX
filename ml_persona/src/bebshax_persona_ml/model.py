"""Local corpus-trained topic selection; scores are not customer probabilities."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import scipy
import sklearn
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.sparse import csr_matrix
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .data import TrainingRecord, fingerprint, normalize_text

PROTECTED_FIELDS = {"sex", "religion", "race", "cultural_background"}
ALGORITHM = "tfidf-nmf-mmr-v1"
FILE_LIMITS = {"config.json": 65536, "vocabulary.json": 16 * 1024**2,
               "records.json": 128 * 1024**2, "parameters.npz": 256 * 1024**2}
RUNTIME = {"numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__}


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

    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    n_topics: int = Field(default=24, ge=1, le=256)
    max_features: int = Field(default=8000, ge=1, le=100000)
    max_iter: int = Field(default=300, ge=1, le=5000)
    lexical_weight: float = Field(default=0.35, ge=0, le=1)
    diversity_weight: float = Field(default=0.25, ge=0, le=1)
    temperature: float = Field(default=0.03, gt=0, le=10)
    device: Literal["cpu", "auto"] = "cpu"


class Selection(BaseModel):
    record: TrainingRecord
    score: float
    topic: int
    warnings: list[str] = Field(default_factory=list)
    model_version: str


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
    schema_version: int = Field(ge=1, le=1)
    algorithm: Literal["tfidf-nmf-mmr-v1"]
    model_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime: dict[str, str]
    files: dict[str, str]
    n_records: int = Field(ge=1, le=100000)
    n_features: int = Field(ge=1, le=100000)
    n_topics: int = Field(ge=1, le=256)
    nnz: int = Field(ge=1, le=20000000)


def _read_bytes(path: Path, limit: int) -> bytes:
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise PersonaModelError(f"Missing or unsafe artifact file: {path.name}")
    if not 0 < path.stat().st_size <= limit:
        raise PersonaModelError(f"Artifact size limit exceeded: {path.name}")
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise PersonaModelError(f"Artifact size limit exceeded: {path.name}")
    return payload


def _arrays(payload: bytes, metadata: _Metadata) -> dict[str, np.ndarray]:
    expected = {
        "idf": ((metadata.n_features,), "<f8"),
        "components": ((metadata.n_topics, metadata.n_features), "<f8"),
        "topics": ((metadata.n_records, metadata.n_topics), "<f8"),
        "lexical_data": ((metadata.nnz,), "<f8"),
        "lexical_indices": ((metadata.nnz,), "<i8"),
        "lexical_indptr": ((metadata.n_records + 1,), "<i8"),
    }
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
    if (arrays["idf"] < 1).any() or not arrays["components"].any():
        raise PersonaModelError("Invalid fitted weights")
    return arrays


class PersonaModel:
    @classmethod
    def fit(
        cls, records: list[TrainingRecord], config: ModelConfig | None = None,
    ) -> PersonaModel:
        if not isinstance(records, list) or not all(isinstance(record, TrainingRecord) for record in records):
            raise PersonaModelError("Training candidates must be a list of TrainingRecord")
        if config is not None and not isinstance(config, ModelConfig):
            raise PersonaModelError("config must be ModelConfig")
        model = cls()
        model.config = config or ModelConfig()
        model.records = _candidates(records)
        if not model.records:
            raise PersonaModelError("No complete adult training candidates")
        model._corpus_fingerprint = fingerprint([record.model_dump(mode="json") for record in records])
        model.version = fingerprint({
            "corpus": model._corpus_fingerprint,
            "config": model.config.model_dump(mode="json"), "algorithm": ALGORITHM,
        })
        model._vectorizer = TfidfVectorizer(max_features=model.config.max_features, stop_words="english")
        try:
            model._lexical = model._vectorizer.fit_transform([_feature_text(record) for record in model.records])
        except ValueError as error:
            raise PersonaModelError(f"Cannot fit training vocabulary: {error}") from error
        model._nmf = NMF(
            n_components=min(model.config.n_topics, *model._lexical.shape),
            init="nndsvda", random_state=model.config.seed, max_iter=model.config.max_iter,
        )
        model._topics = normalize(model._nmf.fit_transform(model._lexical))
        return model

    def _transform(self, texts: list[str]) -> tuple[csr_matrix, np.ndarray]:
        lexical = self._vectorizer.transform(texts)
        return lexical, normalize(self._nmf.transform(lexical))

    def _scores(
        self, lexical: csr_matrix, topics: np.ndarray,
        index: tuple[csr_matrix, np.ndarray] | None = None,
    ) -> np.ndarray:
        candidates_lexical, candidates_topics = index if index is not None else (self._lexical, self._topics)
        return np.clip(
            self.config.lexical_weight * (candidates_lexical @ lexical.T).toarray().ravel()
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
        for _ in range(num_personas):
            available = np.flatnonzero(eligible)
            utility = scores[available] - self.config.diversity_weight * redundancy[available]
            with np.errstate(over="ignore"):
                probabilities = np.exp((utility - utility.max()) / self.config.temperature)
            chosen = int(random.choice(available, p=probabilities / probabilities.sum()))
            record, warnings = self.records[chosen], []
            if context.location.strip() and normalize_text(context.location).casefold() not in normalize_text(record.location).casefold():
                warnings.append(f"Source location {record.location!r} retained; requested location {context.location!r} is not established.")
            if scores[chosen] == 0:
                warnings.append("No learned relevance for this candidate; score is not evidence of customer demand.")
            selected.append(Selection(
                record=record.model_copy(deep=True), score=float(scores[chosen]), warnings=warnings,
                topic=int(self._topics[chosen].argmax()), model_version=self.version,
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
            np.savez(parameters, idf=self._vectorizer.idf_, components=self._nmf.components_,
                     topics=self._topics, lexical_data=self._lexical.data,
                     lexical_indices=self._lexical.indices.astype("<i8"),
                     lexical_indptr=self._lexical.indptr.astype("<i8"))
            payloads = {name: json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
                        for name, value in {"config.json": self.config.model_dump(mode="json"),
                                            "vocabulary.json": {word: int(index) for word, index in self._vectorizer.vocabulary_.items()},
                                            "records.json": records}.items()}
            payloads["parameters.npz"] = parameters.getvalue()
            metadata = _Metadata(
                schema_version=1, algorithm=ALGORITHM, model_version=self.version,
                corpus_fingerprint=self._corpus_fingerprint, training_fingerprint=fingerprint(records),
                runtime=RUNTIME, n_records=len(records), n_features=self._lexical.shape[1],
                n_topics=self._topics.shape[1], nnz=self._lexical.nnz,
                files={name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()},
            )
            if any(len(payload) > FILE_LIMITS[name] for name, payload in payloads.items()):
                raise PersonaModelError("Artifact size limit exceeded")
            for name, payload in payloads.items():
                (path / name).write_bytes(payload)
            (path / "metadata.json").write_text(metadata.model_dump_json(), encoding="utf-8")
        except (OSError, ValueError, TypeError) as error:
            raise PersonaModelError(f"Cannot save model artifact: {error}") from error

    @classmethod
    def load(cls, path: Path) -> PersonaModel:
        """Load validated JSON/numeric state without imports or pickle from the artifact."""
        try:
            if path.is_symlink() or path.is_junction():
                raise PersonaModelError("Unsafe artifact directory")
            metadata = _Metadata.model_validate_json(_read_bytes(path / "metadata.json", 65536))
            if metadata.runtime != RUNTIME or set(metadata.files) != set(FILE_LIMITS):
                raise PersonaModelError("Incompatible runtime version or artifact files")
            payloads = {name: _read_bytes(path / name, limit) for name, limit in FILE_LIMITS.items()}
            if any(hashlib.sha256(payload).hexdigest() != metadata.files[name] for name, payload in payloads.items()):
                raise PersonaModelError("Artifact checksum mismatch")
            model = cls()
            model.config = ModelConfig.model_validate_json(payloads["config.json"])
            model._corpus_fingerprint = metadata.corpus_fingerprint
            model.version = fingerprint({"corpus": model._corpus_fingerprint,
                                         "config": model.config.model_dump(mode="json"), "algorithm": ALGORITHM})
            if model.version != metadata.model_version:
                raise PersonaModelError("Model version fingerprint mismatch")
            records, vocabulary = json.loads(payloads["records.json"]), json.loads(payloads["vocabulary.json"])
            if not isinstance(records, list) or len(records) != metadata.n_records or fingerprint(records) != metadata.training_fingerprint:
                raise PersonaModelError("Invalid training record fingerprint or count")
            model.records = [TrainingRecord.model_validate(record, strict=True) for record in records]
            if len(_candidates(model.records)) != len(records):
                raise PersonaModelError("Invalid or duplicate training candidates")
            if (not isinstance(vocabulary, dict) or len(vocabulary) != metadata.n_features
                    or any(not isinstance(word, str) or not word or type(index) is not int for word, index in vocabulary.items())
                    or set(vocabulary.values()) != set(range(metadata.n_features))):
                raise PersonaModelError("Invalid vocabulary indices")
            if metadata.n_features > model.config.max_features or metadata.n_topics != min(model.config.n_topics, metadata.n_features, metadata.n_records):
                raise PersonaModelError("Inconsistent model dimensions")
            arrays = _arrays(payloads["parameters.npz"], metadata)
            model._vectorizer = TfidfVectorizer(vocabulary=vocabulary, stop_words="english", max_features=model.config.max_features)
            model._vectorizer.idf_ = arrays["idf"]
            model._nmf = NMF(n_components=metadata.n_topics, init="nndsvda",
                             random_state=model.config.seed, max_iter=model.config.max_iter)
            model._nmf.components_ = arrays["components"]
            model._nmf.n_components_, model._nmf.n_features_in_ = metadata.n_topics, metadata.n_features
            model._lexical = csr_matrix((arrays["lexical_data"], arrays["lexical_indices"], arrays["lexical_indptr"]),
                                        shape=(metadata.n_records, metadata.n_features))
            model._topics = arrays["topics"]
            return model
        except (OSError, ValueError, TypeError, KeyError, EOFError, zipfile.BadZipFile, RuntimeError) as error:
            raise PersonaModelError(f"Cannot load model artifact: {error}") from error