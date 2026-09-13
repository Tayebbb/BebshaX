# BebshaX Design System

Updated 2026-09-13 for the user-authorized pitch-black audit. Shared tokens live in [index.css](../apps/frontend/src/index.css); primitives live in [ui.css](../apps/frontend/src/components/ui/ui.css). The public site has a related, independently scoped `--studio-*` palette in [studio.css](../apps/frontend/src/components/landing/studio.css). Existing `--lp-*` aliases support its remaining shared consumers.

These are implementation conventions, not an assertion that every legacy inline style has been migrated. The verification scope and remaining limitations are in [UX_QUALITY_REPORT.md](UX_QUALITY_REPORT.md).

## Principles

0. **Visual language: pitch-black and porcelain.** The user-pinned dark PAGE CANVAS is `#000000`, overriding the earlier graphite direction and generic advice against pure black. Light porcelain `#f6f7f8` is unchanged. Near-black component surfaces, teal actions and semantic cyan/amber/red accents remain allowed; not every pixel or theme must be black. Selection is a quiet fill, not a thick side border.
1. **Clarity over decoration.** Dark page backgrounds have no ambient tint, glow or decorative gradients. Legacy glass tokens resolve to opaque surfaces; `--glass-blur` is `0px` and saturation is `100%`. Keep genuine modal scrims and neutral component surfaces distinct from the page canvas.
2. **Hierarchy over decoration.** One `h1` per view, a concise supporting line when useful, and unframed section headings. Do not add a mandatory eyebrow to every section. Reserve cards for independent repeated objects and genuinely framed tools.
3. **Evidence is first-class.** Claims, sources, memory and synthetic provenance remain progressively disclosed. Routing diagnostics are a developer/admin surface, not a model picker or ordinary-user navigation destination.
4. **Honest numbers.** Unmeasured values render `—` or "not measured", never `0` or a placeholder percentage. Sample/demo/mock data is always labelled.
5. **Text carries state.** Colour never carries meaning alone: every dot, badge and bar has a label.
6. **Restraint in motion.** Transform/opacity only; ≤ 0.5 s; `prefers-reduced-motion` disables all of it.

## Tokens

### Colour (existing, theme-paired via `[data-theme='light']`)

| Role              | Token                                                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Canvas / surfaces | `--bg-pure` `--bg-primary` `--bg-secondary` `--bg-card` `--bg-card-hover`                                                                    |
| Borders           | `--border-subtle` `--border-medium` `--border-hover` `--border-soft`; `--border-control` for meaningful form/control boundaries                |
| Keyboard focus    | `--focus-ring`, defined as `var(--accent-primary)` and resolved per theme                                                                  |
| Soft fills        | `--fill-soft` `--fill-soft-2`                                                                                                                |
| Material aliases  | `--glass-strong` `--glass-mid` `--glass-soft` now resolve to opaque neutral surfaces; `--scrim` remains an overlay                         |
| Text              | `--text-main` `--text-primary` `--text-secondary` `--text-muted` `--text-faint` `--text-label` `--text-on-accent`                            |
| Accent            | `--accent-teal` `--accent-cyan` `--accent-teal-bright` `--accent-emerald` `--accent-amber` `--accent-rose` `--accent-subtle` `--accent-glow` |
| **CTA fill**      | `--accent-gradient` — a flat accent fill with a whisper of top light; primary actions may also use plain `--accent-teal`                        |

Current values read from the shared theme; light values were not redesigned:

| Token | Dark | Light |
| --- | --- | --- |
| `--bg-pure`, `--bg-primary` | `#000000` | `#f6f7f8` |
| `--bg-secondary` | `#080808` | `#eceef0` |
| `--bg-card` | `#101010` | `#ffffff` |
| `--bg-card-hover` | `#191919` | `#f0f2f3` |
| `--border-control` | `#858585` | `#707070` |
| `--focus-ring` (resolved) | `#30d1c7` | `#0b746c` |
| `--text-main` | `#f5f5f4` | `#171c1e` |
| `--text-primary` | `#f2f4f4` | `#202628` |
| `--text-secondary` | `#d0d4d5` | `#3f4b4f` |
| `--text-muted` | `#b5bcbe` | `#4f5d63` |
| `--text-faint` | `#a4adaf` | `#58666c` |
| `--text-label` | `#c3cacc` | `#354247` |

Primary labels and user-authored chat bubbles use `--text-on-accent`: deep ink
(`#062f2c`) on bright dark-mode teal, white on the deeper light-mode teal.
Do not substitute `--text-main` on an accent surface. [StudioTheme.test.ts](../apps/frontend/tests/StudioTheme.test.ts)
checks root text roles on all four shared surfaces and accent labels on solid
fills and both gradient endpoints in both themes, including alpha compositing.
Normal text must reach 4.5:1; meaningful control boundaries and keyboard focus
must reach 3:1 against their adjacent surfaces. Subtle separators are not a
substitute for `--border-control` or `--focus-ring`.

