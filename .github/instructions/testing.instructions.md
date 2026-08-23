---
description: "Test writing rules for this project"
applyTo: "**/*.{test,spec}.*"
---

# Test Rules

- Test names state behavior and condition ("returns 400 when query param is missing").
- One behavior per test; tests are independent and order-agnostic.
- Cover error paths and edge cases (null/empty/boundary), not just the happy path.
- Mock only true externals (network, clock, third-party APIs); prefer real implementations of project code.
- Deterministic: control time and randomness; no sleeps as synchronization.
- Fix implementations, not tests — unless the test is provably wrong.
