---
description: "Measure the BebshaX frontend's real load and scroll performance (FCP/LCP/CLS/long tasks, scroll frame-gap p95, running animations, bundle sizes) with the CDP harness that works inside VS Code's hidden embedded browser, then fix-and-re-measure until the desktop targets hold. Use when asked to check smoothness, latency, jank, bundle size, or to verify a frontend performance change."
argument-hint: "scope: measure | loop   (default: measure — loop keeps fixing and re-measuring until targets hold)"
agent: agent
---

Measure the frontend in `apps/frontend` against the desktop targets below and report real numbers; in `loop` scope, fix the largest measured cost, re-measure, and repeat until every target holds (never claim an improvement without a measured delta). Method and prior results: [docs/IMPLEMENTATION_PLAN.md](../../docs/IMPLEMENTATION_PLAN.md) § "Frontend performance: measured optimization loop".

## Ground rules

- Absolute paths only (the terminal tool strips `cd`). Exit codes via file redirect, never through `Select-Object`.
- **Cold vs warm matters:** after every rebuild do one throwaway `goto` and discard it — a cold-cache first load reads as a regression.
- Browser tool results attach a ~50 KB page snapshot each: batch measurements into one `run_playwright_code` call; keep calls to a minimum.
- Every rAF-based `page.evaluate` promise must carry a `setTimeout` fallback resolve or it hangs forever on a hidden page.
- A >100 ms rAF gap with `lt: []` (no long task) is screencast/CDP pipeline noise, not main-thread jank — report it as such.
- Frontend deps install inside `apps/frontend` only (a root-level install once broke Vite resolution).

## 1. Build and serve

```powershell
${workspaceFolder}\apps\frontend\node_modules\.bin\vite.cmd build --config ${workspaceFolder}\apps\frontend\vite.config.ts 2>&1 | Select-Object -Last 20   # note index.css gz, first-paint JS files, lazy chunks
${workspaceFolder}\apps\frontend\node_modules\.bin\vite.cmd preview --port 4173 --strictPort --root ${workspaceFolder}\apps\frontend    # async terminal
```
Bundle checks from the build table: `index.html` must modulepreload only `vendor-react`, `vendor-icons` and one stylesheet; `DashboardLayout-*.js`, `AuthPage-*.js`, `AuthModal-*.js` must be separate lazy chunks; `index.css` must not inline fonts (`Select-String -Path dist\assets\*.css -Pattern 'url\(data:' -AllMatches` → 0). Never name a lazy route folder in `manualChunks` — it drags the route back into the entry's static graph and silently defeats `React.lazy`.

## 2. Load measurement (one call)

Open `http://localhost:4173/` in the embedded browser, then in `run_playwright_code`. The embedded page reports `visibilityState === 'hidden'`: rAF is throttled and LCP/paint never fire unless the CDP calls below run **after every `goto`** (goto resets the lifecycle state).

```js
await page.setViewportSize({ width: 1600, height: 900 });
await page.addInitScript(() => { window.__perf = { lcp: 0, cls: 0, lt: [] };
  new PerformanceObserver(l => { for (const e of l.getEntries()) window.__perf.lcp = e.startTime; }).observe({ type: 'largest-contentful-paint', buffered: true });
  new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__perf.cls += e.value; }).observe({ type: 'layout-shift', buffered: true });
  new PerformanceObserver(l => { for (const e of l.getEntries()) window.__perf.lt.push(Math.round(e.duration)); }).observe({ type: 'longtask', buffered: true }); });
const cdp = await page.context().newCDPSession(page); await cdp.send('Page.enable');
await page.goto('http://localhost:4173/', { waitUntil: 'load' });   // warm-up, discarded
await page.goto('http://localhost:4173/', { waitUntil: 'load' });
await cdp.send('Page.setWebLifecycleState', { state: 'active' });
await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true });
await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 10, maxWidth: 300, maxHeight: 200, everyNthFrame: 1 });
await page.waitForTimeout(1500);
return page.evaluate(() => { const fcp = performance.getEntriesByName('first-contentful-paint')[0]; const nav = performance.getEntriesByType('navigation')[0];
  return { fcp: Math.round(fcp ? fcp.startTime : -1), lcp: Math.round(window.__perf.lcp), cls: +window.__perf.cls.toFixed(4), lt: window.__perf.lt, domInteractive: Math.round(nav.domInteractive),
           requests: performance.getEntriesByType('resource').length, transferKB: Math.round(performance.getEntriesByType('resource').reduce((s, r) => s + (r.transferSize || 0), 0) / 1024) }; });
```

