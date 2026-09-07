"""Infrastructure failure taxonomy and per-kind fallback policy.

Owner rule (2026-08-22): LOW ANSWER QUALITY IS NOT A FAILURE KIND HERE.
Quality assessment belongs to the evaluation layer (Phase 11) and must never
trigger silent infrastructure fallback. A test enforces this.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class FailureKind(StrEnum):
    TIMEOUT = "TIMEOUT"
    CONNECTION = "CONNECTION"
    RATE_LIMITED = "RATE_LIMITED"  # HTTP 429
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"  # daily/monthly cap hit
    SERVER_ERROR = "SERVER_ERROR"  # HTTP 5xx
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    AUTH_INVALID = "AUTH_INVALID"  # 401/403 — bad or revoked key
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"  # 404 / model removed
    CONTEXT_WINDOW_EXCEEDED = "CONTEXT_WINDOW_EXCEEDED"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"  # tools/JSON/vision missing
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"  # invalid JSON/tool payload, empty reply
    CONTENT_REFUSAL = "CONTENT_REFUSAL"
    INTERNAL_ERROR = "INTERNAL_ERROR"  # bug in our own layer — surface it


CooldownScope = Literal["route", "provider"]


@dataclass(frozen=True)
class FailurePolicy:
    retry_same_once: bool  # one immediate retry on the same route
    try_next_candidate: bool  # advance the fallback chain
    cooldown_route: bool  # temporarily remove route from selection
    # "route" cools (provider, model); "provider" cools every model of the
    # provider — for account-level signals where sibling models share the fate.
    cooldown_scope: CooldownScope = "route"


# Consumed by the Phase-5 router. CONTEXT_WINDOW_EXCEEDED advances only to
# larger-context candidates; INTERNAL_ERROR never burns candidates.
FAILURE_POLICIES: dict[FailureKind, FailurePolicy] = {
    FailureKind.TIMEOUT: FailurePolicy(False, True, False),
    FailureKind.CONNECTION: FailurePolicy(True, True, False),
    FailureKind.RATE_LIMITED: FailurePolicy(False, True, True, cooldown_scope="provider"),
    FailureKind.QUOTA_EXHAUSTED: FailurePolicy(False, True, True, cooldown_scope="provider"),
    FailureKind.SERVER_ERROR: FailurePolicy(False, True, True),
    FailureKind.PROVIDER_UNAVAILABLE: FailurePolicy(False, True, True),
    FailureKind.AUTH_INVALID: FailurePolicy(False, True, True, cooldown_scope="provider"),
    FailureKind.MODEL_UNAVAILABLE: FailurePolicy(False, True, True),
    FailureKind.CONTEXT_WINDOW_EXCEEDED: FailurePolicy(False, True, False),
    FailureKind.CAPABILITY_UNSUPPORTED: FailurePolicy(False, True, False),
    FailureKind.MALFORMED_RESPONSE: FailurePolicy(True, True, False),
    FailureKind.CONTENT_REFUSAL: FailurePolicy(False, True, False),
    FailureKind.INTERNAL_ERROR: FailurePolicy(False, False, False),
}


class LLMError(Exception):
    """Base class for infrastructure-level LLM errors."""


class AttemptFailed(LLMError):
    """One provider/model attempt failed, classified by kind. Raised by adapters."""

    def __init__(self, kind: FailureKind, provider: str, model: str, detail: str = "") -> None:
        self.kind = kind
        self.provider = provider
        self.model = model
        self.detail = detail
        super().__init__(f"{kind}: {provider}/{model}: {detail}")


class ContextWindowExceeded(LLMError):
    """No eligible model can fit the request. NEVER silently truncate instead."""

    def __init__(self, estimated_tokens: int, largest_window: int | None = None) -> None:
        self.estimated_tokens = estimated_tokens
        self.largest_window = largest_window
        super().__init__(
            f"request needs ~{estimated_tokens} tokens; "
            f"largest eligible model window: {largest_window}"
        )


class AllCandidatesFailed(LLMError):
    """Every eligible candidate failed. Carries the full provenance trail."""

    def __init__(self, provenance) -> None:
        self.provenance = provenance
        super().__init__(f"all candidates failed after {len(provenance.attempts)} attempt(s)")
