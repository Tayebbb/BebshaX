"""Live 5-turn interview consistency check (REAL network + REAL Postgres).

Phase-10 exit criterion: name/age/occupation stay consistent across 5 turns.
Run:  .venv\\Scripts\\python scripts/smoke_interview.py [persona_id]
Not part of the unit suite (RULES.md R7).
"""

import sys

from dotenv import load_dotenv
from fastapi.testclient import TestClient

QUESTIONS = [
    "Hi! Could you introduce yourself — your name and what you do?",
    "How old are you, if you don't mind me asking?",
    "Walk me through how you usually order food online.",
    "What's the most frustrating part of the experience?",
    "Quick recap: what was your name and occupation again?",
]


def main() -> int:
    load_dotenv()
    from bebshax.main import create_app

    app = create_app()
    with TestClient(app) as client:
        if len(sys.argv) > 1:
            persona_id = sys.argv[1]
            persona = client.get(f"/api/personas/{persona_id}").json()
        else:
            business = client.post(
                "/api/businesses",
                json={
                    "name": "QuickBite Dhaka",
                    "description": "Online food delivery for students and young professionals in Dhaka.",
                },
            ).json()
            print("generating a fresh persona (live)...")
            created = client.post(f"/api/businesses/{business['id']}/personas", json={})
            if created.status_code != 201:
                print(f"SMOKE FAILED generating persona: {created.status_code} {created.text}")
                return 1
            persona = created.json()
            persona_id = persona["id"]

        name, age, occupation = persona["name"], persona["age"], persona["occupation"]
        print(f"persona: {name} — {age}, {occupation}\n")

        conversation = client.post(
            f"/api/personas/{persona_id}/conversations",
            json={"objective": "understand food-delivery habits and pain points"},
        ).json()

        replies: list[str] = []
        for i, question in enumerate(QUESTIONS, 1):
            response = client.post(
                f"/api/conversations/{conversation['id']}/messages", json={"message": question}
            )
            if response.status_code != 200:
                print(f"SMOKE FAILED on turn {i}: {response.status_code} {response.text}")
                return 1
            data = response.json()
            replies.append(data["reply"])
            print(f"Q{i}: {question}\nA{i} [{data['served_by']}]: {data['reply'][:180]}\n")

    full_text = " ".join(replies).lower()
    first_name = name.split()[0].lower()
    checks = {
        "name mentioned and consistent": first_name in full_text,
        "age consistent (stated age appears)": str(age) in full_text,
        "occupation consistent": any(
            word in full_text for word in occupation.lower().split() if len(word) > 3
        ),
    }
    print("consistency checks:")
    failed = False
    for label, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        failed |= not ok
    print("\nSMOKE" + (" FAILED" if failed else " OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
