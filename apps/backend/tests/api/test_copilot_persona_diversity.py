"""Persona diversity inside one study.

Observed live: roles are generated concurrently and two roles came back as
the same person ("Maria Chen" twice, incompatible bios). Duplicates are
regenerated once with the used names excluded; a survivor is flagged, never
silently renamed or dropped.
"""

import pytest

from bebshax.api.copilot import PersonaRoleSuggestion, _dedupe_persona_names


def _persona(name: str, role_id: str) -> dict:
    return {"name": name, "role_id": role_id, "description": f"{name} bio"}


_ROLES = [
    PersonaRoleSuggestion(id="r1", role="INDEPENDENT PIANO TEACHER", description=""),
    PersonaRoleSuggestion(id="r2", role="STUDIO OWNER", description=""),
]


async def test_unique_names_are_left_untouched() -> None:
    calls: list = []

    async def regenerate(role, avoid):
        calls.append(role.id)
        return [], None, None

    personas = [_persona("Maria Chen", "r1"), _persona("Daniel Ortiz", "r2")]
    assert await _dedupe_persona_names(list(personas), _ROLES, regenerate) == personas
    assert calls == []


async def test_duplicate_is_regenerated_with_used_names_excluded() -> None:
    seen_avoid: list[list[str]] = []

    async def regenerate(role, avoid):
        seen_avoid.append(list(avoid))
        return [_persona("Priya Raman", role.id)], None, None

    personas = [_persona("Maria Chen", "r1"), _persona("Maria  chen", "r2")]  # same person, sloppy spacing
    result = await _dedupe_persona_names(personas, _ROLES, regenerate)
    assert [p["name"] for p in result] == ["Maria Chen", "Priya Raman"]
    assert result[1]["role_id"] == "r2"
    assert seen_avoid == [["Maria  chen", "Maria Chen"]]


async def test_surviving_duplicate_is_flagged_not_hidden() -> None:
    async def regenerate(role, avoid):
        return [_persona("Maria Chen", role.id)], None, None  # the model insists

    personas = [_persona("Maria Chen", "r1"), _persona("Maria Chen", "r2")]
    result = await _dedupe_persona_names(personas, _ROLES, regenerate)
    assert len(result) == 2 and result[1]["name"] == "Maria Chen"
    assert any("duplicate_name" in w for w in result[1]["validation_warnings"])
    assert "validation_warnings" not in result[0]


async def test_regeneration_failure_keeps_and_flags_the_duplicate() -> None:
    async def regenerate(role, avoid):
        return [], object(), RuntimeError("route down")  # FailedRole-shaped tuple

    personas = [_persona("Maria Chen", "r1"), _persona("Maria Chen", "r2")]
    result = await _dedupe_persona_names(personas, _ROLES, regenerate)
    assert len(result) == 2 and result[1].get("validation_warnings")


@pytest.mark.parametrize("missing_role", ["r9", ""])
async def test_unknown_role_cannot_regenerate_so_the_duplicate_is_flagged(missing_role) -> None:
    async def regenerate(role, avoid):  # pragma: no cover - must not be called
        raise AssertionError("no role to regenerate with")

    personas = [_persona("Maria Chen", "r1"), _persona("Maria Chen", missing_role)]
    result = await _dedupe_persona_names(personas, _ROLES, regenerate)
    assert result[1].get("validation_warnings")