### Semantic status (new)

| Meaning                                                            | Tokens                                                |
| ------------------------------------------------------------------ | ----------------------------------------------------- |
| Success — confirmed, grounded, completed, healthy                  | `--status-success-bg / -border / -text`               |
| Warning — uncertainty, conflicting evidence, degraded, sample data | `--status-warn-bg / -border / -text`                  |
| Error — failed, unavailable, invalid                               | `--status-error-bg / -border / -text`                 |
| Info — explanation, provenance, insight                            | `--status-info-bg / -border` (+ `--accent-cyan` text) |

### Provenance & traits (new)

`--prov-observed` (emerald), `--prov-inferred` (amber), `--prov-synthetic` (muted). Big Five hues `--trait-o/c/e/a/n` are darkened in light mode for contrast.

### Type scale

| Token       | Size                         | Use                                          |
| ----------- | ---------------------------- | -------------------------------------------- |
| `--fs-xs`   | 0.75rem                      | metadata floor for migrated components       |
| `--fs-sm`   | 0.8rem                       | labels, secondary rows, badges               |
| `--fs-base` | 0.875rem                     | body, buttons                                |
| `--fs-md`   | 0.95rem                      | ledes, emphasised body                       |
| `--fs-lg`   | 1.1rem                       | section titles, empty-state titles           |
| `--fs-xl`   | 1.35rem                      | card headlines                               |
| `--fs-2xl`  | 1.75rem                      | page titles, metric values                   |
| `--fs-3xl`  | 2.25rem                      | display titles (Studies, New Study)            |

Weights: 400 body, 500 navigation, 600 controls and titles, 700 emphasis. Shared
headings use `letter-spacing: 0` and balanced wrapping. Do not scale text with
viewport-width units. `--font-sans` leads with self-hosted Plus Jakarta Sans;
`--font-display` leads with Space Grotesk; `--font-mono` leads with JetBrains Mono
for identifiers and measured data. These existing fonts were deliberately
retained after the Impeccable review; no new font dependency was installed.

### Spacing

4 px base: `--sp-1…--sp-12` = 4 8 12 16 20 24 32 40 48. Page gutter `--page-x = clamp(16px, 4vw, 40px)`; reading width `--page-max = 1280px`. Vertical rhythm tiers: 16 (inside a block) · 24 (between blocks) · 32 (between sections).

### Radius

Compact scale: `--r-xs 4`, `--r-sm 6`, `--r-md 8`, `--r-lg 8`, `--r-xl 12`,
`--r-pill 999` (pixels). Use 6px controls, up to 8px cards, and the 12px stop for
dialogs. Pills are for small state badges, not general page sections. Older
inline radius values are not evidence of a different approved scale.

### Elevation

`--shadow-sm / -md / -lg` are two-layer (tight contact + wide soft diffuse), low-contrast and theme-aware. Raised surfaces add `inset 0 1px 0 var(--reflect)`. Buttons and cards do **not** cast accent-coloured glows; selection is shown with a `0 0 0 3px var(--accent-subtle)` ring.

## Components (`src/components/ui`)

All primitives are CSS classes (`ui.css`) with thin React wrappers so inline-styled views can adopt them incrementally.

| Primitive                   | Class                                                                           | Notes                                                                                                      |
| --------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `Button`                    | `.bx-btn --primary/--secondary/--ghost/--danger --sm/--lg --icon --block`       | `loading` → disabled + `aria-busy` + spinner. Icon-only buttons must pass `aria-label`.                    |
| Page header CSS             | `.bx-page-header .bx-eyebrow .bx-title .bx-lede`                                | Exactly one `h1` per view; no React wrapper is exported.                                                   |
| `EmptyState`                | `.bx-empty`                                                                     | Title + _why it matters_ + next action. Never "No data".                                                   |
| `Callout`                   | `.bx-callout --info/--success/--warn/--error`                                   | Errors get `role="alert"`, others `role="status"`.                                                         |
| Badge CSS                   | `.bx-badge --tone --mono` + `.bx-dot --live`                                    | Dot is decorative; text is mandatory; use domain evidence badges where appropriate.                       |
| `ConfidenceBar`             | `.bx-conf`                                                                      | `role="meter"`; `null` → "not measured"; tone by meaning (≥50 % success, >0 warn, 0 muted).                |
| `Metric`                    | `.bx-metric` (+ `.bx-metric-grid`)                                              | `null` → `—` with `aria-label="not measured"`; always carries a footnote.                                  |
| Skeleton CSS                | `.bx-skeleton .bx-skel-*`                                                       | Shape-true; shimmer off under reduced motion; views use these classes directly.                           |
| `CommandMenu`               | `.bx-cmdk*`                                                                     | Ctrl/⌘ K; `role="dialog"` + `combobox`/`listbox`; shares the Escape-stacking protocol via `useDialogA11y`. |
| Shell                       | `.bx-nav-group .bx-nav-item .bx-study-chip .bx-topbar .bx-health .bx-skip-link` | `aria-current="page"` marks the active destination; the study chip marks the open study.                   |

