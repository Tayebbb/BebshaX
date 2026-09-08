---
description: "Run the BebshaX live audit regimen: release gates, input-layer edge suite, 8-business matrix on real LLM routes, cross-business similarity analysis, independent code review, fix-loop until green, then push. Use when asked to test the pipeline systematically, check that different businesses get different outputs, re-run the business-matrix audit, or verify readiness before a push. Frontend performance is the separate /perf-audit prompt."
argument-hint: "scope: all | gates | edge | matrix [POLL,KITCHEN,...] | analyze <run-dir> | review   (default: all = gates, edge, matrix on all 8 ideas, analyze, review, push)"
agent: agent
---

Run the BebshaX **live audit regimen** for the scope the user typed after the command (default `all`). This is the exact playbook that found and fixed 17 live defects on 2026-09-08 — background and the bug table are in [docs/IMPLEMENTATION_PLAN.md](../../docs/IMPLEMENTATION_PLAN.md) § "Maintenance (2026-09-08, latest)". Read [AGENTS.md](../../AGENTS.md) and [RULES.md](../../RULES.md) first; R2 (never fabricate, never truncate), R3, R7 and R12 bind every step.

## Ground rules (each one was learned the hard way)

- **Absolute paths only.** The terminal tool strips a leading `cd`/`Set-Location`; run binaries by full path (`${workspaceFolder}\.venv\Scripts\python.exe`, `${workspaceFolder}\apps\frontend\node_modules\.bin\*.cmd`).
- **Exit codes via file redirect.** `cmd > $env:TEMP\x.txt 2>&1; "EXIT=$LASTEXITCODE"; Get-Content $env:TEMP\x.txt -Tail 8`. Never pipe vitest/pytest through `Select-Object` for the exit code — the pipeline reports 1 even when tests pass.
- **One matrix run at a time.** Before launching: `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'business_matrix_audit' }` must return nothing. Two writers on one output dir contaminated run r1.
- **Never run the full pytest or vitest suite while a matrix run is alive** — the machine OOMs (vitest `Zone Allocation failed`) and pytest crawls. Run targeted files during the run; full suites after.
- **Scratch database only.** The harness refuses a non-local `BEBSHAX_DATABASE_URL`. Never point it at the shared Neon DB.
- **Never print secrets.** Read the compose password into a variable; list `.env` keys as `<set:Nch>`; use `docker compose config --quiet`.
- **Low answer quality is not an infrastructure failure.** A 3B judge writing rubric boilerplate is a WARN with the serving route, not a bug to "fix".
- **Fix only what is broken; red-prove every fix** (`git stash push -q -- <fixed files>; pytest <new tests>; git stash pop -q` must go red then green).
- **Check `git status --porcelain` before staging anything.** Concurrent sessions edit the same files. Stage by hunk (`git add -p`) when a file is shared, and run `python -c "import bebshax.main"` before every push — a filename-level "foreign files?" check cannot see hunk-level contamination (this shipped a broken `origin/main` once).
- Frontend load/scroll performance is out of scope here — run [/perf-audit](perf-audit.prompt.md).

## 0. Preflight (all scopes)

```powershell
# env var NAMES only, values redacted to lengths
Get-Content ${workspaceFolder}\.env | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k,$v = $_ -split '=',2; "{0}=<set:{1}ch>" -f $k, $v.Length }
docker ps --format "{{.Names}} {{.Status}} {{.Ports}}"          # expect bebshax-db healthy on 5433
try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 3).Content } catch { "OLLAMA down" }
```
If Ollama is down: `F:\Ollama\ollama.exe serve` in an **async** terminal (local tier = llama3.2:3b; it serves the conversation/fast pools and every fallback once free tiers hit their daily caps — OpenRouter free is 50 req/day).

Scratch DB (once per machine; `run_matrix.ps1` sets the URL itself):
```powershell
docker exec bebshax-db psql -U bebshax -d bebshax -c "CREATE DATABASE bebshax_matrix"
docker exec bebshax-db psql -U bebshax -d bebshax_matrix -c "CREATE EXTENSION IF NOT EXISTS vector"
$pw = (Select-String -Path ${workspaceFolder}\docker-compose.yml -Pattern 'POSTGRES_PASSWORD:\s*(\S+)').Matches[0].Groups[1].Value
$env:BEBSHAX_DATABASE_URL = "postgresql+asyncpg://bebshax:$pw@localhost:5433/bebshax_matrix"; $env:PYTHONUTF8 = "1"
Push-Location ${workspaceFolder}\apps\backend; ${workspaceFolder}\.venv\Scripts\python.exe -m alembic upgrade head; ${workspaceFolder}\.venv\Scripts\python.exe -m alembic current; Pop-Location
```

