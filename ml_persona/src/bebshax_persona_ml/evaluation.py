"""Offline cross-view retrieval proxies, not labels for business/customer fit."""

from __future__ import annotations

from collections import Counter
from time import perf_counter
from typing import Any

import numpy as np
from scipy.spatial.distance import jensenshannon

from .data import NARRATIVE_FIELDS, TrainingRecord
from .model import (
    PROTECTED_FIELDS, BusinessContext, PersonaModel, PersonaModelError, Selection,
    _complete, _feature_text, _identity_keys,
    _validate_seed,
)

QUERY_FIELDS = ("culinary_persona", "hobbies_and_interests")
PROFILE_FIELDS = tuple(field for field in NARRATIVE_FIELDS
                       if field not in {*QUERY_FIELDS, *PROTECTED_FIELDS, "persona"})
AGE_EDGES = [18, 25, 35, 45, 55, 65, 96]
MAX_GENERATION_QUERIES = 32


def _views(records: list[TrainingRecord]) -> tuple[list[str], list[str]]:
    queries = [_feature_text(record, [record.documents.get(field, "") for field in QUERY_FIELDS])
               for record in records]
    profiles = [_feature_text(record, [record.documents.get(field, "") for field in PROFILE_FIELDS])
                for record in records]
    return queries, profiles


def _metrics(ranks: list[float]) -> dict[str, float]:
    values = np.asarray(ranks, dtype=float)
    return {"mrr": float(np.mean(1 / values)),
            **{f"recall@{count}": float(np.mean(values <= count)) for count in (1, 5, 10)}}


def _rank(scores: np.ndarray, target: int, random: np.random.Generator) -> float:
    order = np.lexsort((random.random(len(scores)), -scores))
    return float(np.flatnonzero(order == target)[0] + 1)


def _age_distribution(
    generated: list[TrainingRecord], source: list[TrainingRecord],
) -> dict[str, Any]:
    counts = [np.histogram([record.age for record in records
                           if type(record.age) is int and 18 <= record.age <= 95], AGE_EDGES)[0]
              for records in (generated, source)]
    generated_counts, source_counts = counts
    divergence = (float(np.clip(jensenshannon(*counts, base=2) ** 2, 0, 1))
                  if all(values.sum() for values in counts) else None)
    return {
        "reference": "heldout_source_records", "bins": ["18-24", "25-34", "35-44", "45-54", "55-64", "65-95"],
        "generated_counts": generated_counts.tolist(), "source_counts": source_counts.tolist(),
        "generated_unknown": len(generated) - int(generated_counts.sum()),
        "source_unknown": len(source) - int(source_counts.sum()),
        "unknown_includes_invalid": True, "js_divergence": divergence,
        "protocol": "Base-2 Jensen-Shannon divergence; unknown/invalid ages excluded and counted, not imputed.",
    }


def _generation_metrics(
    model: PersonaModel, records: list[TrainingRecord], queries: list[str], valid: np.ndarray, seed: int,
) -> dict[str, Any]:
    random = np.random.default_rng(seed)
    available = np.flatnonzero(valid & np.array([len(query) <= 20000 for query in queries]))
    chosen = np.sort(random.choice(available, min(len(available), MAX_GENERATION_QUERIES), replace=False))
    batches: list[list[Selection]] = []
    latencies, failures = [], 0
    for index in chosen:
        started = perf_counter()
        try:
            batches.append(model.generate(
                BusinessContext(description=queries[index].ljust(3)), min(5, len(model.records)),
                seed=int(random.integers(0, 2**32)),
            ))
        except PersonaModelError:
            failures += 1
        latencies.append((perf_counter() - started) * 1000)
    generated = [selection for batch in batches for selection in batch]
    source = {record.record_id: record for record in model.records}
    structural = {key: 0 for key in (
        "incomplete_count", "underage_count", "duplicate_id_count", "duplicate_name_count",
        "duplicate_persona_count", "bundle_mismatch_count", "location_rewrite_count",
    )}
    cosine_sum, pair_count, unscorable = 0.0, 0, 0
    for batch in batches:
        keys = [key for selection in batch for key in _identity_keys(selection.record)]
        for field in ("id", "name", "persona"):
            values = [value for kind, value in keys if kind == field]
            structural[f"duplicate_{field}_count"] += len(values) - len(set(values))
        vectors = model._vectorizer.transform([_feature_text(selection.record) for selection in batch])
        nonempty = np.diff(vectors.indptr) > 0
        unscorable += int((~nonempty).sum())
        vectors = vectors[nonempty]
        if vectors.shape[0] > 1:
            summed = np.asarray(vectors.sum(axis=0)).ravel()
            cosine_sum += float((summed @ summed - vectors.multiply(vectors).sum()) / 2)
            pair_count += vectors.shape[0] * (vectors.shape[0] - 1) // 2
    for selection in generated:
        record, original = selection.record, source.get(selection.record.record_id)
        structural["incomplete_count"] += int(not _complete(record))
        structural["underage_count"] += int(type(record.age) is int and record.age < 18)
        structural["bundle_mismatch_count"] += int(record != original)
        structural["location_rewrite_count"] += int(original is not None and record.location != original.location)
    occupations = Counter(selection.record.occupation for selection in generated)
    topics = Counter(str(selection.topic) for selection in generated if selection.topic is not None)
    reference_occupations = {record.occupation for record in model.records}
    return {
        "requested_batches": len(chosen), "successful_batches": len(batches), "failed_batches": failures,
        "skipped_queries": len(records) - len(available), "sampled_out_queries": len(available) - len(chosen),
        "sample_count": len(generated), "structural": structural,
        "sampling_protocol": "Up to 32 seeded scorable heldout query pairs, up to 5 training prototypes per query. Oversized contexts skipped, never truncated.",
        "exact_source_reuse_rate": (1 - structural["bundle_mismatch_count"] / len(generated)) if generated else None,
        "reuse_interpretation": "Exact source reuse is expected for coherent prototype selection; these are not newly synthesized identities.",
        "age_distribution": _age_distribution([selection.record for selection in generated], records),
        "diversity": {"space": "training_tfidf_cosine", "scope": "within_generated_batches",
                      "pair_count": pair_count, "unscorable_profile_count": unscorable,
                      "mean_pairwise_cosine_distance": float(np.clip(1 - cosine_sum / pair_count, 0, 1)) if pair_count else None},
        "coverage": {
            "record_fraction": len({selection.record.record_id for selection in generated} & source.keys()) / len(source),
            "occupation_fraction": len(occupations.keys() & reference_occupations) / len(reference_occupations),
            "topic_fraction": (len(topics.keys() & {str(index) for index in range(model._topics.shape[1])})
                               / model._topics.shape[1]) if model._topics.shape[1] else None,
            "occupation_counts": dict(occupations), "topic_counts": dict(topics),
        },
        "latency_ms": {"mean": float(np.mean(latencies)) if latencies else 0.0,
                       "p95": float(np.percentile(latencies, 95)) if latencies else 0.0,
                       "total": float(sum(latencies))},
    }