Existing domain components remain the canonical way to show honesty: `ProvenanceChip`, `EvidenceBadge`, `TemplateBadge`, `RequestIdTag`, `MemoryDisclosure`, `RouteDisclosure`, `ProvenanceTraceRow`, `EvaluationCard`.

Unused `PageHeader`, `Badge`, `Skeleton`, and `SkeletonText` wrappers were removed
during repository cleanup; their shared CSS remains available. The prompt-box
demo and legacy auth modal are retained for their direct component tests, but
are no longer exported or wired through unused application entry points.

## Interaction patterns

- **Navigation:** Workspace and Study for regular users; System is visible only to developer/admin accounts. Direct router URLs enforce that same role guard; hiding navigation alone is insufficient. Study-group items retain their study context; persona-to-evidence navigation uses the library's selected study. The chip shows the active study and current step.
- **Command menu:** Ctrl/⌘ K anywhere in the console; destinations, recent studies, theme, sign-out. Type to filter, ↑↓, Enter, Esc.
- **Dialogs:** `useDialogA11y` focuses the explicit initial target or first tabbable control, excludes negative-tab-index, disabled, hidden and inert controls from the Tab loop, and returns focus on close. Pending content with no enabled controls uses a programmatically focusable fallback and cannot release Tab to the page. Legal dialogs use the same labeled trap/restore protocol. The mobile drawer suspends its handler while command/account menus are above it. Escape closes one surface at a time; a closed drawer stays inert.
- **Buttons:** global spring (`hover brightness 1.06`, `active scale .975`), no layout shift.
- **Forms:** inline validation next to the field, `role="alert"` on errors, entered data preserved on failure.
- **Authentication:** fixed OTP slots preserve edit/backspace/paste/autofill position; submit requires exactly six digits. After reset succeeds, a failed automatic sign-in retries sign-in only. Simulated tests do not certify mobile-OS autofill.
- **Composers and copy:** composition Enter must not submit. Clipboard success requires a successful write for the current identity; cleanup clears status timers, and failures offer manual copy.
- **Study creation:** native study-type radios change selection only. Starting a study requires the explicit Start action; selecting a mode never submits an entered idea.
- **Study persistence:** retry the real failed queue entry with owner/study/revision/session/abort guards, retaining the full payload and canonical order. Failed save blocks Regenerate until durable acknowledgment or discard; abort publishes current-owner UNSAVED, never permanent Saving or stale/cross-session SAVED. Save errors must not be described as generation failures.
- **Persona/workflow:** native role checkboxes preserve counts; reselecting the active persona preserves conversation identity/messages. Fresh-batch prerequisites must not block pending resume. Generation success survives auxiliary list-read failure; stale completions cannot reopen dismissed or different inspectors/modals.
- **Evidence:** retain full SUPPORTING/CONTRADICTING sources, provenance and excerpts. Only HTTP(S) URLs without C0/DEL/C1 controls become links; rejected URLs remain complete plain text. Keep selected study/run provenance pinned.
- **Deletion:** a study's options menu opens a confirmation dialog. A failed delete retains the study and exposes an error; cancel returns to the original context.
- **Loading:** skeletons shaped like the result (persona cards, report cards) with real counts where known; spinners only inside buttons. Never fake progress — stages shown only when they map to real state.
- **Errors:** plain-language title + what happened + what is safe + Retry, with `RequestIdTag` where an id exists. Never raw status text as the primary message.
- **Reports:** recovery is operation-specific: reload saved versions, retry generation, or try copying again. A failure does not replace a saved report. Read-only studies cannot regenerate. Model-estimated scores remain explicitly non-observational; invalid/missing values remain unknown.
- **Success:** subtle motion, one confirmation line, obvious next action. No confetti.

## Accessibility rules