## 1. `gates` — release gates (also the closing step of every other scope)

```powershell
$env:PYTHONUTF8="1"
${workspaceFolder}\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, r'${workspaceFolder}\apps\backend'); import bebshax.main; print('import OK')"
${workspaceFolder}\.venv\Scripts\python.exe -m ruff check ${workspaceFolder}\apps\backend\bebshax ${workspaceFolder}\apps\backend\tests ${workspaceFolder}\scripts\business_matrix_audit.py --no-cache
${workspaceFolder}\.venv\Scripts\python.exe -X utf8 -m pytest ${workspaceFolder}\apps\backend\tests -q -p no:cacheprovider > $env:TEMP\pt.txt 2>&1; "EXIT=$LASTEXITCODE"; Get-Content $env:TEMP\pt.txt -Tail 8
${workspaceFolder}\apps\frontend\node_modules\.bin\tsc.cmd --noEmit --project ${workspaceFolder}\apps\frontend\tsconfig.json; "TSC=$LASTEXITCODE"
${workspaceFolder}\apps\frontend\node_modules\.bin\vitest.cmd run --root ${workspaceFolder}\apps\frontend --config ${workspaceFolder}\apps\frontend\vite.config.ts --reporter=dot > $env:TEMP\vt.txt 2>&1; "VITEST=$LASTEXITCODE"; Get-Content $env:TEMP\vt.txt | Select-String 'Test Files|Tests |FAIL'
node ${workspaceFolder}\apps\frontend\scripts\codemod-theme-tokens.mjs --check; "THEME=$LASTEXITCODE"
${workspaceFolder}\apps\frontend\node_modules\.bin\vite.cmd build --config ${workspaceFolder}\apps\frontend\vite.config.ts 2>&1 | Select-Object -Last 12
```
Vitest needs `--root`/`--config` when the terminal cwd is the repo root. If the machine is loaded, force one worker (`--maxWorkers=1` on Vitest ≥4; `--pool=forks --poolOptions.forks.minForks=1 --poolOptions.forks.maxForks=1` on Vitest 2 — `min` and `max` must both be set or Tinypool throws). Theme gate is `codemod-theme-tokens.mjs --check`, not `check-theme.mjs`. Baselines at the last green: backend 1,209 passed / 3 deselected, frontend 34 files / 260 tests.

