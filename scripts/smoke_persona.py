"""Live end-to-end persona generation (REAL network + REAL Postgres).

Prereqs: docker compose up -d db && alembic upgrade head; optionally
`python scripts/setup_datasets.py --profile minimal` for evidence grounding.

Run:  .venv\\Scripts\\python scripts/smoke_persona.py
Not part of the unit suite (RULES.md R7).
"""

import sys
from collections import Counter

from dotenv import load_dotenv
from fastapi.testclient import TestClient


def main() -> int:
    load_dotenv()
    from bebshax.main import create_app

    app = create_app()
    with TestClient(app) as client:
        business = client.post(
            "/api/businesses",
            json={
                "name": "QuickBite Dhaka",
                "description": (
                    "An online food delivery service for students and young professionals "
                    "in Dhaka, Bangladesh, focused on affordable meals and fast delivery."
                ),
            },
        )
        if business.status_code != 201:
            print(f"SMOKE FAILED creating business: {business.status_code} {business.text}")
            return 1
        business_id = business.json()["id"]
        print(f"business created: {business_id}")

        print("generating persona (live LLM via PoolRouter — may take a while)...")
        generated = client.post(f"/api/businesses/{business_id}/personas", json={})
        if generated.status_code != 201:
            print(f"SMOKE FAILED generating persona: {generated.status_code} {generated.text}")
            return 1
        persona = generated.json()

        fetched = client.get(f"/api/personas/{persona['id']}")
        if fetched.status_code != 200:
            print(f"SMOKE FAILED fetching persona: {fetched.status_code}")
            return 1
        stored = fetched.json()

    prov_counts = Counter(a["provenance_class"] for a in stored["attributes"])
    print("SMOKE OK")
    print(f"  persona    : {stored['name']} — {stored['age']}, {stored['occupation']}, {stored['location']}")
    print(f"  model      : {stored['generation_model']}")
    print(f"  attributes : {len(stored['attributes'])} ({dict(prov_counts)})")
    print(f"  evidence   : {len(stored['evidence'])} item(s) attached")
    print(f"  warnings   : {stored['warnings'] or 'none'}")
    missing = [a for a in stored["attributes"] if not a.get("provenance_class")]
    if missing:
        print(f"  PROVENANCE MISSING on {len(missing)} attributes — FAIL")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
