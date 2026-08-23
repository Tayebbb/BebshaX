---
description: "Security rules for this project's sensitive paths: input validation, authn/authz, secrets, data handling. Use when touching auth, APIs, user input, or secrets."
applyTo: "TODO(ecc): set SECURITY_GLOBS"
---


# Security Rules

- Validate all external input at the boundary with TODO(ecc): set VALIDATION_LIB; internal code trusts validated types.
- Authorization is checked in TODO(ecc): set AUTHZ_LOCATION on every state-changing operation — never only in the UI.
- Secrets come from TODO(ecc): set SECRET_SOURCE ; never hardcode, never log them.
- Database access uses parameterized queries/ORM bindings only — no string-built queries.
- TODO(ecc): set DATA_RULES - Error responses in production are generic; details go to logs with request IDs, without sensitive payloads.
- New endpoints require: input schema, authz check, rate limit decision, audit-log decision.
- Run `/security-review` before merging changes to any path this file covers.
