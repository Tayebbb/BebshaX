"""Persona domain schema (brief §14/§17).

Every attribute carries a provenance class; SYNTHETIC assumptions are never
presented as facts. `coerce_provenance` enforces honesty in code rather than
trusting the LLM: evidence ids are validated against what was actually shown
to the model, and unverifiable claims are downgraded.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProvenanceClass(StrEnum):
    OBSERVED = "OBSERVED"  # directly supported by cited evidence
    INFERRED = "INFERRED"  # reasoned from business context / evidence themes
    SYNTHETIC = "SYNTHETIC"  # plausible assumption; no grounding


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=_uuid)
    source: str  # dataset id or "user_provided"
    text: str
    type: str = "dataset_record"
    relevance: float = 0.0
    confidence: float | None = None
    timestamp: datetime = Field(default_factory=_utcnow)


class PersonaAttribute(BaseModel):
    key: str  # group: goal | pain_point | need | motivation | behavior | ...
    value: str
    provenance_class: ProvenanceClass = ProvenanceClass.SYNTHETIC
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None


# ---- LLM output contract (what PERSONA_GENERATION must return as JSON) ----

class GeneratedClaim(BaseModel):
    value: str
    provenance: str = "SYNTHETIC"
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("claim value must be non-empty")
        return v


class BigFivePersonality(BaseModel):
    openness: int = Field(default=50, ge=0, le=100)
    conscientiousness: int = Field(default=50, ge=0, le=100)
    extroversion: int = Field(default=50, ge=0, le=100)
    agreeableness: int = Field(default=50, ge=0, le=100)
    neuroticism: int = Field(default=50, ge=0, le=100)


class GeneratedPersona(BaseModel):
    """Strict schema the model must emit. Groups mirror brief §14."""

    name: str
    age: int = Field(ge=16, le=95)
    occupation: str
    location: str
    income_range: str
    education: str
    description: str
    goals: list[GeneratedClaim] = Field(min_length=1)
    pain_points: list[GeneratedClaim] = Field(min_length=1)
    needs: list[GeneratedClaim] = Field(default_factory=list)
    motivations: list[GeneratedClaim] = Field(default_factory=list)
    behaviors: list[GeneratedClaim] = Field(default_factory=list)
    technology_usage: list[GeneratedClaim] = Field(default_factory=list)
    purchase_behavior: list[GeneratedClaim] = Field(default_factory=list)
    personality_traits: list[GeneratedClaim] = Field(default_factory=list)
    personality: BigFivePersonality | None = None
    detailed_attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "occupation", "location")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must be non-empty")
        return v


CLAIM_GROUPS: list[str] = [
    "goals",
    "pain_points",
    "needs",
    "motivations",
    "behaviors",
    "technology_usage",
    "purchase_behavior",
    "personality_traits",
]

# singular attribute keys stored in the DB, aligned with the Phase-11 evaluator
_GROUP_KEY = {
    "goals": "goal",
    "pain_points": "pain_point",
    "needs": "need",
    "motivations": "motivation",
    "behaviors": "behavior",
    "technology_usage": "technology_usage",
    "purchase_behavior": "purchase_behavior",
    "personality_traits": "personality_trait",
}


class PersonaProfile(BaseModel):
    """Validated, provenance-coerced persona ready for storage/serving."""

    id: str = Field(default_factory=_uuid)
    business_id: str
    name: str
    age: int
    occupation: str
    location: str
    income_range: str
    education: str
    description: str
    status: str = "active"
    version: int = 1
    generation_model: str | None = None
    attributes: list[PersonaAttribute] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def goals(self) -> list[str]:
        return [a.value for a in self.attributes if a.key == "goal"]

    @property
    def pain_points(self) -> list[str]:
        return [a.value for a in self.attributes if a.key == "pain_point"]

    def to_eval_dict(self) -> dict:
        """Shape consumed by the Phase-11 PersonaEvaluator."""
        return {
            "id": self.id,
            "business_id": self.business_id,
            "name": self.name,
            "age": self.age,
            "occupation": self.occupation,
            "description": self.description,
            "goals": self.goals,
            "pain_points": self.pain_points,
            "attributes": [
                {
                    "key": a.key,
                    "value": a.value,
                    "provenance_class": a.provenance_class.value,
                    "evidence_ids": a.evidence_ids,
                }
                for a in self.attributes
            ],
        }


def coerce_provenance(
    generated: GeneratedPersona,
    business_id: str,
    evidence: list[EvidenceItem],
    generation_model: str | None = None,
) -> PersonaProfile:
    """Convert model output into a PersonaProfile with ENFORCED provenance:
    - cited evidence ids must exist in the evidence actually shown → OBSERVED;
    - invalid/unknown citations are stripped and the claim downgrades to INFERRED;
    - unknown provenance labels downgrade to SYNTHETIC. Never upgraded."""
    known_ids = {e.id for e in evidence}
    attributes: list[PersonaAttribute] = []
    for group in CLAIM_GROUPS:
        for claim in getattr(generated, group):
            valid_ids = [eid for eid in claim.evidence_ids if eid in known_ids]
            label = claim.provenance.strip().upper()
            if valid_ids:
                prov = ProvenanceClass.OBSERVED
            elif label == "INFERRED":
                prov = ProvenanceClass.INFERRED
            elif label == "OBSERVED":
                # claimed observed but cited nothing verifiable → downgrade
                prov = ProvenanceClass.INFERRED
            else:
                prov = ProvenanceClass.SYNTHETIC
            attributes.append(
                PersonaAttribute(
                    key=_GROUP_KEY[group],
                    value=claim.value,
                    provenance_class=prov,
                    evidence_ids=valid_ids,
                )
            )
    return PersonaProfile(
        business_id=business_id,
        name=generated.name,
        age=generated.age,
        occupation=generated.occupation,
        location=generated.location,
        income_range=generated.income_range,
        education=generated.education,
        description=generated.description,
        generation_model=generation_model,
        attributes=attributes,
        evidence=list(evidence),
    )
