"""Enforces RULES.md R1: provider SDK imports only inside bebshax/llm/adapters/."""

from pathlib import Path

import bebshax

FORBIDDEN_IMPORTS = ("freellmpool", "ollama", "litellm", "openai", "anthropic")


def test_provider_sdk_imports_only_inside_adapters() -> None:
    pkg_root = Path(bebshax.__file__).parent
    offenders: list[str] = []
    for py in pkg_root.rglob("*.py"):
        if "adapters" in py.parts:
            continue
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and any(
                f in stripped for f in FORBIDDEN_IMPORTS
            ):
                offenders.append(f"{py.relative_to(pkg_root)}:{lineno}: {stripped}")
    assert not offenders, "Provider SDK imports outside bebshax/llm/adapters/:\n" + "\n".join(
        offenders
    )
