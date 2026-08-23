---
description: "Security rules for sensitive paths: input validation, secrets, data handling."
applyTo: "apps/backend/bebshax/api/**,apps/backend/bebshax/config.py,.env*,scripts/**"
---

# Security Rules

- Validate all external input at the API boundary with **pydantic models** (length-capped fields, as in `api/personas.py`).
- Secrets come from **environment variables / `.env` (gitignored)** only; never hardcode, never log them; mask keys in any output (`gsk_****`).
- No authentication yet by design: the API binds to localhost for a single-researcher deployment — revisit before any network exposure (record a decision in PROJECT_CONTEXT.md first).
- Data rules: personas are synthetic — never ingest or store real PII; some free LLM tiers train on prompts, so nothing sensitive ever goes into an LLM request.
- Error responses stay generic in production paths; internals (provider errors, stack traces) belong in provenance records and logs, not HTTP bodies.
- Legitimate free-tier use only (R5): no rate-limit evasion, no account multiplication, no scraped endpoints.
