"""Auditable normalization and entity-disjoint splitting of synthetic profiles."""

from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


NARRATIVE_FIELDS = (
    "persona", "professional_persona", "sports_persona", "arts_persona",
    "travel_persona", "culinary_persona", "cultural_background",
    "skills_and_expertise", "hobbies_and_interests", "career_goals_and_ambitions",
)
CONSTRAINT_PATTERN = re.compile(
    r"\b(budget|costs?|expensive|struggl\w*|limited|lack\w*|difficult\w*|"
    r"challeng\w*|barrier\w*|concern\w*|worr\w*|pressure|constraint\w*|"
    r"unaffordable|frustrat\w*|dislik\w*|needs?)\b", re.IGNORECASE,
)
CONTACT_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|https?://\S+")


class TrainingRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str
    source: str
    revision: str
    age: int | None = Field(default=None, ge=18, le=95, strict=True)
    occupation: str = ""
    education: str = ""
    location: str = ""
    name: str | None = None
    description: str
    goals: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)
    documents: dict[str, str] = Field(default_factory=dict)


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _record(row: dict[str, Any], source: str, revision: str) -> TrainingRecord:
    identity = normalize_text(row.get("persona"))
    upstream_id = normalize_text(row.get("uuid"))
    if not identity or not upstream_id:
        raise ValueError("missing_identity")
    documents = {
        field: text for field in NARRATIVE_FIELDS
        if (text := normalize_text(row.get(field)))
    }
    if any(CONTACT_PATTERN.search(text) for text in documents.values()):
        raise ValueError("contact_information")
    name_match = re.match(
        r"^([A-Z][\w-]*(?: [A-Z][\w'-]*){1,3}?)(?=(?:['\u2019]s\b|[,;:]|\s+[a-z]))",
        identity,
    )
    goals = normalize_text(row.get("career_goals_and_ambitions"))
    sentences = dict.fromkeys(
        sentence.strip() for text in documents.values()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if CONSTRAINT_PATTERN.search(sentence)
    )
    return TrainingRecord(
        record_id=fingerprint([source, upstream_id]),
        source=source,
        revision=revision,
        age=row.get("age"),
        occupation=normalize_text(row.get("occupation")),
        education=normalize_text(row.get("education_level")),
        location=", ".join(
            value for field in ("city", "state", "country")
            if (value := normalize_text(row.get(field)))
        ),
        name=re.sub(r"['\u2019]s$", "", name_match.group(1)) if name_match else None,
        description=identity,
        goals=[goals] if goals else [],
        pain_points=list(sentences),
        behaviors=[documents[field] for field in ("hobbies_and_interests", "persona") if field in documents],
        documents=documents,
    )


def prepare_records(
    rows: list[dict[str, Any]], *, source: str, revision: str,
) -> tuple[list[TrainingRecord], dict[str, Any]]:
    records: list[TrainingRecord] = []
    seen_ids: set[str] = set()
    seen_content: set[str] = set()
    reasons: Counter[str] = Counter()
    duplicates = 0
    for row in rows:
        try:
            record = _record(row, source, revision)
        except ValidationError:
            reasons["invalid_schema"] += 1
            continue
        except ValueError as error:
            reasons[str(error)] += 1
            continue
        content_hash = fingerprint(record.model_dump(exclude={"record_id", "revision"}))
        if record.record_id in seen_ids or content_hash in seen_content:
            duplicates += 1
            continue
        seen_ids.add(record.record_id)
        seen_content.add(content_hash)
        records.append(record)
    return records, {
        "input": len(rows), "accepted": len(records),
        "rejected": sum(reasons.values()), "duplicates": duplicates,
        "rejection_reasons": dict(reasons),
        "missing": {field: sum(not getattr(record, field) for record in records)
                    for field in ("age", "occupation", "education", "location", "goals", "pain_points")},
        "age_distribution": dict(Counter(
            str((record.age // 10) * 10) if record.age else "unknown" for record in records
        )),
        "occupation_distribution": dict(Counter(record.occupation or "unknown" for record in records)),
        "location_distribution": dict(Counter(record.location or "unknown" for record in records)),
    }


def split_records(
    records: list[TrainingRecord], *, seed: int = 42,
    validation_fraction: float = 0.15, test_fraction: float = 0.15,
) -> dict[str, list[TrainingRecord]]:
    if not 0 < validation_fraction < 1 or not 0 < test_fraction < 1:
        raise ValueError("Split fractions must be between zero and one")
    if validation_fraction + test_fraction >= 1:
        raise ValueError("Split fractions leave no training data")
    parents = list(range(len(records)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    identities: dict[tuple[str, str], int] = {}
    for index, record in enumerate(records):
        content_key = " ".join(re.findall(r"\w+", record.description.casefold()))
        signatures = [("id", record.record_id), ("description", content_key)]
        if record.name:
            signatures.append(("name", normalize_text(record.name).casefold()))
        for signature in signatures:
            previous = identities.setdefault(signature, index)
            parents[root(index)] = root(previous)
    groups: dict[str, list[TrainingRecord]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[str(root(index))].append(record)
    keys = sorted(groups)
    if len(keys) < 3:
        raise ValueError("At least three independent identities are required")
    random.Random(seed).shuffle(keys)
    test_count = max(1, int(len(keys) * test_fraction))
    validation_count = max(1, int(len(keys) * validation_fraction))
    partitions = {
        "test": keys[:test_count],
        "validation": keys[test_count:test_count + validation_count],
        "train": keys[test_count + validation_count:],
    }
    if not partitions["train"]:
        raise ValueError("Split fractions leave no training data")
    return {name: [record for key in selected for record in groups[key]]
            for name, selected in partitions.items()}