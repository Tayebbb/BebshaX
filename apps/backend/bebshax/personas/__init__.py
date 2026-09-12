"""Persona Generation and Validation Package for BebshaX.

Provides data-grounded synthetic customer persona generation,
range and constraint validation, deterministic grounding scoring,
and study-scoped multi-tenant lifecycle management.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from bebshax.personas.generator import generate_personas_for_study
from bebshax.personas.validator import validate_synthetic_persona

if TYPE_CHECKING:
    from bebshax.personas.service import PersonaGenerationService


def __getattr__(name: str) -> Any:
    if name != "PersonaGenerationService":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module("bebshax.personas.service"), name)


__all__ = [
    "generate_personas_for_study",
    "validate_synthetic_persona",
    "PersonaGenerationService",
]
