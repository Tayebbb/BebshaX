"""Live end-to-end AI audit (REAL LLM routes, REAL database). Not a unit test.

Drives the whole study workflow through the HTTP API twice, with two product
ideas from unrelated domains and countries, and then asks the independent AI
judge to review each study. It proves, with evidence written to
data/metadata/, that the pipeline is dynamic:

  * every stage reports the real route that served it (no template source);
  * artefacts are specific to the idea they were produced for (domain terms
    appear; the other idea's terms do not);
  * the two runs produce different personas, scripts, findings and reviews;
  * no persona is silently placed in a default country;
  * an optional repeat of the same idea still yields non-identical wording.

Run from the repo root (backend .env must point at a reachable database and
at least one LLM route must be usable — keyless freellmpool is enough):

    .venv\\Scripts\\python scripts\\live_ai_audit.py [--repeat] [--questions 3]

Exit code 0 only when every check passes. Failures are printed with the
backend's error envelope (error_code) — nothing is retried into success.
Uses the backend's own dependencies only (RULES.md R1/R3 respected: all model
traffic goes through the API, which routes through LLMService).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "metadata"

# Deliberately far from each other AND far from the seed/demo domain so a
# hard-coded default (food delivery, Dhaka, BDT, "budget resistance", ...)
# would stand out immediately.
IDEAS: list[dict[str, Any]] = [
    {
        "key": "A",
        "prompt": (
            "A subscription box that delivers fresh, locally sourced fishing bait and "
            "seasonal tackle to recreational sea anglers along the coast of Norway."
        ),
        "must_mention": ["bait", "angl", "fish"],
        "country_hint": "NOR",
        "forbidden_country_codes": {"BD"},
    },
    {
        "key": "B",
        "prompt": (
            "A scheduling and billing app for independent piano teachers in Chicago "
            "who run student recitals and juggle make-up lessons."
        ),
        "must_mention": ["piano", "teacher", "lesson"],
        "country_hint": "USA",
        "forbidden_country_codes": {"BD"},
    },
]

WORD_RE = re.compile(r"[a-z][a-z']+")
STOPWORDS = {
    "the", "and", "for", "you", "your", "with", "that", "this", "what", "how", "when",
    "would", "could", "about", "have", "from", "they", "them", "their", "there",
    "which", "into", "than", "then", "were", "been", "being", "does", "did", "are",
    "was", "will", "can", "not", "but", "any", "all", "our", "who", "why", "where",
    "most", "more", "some", "such", "also", "very", "just", "like", "over", "under",
}


def tokens(text: str) -> set[str]:
    return {w for w in WORD_RE.findall((text or "").lower()) if w not in STOPWORDS and len(w) > 3}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class Audit:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []

    def check(self, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append({"name": name, "passed": bool(passed), "detail": detail})
        mark = "OK  " if passed else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
        return passed

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if not c["passed"]]


def _envelope(response) -> str:
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 — body may not be JSON on transport errors
        body = response.text[:300]
    if isinstance(body, dict):
        code = body.get("error_code") or (body.get("detail") if isinstance(body.get("detail"), dict) else None)
        detail = body.get("detail") if isinstance(body.get("detail"), str) else body.get("message")
        return f"HTTP {response.status_code} error_code={code!r} detail={str(detail)[:200]!r}"
    return f"HTTP {response.status_code} {str(body)[:200]}"


def run_idea(client, audit: Audit, idea: dict[str, Any], *, questions: int, label: str) -> dict[str, Any]:
    """Drive one idea through the workflow; returns the collected artefacts."""
    run: dict[str, Any] = {"label": label, "idea": idea["prompt"], "steps": {}, "served_by": {}}
    print(f"\n=== Run {label}: {idea['prompt'][:80]}...")

    # 0. Account (copilot endpoints require a signed-in user).
    email = f"audit+{uuid.uuid4().hex[:10]}@bebshax.local"
    signup = client.post(
        "/api/auth/signup",
        json={"full_name": "Live Audit", "email": email, "password": uuid.uuid4().hex},
    )
    if not audit.check(f"{label}: signup", signup.status_code == 201, _envelope(signup) if signup.status_code != 201 else email):
        return run
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    # 1. Study.
    t0 = time.perf_counter()
    created = client.post("/api/studies", json={"prompt": idea["prompt"], "type": "interviews"}, headers=headers)
    if not audit.check(f"{label}: create study", created.status_code == 201, _envelope(created) if created.status_code != 201 else ""):
        return run
    study = created.json()
    study_id = study["id"]
    run["study_id"] = study_id

    # 2. Copilot turn.
    copilot = client.post(
        "/api/study/copilot",
        json={"messages": [{"role": "user", "content": idea["prompt"]}], "study_id": study_id},
        headers=headers,
    )
    if audit.check(f"{label}: copilot reply", copilot.status_code == 200, _envelope(copilot) if copilot.status_code != 200 else ""):
        body = copilot.json()
        run["steps"]["copilot"] = {"reply": body.get("reply"), "goal_card": body.get("research_goal_card")}
        run["served_by"]["copilot"] = body.get("served_by")
        audit.check(f"{label}: copilot names its route", bool(body.get("served_by")) and "template" not in str(body.get("served_by")).lower(), str(body.get("served_by")))
        audit.check(f"{label}: copilot reply is about the idea", any(k in (body.get("reply") or "").lower() for k in idea["must_mention"]), (body.get("reply") or "")[:120])

    # 3. Roles.
    roles_res = client.post(
        "/api/study/suggest-roles",
        json={"study_prompt": idea["prompt"], "study_title": study.get("title")},
        headers=headers,
    )
    roles: list[dict[str, Any]] = []
    if audit.check(f"{label}: suggest roles", roles_res.status_code == 200, _envelope(roles_res) if roles_res.status_code != 200 else ""):
        roles = roles_res.json()
        run["steps"]["roles"] = [r.get("role") for r in roles]
        audit.check(f"{label}: roles are idea-specific", any(any(k in json.dumps(r).lower() for k in idea["must_mention"]) for r in roles), "; ".join(str(r.get("role")) for r in roles)[:160])

    # 4. Personas (two roles, one persona each — keeps the free tier polite).
    chosen = [dict(r, count=1, selected=True) for r in roles[:2]] or [
        {"id": "role_1", "role": "Primary customer", "description": idea["prompt"], "count": 1, "selected": True}
    ]
    personas_res = client.post(
        "/api/study/generate-personas",
        json={"study_id": study_id, "study_prompt": idea["prompt"], "roles": chosen},
        headers=headers,
    )
    personas: list[dict[str, Any]] = []
    if audit.check(f"{label}: generate personas", personas_res.status_code == 200, _envelope(personas_res) if personas_res.status_code != 200 else ""):
        body = personas_res.json()
        personas = body.get("personas") or []
        run["served_by"]["personas"] = body.get("served_by")
        run["steps"]["personas"] = [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "occupation": (p.get("demographics") or {}).get("occupation") or p.get("archetype"),
                "country_code": p.get("country_code"),
                "description": (p.get("description") or "")[:240],
            }
            for p in personas
        ]
        run["steps"]["failed_roles"] = body.get("failed_roles") or []
        audit.check(f"{label}: at least one persona", len(personas) >= 1, f"{len(personas)} personas, {len(body.get('failed_roles') or [])} failed roles")
        audit.check(f"{label}: persona generation names its routes", bool(body.get("served_by")), str(body.get("served_by")))
        codes = {p.get("country_code") for p in personas}
        audit.check(f"{label}: no persona defaulted to a forbidden country", not (codes & idea["forbidden_country_codes"]), f"country_codes={sorted(str(c) for c in codes)}")
        blob = json.dumps(personas).lower()
        audit.check(f"{label}: personas reference the idea's domain", any(k in blob for k in idea["must_mention"]), "")

    # 5. Script.
    script_res = client.post(f"/api/studies/{study_id}/script/generate", json={"question_count": questions}, headers=headers)
    script: list[str] = []
    if audit.check(f"{label}: generate script", script_res.status_code == 200, _envelope(script_res) if script_res.status_code != 200 else ""):
        body = script_res.json()
        script = body.get("questions") or []
        run["steps"]["script"] = script
        run["served_by"]["script"] = body.get("served_by")
        audit.check(f"{label}: script source is the model", body.get("source") == "llm", f"source={body.get('source')!r} served_by={body.get('served_by')!r}")
        audit.check(f"{label}: script has the requested {questions} questions", len(script) == questions, f"{len(script)} questions")
        audit.check(f"{label}: script is idea-specific", any(any(k in q.lower() for k in idea["must_mention"]) for q in script), (script[0] if script else "")[:120])

    # 6. One batch interview (first persona, the generated script).
    if personas and script:
        batch = client.post(
            f"/api/studies/{study_id}/interviews/batch-run",
            json={"persona_ids": [personas[0]["id"]]},
            headers=headers,
        )
        if audit.check(f"{label}: start batch interview", batch.status_code == 202, _envelope(batch) if batch.status_code != 202 else ""):
            job_id = batch.json()["job_id"]
            deadline = time.monotonic() + 420
            job: dict[str, Any] = {}
            while time.monotonic() < deadline:
                job = client.get(f"/api/studies/{study_id}/interviews/batch-run/{job_id}", headers=headers).json()
                if job.get("status") != "running":
                    break
                time.sleep(3)
            run["steps"]["interview_job"] = {"status": job.get("status"), "completed": job.get("completed_count"), "failed": job.get("failed_count")}
            audit.check(f"{label}: interview completed", job.get("status") == "completed", f"status={job.get('status')!r} personas={job.get('personas')}")
            entry = next(iter((job.get("personas") or {}).values()), {})
            if entry.get("interview_id"):
                detail = client.get(f"/api/studies/{study_id}/interviews/{entry['interview_id']}", headers=headers)
                if detail.status_code == 200:
                    d = detail.json()
                    answers = [
                        str(t.get("content") or "")
                        for t in (d.get("turns") or [])
                        if isinstance(t, dict) and t.get("role") not in ("user", "interviewer", "system")
                    ]
                    run["steps"]["interview_answers"] = [a[:200] for a in answers if a][:questions]
                    run["served_by"]["interview"] = sorted({str(t.get("served_by")) for t in (d.get("turns") or []) if isinstance(t, dict) and t.get("served_by")})
                    audit.check(f"{label}: interview answers are on-topic", any(any(k in a.lower() for k in idea["must_mention"]) for a in answers), f"{len(answers)} persona turns")

    # 7. Report.
    report_res = client.post(f"/api/studies/{study_id}/reports/generate", json={}, headers=headers)
    if audit.check(f"{label}: generate report", report_res.status_code == 201, _envelope(report_res) if report_res.status_code != 201 else ""):
        rep = report_res.json()
        run["steps"]["report"] = {
            "title": rep.get("title"),
            "executive_summary": rep.get("executive_summary"),
            "key_findings": rep.get("key_findings"),
            "recommendations": rep.get("recommendations"),
            "limitations": rep.get("limitations"),
        }
        metrics = rep.get("metrics") or {}
        run["served_by"]["report"] = metrics.get("served_by")
        audit.check(f"{label}: report synthesis is model-written", metrics.get("synthesis_source") == "llm", f"synthesis_source={metrics.get('synthesis_source')!r} served_by={metrics.get('served_by')!r}")
        summary = rep.get("executive_summary") or ""
        audit.check(f"{label}: report summary is idea-specific", any(k in summary.lower() for k in idea["must_mention"]), summary[:140])

    # 8. Independent AI review.
    review = client.post(f"/api/studies/{study_id}/ai-review", headers=headers)
    if audit.check(f"{label}: AI review", review.status_code == 200, _envelope(review) if review.status_code != 200 else ""):
        v = review.json()
        run["steps"]["ai_review"] = {
            "overall": v.get("overall_score"),
            "scores": v.get("dimension_scores"),
            "summary": v.get("verdict"),
            "strengths": v.get("strengths"),
            "issues": v.get("issues"),
            "reviewed_artifacts": v.get("reviewed_artifacts"),
            "served_by": v.get("served_by"),
        }
        run["served_by"]["ai_review"] = v.get("served_by")
        scores = v.get("dimension_scores") or {}
        audit.check(f"{label}: review carries dimension scores", isinstance(scores, dict) and len(scores) >= 3, str(scores))
        audit.check(f"{label}: review names its route", bool(v.get("served_by")), str(v.get("served_by")))

    run["elapsed_s"] = round(time.perf_counter() - t0, 1)
    return run


def compare_runs(audit: Audit, a: dict[str, Any], b: dict[str, Any], *, same_idea: bool) -> None:
    la, lb = a["label"], b["label"]
    sa, sb = a.get("steps", {}), b.get("steps", {})
    tag = "same idea" if same_idea else "different ideas"
    print(f"\n=== Variability {la} vs {lb} ({tag})")

    names_a = {p.get("name") for p in sa.get("personas", [])}
    names_b = {p.get("name") for p in sb.get("personas", [])}
    if names_a and names_b:
        audit.check(f"{la}/{lb}: persona names differ", not (names_a & names_b), f"{sorted(map(str, names_a))} vs {sorted(map(str, names_b))}")

    script_a, script_b = " ".join(sa.get("script", [])), " ".join(sb.get("script", []))
    if script_a and script_b:
        sim = jaccard(script_a, script_b)
        threshold = 0.6 if same_idea else 0.35
        audit.check(f"{la}/{lb}: scripts are not copies (jaccard {sim:.2f} < {threshold})", sim < threshold and script_a != script_b, "")

    sum_a = (sa.get("report") or {}).get("executive_summary") or ""
    sum_b = (sb.get("report") or {}).get("executive_summary") or ""
    if sum_a and sum_b:
        sim = jaccard(sum_a, sum_b)
        threshold = 0.6 if same_idea else 0.35
        audit.check(f"{la}/{lb}: report summaries differ (jaccard {sim:.2f} < {threshold})", sim < threshold and sum_a != sum_b, "")

    rev_a, rev_b = sa.get("ai_review") or {}, sb.get("ai_review") or {}
    if rev_a.get("summary") and rev_b.get("summary"):
        audit.check(f"{la}/{lb}: AI reviews are written per study", rev_a["summary"] != rev_b["summary"], "")

    if not same_idea:
        # Cross-contamination: idea B's terms must not leak into idea A's artefacts.
        for run, other in ((a, b), (b, a)):
            own_blob = json.dumps(run.get("steps", {})).lower()
            other_terms = next(i for i in IDEAS if i["prompt"] == other["idea"])["must_mention"]
            leaked = [t for t in other_terms if t in own_blob]
            audit.check(f"{run['label']}: no leakage of the other idea's domain", not leaked, f"leaked={leaked}")


def write_reports(audit: Audit, args: argparse.Namespace) -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    passed = sum(1 for c in audit.checks if c["passed"])
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS" if not audit.failed else "FAIL",
        "checks_passed": passed,
        "checks_total": len(audit.checks),
        "questions_per_script": args.questions,
        "repeat": args.repeat,
        "checks": audit.checks,
        "runs": audit.runs,
    }
    json_path = OUT_DIR / f"live_ai_audit_{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# Live AI audit — {payload['generated_at']}",
        "",
        f"**Verdict:** {payload['verdict']} — {passed}/{len(audit.checks)} checks passed",
        "",
        "Real routes, real database, no fixtures. Every artefact below was written by the model that served it.",
        "",
        "## Routes that served each stage",
        "",
        "| Run | Stage | served_by |",
        "|---|---|---|",
    ]
    for run in audit.runs:
        for stage, served in (run.get("served_by") or {}).items():
            lines.append(f"| {run['label']} | {stage} | {served} |")
    lines += ["", "## Checks", "", "| Result | Check | Detail |", "|---|---|---|"]
    for c in audit.checks:
        detail = str(c["detail"]).replace("|", "\\|").replace("\n", " ")[:160]
        lines.append(f"| {'PASS' if c['passed'] else 'FAIL'} | {c['name']} | {detail} |")
    for run in audit.runs:
        steps = run.get("steps", {})
        lines += ["", f"## Run {run['label']} — {run['idea']}", ""]
        lines.append(f"Study `{run.get('study_id')}` · {run.get('elapsed_s', '?')} s")
        if steps.get("script"):
            lines += ["", "**Script**", ""] + [f"{i}. {q}" for i, q in enumerate(steps["script"], 1)]
        if steps.get("personas"):
            lines += ["", "**Personas**", ""] + [
                f"- {p.get('name')} — {p.get('occupation')} (country_code={p.get('country_code')})" for p in steps["personas"]
            ]
        if steps.get("report"):
            lines += ["", "**Executive summary**", "", str(steps["report"].get("executive_summary") or "")]
        if steps.get("ai_review"):
            r = steps["ai_review"]
            lines += ["", f"**AI review** overall={r.get('overall')} scores={r.get('scores')}", "", str(r.get("summary") or "")]
    md_path = OUT_DIR / f"live_ai_audit_{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeat", action="store_true", help="also re-run idea A to prove same-idea outputs are not identical")
    parser.add_argument("--questions", type=int, default=3, help="script length per study (3-10)")
    args = parser.parse_args()
    args.questions = max(3, min(10, args.questions))

    load_dotenv(REPO_ROOT / ".env")
    from fastapi.testclient import TestClient  # noqa: I001 — app import must follow load_dotenv

    from bebshax.main import create_app

    audit = Audit()
    app = create_app()
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        print(f"backend health: status={health.get('status')} demo_mode={health.get('demo_mode')} llm={health.get('llm') or health.get('llm_ready')}")
        for idea in IDEAS:
            audit.runs.append(run_idea(client, audit, idea, questions=args.questions, label=idea["key"]))
        if args.repeat:
            audit.runs.append(run_idea(client, audit, IDEAS[0], questions=args.questions, label="A2"))

    runs = {r["label"]: r for r in audit.runs}
    if "A" in runs and "B" in runs:
        compare_runs(audit, runs["A"], runs["B"], same_idea=False)
    if "A" in runs and "A2" in runs:
        compare_runs(audit, runs["A"], runs["A2"], same_idea=True)

    json_path, md_path = write_reports(audit, args)
    print(f"\nreport: {md_path.relative_to(REPO_ROOT)}  (json: {json_path.name})")
    if audit.failed:
        print(f"\nLIVE AI AUDIT FAILED — {len(audit.failed)} of {len(audit.checks)} checks:")
        for c in audit.failed:
            print(f"  - {c['name']}: {c['detail']}")
        return 1
    print(f"\nLIVE AI AUDIT OK — {len(audit.checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
