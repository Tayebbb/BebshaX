"""Static invariant: every `TaskType.X` referenced anywhere in the package
must be a real enum member. Catches phantom members (e.g. the
`TaskType.INTERVIEW_PROBING` AttributeError found 2026-08-26) that only crash
at request time and slip past import-level collection.
"""

import re
from pathlib import Path

from bebshax.llm.types import TaskType

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "bebshax"
_REF = re.compile(r"\bTaskType\.([A-Z_]+)\b")


def test_every_tasktype_reference_is_a_real_member() -> None:
    unknown: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in _REF.findall(text):
            if name not in TaskType.__members__:
                unknown.append(f"{path.relative_to(PACKAGE_ROOT)}: TaskType.{name}")
    assert not unknown, f"references to nonexistent TaskType members: {unknown}"