- Skip link first in DOM; one main landmark per view (`<main id="bx-main">` in the console, named "BebshaX account" on auth); `<nav aria-label>` for every nav.
- Use native buttons, links, inputs, selects and disclosures; icon-only controls carry `aria-label`. Mobile persona trash/synthesis controls retain 44px targets.
- Global `:focus-visible` uses a 2 px solid `--focus-ring` outline with 2 px offset; the defined theme-paired values must reach 3:1. Meaningful form borders use `--border-control`, also at least 3:1. Inline `outline: none` requires an equally visible replacement focus indicator.
- Contrast target: body, secondary and placeholder text at least 4.5:1; large text and meaningful control indicators at least 3:1. Root-token tests are not a whole-site WCAG certification: verify component overrides in the browser too.
- Colour never alone: dots/badges/bars pair with text; provenance chips carry their word.
- `prefers-reduced-motion` disables shimmer, reveals, sweeps, button springs, live dots.
- `prefers-reduced-transparency` and no-`backdrop-filter` environments get opaque chrome.

## Responsive breakpoints

| Width     | Behaviour                                                                                                                                         |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| ≤ 720 px  | Modals full-width (94dvh); stepper shows numbers + "Step N of 5"; page gutter 16 px                                                               |
| ≤ 900 px  | Sidebar becomes a drawer; mobile bar is explicitly 52px border-box with 44px targets; top bar hides greeting/health label; command trigger icon-only; app headers stick under the bar |
| ≤ 1280 px | Greeting hidden; stepper sub-labels hidden                                                                                                        |
| ≥ 1281 px | Full chrome; content column capped at `--page-max`                                                                                                |

Grids use `repeat(auto-fit|auto-fill, minmax(min(Npx, 100%), 1fr))` — never a raw `minmax(Npx, 1fr)` (overflows phones). Inline-styled layouts use `clamp()` gutters.

## Motion principles

Keep the existing GSAP view/count transitions and short transform/opacity
feedback. Respect reduced motion. Do not animate width, height, padding or
margin: sidebar collapse and progress values now update without width
interpolation. Do not add perpetual decorative motion or an animation library.

## Public site

Redesigned 2026-09-13 in a minimal black/porcelain system with one sans family
and one blue for links and actions. [LandingPage.tsx](../apps/frontend/src/components/landing/LandingPage.tsx)
uses seven main sections: wordmark hero, a tabbed product gallery
([ProductGallery.tsx](../apps/frontend/src/components/landing/ProductGallery.tsx)),
a numbered four-step workflow, research boundaries, available pricing, native
FAQ disclosures, and a closing workspace action. Design dials: variance 5,
motion 3, density 3.

The gallery shows three real Edge captures of the mock preview from
`src/components/landing/gallery/` (brief, persona library, interviews list) at
1200x1000, with a 390x844 phone capture for the brief. Every frame is captioned
SAMPLE and its `alt` says synthetic. Tabs are a real `role="tablist"` with
arrow/Home/End keys. No invented people, customer counts, testimonials,
validated-demand claims or provider uptime guarantees.

`--studio-*` tokens stay independently scoped. Dark: `--studio-bg`/`--studio-band`
`#000000`, `--studio-raised: #101010`, `--studio-text: #f5f5f7`,
`--studio-muted: #a1a1a6`, `--studio-border: #2a2a2e`. Light: canvas `#f5f5f7`,
raised `#ffffff`, text `#1d1d1f`. `--studio-action` (`#2997ff` dark, `#0066cc`
light) is for text links, focus rings and check glyphs; `--studio-action-fill`
(`#0071e3` dark, `#0066cc` light) is the button/avatar fill so white labels meet
4.5:1. Headings inherit the body family (no display face), `letter-spacing: 0`,
weight 600; the wordmark is `clamp(3.5rem, 8vw, 6rem)` at 700. Sections use
7rem vertical rhythm (5rem ≤60rem, 4rem ≤40rem) separated by hairlines, never
cards. Pills are for controls only; the screenshot frame is 1rem. Public
controls are at least 44px high. Mobile navigation appears below 60rem; the
40rem breakpoint stacks layouts and actions. The sticky header is translucent
(`color-mix` + backdrop blur) with a solid fallback.

No eyebrows, gradient text, icon tiles, glass panels, three-equal-card rows, or
teal/mint/gold on the public site. The in-app "Showing sample data (mock mode)"
banner is an honesty marker and stays as-is inside captured screenshots.

## Adding UI — checklist

1. Use tokens for every colour, size, radius, gap. Run `npm run theme:check`.
2. Reach for a primitive before hand-building; if none fits, add one here (class + wrapper + test) rather than a one-off.
3. Design all four states: loading (skeleton), empty (what/why/next), error (what/safe/retry), success (confirm/next).
4. Keyboard path, `aria-*` on icon-only controls, one `h1`.
5. Check 390 / 768 / 1440 and both themes in the mock dev server (`VITE_MOCK=1`).
