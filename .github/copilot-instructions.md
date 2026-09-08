# BebshaX — Copilot Instructions

**The single agent contract for this repo is [AGENTS.md](../AGENTS.md).** Read it first, then [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) and [RULES.md](../RULES.md). This file only adds the verified command table.

## Commands (verified against this repo)

| Action                       | Command (Windows dev machine)                                                                                 |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Install backend              | `.venv\Scripts\pip install -e ml_persona -e "apps/backend[dev]"`                                              |
| Test (unit)                  | `.venv\Scripts\python -m pytest apps/backend/tests -q`                                                        |
| Test (integration, needs db) | `.venv\Scripts\python -m pytest apps/backend/tests -m integration -q`                                         |
| Run full stack               | `node scripts/dev.js`                                                                                         |
| Run API                      | `.venv\Scripts\python -m uvicorn bebshax.main:app --host 127.0.0.1 --port 8000`                               |
| Database                     | `docker compose up -d --wait db` then `cd apps/backend && ..\..\.venv\Scripts\python -m alembic upgrade head` |
| Datasets                     | `.venv\Scripts\python scripts/setup_datasets.py --profile minimal`                                            |
| Frontend                     | `cd apps/frontend && npm ci && npm run build && npm test -- --run`                                            |

CI runs Ubuntu (`python -m pytest apps/backend/tests -q`) — keep code and tests portable.

# GSAP Animation Guidelines

Use GSAP and the installed official GSAP Skills whenever implementing animation in this project.

## Core principles

- Use GSAP for complex UI animation, timelines, scroll-driven animation, transitions, parallax, and coordinated motion.
- Do not introduce another animation library unless there is a strong technical reason.
- Prefer subtle, purposeful motion over decorative animation.
- Animations should feel cinematic, smooth, spatial, and physically believable.
- Use transforms and opacity where possible for performance.
- Avoid layout-triggering animations when unnecessary.
- Respect `prefers-reduced-motion`.

## React

When working in React:

- Prefer `useGSAP()` from `@gsap/react`.
- Use refs to scope animations.
- Properly clean up animations and ScrollTriggers.
- Avoid uncontrolled global DOM selectors.
- Make animations responsive.
- Handle component mounting/unmounting correctly.

## Motion direction

The visual language should feel:

- Apple-inspired
- cinematic
- spatial
- premium
- dark-first
- subtly futuristic
- restrained rather than flashy
- smooth and tactile

Use:

- GSAP timelines for orchestrated sequences
- ScrollTrigger for scroll-driven storytelling
- staggered reveals for typography and cards
- subtle Z-axis/depth movement
- physically believable easing
- inertia/momentum where appropriate
- tactile hover and click feedback
- smooth modal/drawer transitions
- meaningful micro-interactions

## Important

Before adding animation:

1. Inspect the existing component and surrounding UI.
2. Determine what the animation communicates.
3. Choose the simplest GSAP technique that achieves the desired result.
4. Check responsiveness.
5. Check accessibility and reduced-motion behavior.
6. Avoid animation that makes the interface slower or distracting.

Do not blindly animate every element.

Motion should reinforce hierarchy, interaction, depth, feedback, and storytelling.
