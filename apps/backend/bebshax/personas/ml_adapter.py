"""Backend boundary for the independently trained local persona model."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, TypedDict, TypeVar

from bebshax_persona_ml.model import BusinessContext, PersonaModel, PersonaModelError, Selection
from bebshax_persona_ml.provenance import ExpectedArtifactManifest
from pydantic import ValidationError
from starlette.applications import Starlette

from bebshax.api.errors import APIError
from bebshax.persona.schema import GeneratedClaim, GeneratedPersona, PersonaProfile, coerce_provenance

if TYPE_CHECKING:
    from bebshax.config import Settings
    from bebshax.personas.generator import GeneratedPersonaDraft


_UNAVAILABLE_VALUE = "Not recorded"
_PROXY_WARNING = (
    "Selected from USA synthetic training data as a proxy; selection scores are not "
    "observed customer evidence or customer demand."
)
_AGE_RANGE = r"([+-]?\d+)\s*(?:[-\u2013\u2014]|\bto\b)\s*([+-]?\d+)"
_EXPLICIT_AGE_PATTERNS = (
    re.compile(r"\b(?:aged|ages|age)\s+" + _AGE_RANGE + r"(?!\w|\.\d)", re.IGNORECASE),
    re.compile(r"(?<![\w.+-])" + _AGE_RANGE + r"\s+years\s+old\b", re.IGNORECASE),
)
_Result = TypeVar("_Result")
logger = logging.getLogger(__name__)

# Mirrors the BusinessContext field limits; guarded by tests so drift is caught.
_RESEARCH_ITEM_LIMIT = 10_000
_RESEARCH_ITEMS_LIMIT = 100
_SCALAR_LIMITS = {"description": 20_000, "target_audience": 4_000, "location": 512, "price_range": 512, "product_category": 512, "role": 512}


class MLPersonaReadiness(TypedDict):
    status: Literal["configured", "available", "unavailable"]
    reason: str
    validation: Literal["manifest", "loaded", "unavailable"]
    model_loaded: bool
    expected_manifest_matched: bool


def _unsupported_context(reason: str | None = None) -> APIError:
    detail = "The local persona model cannot support the requested context or constraints."
    if reason:
        detail = f"{detail} ({reason})"
    logger.warning("ML persona context refused: %s", reason or "unspecified")
    return APIError(422, detail, error_code="ml_persona_unsupported_context")


def _validation_reason(error: ValidationError) -> str:
    first = error.errors()[0] if error.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", ())) or "context"
    return f"{location}: {first.get('msg', 'invalid value')}"


def _chunked(text: str, limit: int) -> list[str]:
    return [text[start:start + limit] for start in range(0, len(text), limit)]


def bounded_research(items: Any, extra: list[str] | None = None) -> list[str]:
    """Fit free-form research into the model's list limits without losing text.

    Callers hand over whole study histories (copilot transcripts, dataset
    statistics) as single JSON strings that outgrow the 10k per-item limit
    after a few conversation turns; the bag-of-words model does not care about
    item boundaries, so oversize items are split, never cut. Only when the
    total exceeds 100 chunks are the trailing chunks dropped, and that is logged.
    """
    chunks: list[str] = []
    for item in [*(items or []), *(extra or [])]:
        text = item.strip() if isinstance(item, str) else ""
        if text:
            chunks.extend(_chunked(text, _RESEARCH_ITEM_LIMIT))
    if len(chunks) > _RESEARCH_ITEMS_LIMIT:
        logger.warning("ML persona research context dropped %d trailing chunk(s) beyond the model limit", len(chunks) - _RESEARCH_ITEMS_LIMIT)
        chunks = chunks[:_RESEARCH_ITEMS_LIMIT]
    return chunks


def _explicit_age_bounds(text: str) -> tuple[int, int] | None:
    bounds: tuple[int, int] | None = None
    for pattern in _EXPLICIT_AGE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                minimum, maximum = (int(value) for value in match.groups())
            except ValueError as error:
                raise _unsupported_context("explicit age range is not numeric") from error
            if not 18 <= minimum <= maximum <= 95:
                raise _unsupported_context(f"explicit age range {minimum}-{maximum} is outside the supported 18-95 adult range")
            bounds = (minimum, maximum) if bounds is None else (
                max(bounds[0], minimum), min(bounds[1], maximum),
            )
            if bounds[0] > bounds[1]:
                raise _unsupported_context("explicit age ranges contradict each other")
    return bounds


def build_business_context(**fields: Any) -> BusinessContext:
    overflow: list[str] = []
    for name, limit in _SCALAR_LIMITS.items():
        value = fields.get(name)
        if isinstance(value, str) and len(value) > limit:
            # Keep the head in place and carry the remainder as research text.
            fields[name], remainder = value[:limit], value[limit:]
            overflow.append(remainder)
    fields["research"] = bounded_research(fields.get("research"), overflow)
    try:
        context = BusinessContext(**fields)
        minimum, maximum = context.min_age, context.max_age
        for text in (context.description, context.target_audience):
            bounds = _explicit_age_bounds(text)
            if bounds is not None:
                minimum = bounds[0] if minimum is None else max(minimum, bounds[0])
                maximum = bounds[1] if maximum is None else min(maximum, bounds[1])
        return BusinessContext(**{**context.model_dump(), "min_age": minimum, "max_age": maximum})
    except ValidationError as error:
        raise _unsupported_context(_validation_reason(error)) from error


def get_persona_ml(app: Starlette) -> MLPersonaAdapter:
    adapter = getattr(app.state, "persona_ml", None)
    if adapter is None:
        adapter = MLPersonaAdapter.from_settings()
        app.state.persona_ml = adapter
    return adapter


def _selection_warnings(selection: Selection) -> list[str]:
    warnings = [
        *selection.warnings, _PROXY_WARNING,
        "Income, budget, structured needs and personality measurements are unavailable in this model; no values were inferred.",
    ]
    if not selection.record.name:
        warnings.append("No name is available in the training record; the displayed identifier is synthetic, not learned.")
    for field in ("education", "location", "behaviors"):
        if not getattr(selection.record, field):
            warnings.append(f"No {field} is available in the training record; the value remains unknown.")
    return list(dict.fromkeys(warnings))


def to_generated_persona(selection: Selection) -> GeneratedPersona:
    record = selection.record
    if record.age is None:
        raise _unsupported_context()
    claims = {
        group: [GeneratedClaim(value=value, provenance="SYNTHETIC", evidence_ids=[]) for value in values]
        for group, values in (
            ("goals", record.goals), ("pain_points", record.pain_points), ("behaviors", record.behaviors),
        )
    }
    return GeneratedPersona(
        name=record.name or f"Synthetic profile {record.record_id}",
        age=record.age,
        occupation=record.occupation,
        location=record.location or _UNAVAILABLE_VALUE,
        income_range=_UNAVAILABLE_VALUE,
        education=record.education or _UNAVAILABLE_VALUE,
        description=record.description,
        goals=claims["goals"],
        pain_points=claims["pain_points"],
        behaviors=claims["behaviors"],
        detailed_attributes={
            "ml_provenance": {
                "source": record.source,
                "revision": record.revision,
                "record_id": record.record_id,
                "model_version": selection.model_version,
                "selection_score": selection.score,
                "topic": selection.topic,
                "strategy": selection.strategy,
                "source_attribution": selection.source_attribution.model_dump(mode="json"),
                "source_corpus_sha256": selection.source_corpus_sha256,
                "training_code_sha256": selection.training_code_sha256,
            },
            "source_documents": dict(record.documents),
            "validation_warnings": _selection_warnings(selection),
            "claim_provenance": {
                group: [claim.model_dump() for claim in group_claims]
                for group, group_claims in claims.items()
            },
        },
    )


def to_persona_profile(selection: Selection, business_id: str) -> PersonaProfile:
    profile = coerce_provenance(
        to_generated_persona(selection), business_id, [],
        generation_model=f"bebshax-persona-ml/{selection.model_version}",
    )
    return profile.model_copy(update={"warnings": _selection_warnings(selection)})


def to_persona_draft(selection: Selection) -> GeneratedPersonaDraft:
    from bebshax.personas.generator import GeneratedPersonaDraft

    generated = to_generated_persona(selection)
    return GeneratedPersonaDraft(
        name=generated.name,
        demographics={
            "age": generated.age,
            "occupation": generated.occupation,
            "location": generated.location,
            "education": generated.education,
            "income_or_budget": generated.income_range,
        },
        bio=generated.description,
        detailed_attributes=generated.detailed_attributes,
        goals=[claim.value for claim in generated.goals],
        pain_points=[claim.value for claim in generated.pain_points],
        behaviors=[claim.value for claim in generated.behaviors],
        dataset_refs=[dict(generated.detailed_attributes["ml_provenance"])],
        status="needs_review",
        validation_warnings=_selection_warnings(selection),
        generation_model=f"bebshax-persona-ml/{selection.model_version}",
    )


def to_workflow_persona(selection: Selection, *, role_id: str, role_title: str) -> dict[str, Any]:
    generated = to_generated_persona(selection)
    persona = to_persona_draft(selection).model_dump(mode="json")
    persona.update(generated.model_dump(include={
        "age", "occupation", "location", "income_range", "education", "description",
    }))
    name_parts = generated.name.split()
    persona.update({
        "id": f"per_{uuid.uuid4().hex[:12]}",
        "role_id": role_id,
        "role_title": role_title,
        "archetype": generated.occupation,
        "initials": "".join(part[0].upper() for part in name_parts[:2]),
        "status": "active",
        "version": 1,
        "badges": [],
        "attributes": [
            {"category": category, "title": claim.value, "provenance_class": "SYNTHETIC", "evidence_ids": [], "evidence": None}
            for category, claims in (
                ("Goals", generated.goals), ("Pain Points", generated.pain_points), ("Behaviors", generated.behaviors),
            )
            for claim in claims
        ],
        "grounding_ratio": 0.0,
        "consistency_score": 0.0,
        "grounding_basis": "synthetic_training_proxy",
        "evidence_claim_count": 0,
        "is_synthetic": True,
    })
    return persona


class MLPersonaAdapter:
    def __init__(
        self, artifact_dir: Path, *, max_concurrency: int = 1,
        expected_manifest: ExpectedArtifactManifest | None = None,
        verify_training_code: bool = False,
    ) -> None:
        if type(max_concurrency) is not int or max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive integer")
        if expected_manifest is not None and not isinstance(expected_manifest, ExpectedArtifactManifest):
            raise ValueError("expected_manifest must be a trusted ExpectedArtifactManifest")
        if type(verify_training_code) is not bool:
            raise ValueError("verify_training_code must be boolean")
        self.artifact_dir = artifact_dir
        self._expected_manifest = expected_manifest
        self._verify_training_code = verify_training_code
        self._model: PersonaModel | None = None
        self._load_failed = False
        self._unavailable_reason: str | None = None
        self._load_lock = threading.Lock()
        self._inference_limit = threading.BoundedSemaphore(max_concurrency)
        self._submission_limit = asyncio.Semaphore(max_concurrency)
        self._inflight: set[asyncio.Task[Any]] = set()

    @classmethod
    def from_settings(
        cls, settings: Settings | None = None, *, expected_manifest: ExpectedArtifactManifest | None = None,
        verify_training_code: bool = False, max_concurrency: int = 1,
    ) -> MLPersonaAdapter:
        if settings is None:
            from bebshax.config import get_settings

            settings = get_settings()
        expected = expected_manifest if expected_manifest is not None else settings.expected_ml_persona_manifest
        adapter = cls(
            settings.ml_persona_artifact_path, expected_manifest=expected,
            verify_training_code=verify_training_code, max_concurrency=max_concurrency,
        )
        if not settings.ml_persona_enabled:
            adapter._unavailable_reason = "feature_disabled"
        elif settings.environment in ("production", "staging") and expected is None:
            adapter._unavailable_reason = "expected_manifest_required"
        return adapter

    def _load(self) -> PersonaModel:
        with self._load_lock:
            if self._unavailable_reason is not None:
                raise APIError(503, "The local persona model is unavailable.", error_code="ml_persona_unavailable")
            if self._model is None:
                try:
                    checks: dict[str, Any] = {}
                    if self._expected_manifest is not None:
                        checks["expected_manifest"] = self._expected_manifest
                    if self._verify_training_code:
                        checks["verify_training_code"] = True
                    self._model = PersonaModel.load(self.artifact_dir, **checks)
                    self._load_failed = False
                except (OSError, PersonaModelError) as error:
                    self._load_failed = True
                    raise APIError(
                        503,
                        "The local persona model is unavailable.",
                        error_code="ml_persona_unavailable",
                    ) from error
            return self._model

    def _readiness(self) -> MLPersonaReadiness:
        unavailable: MLPersonaReadiness = {
            "status": "unavailable", "reason": "artifact_unavailable", "validation": "unavailable",
            "model_loaded": False, "expected_manifest_matched": False,
        }
        with self._load_lock:
            if self._unavailable_reason is not None:
                return {**unavailable, "reason": self._unavailable_reason}
            if self._model is not None:
                return {
                    "status": "available", "reason": "model_loaded", "validation": "loaded",
                    "model_loaded": True, "expected_manifest_matched": self._expected_manifest is not None,
                }
            if self._load_failed:
                return unavailable
            try:
                PersonaModel.validate_manifest(
                    self.artifact_dir, expected_manifest=self._expected_manifest,
                    verify_training_code=self._verify_training_code,
                )
            except (OSError, PersonaModelError):
                return unavailable
        return {
            "status": "configured", "reason": "lazy_model_load_pending", "validation": "manifest",
            "model_loaded": False, "expected_manifest_matched": self._expected_manifest is not None,
        }

    async def readiness(self) -> MLPersonaReadiness:
        return await self._run(self._readiness)

    def _generate(
        self,
        context: BusinessContext,
        num_personas: int,
        seed: int | None,
        exclude_ids: set[str] | None,
        exclude_names: set[str] | None,
    ) -> list[Selection]:
        with self._inference_limit:
            model = self._load()
            try:
                selections = model.generate(context, num_personas, seed, exclude_ids, exclude_names)
            except PersonaModelError as error:
                raise _unsupported_context(str(error)) from error
        results: list[Selection] = []
        for selection in selections:
            warnings = _selection_warnings(selection)
            if context.role.strip() and context.role.strip().casefold() != selection.record.occupation.strip().casefold():
                warnings.append("Source occupation retained; the requested role is a relevance hint, not a validated occupation constraint.")
            results.append(selection.model_copy(update={"warnings": warnings}))
        return results

    def _inference_finished(self, task: asyncio.Task[Any]) -> None:
        self._inflight.discard(task)
        self._submission_limit.release()
        if not task.cancelled():
            task.exception()

    async def _run(self, function: Callable[..., _Result], *args: Any) -> _Result:
        await self._submission_limit.acquire()
        inference = asyncio.create_task(asyncio.to_thread(function, *args))
        self._inflight.add(inference)
        inference.add_done_callback(self._inference_finished)
        return await asyncio.shield(inference)

    async def generate(
        self,
        context: BusinessContext,
        num_personas: int = 5,
        seed: int | None = None,
        exclude_ids: set[str] | None = None,
        exclude_names: set[str] | None = None,
    ) -> list[Selection]:
        return await self._run(
            self._generate, context, num_personas, seed, exclude_ids, exclude_names,
        )