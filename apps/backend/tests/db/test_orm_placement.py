"""Convention guard: new ORM tables belong in the owning feature package's
orm.py (like behavioral/orm.py, memory/orm.py, interview/orm.py), NOT in the
shared db/models.py. The classes below are FROZEN pre-convention legacy —
this test fails when anything new is added there, without forcing a risky
mass-refactor of the existing ones.
"""

from sqlalchemy.orm import DeclarativeBase

import bebshax.db.models as models

FROZEN_LEGACY_CLASSES = {
    "Businesses",
    "DatasetCandidates",
    "DatasetPersonaRuns",
    "DatasetSources",
    "EvidenceChunks",
    "EvidenceClaims",
    "EvidenceSources",
    "LLMRequests",
    "MarketSegments",
    "ModelRegistry",
    "PersonaGenerationRuns",
    "Personas",
    "ResearchPlans",
    "ResearchRuns",
    "SavedAudiences",
    "SegmentationRuns",
    "Studies",
    "StudyReports",
}


def _orm_classes_defined_in_models() -> set[str]:
    found = set()
    for name in dir(models):
        obj = getattr(models, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, DeclarativeBase)
            and obj.__module__ == models.__name__
            and hasattr(obj, "__tablename__")
        ):
            found.add(name)
    return found


def test_no_new_tables_in_shared_models() -> None:
    current = _orm_classes_defined_in_models()
    added = current - FROZEN_LEGACY_CLASSES
    removed = FROZEN_LEGACY_CLASSES - current
    assert not added, (
        f"new ORM classes in shared db/models.py: {sorted(added)} — "
        "put new tables in the owning feature package's orm.py "
        "(see .github/instructions/conventions.instructions.md)"
    )
    assert not removed, (
        f"classes removed from db/models.py: {sorted(removed)} — "
        "update FROZEN_LEGACY_CLASSES if a deliberate refactor moved them"
    )
