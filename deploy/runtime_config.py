"""Validate public production settings before exec; never load credential files."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from urllib.parse import urlsplit


def https_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("An exact public HTTPS frontend origin is required")
    if parsed.path not in ("", "/") or parsed.port or re.search(r"[\s*'\"<>;\\]", value):
        raise ValueError("The frontend origin cannot contain a path, port, wildcard or policy delimiters")
    if not re.fullmatch(r"[a-zA-Z0-9.-]+", parsed.hostname) or "." not in parsed.hostname \
            or re.fullmatch(r"[\d.]+", parsed.hostname) or parsed.hostname.endswith(".localhost"):
        raise ValueError("The frontend origin must use a qualified public hostname")
    return f"https://{parsed.hostname}"


def validate(environment: Mapping[str, str]) -> None:
    if environment.get("BEBSHAX_ENVIRONMENT") not in {"production", "staging"}:
        raise ValueError("Release containers require an explicit hosted environment")
    origin = https_origin(environment.get("BEBSHAX_FRONTEND_BASE_URL", ""))
    if environment.get("BEBSHAX_CORS_ORIGINS", "").rstrip("/") != origin or environment.get("BEBSHAX_CORS_ORIGIN_REGEX", ""):
        raise ValueError("Credentialed CORS must match the exact frontend origin, with no regex")
    if environment.get("BEBSHAX_DEMO_MODE", "false").lower() not in {"false", "0"}:
        raise ValueError("Demo seeding is forbidden in release containers")
    if environment.get("BEBSHAX_ML_PERSONA_REQUIRED", "").lower() != "true":
        raise ValueError("The release requires explicit model readiness")
    if not re.fullmatch(r"[0-9a-f]{64}", environment.get("BEBSHAX_ML_PERSONA_MANIFEST_SHA256", "")):
        raise ValueError("The release requires an independently approved model metadata SHA256")


def main() -> int:
    try:
        validate(os.environ)
        if len(sys.argv) < 2:
            raise ValueError("No server command was supplied")
        os.execvp(sys.argv[1], sys.argv[1:])
    except (ValueError, OSError) as error:
        print(f"Release configuration blocked: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())