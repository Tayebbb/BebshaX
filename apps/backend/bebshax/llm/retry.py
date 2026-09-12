"""Provider recovery hints converted to durations before monotonic storage."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Mapping
from datetime import timezone
from email.utils import parsedate_to_datetime

_RESET_IN_MESSAGE = re.compile(r'X-RateLimit-Reset\\?"?\s*:\s*\\?"?(\d{10,16})', re.IGNORECASE)


def retry_after_hint(headers: Mapping | None, body: str | dict | None, *, now: float | None = None) -> float | None:
    current = time.time() if now is None else now
    hints: list[float] = []

    def collect(values: Mapping, depth: int = 0) -> None:
        if depth > 8:
            return
        for name, raw in values.items():
            key = str(name).casefold().replace("_", "-")
            if isinstance(raw, Mapping):
                collect(raw, depth + 1)
            if key not in {"retry-after", "x-ratelimit-reset", "x-rate-limit-reset", "ratelimit-reset"}:
                continue
            try:
                number = float(raw)
                if not math.isfinite(number) or number < 0:
                    continue
                if key not in {"retry-after", "ratelimit-reset"}:
                    number = number / 1000 if number > 10**11 else number
                    number -= current
                if number >= 0:
                    hints.append(number)
            except (ValueError, TypeError):
                try:
                    parsed = parsedate_to_datetime(str(raw))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    hints.append(max(0.0, parsed.timestamp() - current))
                except (ValueError, TypeError, OverflowError):
                    continue

    if headers is not None:
        collect(headers)
    if isinstance(body, dict):
        collect(body)
    elif isinstance(body, str):
        try:
            parsed = json.loads(body)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            collect(parsed)
        for match in _RESET_IN_MESSAGE.finditer(body):
            collect({"X-RateLimit-Reset": match.group(1)})
    return max(hints) if hints else None