---
description: "Python coding rules for this project"
applyTo: "**/*.py"
---

# Python Rules

- Type hints on all public functions; keep them accurate (checked by the project's type checker if configured).
- Raise specific exceptions with context; never bare `except:` — catch what you can handle.
- No bare `print()` in library/app code; use the project's logging setup.
- Validate external input at boundaries (pydantic or the project's chosen tool).
- Follow the project's formatter/linter (ruff/black) configuration; do not fight it inline.
- Prefer pure functions and explicit dependencies over module-level state.
