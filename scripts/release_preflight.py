"""Local release checks by default; optional explicit HTTP readiness, no .env."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops.artifacts import ArtifactError, verify_bundle
from scripts.ops.dependencies import check as check_dependencies


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def ready_url(base: str) -> str:
    parsed = urlsplit(base)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Supply an API origin without credentials, path or query")
    if not parsed.hostname or parsed.scheme not in ({"http", "https"} if local else {"https"}):
        raise ValueError("Remote API readiness requires an explicit HTTPS origin")
    return base.rstrip("/") + "/api/health/ready"


def check_readiness(base: str) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(ready_url(base), timeout=12) as response:
        content = response.read(65537)
        if response.status != 200 or len(content) > 65536:
            raise ValueError("Readiness did not return a bounded successful response")
    result = json.loads(content)
    if not isinstance(result, dict) or result.get("status") != "ready" or result.get("db") != "ok":
        raise ValueError("The API did not report schema/model/database readiness")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--api-url")
    parser.add_argument("--allow-network", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.api_url and not arguments.allow_network:
            raise ValueError("HTTP probing requires --allow-network")
        if bool(arguments.bundle) != bool(arguments.manifest_sha256):
            raise ValueError("Bundle checks require both the path and its independently approved manifest SHA256")
        check_dependencies()
        if arguments.bundle:
            verify_bundle(arguments.bundle, arguments.manifest_sha256)
            print("PASS: supplied recovery bundle integrity and lineage")
        if arguments.api_url:
            check_readiness(arguments.api_url)
            print("PASS: explicitly selected API readiness")
        print("Scope: local dependency checks plus only the requested probes; remote inference availability is unverified")
        print("CPU persona selection and labeled cached examples do not provide offline live chat")
        return 0
    except (OSError, ValueError, ArtifactError) as error:
        print(f"Preflight blocked: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())