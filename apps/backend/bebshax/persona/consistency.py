"""Deterministic, table-driven consistency rules (brief §18).

These gate personas BEFORE storage. The Phase-11 evaluator re-scores stored
personas independently; rules here are the generation-time contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from bebshax.persona.schema import PersonaProfile


@dataclass(frozen=True)
class ConsistencyViolation:
    code: str
    severity: str  # "error" blocks storage (after one refinement); "warning" is recorded
    message: str


# occupation keyword → minimum plausible age
OCCUPATION_MIN_AGE: dict[str, int] = {
    "retired": 50,
    "ceo": 25,
    "chief executive": 25,
    "executive": 24,
    "director": 26,
    "senior": 24,
    "professor": 28,
    "surgeon": 27,
    "principal": 28,
}

LOW_INCOME_MARKERS = ("student", "stipend", "minimum", "low", "entry-level", "unemployed")
LUXURY_MARKERS = ("luxury", "premium", "designer", "high-end", "first-class")
FREQUENCY_MARKERS = ("frequent", "regular", "weekly", "monthly", "often", "habitual")

# location substring → timezone mentions that contradict it
LOCATION_TZ_CONFLICTS: dict[str, tuple[str, ...]] = {
    "bangladesh": ("us pacific", "pacific time", "pst", "pdt", "us eastern"),
    "germany": ("us pacific", "pst", "pdt"),
    "japan": ("us pacific", "pst", "central european"),
}


def _texts(profile: PersonaProfile) -> list[str]:
    values = [profile.description]
    values.extend(a.value for a in profile.attributes)
    return [v.lower() for v in values if v]


def check_consistency(profile: PersonaProfile) -> list[ConsistencyViolation]:
    violations: list[ConsistencyViolation] = []
    occupation = profile.occupation.lower()

    for marker, min_age in OCCUPATION_MIN_AGE.items():
        if marker in occupation and profile.age < min_age:
            violations.append(
                ConsistencyViolation(
                    code="age_occupation",
                    severity="error",
                    message=(
                        f"age {profile.age} is implausible for occupation "
                        f"'{profile.occupation}' (marker '{marker}' implies ≥{min_age})"
                    ),
                )
            )
            break

    if "student" in occupation and profile.age > 60:
        violations.append(
            ConsistencyViolation(
                code="age_student",
                severity="warning",
                message=f"age {profile.age} is unusual for a student — verify intent",
            )
        )

    income = profile.income_range.lower()
    if any(marker in income for marker in LOW_INCOME_MARKERS):
        for text in _texts(profile):
            if any(l in text for l in LUXURY_MARKERS) and any(
                f in text for f in FREQUENCY_MARKERS
            ):
                violations.append(
                    ConsistencyViolation(
                        code="income_luxury",
                        severity="error",
                        message=(
                            f"income '{profile.income_range}' contradicts habitual "
                            f"luxury behavior: '{text[:120]}'"
                        ),
                    )
                )
                break

    location = profile.location.lower()
    for loc_marker, tz_conflicts in LOCATION_TZ_CONFLICTS.items():
        if loc_marker in location:
            for text in _texts(profile):
                conflict = next((tz for tz in tz_conflicts if tz in text), None)
                if conflict:
                    violations.append(
                        ConsistencyViolation(
                            code="location_timezone",
                            severity="warning",
                            message=(
                                f"location '{profile.location}' conflicts with "
                                f"timezone mention '{conflict}'"
                            ),
                        )
                    )
                    break
            break

    return violations
