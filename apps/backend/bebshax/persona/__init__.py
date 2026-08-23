"""BebshaX persona engine: evidence-grounded persona generation.

Pipeline (brief §15): business context → evidence retrieval (Phase-7 datasets)
→ persona-driven prompt (PersonaHub methodology: a seed persona diversifies
perspective, it is never copied) → PERSONA_GENERATION via LLMService →
parse/validate → provenance coercion → deterministic consistency rules →
optional CRITIC → store.
"""

from bebshax.persona.consistency import ConsistencyViolation, check_consistency
from bebshax.persona.evidence import EvidenceStore
from bebshax.persona.generation import PersonaEngine, PersonaGenerationFailed
from bebshax.persona.schema import (
    EvidenceItem,
    GeneratedPersona,
    PersonaAttribute,
    PersonaProfile,
    ProvenanceClass,
)

__all__ = [
    "ConsistencyViolation",
    "EvidenceItem",
    "EvidenceStore",
    "GeneratedPersona",
    "PersonaAttribute",
    "PersonaEngine",
    "PersonaGenerationFailed",
    "PersonaProfile",
    "ProvenanceClass",
    "check_consistency",
]
