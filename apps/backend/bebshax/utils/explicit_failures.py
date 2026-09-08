"""Explicit, layer-neutral failures for "the AI could not do this" situations.

RULES.md R2: a request that cannot be served honestly must FAIL VISIBLY — never
be answered with a template, a canned list, or invented numbers. These
exceptions let domain modules (persona generation, research, segmentation,
behavioral simulation, …) refuse without importing the API layer; the API
layer maps them onto the standard error envelope
``{detail, error_code, request_id, ...extra}``.

They are deliberately NOT ``FailureKind``s and NOT ``LLMError``s: an
unparseable or empty model reply is an output-quality problem, not an
infrastructure failure, so it must never trigger routing fallback (R2/R6).
"""

from __future__ import annotations

from typing import Any


class ExplicitFailure(Exception):
    """Base: carries the HTTP status and error code the envelope should show."""

    status_code: int = 502
    error_code: str = "explicit_failure"

    def __init__(
        self,
        detail: str,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        self.extra = dict(extra or {})
        super().__init__(f"{self.error_code}: {detail}")


class LLMUnavailable(ExplicitFailure):
    """No LLM service is wired for this feature (misconfiguration, not a template trigger)."""

    status_code = 503
    error_code = "llm_unavailable"

    def __init__(self, feature: str, **kwargs: Any) -> None:
        super().__init__(
            f"{feature} needs the AI routing layer, which is not configured on this server.",
            **kwargs,
        )


class UnusableModelOutput(ExplicitFailure):
    """The model answered, but the reply could not be used (after a retry).

    Reported instead of silently substituting content. ``attempts`` records how
    many model replies were tried so the envelope can say so.
    """

    status_code = 502

    def __init__(
        self,
        error_code: str,
        detail: str,
        *,
        attempts: int = 1,
        served_by: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        merged = {"attempts": attempts, "served_by": served_by, **(extra or {})}
        super().__init__(detail, error_code=error_code, extra=merged)
        self.attempts = attempts
        self.served_by = served_by


class InsufficientInput(ExplicitFailure):
    """A precondition the user must satisfy first (e.g. attach a dataset, generate a script)."""

    status_code = 400

    def __init__(self, error_code: str, detail: str, *, extra: dict[str, Any] | None = None) -> None:
        super().__init__(detail, error_code=error_code, extra=extra)


__all__ = ["ExplicitFailure", "InsufficientInput", "LLMUnavailable", "UnusableModelOutput"]
