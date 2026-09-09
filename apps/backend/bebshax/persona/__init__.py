"""Persona contracts with lazily loaded generation and evidence services."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from bebshax.persona.consistency import ConsistencyViolation, check_consistency
from bebshax.persona.schema import (
    EvidenceItem,
    GeneratedPersona,
    PersonaAttribute,
    PersonaProfile,
    ProvenanceClass,
)

if TYPE_CHECKING:
    from bebshax.persona.evidence import EvidenceStore
    from bebshax.persona.generation import PersonaEngine, PersonaGenerationFailed

_SERVICE_MODULES = {
    "EvidenceStore": "bebshax.persona.evidence",
    "PersonaEngine": "bebshax.persona.generation",
    "PersonaGenerationFailed": "bebshax.persona.generation",
}


def __getattr__(name: str) -> Any:
    if name not in _SERVICE_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(_SERVICE_MODULES[name]), name)


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
