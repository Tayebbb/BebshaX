"""Inspect public release metadata without registry login or credential files."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
IMAGE_QUERIES = {
    "python": ("library/python", "3.12."),
    "node": ("library/node", "24.20.0"),
    "nginx": ("library/nginx", "1.30.4"),
    "postgres": ("pgvector/pgvector", "pg16"),
}
ACTION_REFS = {
    "actions/checkout": "v4",
    "actions/setup-python": "v5",
    "actions/setup-node": "v4",
    "actions/upload-artifact": "v4",
    "gitleaks/gitleaks-action": "v2",
    "aquasecurity/trivy-action": "0.35.0",
}


def public_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "BebshaX-release-verifier"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read(4 * 1024 * 1024 + 1)
    if len(content) > 4 * 1024 * 1024:
        raise ValueError("Registry metadata exceeds the inspection limit")
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("Registry response is not an object")
    return result


def candidates() -> dict[str, Any]:
    output = {}
    for label, (repository, prefix) in IMAGE_QUERIES.items():
        data = public_json(f"https://hub.docker.com/v2/repositories/{repository}/tags?page_size=25&name={prefix}")
        output[label] = [
            {"tag": item["name"], "digest": item["digest"], "updated": item["last_updated"]}
            for item in data["results"]
            if any(image.get("architecture") == "amd64" and image.get("os") == "linux" for image in item["images"])
        ]
    return output


def actions() -> dict[str, Any]:
    output = {}
    for repository, tag in ACTION_REFS.items():
        try:
            data = public_json(f"https://api.github.com/repos/{repository}/git/ref/tags/{tag}")
            target = data["object"]
            for _attempt in range(3):
                if target["type"] == "commit":
                    break
                if target["type"] != "tag":
                    raise ValueError("Unexpected Git reference type")
                target = public_json(target["url"])["object"]
            if target["type"] != "commit" or not re.fullmatch(r"[0-9a-f]{40}", target["sha"]):
                raise ValueError("No immutable commit found")
            output[repository] = {"tag": tag, "sha": target["sha"]}
        except urllib.error.HTTPError as error:
            output[repository] = {"tag": tag, "status": error.code}
    return output


def check() -> dict[str, str]:
    inventory = json.loads((ROOT / "deploy/images.json").read_text(encoding="utf-8"))
    for image in inventory["images"].values():
        repository, tag, digest = image["repository"], image["tag"], image["digest"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("Invalid recorded image digest")
        data = public_json(f"https://hub.docker.com/v2/repositories/{repository}/tags/{tag}")
        if data["digest"] != digest:
            raise ValueError("Registry tag moved; review a new digest without silently updating the pin")
    return {"status": "PASS", "scope": "public image index digests; not image CVEs or running containers"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("candidates", "actions", "check"))
    arguments = parser.parse_args()
    try:
        result = {"candidates": candidates, "actions": actions, "check": check}[arguments.operation]()
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError):
        print("Public release metadata verification failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())