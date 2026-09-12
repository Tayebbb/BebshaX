"""Mechanically normalize only the public, empty-value environment template."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTRA_NAMES = {
    "BEBSHAX_POSTGRES_USER", "BEBSHAX_POSTGRES_PASSWORD", "BEBSHAX_POSTGRES_DB",
    "BEBSHAX_ARTIFACT_RELEASE_DIR", "BEBSHAX_BACKUP_SOURCE_URL", "BEBSHAX_RESTORE_TARGET_URL",
    "BEBSHAX_OPENROUTER_MODELS",
    "VITE_API_BASE", "VITE_NEON_AUTH_URL", "VITE_MOCK", "FREELLMPOOL_CONFIG",
}


def settings_names(source: str) -> set[str]:
    tree = ast.parse(source)
    settings = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Settings")
    return {f"BEBSHAX_{node.target.id.upper()}" for node in settings.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and not node.target.id.startswith("_")}


def render_template(previous: str, source: str) -> str:
    known = settings_names(source)
    names = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", previous, flags=re.MULTILINE))
    names = {name for name in names if "OLLAMA" not in name}
    names.update(known | EXTRA_NAMES)
    return "# Public names only. Supply real values through an operator-controlled environment.\n" + "".join(f"{name}=\n" for name in sorted(names))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--restore-documented-names", action="store_true", help="Preserve names from the committed public example, never values")
    arguments = parser.parse_args()
    example = ROOT / ".env.example"
    previous = example.read_text(encoding="utf-8")
    template_source = previous
    if arguments.restore_documented_names:
        result = subprocess.run(["git", "show", "HEAD:.env.example"], cwd=ROOT, capture_output=True, text=True, check=True)
        template_source += "\n" + "\n".join(f"{name}=" for name in re.findall(r"^([A-Z][A-Z0-9_]*)=", result.stdout, flags=re.MULTILINE))
    rendered = render_template(template_source, (ROOT / "apps/backend/bebshax/config.py").read_text(encoding="utf-8"))
    if arguments.write:
        example.write_text(rendered, encoding="utf-8")
    elif previous != rendered:
        print("FAIL: example template is stale or contains nonempty values; contents are not printed")
        return 1
    print("PASS: empty-value example template matches current Settings and explicit operations inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())