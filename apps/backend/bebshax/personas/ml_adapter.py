"""Backend boundary for the independently trained local persona model."""

from __future__ import annotations

import asyncio
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bebshax_persona_ml.model import BusinessContext, PersonaModel, PersonaModelError, Selection
from pydantic import ValidationError
from starlette.applications import Starlette

from bebshax.api.errors import APIError
from bebshax.persona.schema import GeneratedClaim, GeneratedPersona, PersonaProfile, coerce_provenance

if TYPE_CHECKING:
    from bebshax.config import Settings
    from bebshax.personas.generator import GeneratedPersonaDraft


_UNAVAILABLE_VALUE = "Not available in training data"
_PROXY_WARNING = (
    "Selected from USA synthetic training data as a proxy; selection scores are not "
    "observed customer evidence or customer demand."
)


def _unsupported_context() -> APIError:
    return APIError(
        422,
        "The local persona model cannot support the requested context or constraints.",
        error_code="ml_persona_unsupported_context",
    )


def build_business_context(**fields: Any) -> BusinessContext:
    try:
        return BusinessContext(**fields)
    except ValidationError as error:
        raise _unsupported_context() from error


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
    def __init__(self, artifact_dir: Path, *, max_concurrency: int = 1) -> None:
        if type(max_concurrency) is not int or max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive integer")
        self.artifact_dir = artifact_dir
        self._model: PersonaModel | None = None
        self._load_lock = threading.Lock()
        self._inference_limit = threading.BoundedSemaphore(max_concurrency)
        self._submission_limit = asyncio.Semaphore(max_concurrency)
        self._inflight: set[asyncio.Task[list[Selection]]] = set()

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> MLPersonaAdapter:
        from bebshax.config import get_settings

        return cls((settings or get_settings()).ml_persona_artifact_path)

    def _load(self) -> PersonaModel:
        with self._load_lock:
            if self._model is None:
                try:
                    self._model = PersonaModel.load(self.artifact_dir)
                except (OSError, PersonaModelError) as error:
                    raise APIError(
                        503,
                        "The local persona model is unavailable.",
                        error_code="ml_persona_unavailable",
                    ) from error
            return self._model

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
                raise _unsupported_context() from error
        results: list[Selection] = []
        for selection in selections:
            warnings = _selection_warnings(selection)
            if context.role.strip() and context.role.strip().casefold() != selection.record.occupation.strip().casefold():
                warnings.append("Source occupation retained; the requested role is a relevance hint, not a validated occupation constraint.")
            results.append(selection.model_copy(update={"warnings": warnings}))
        return results

    def _inference_finished(self, task: asyncio.Task[list[Selection]]) -> None:
        self._inflight.discard(task)
        self._submission_limit.release()
        if not task.cancelled():
            task.exception()

    async def generate(
        self,
        context: BusinessContext,
        num_personas: int = 5,
        seed: int | None = None,
        exclude_ids: set[str] | None = None,
        exclude_names: set[str] | None = None,
    ) -> list[Selection]:
        await self._submission_limit.acquire()
        inference = asyncio.create_task(asyncio.to_thread(
            self._generate, context, num_personas, seed, exclude_ids, exclude_names,
        ))
        self._inflight.add(inference)
        inference.add_done_callback(self._inference_finished)
        return await asyncio.shield(inference)