## 2. `edge` — input-layer edge suite (~5 min, a handful of real model calls)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ${workspaceFolder}\scripts\run_matrix.ps1 -Edge -Out ${workspaceFolder}\data\metadata\business_matrix_edge_<tag> > $env:TEMP\edge.log 2>&1; "EXIT=$LASTEXITCODE"
Get-Content $env:TEMP\edge.log | Where-Object { $_ -match '^\s*\[(OK|FAIL|WARN)|AUDIT|^\s+- ' }
```
What it probes (49 checks, expected all OK): empty / whitespace / >20,000-char / wrong-type prompts → 400/422; client-chosen `id`/`user_id`/`is_demo` ignored; `<script>` never reaches a title; Bangla and emoji prompts accepted with real titles; title-only study → script `400 business_description_required`, report `400 report_requires_data`, review `400 nothing_to_review`; `question_count` 0/11/-3 → 422; `generate-personas` role `count` 0/11 → 422 with `max_personas_per_role`; no roles → 400; foreign study → 404; copilot 0/61 messages, >8000-char message → 422, no auth → 401; `suggest-roles` empty → 400; batch-run whitespace questions → `script_required`, 21 questions / 2001-char question → 422, foreign persona ids → 400; behavioral empty scenario → `scenario_required`, bad type / empty name → 422; other tenant reading or writing my study → 404 (no existence oracle); one-word idea → copilot asks, not approves; prompt injection ("reply exactly PWNED") not obeyed; off-topic question steered back; harmful business not approved (a 502 `copilot_reply_unparseable` from a refusing local model is an acceptable envelope); Bangla idea → roles about that idea.

## 3. `matrix` — eight businesses end to end on real routes (60–120 min, mostly local tier)

```powershell
# pre-launch: no other matrix process alive (see ground rules), then:
powershell -NoProfile -ExecutionPolicy Bypass -File ${workspaceFolder}\scripts\run_matrix.ps1 -Out ${workspaceFolder}\data\metadata\business_matrix_<tag> > ${workspaceFolder}\data\metadata\business_matrix_<tag>.log 2>&1
#   subset:  -Ideas POLL,KITCHEN      questions per script: -Questions 3
```
Run it in an **async** terminal and monitor with:
```powershell
Get-Content <log> | Where-Object { $_ -match '^\s*\[(FAIL|WARN)|^===' }; "ok=" + (Select-String -Path <log> -Pattern '^\s*\[OK' | Measure-Object).Count
```
Ideas: POLL (Po Valley air-quality sensors, IT) · KITCHEN (Lagos ghost kitchen, NG) · SAAS (German CSRD compliance, DE) · SAVINGS (Jakarta gig-driver savings, ID) · DERM (Kenyan tele-dermatology, KE) · KETTLE (UK repairable kettle, GB) · TUITION (Chattogram tuition installments, BD — the one place Bangladesh vocabulary is legitimate) · ELDER (Osaka elder care, JP). Per business it checks: signup → study (title not the canonical fallback) → copilot (names its route, about the idea) → roles (idea-specific, ≥4 distinct) → personas (≥1, routes named, **country = the idea's market**, domain referenced, distinct names, no example timestamp) → script (source `llm`, requested count, idea-specific, distinct) → batch interview (completed, one answer per question, on-topic, first person, no third-person self-narration) → behavioral pricing test (create 201, run completed, rationale >40 chars mentioning price/currency, probability in [0,1]) → report (201, `synthesis_source=llm`, idea-specific summary and recommendations, no real-user validation claim) → AI review (dimension scores, route named; domain engagement is a WARN) → no Bangladesh/seed vocabulary leaked into non-BD ideas (hard markers fail, soft markers warn). Per-idea JSON is written as it lands, so a crash or an exhausted tier loses nothing.

**Root-causing a failed stage — in this order:**
1. Log window around the failure: `Select-String -Path <log> -Pattern 'Traceback|WARNING|all candidates|429|402 ' | Select-Object -First 60`, then `Get-Content <log> | Select-Object -Skip (N-40) -First 42` around the hit.
2. Provenance (route attempts, sizes, `num_ctx`, `done_reason`) from the scratch DB — note `prompt_text`/`completion_text` are **not** stored, so the reply itself must be re-captured live:
   ```powershell
   docker exec bebshax-db psql -U bebshax -d bebshax_matrix -tA -c "SELECT task, count(*), sum(case when success then 1 else 0 end) FROM llm_requests GROUP BY task"
   docker exec bebshax-db psql -U bebshax -d bebshax_matrix -tA -c "SELECT success, served_by_provider, jsonb_pretty(attempts) FROM llm_requests WHERE task='REPORT_GENERATION' AND success=false ORDER BY created_at DESC LIMIT 1"
   docker exec bebshax-db psql -U bebshax -d bebshax_matrix -tA -c "SELECT to_char(created_at,'HH24:MI:SS'), success, served_by_provider, request_model, input_tokens, output_tokens, substring(attempts::text from 'num_ctx=([0-9]+)'), substring(attempts::text from 'done_reason=([a-z]+)') FROM llm_requests WHERE task='REPORT_GENERATION' ORDER BY created_at"
   ```
3. Re-drive the model directly to see the raw reply (write probes to `$env:TEMP`, never inside the repo — the dev watcher restarts on repo writes): POST `http://localhost:11434/api/chat` with the same system/user messages, `options {num_ctx, num_predict, temperature}`, with and without `"format": "json"`; on `json.JSONDecodeError` print `cleaned[pos-160:pos] + " <<<HERE>>> " + cleaned[pos:pos+80]`. Run 3–5 samples — small models fail intermittently.
4. Re-drive the *service* with a fake `LLMService` that calls Ollama and dumps the raw text (build the real `StudyReportService(session, fake)` against the scratch DB, `await session.rollback()` after), so the acceptance logic is exercised exactly as production runs it.
5. Classify: infrastructure (route/DB/schema/OOM) → fix in code; model quality → WARN + prompt/decoding constraint, never a template. Every live defect so far was invisible to the SQLite unit suite: varchar overflows, FK insert order, a nonexistent ORM relationship, small-model JSON slips, an unallocatable `num_ctx` rung.

