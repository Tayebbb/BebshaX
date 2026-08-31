"""Enforces RULES.md R1: provider SDK imports only inside bebshax/llm/adapters/.

AST-based (not line matching) so it cannot be evaded by formatting, aliasing,
multi-line imports, or dynamic ``importlib.import_module("...")`` /
``__import__("...")`` calls with a literal module name. Dependency-free and
fast: one ``ast.parse`` per package file.
"""

import ast
from pathlib import Path

import bebshax

FORBIDDEN_ROOTS = frozenset({"freellmpool", "ollama", "litellm", "openai", "anthropic"})

_DYNAMIC_IMPORT_FUNCS = {"import_module", "__import__"}


def _root(module_name: str) -> str:
    return module_name.split(".", 1)[0]


def _is_dynamic_import(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "import_module":
        return True  # importlib.import_module(...) / any_alias.import_module(...)
    return isinstance(func, ast.Name) and func.id in _DYNAMIC_IMPORT_FUNCS


def _forbidden_uses(tree: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, description) for every forbidden import in the tree."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _root(alias.name) in FORBIDDEN_ROOTS:
                    found.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import inside bebshax — cannot reach a
            # top-level provider package.
            if node.module and node.level == 0 and _root(node.module) in FORBIDDEN_ROOTS:
                found.append((node.lineno, f"from {node.module} import ..."))
        elif isinstance(node, ast.Call) and _is_dynamic_import(node):
            for arg in node.args[:1]:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and _root(arg.value) in FORBIDDEN_ROOTS
                ):
                    found.append((node.lineno, f"dynamic import of {arg.value!r}"))
    return found


def test_provider_sdk_imports_only_inside_adapters() -> None:
    pkg_root = Path(bebshax.__file__).parent
    offenders: list[str] = []
    for py in sorted(pkg_root.rglob("*.py")):
        if "adapters" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for lineno, description in _forbidden_uses(tree):
            offenders.append(f"{py.relative_to(pkg_root)}:{lineno}: {description}")
    assert not offenders, "Provider SDK imports outside bebshax/llm/adapters/:\n" + "\n".join(
        offenders
    )


class TestDetectorCatchesEvasions:
    """The detector itself must flag patterns the old line-based test missed."""

    def _offenses(self, source: str) -> list[tuple[int, str]]:
        return _forbidden_uses(ast.parse(source))

    def test_plain_import(self):
        assert self._offenses("import openai")

    def test_aliased_import(self):
        assert self._offenses("import freellmpool as fp")

    def test_submodule_from_import(self):
        assert self._offenses("from litellm.router import Router")

    def test_multiline_parenthesized_import(self):
        assert self._offenses("from anthropic import (\n    Anthropic,\n)")

    def test_importlib_string_literal(self):
        assert self._offenses("import importlib\nimportlib.import_module('openai')")

    def test_dunder_import(self):
        assert self._offenses("__import__('ollama')")

    def test_clean_code_passes(self):
        source = (
            "from bebshax.llm.adapters.factory import build_default_adapters\n"
            "import importlib\n"
            "importlib.import_module('bebshax.llm.pools')\n"
        )
        assert not self._offenses(source)
