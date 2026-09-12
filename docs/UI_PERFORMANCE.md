# UI Performance

Date: 2026-09-09. Performance budgets are targets, not measured achievements.
This work retains full persona/history/evidence and complete exported answers.

## What Changed

- Dashboard views and dialogs are dynamic chunks. Intent-prefetch loads code
  only, at most two modules concurrently, and respects Save-Data/2G signals.
- Public pages do not wait for Neon session discovery. Private routes retain
  their auth gate; cookie startup uses the current app auth authority.
- Interview and behavioral primary lists are independent of metric reads.
  Persona results are independent of segment metadata. Existing saved reports
  remain visible during generation and errors; unresolved history is not empty.
- A saved-study cache is scoped by session epoch and known revision, with a
  1.5-second TTL, 24 entries, 2 MiB maximum and coalesced reads. Oversized values
  bypass caching in full. Writes invalidate it; stale in-flight reads cannot
  install results after invalidation. It never caches generation as a shortcut.
- GSAP entrance effects exclude containers with required interactive controls.
- Polling is serial and bounded. Pausing updates does not cancel server work.

## Explicit Instrumentation

No analytics SDK, telemetry endpoint, automatic URL logging, or private content
capture was added. `window.__bebshaxTiming` is opt-in and in-memory only.

```javascript
window.__bebshaxTiming.enable(true)
window.__bebshaxTiming.clear()
// Navigate normally, then read the captured samples.
window.__bebshaxTiming.read()
window.__bebshaxTiming.enable(false)
```

Each sample contains only a finite route group, stage, elapsed milliseconds,
content/empty/error outcome, and mock/live build mode. No URL, query, account,
study/persona ID, prompt, transcript, credential, or report content is recorded.
At most 200 samples are retained. This is manual lifecycle instrumentation,
not DOM-content scraping or an automatic analytics collector.

Stages are distinct:

- `primary-content`: explicit view readiness after two animation frames; loading
  fallbacks are not readiness. Metrics can remain pending independently.
- `ai-first-text`: first nonempty real transport delta, not presentation reveal.
- `canonical-response`: validated response accepted by the caller; not an
  unsupported durability claim.
- `saved-completion`: report job result followed by successful readback of the
  matching report ID/version. This is not independent DB/provenance certification.

## Measured Scope

Focused baseline: 24/24 interview tests, including the previous eight failures,
were already passing before this work. Added deterministic tests validate cache
bounds, invalidation, exact route grouping, no private identifiers in samples,
separate AI/canonical stages, and readiness only after declared content.
These are jsdom/fixture checks, not browser or real-provider latency benchmarks.

Final frontend suite: **431 passed / 0 failed / 0 skipped, 54 files, 72.386 s**.
Final production TypeScript/Vite build: **exit 0, 11.859 s**. Theme check: exit 0.
The previous build (13.574 s) ran while tests were active; do not interpret the
duration difference as a performance improvement.

Actual emitted sizes (bytes; gzip computed with Node zlib, not network transfer):

| Chunk | Raw bytes | Gzip bytes |
| --- | ---: | ---: |
| Entry | 218117 | 54709 |
| React vendor | 153618 | 49728 |
| Icons vendor | 45532 | 9281 |
| Dashboard | 252678 | 81430 |
| Study workflow | 89207 | 22181 |
| Persona library | 66547 | 13787 |
| Interview workspace | 19417 | 6004 |
| Evidence laboratory | 24138 | 5318 |
| Segmentation | 37645 | 8372 |
| Routing | 30982 | 7497 |
| Auth page | 31586 | 7997 |
| Behavioral detail | 26477 | 5889 |
| Behavioral list | 14808 | 3656 |
| Behavioral comparison | 5535 | 1799 |
| Studies dashboard | 7745 | 2544 |
| Mock store (lazy) | 70154 | 20636 |
| Entry CSS | 61581 | 12993 |

There are **25 JS chunks totaling 1,229,314 raw bytes**. The entry's static
imports/preloads contain only React and icons, not the dashboard. Its initial
JS graph is 417,267 raw bytes / 113,718 summed gzip bytes, excluding CSS, fonts,
images, headers and subsequent requests. Dashboard remains a substantial chunk;
these figures do not establish any route latency budget or before/after gain.

MOCK development HTTP smoke, one sample each, with no browser rendering:

| Request | Status | HTTP delivery ms |
| --- | ---: | ---: |
| `/` | 200 | 56.1 |
| `/auth/signin` | 200 | 372.2 |
| `/dashboard` | 200 | 491.8 |
| `/src/main.tsx` | 200 | 60.0 |
| `/src/services/api.ts` | 200 | 153.9 |
| `/api/health` (mock-only refusal) | 503 | 258.1 |

These are measured HTTP response times, **not page readiness, first AI text,
saved completion, browser E2E, or p50/p95**. No near-instant claim is made.
The route instrumentation tests validate the measurement contract but do not
substitute for running a desktop/mobile browser under declared conditions.

## MOCK Preview And Browser Gate

```text
npm --prefix apps/frontend run preview:mock
```

The dedicated preview binds only `127.0.0.1:5194`, forces synthetic fixture mode,
disables environment-file loading/federation, and rejects live `/api` requests.
It is a development preview, not a production build or authenticated E2E run.
No browser automation package was added. Desktop/mobile route measurements,
canvas/image checks, layout/overflow checks, cold/warm p50/p95 and real-session
workflows still require an authorized browser-capable session.