## 3. Scroll measurement (same session, 3 runs)

```js
const runs = [];
for (let r = 0; r < 3; r++) {
  await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(500);
  await page.evaluate(() => { window.__perf.lt = []; });
  const rec = page.evaluate(() => new Promise(resolve => { const gaps = []; let last = performance.now(); const t0 = performance.now();
    const tick = t => { gaps.push(t - last); last = t; if (performance.now() - t0 < 3200) requestAnimationFrame(tick); else resolve(gaps); };
    requestAnimationFrame(tick); setTimeout(() => resolve(gaps), 5000); }));
  for (let i = 0; i < 30; i++) { await page.mouse.wheel(0, 260); await page.waitForTimeout(90); }
  const s = (await rec).slice(1).sort((a, b) => a - b);
  runs.push({ frames: s.length, avg: +(s.reduce((a, b) => a + b, 0) / s.length).toFixed(2), p95: +s[Math.floor(s.length * 0.95)].toFixed(1), max: +s[s.length - 1].toFixed(1), over32: s.filter(x => x > 32).length,
              anims: await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running').length), lt: await page.evaluate(() => window.__perf.lt) });
}
return runs;
```
Also probe scroll integrity when `content-visibility` is in play: record `scrollY` deltas while scrolling and assert no negative jumps; compare `document.documentElement.scrollHeight` before/after (placeholders growing into real content is fine; backward jumps are not).

## 4. Visual check

Screenshot at `scrollY` 0 and mid-page after any compositing change (backdrop blur, `content-visibility`, `will-change`, skeleton/dot rewrites) — verify no blurred hero, no clipped sections, no frozen animation halos. Check both themes when CSS tokens changed.

## Targets (modern desktop, localhost, warm, no throttling — met on 2026-09-08)

| Metric | Target | Last measured |
|---|---|---|
| FCP / LCP | ≤ ~200 ms | 184 / 184 ms |
| CLS | ≤ 0.02 | 0 |
| Long tasks at load / during scroll | none | none |
| Scroll frame gap p95 | ≤ 20 ms (p95 ≈ avg means vsync-paced) | 16.9 ms |
| Frames > 32 ms per 30-wheel scroll | ≤ 1 | 1 |
| Animations running after scroll | ≤ 2 | 2 |
| First-paint JS (gz) / index.css (gz) | ≤ ~120 KB / ≤ ~12 KB | 102.9 KB / 10.87 KB |

## `loop` scope

Attack the largest measured cost first (fonts and render-blocking CSS → route splitting → non-composited infinite animations (`scale`, `box-shadow`, `background-position` → `transform`/`opacity`) → per-frame `setState`/`getBoundingClientRect` → app-layer request coalescing). Each change: measure → edit → rebuild → warm-up → re-measure; keep only changes with a measured win; revert changes whose risk outweighs the win (e.g. skipping the auth revalidation spinner). Then run the frontend gates (`tsc --noEmit`, vitest with `--root`/`--config`, `codemod-theme-tokens.mjs --check`, `vite build`), dispatch the `code-reviewer` subagent over the diff (it must check reduced-motion coverage, cache invalidation across sign-out, backdrop-filter at rest, duplicate `Cache-Control` in nginx), fix every MEDIUM+, and re-measure once more. Close only on a SHIP verdict with all targets holding. Docs: `### Maintenance (<date>)` entry in IMPLEMENTATION_PLAN.md with the before/after table; deploy changes (`gzip`, immutable `/assets/`) cannot be measured on localhost — say so.

## Report format

Build table (baseline → now), load metrics, the three scroll runs, running animations, visual check result, gates, review verdict, and which targets hold.