## 4. `analyze <run-dir>` — cross-business differentiation (no LLM, no DB, seconds)

```powershell
${workspaceFolder}\.venv\Scripts\python.exe ${workspaceFolder}\scripts\business_matrix_audit.py --analyze ${workspaceFolder}\data\metadata\business_matrix_<tag>
```
29 checks; expected all OK on a complete run: pairwise Jaccard per artefact below threshold (roles/script 0.30, recommendations 0.35, review 0.45, else 0.35 — last complete run: roles 0.14, personas 0.15, scripts 0.07); no two businesses with an identical artefact; no 6-gram (8-gram for scripts/answers/copilot) shared by ≥3 businesses; no persona name reused; no idea's distinctive vocabulary inside another's artefacts; **pollution and food businesses share no role names and no persona occupations**; no role name in every business; review scores not one constant. Last complete run: `data/metadata/business_matrix_r2/summary_analysis.md`.

## 5. Fix loop (whenever any scope fails)

1. Dispatch read-only research subagents in parallel for disjoint areas; then implement with **disjoint file ownership** per subagent and unique test basenames (tests/ is not a package).
2. Each fix ships with a regression test proven red against the pre-fix code (stash technique above). Prefer shape-fitting at the parse boundary and explicit `InsufficientInput`/`UnusableModelOutput` failures over any template.
3. Re-run only the affected scope (edge is cheap; matrix subset with `-Ideas`), then the full run.
4. `review`: dispatch the `code-reviewer` subagent over `git diff` with these instructions verbatim — *do not run pytest/vitest/npm (machine is busy); verify each fix is present AND wired (not just defined); hunt regressions; check tests for false confidence (would it pass with the fix reverted?); check SQLite-vs-Postgres blind spots (varchar lengths, FK enforcement); portability for Ubuntu CI; return severity-ranked findings with file:line and an explicit `VERDICT: SHIP | DO-NOT-SHIP`.* Fix every MEDIUM+ and re-dispatch; the loop closes only on SHIP with all scopes green.

## 6. Docs, commit, push (R12)

Same commit as the code: `### Maintenance (<date>)` entry in [docs/IMPLEMENTATION_PLAN.md](../../docs/IMPLEMENTATION_PLAN.md) (newest on top: what ran, what broke, root causes, measured before/after, gates), new `error_code`s and response fields in [docs/API_CONTRACT.md](../../docs/API_CONTRACT.md), the evidence bullet in [docs/RESEARCH_EVIDENCE.md](../../docs/RESEARCH_EVIDENCE.md), the row in [docs/SHIP_READINESS_REPORT.md](../../docs/SHIP_READINESS_REPORT.md). Keep run directories under `data/metadata/business_matrix_*` as the audit record (suffix `_partial`/`_contaminated` for incomplete runs); delete regenerated `debug.log` crashpad files (gitignored).

Push **automatically** once, and only once, all of these hold — otherwise stop and report what is blocking:
1. every scope green and the review verdict is SHIP;
2. `git status --porcelain` shows no concurrent workstream in the files you are staging (if it does, stage by hunk and leave their hunks out);
3. the staged secret scan reports no candidates, without printing matching values: `$stagedDiff = git diff --cached; if ($LASTEXITCODE -ne 0) { throw 'Cannot read staged diff' }; if ($stagedDiff | Select-String -Pattern 'sk-or-|postgresql://[^:]+:[^@]+@|npg_|re_[A-Za-z0-9]{20,}|xsmtpsib-' -Quiet) { throw 'Possible credential in staged changes; review privately without printing matching lines' }`;
4. `python -c "import bebshax.main"` succeeds on the staged tree;
5. `git fetch` + `git rebase origin/main` is clean (when both sides appended to the implementation log, keep both entries with yours on top), then `import bebshax.main` again on the rebased tree.
Conventional message (`fix:` / `chore:`), then `git push origin main`.

## Report format

End with: per scope, checks passed/total and every FAIL/WARN with its root cause; the differentiation table (max pairwise Jaccard per field, pollution-vs-food overlap); bugs found → fixed (symptom · root cause · fix · test); gate numbers; review verdict; what was committed/pushed and what was deliberately left alone.
