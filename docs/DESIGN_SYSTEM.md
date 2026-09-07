# BebshaX Design System

Source of truth for console UI work. Tokens live in [`apps/frontend/src/index.css`](../apps/frontend/src/index.css); primitives in [`apps/frontend/src/components/ui/`](../apps/frontend/src/components/ui/). The landing page (`components/landing`) has its own `lp-*` token set and is out of scope here.

## Principles

1. **Clarity over decoration.** Frosted glass is for chrome (sidebar, headers, drawers, dialogs) — never for content cards. Content cards use a _simulated_ material (surface gradient + top hairline), so the compositor budget stays at ≤ 4 blurred surfaces.
2. **Hierarchy over density.** One `h1` per view, one eyebrow, one lede. Cards mark grouping, not everything.
3. **Evidence is first-class.** Grounding, provenance and routing are never hidden — they are progressively disclosed (`ProvenanceChip` → `EvidenceClaimPeek`; `RouteDisclosure`; `MemoryDisclosure`).
4. **Honest numbers.** Unmeasured values render `—` or "not measured", never `0` or a placeholder percentage. Sample/demo/mock data is always labelled.
5. **Text carries state.** Colour never carries meaning alone: every dot, badge and bar has a label.
6. **Restraint in motion.** Transform/opacity only; ≤ 0.5 s; `prefers-reduced-motion` disables all of it.

## Tokens

### Colour (existing, theme-paired via `[data-theme='light']`)

| Role              | Token                                                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Canvas / surfaces | `--bg-pure` `--bg-primary` `--bg-secondary` `--bg-card` `--bg-card-hover`                                                                    |
| Borders           | `--border-subtle` `--border-medium` `--border-hover` `--border-soft`                                                                         |
| Soft fills        | `--fill-soft` `--fill-soft-2`                                                                                                                |
| Glass tiers       | `--glass-strong` `--glass-mid` `--glass-soft` (+ `--glass-blur` `--glass-saturate` `--reflect` `--scrim`)                                    |
| Text              | `--text-main` `--text-primary` `--text-secondary` `--text-muted` `--text-faint` `--text-label` `--text-on-accent`                            |
| Accent            | `--accent-teal` `--accent-cyan` `--accent-teal-bright` `--accent-emerald` `--accent-amber` `--accent-rose` `--accent-subtle` `--accent-glow` |
| **CTA gradient**  | `--accent-gradient` — the only gradient allowed on primary actions                                                                           |

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
| `--fs-xs`   | 0.72rem                      | metadata **floor** — nothing renders smaller |
| `--fs-sm`   | 0.8rem                       | labels, secondary rows, badges               |
| `--fs-base` | 0.875rem                     | body, buttons                                |
| `--fs-md`   | 0.95rem                      | ledes, emphasised body                       |
| `--fs-lg`   | 1.1rem                       | section titles, empty-state titles           |
| `--fs-xl`   | 1.35rem                      | card headlines                               |
| `--fs-2xl`  | 1.75rem                      | page titles, metric values                   |
| `--fs-3xl`  | clamp(1.9rem, 3.4vw, 2.5rem) | display titles (Studies, New Study)          |

Weights: 400 body · 500 nav/labels · 600 titles, buttons · 700 display, metrics. Headings use `letter-spacing: -0.03em` and `text-wrap: balance`. Numbers use `font-variant-numeric: tabular-nums`. Fonts: Plus Jakarta Sans (UI), JetBrains Mono (ids, request ids, kbd), self-hosted via `@fontsource`.

### Spacing

4 px base: `--sp-1…--sp-12` = 4 8 12 16 20 24 32 40 48. Page gutter `--page-x = clamp(16px, 4vw, 40px)`; reading width `--page-max = 1280px`. Vertical rhythm tiers: 16 (inside a block) · 24 (between blocks) · 32 (between sections).

### Radius

`--r-xs 6` `--r-sm 8` `--r-md 12` `--r-lg 16` `--r-xl 20` `--r-pill 999`. Buttons/inputs `sm`; callouts/metrics `md`/`lg`; cards `lg`; dialogs `xl`; badges `pill`.

### Elevation

`--shadow-sm / -md / -lg` are two-layer (tight contact + soft diffuse) and theme-aware; `--shadow-glow` for the primary CTA only. Raised surfaces add `inset 0 1px 0 var(--reflect)`.

## Components (`src/components/ui`)

All primitives are CSS classes (`ui.css`) with thin React wrappers so inline-styled views can adopt them incrementally.

