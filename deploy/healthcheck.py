"""Bounded loopback readiness probe; never calls providers or prints responses."""

import json
import sys
import urllib.request

TIMEOUT_SECONDS = 12


def main() -> int:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8000/api/health/ready", timeout=TIMEOUT_SECONDS) as response:
            body = response.read(65537)
            if len(body) > 65536 or response.status != 200:
                return 1
        payload = json.loads(body)
        return 0 if payload.get("status") == "ready" and payload.get("db") == "ok" else 1
    except (OSError, ValueError, AttributeError):
        return 1


if __name__ == "__main__":
    sys.exit(main())