def evaluate_model(
    model: PersonaModel, records: list[TrainingRecord], *, seed: int = 42,
) -> dict[str, Any]:
    """Rank complementary heldout profiles with training-only TF-IDF/NMF transforms."""
    started = perf_counter()
    _validate_seed(seed)
    if not isinstance(model, PersonaModel) or not isinstance(records, list) or not records:
        raise PersonaModelError("Evaluation requires a fitted model and nonempty heldout records")
    if not all(isinstance(record, TrainingRecord) for record in records):
        raise PersonaModelError("Evaluation requires TrainingRecord instances")
    training_keys = set().union(*(_identity_keys(record) for record in model.records))
    if any(_identity_keys(record) & training_keys for record in records):
        raise PersonaModelError("Evaluation identities must be heldout and disjoint from training")
    seen: set[tuple[str, str]] = set()
    for record in records:
        keys = _identity_keys(record)
        if keys & seen:
            raise PersonaModelError("Evaluation identities must be unique; duplicate found")
        seen.update(keys)
    queries, profiles = _views(records)
    query_lexical, query_topics = model._transform(queries)
    profile_lexical, profile_topics = model._transform(profiles)
    query_known, profile_known = np.diff(query_lexical.indptr) > 0, np.diff(profile_lexical.indptr) > 0
    query_present = np.array([bool(query.strip()) for query in queries])
    profile_present = np.array([bool(profile.strip()) for profile in profiles])
    valid = query_known & profile_known
    transform_ms = (perf_counter() - started) * 1000
    ranking_started = perf_counter()
    counts = Counter(record.occupation for record in model.records)
    popularity = np.array([counts[record.occupation] for record in records], dtype=float)
    ranks: dict[str, list[float]] = {name: [] for name in ("model", "lexical_tfidf", "popular_occupation")}
    random = np.random.default_rng(seed)
    for index in range(len(records)):
        ranks["popular_occupation"].append(_rank(popularity, index, random))
        if valid[index]:
            lexical_scores = (profile_lexical @ query_lexical[index].T).toarray().ravel()
            model_scores = model._scores(query_lexical[index], query_topics[index:index + 1],
                                         (profile_lexical, profile_topics))
            ranks["model"].append(_rank(model_scores, index, random))
            ranks["lexical_tfidf"].append(_rank(lexical_scores, index, random))
        else:
            ranks["model"].append(float("inf"))
            ranks["lexical_tfidf"].append(float("inf"))
    candidate_count = len(records)
    retrieval_ms = (perf_counter() - ranking_started) * 1000
    generation_started = perf_counter()
    generation = _generation_metrics(model, records, queries, valid, seed)
    return {
        "schema_version": 1, "model_version": model.version, "seed": seed,
        "interpretation": "Heldout cross-view retrieval is a proxy, not measured business relevance or customer demand.",
        "retrieval": {
            "rank_scope": "evaluation_records_only", "query_count": candidate_count,
            "candidate_count": candidate_count, "valid_query_count": int(valid.sum()),
            "query_fields": list(QUERY_FIELDS), "profile_fields": list(PROFILE_FIELDS),
            "invalid_view_counts": {
                "missing_query": int((~query_present).sum()), "missing_profile": int((~profile_present).sum()),
                "oov_query": int((query_present & ~query_known).sum()), "oov_profile": int((profile_present & ~profile_known).sum()),
            },
            "missing_view_policy": "Missing/OOV view pairs count as model/lexical misses, not dropped queries; text-free baselines can still rank.",
            **{name: _metrics(values) for name, values in ranks.items()},
            "random": {"mrr": float(np.mean(1 / np.arange(1, candidate_count + 1))),
                       **{f"recall@{count}": min(count / candidate_count, 1.0) for count in (1, 5, 10)}},
            "random_protocol": "Exact expected uniform random rank; no sampled baseline noise.",
            "popular_occupation_protocol": "Training occupation frequencies; seeded random ties, no heldout fitting.",
        },
        "generation": generation,
        "latency_ms": {"transform": transform_ms, "retrieval": retrieval_ms,
                       "generation": (perf_counter() - generation_started) * 1000,
                       "total": (perf_counter() - started) * 1000},
    }