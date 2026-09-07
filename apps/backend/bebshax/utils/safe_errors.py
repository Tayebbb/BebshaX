"""Error-text hygiene shared by domain engines and the API layer.

Domain modules must not import ``bebshax.api`` (layering), so the helper the
engines persist instead of ``str(exc)`` lives here; ``bebshax.api.errors``
re-exports it.
"""

from __future__ import annotations

import hashlib


def safe_error_summary(exc: BaseException) -> str:
    """Persist/serve THIS instead of ``str(exc)``: the class name plus a short
    correlation code (hash of the real message). The raw text may echo prompt
    fragments, provider bodies, or secrets; the code lets an operator match the
    logged traceback without shipping the text."""
    digest = hashlib.sha256(f"{type(exc).__name__}:{exc}".encode("utf-8", "replace")).hexdigest()
    return f"{type(exc).__name__} (ref {digest[:8]})"


__all__ = ["safe_error_summary"]