| Primitive                   | Class                                                                           | Notes                                                                                                      |
| --------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `Button`                    | `.bx-btn --primary/--secondary/--ghost/--danger --sm/--lg --icon --block`       | `loading` → disabled + `aria-busy` + spinner. Icon-only buttons must pass `aria-label`.                    |
| `PageHeader`                | `.bx-page-header .bx-eyebrow .bx-title .bx-lede`                                | Exactly one `h1` per view.                                                                                 |
| `EmptyState`                | `.bx-empty`                                                                     | Title + _why it matters_ + next action. Never "No data".                                                   |
| `Callout`                   | `.bx-callout --info/--success/--warn/--error`                                   | Errors get `role="alert"`, others `role="status"`.                                                         |
| `Badge`                     | `.bx-badge --tone --mono` + `.bx-dot --live`                                    | Dot is decorative; text is mandatory.                                                                      |
| `ConfidenceBar`             | `.bx-conf`                                                                      | `role="meter"`; `null` → "not measured"; tone by meaning (≥50 % success, >0 warn, 0 muted).                |
| `Metric`                    | `.bx-metric` (+ `.bx-metric-grid`)                                              | `null` → `—` with `aria-label="not measured"`; always carries a footnote.                                  |
| `Skeleton` / `SkeletonText` | `.bx-skeleton .bx-skel-*`                                                       | Shape-true; shimmer off under reduced motion.                                                              |
| `CommandMenu`               | `.bx-cmdk*`                                                                     | Ctrl/⌘ K; `role="dialog"` + `combobox`/`listbox`; shares the Escape-stacking protocol via `useDialogA11y`. |
| Shell                       | `.bx-nav-group .bx-nav-item .bx-study-chip .bx-topbar .bx-health .bx-skip-link` | `aria-current="page"` marks the active destination; the study chip marks the open study.                   |

Existing domain components remain the canonical way to show honesty: `ProvenanceChip`, `EvidenceBadge`, `TemplateBadge`, `RequestIdTag`, `MemoryDisclosure`, `RouteDisclosure`, `ProvenanceTraceRow`, `EvaluationCard`.

## Interaction patterns

- **Navigation:** three groups (Workspace / Study / System). Study-group items are muted until a study is open; the chip shows the study title and current step. Breadcrumb = group › page › study.
- **Command menu:** Ctrl/⌘ K anywhere in the console; destinations, recent studies, theme, sign-out. Type to filter, ↑↓, Enter, Esc.
- **Dialogs:** `useDialogA11y` — focus first control, Tab trap, Escape closes _only the topmost_ surface (capture phase + `defaultPrevented`), focus returns to the opener. Backdrop `.bx-backdrop` frosts the page; dialog `.bx-modal`.
- **Buttons:** global spring (`hover brightness 1.06`, `active scale .975`), no layout shift.
- **Forms:** inline validation next to the field, `role="alert"` on errors, entered data preserved on failure.
- **Loading:** skeletons shaped like the result (persona cards, report cards) with real counts where known; spinners only inside buttons. Never fake progress — stages shown only when they map to real state.
- **Errors:** plain-language title + what happened + what is safe + Retry, with `RequestIdTag` where an id exists. Never raw status text as the primary message.
- **Success:** subtle motion, one confirmation line, obvious next action. No confetti.

## Accessibility rules

- Skip link first in DOM; one `<main id="bx-main">`; `<nav aria-label>` for every nav.
- Every interactive element is a real `<button>`/`<a>`; icon-only controls carry `aria-label`.
- Global `:focus-visible` ring (2 px solid teal-600, ≥ 3:1 in both themes) — inline `outline: none` is forbidden except inside the command input where the dialog itself is the focus indicator.
- Contrast: body ≥ 4.5:1, secondary ≥ 3:1 in both themes (tokens chosen for this).
- Colour never alone: dots/badges/bars pair with text; provenance chips carry their word.
- `prefers-reduced-motion` disables shimmer, reveals, sweeps, button springs, live dots.
- `prefers-reduced-transparency` and no-`backdrop-filter` environments get opaque chrome.

## Responsive breakpoints

| Width     | Behaviour                                                                                                                                         |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| ≤ 720 px  | Modals full-width (94dvh); stepper shows numbers + "Step N of 5"; page gutter 16 px                                                               |
| ≤ 900 px  | Sidebar becomes a drawer with a 52 px mobile bar; top bar hides greeting/health label; command trigger icon-only; app headers stick under the bar |
| ≤ 1280 px | Greeting hidden; stepper sub-labels hidden                                                                                                        |
| ≥ 1281 px | Full chrome; content column capped at `--page-max`                                                                                                |

Grids use `repeat(auto-fit|auto-fill, minmax(min(Npx, 100%), 1fr))` — never a raw `minmax(Npx, 1fr)` (overflows phones). Inline-styled layouts use `clamp()` gutters.

## Motion principles

One ease: `--bx-ease: cubic-bezier(0.16, 1, 0.3, 1)`. View entrance 0.5 s rise 14 px; card stagger 45 ms/step capped 0.36 s total; modal 0.4 s rise+scale; chat bubble 0.3 s; CTA sheen sweep 0.6 s one-shot. GSAP (`src/motion/`) is used for count-ups and view staggers; everything else is CSS. Nothing animates infinitely except the skeleton shimmer and the health dot pulse (both off under reduced motion).

## Adding UI — checklist

1. Use tokens for every colour, size, radius, gap. Run `npm run theme:check`.
2. Reach for a primitive before hand-building; if none fits, add one here (class + wrapper + test) rather than a one-off.
3. Design all four states: loading (skeleton), empty (what/why/next), error (what/safe/retry), success (confirm/next).
4. Keyboard path, `aria-*` on icon-only controls, one `h1`.
5. Check 390 / 768 / 1440 and both themes in the mock dev server (`VITE_MOCK=1`).
