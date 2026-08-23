# BebshaX — Project Guidelines

## Stack

TypeScript · Python · pip

## Commands (verified against this repo)

| Action  | Command         |
| ------- | --------------- |
| Install | pip install -r requirements.txt |
| Build   | echo "no build step"   |
| Test    | TODO(ecc): set TEST_CMD    |
| Lint    | ruff check .    |

Use these exact commands; do not substitute other package managers or flags.

## Conventions

- Follow the patterns of neighboring files; ask before introducing a new pattern.

## Working Rules

- Inspect existing code and follow its patterns before writing new code.
- Prefer minimal, focused changes; do not modify files unrelated to the task.
- Plan multi-file changes before implementing (`/plan`); implement test-first where practical (`/tdd`).
- Run the verification gate before declaring work done (`/verify`).
- Never commit secrets, debug output, or generated artifacts.

## Project Context

- Canonical context: [.github/copilot/foundation.md](copilot/foundation.md) — read it before planning large changes.
- Recorded decisions: [.github/copilot/decisions.md](copilot/decisions.md) — do not relitigate; propose a new decision entry instead.

## Framework

This project uses the Everything Copilot Code framework (agents, skills, and hooks provided globally via plugin). Key workflows: `/plan`, `/tdd`, `/verify`, `/code-review`, `/security-review`, `/checkpoint`, `/release-readiness`.
