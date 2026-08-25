"""Persona Generation and Validation Package for BebshaX.

Provides data-grounded synthetic customer persona generation,
range and constraint validation, deterministic grounding scoring,
and study-scoped multi-tenant lifecycle management.
"""

from bebshax.personas.generator import generate_personas_for_study
from bebshax.personas.validator import validate_synthetic_persona
from bebshax.personas.service import PersonaGenerationService

__all__ = [
    "generate_personas_for_study",
    "validate_synthetic_persona",
    "PersonaGenerationService",
]
