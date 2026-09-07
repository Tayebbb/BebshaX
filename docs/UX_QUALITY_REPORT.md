# BebshaX — UX Quality Report (2026-09-07)

Scored after the premium product-experience pass. Scores are 0–10 per dimension, judged against the bar in the transformation brief (Apple-level restraint, Notion-level IA, Linear-level interaction). They are honest, not aspirational — "what remains" lists what would move each number. A subsequent creative-direction pass is recorded in [TASTE_REVIEW.md](TASTE_REVIEW.md); it raises Persona Library and Routing & Provenance to 8.6 and moves the landing page into compliance with the eyebrow / hero-stack / dash rules.

Method: three independent code audits ([UI_UX_AUDIT.md](UI_UX_AUDIT.md)), live inspection of the mock-mode app at 1440 / 1024 / 390 px in both themes, keyboard walk-throughs of the shell, and the eight review lenses from the brief (Apple · Notion · Linear · UX researcher · accessibility · competition judge · frontend engineer · hostile user). Gates at time of writing: `tsc` 0 errors · 244/244 vitest · `vite build` 0 · `theme:check` 0 files.

## Page scores

| Page                                   | Visual | UX  | Product | A11y | Responsive | Overall |
| -------------------------------------- | :----: | :-: | :-----: | :--: | :--------: | :-----: |
| Console shell (sidebar · top bar · ⌘K) |   9    |  9  |    9    |  9   |     9      | **9.0** |
| New Study (entry)                      |   9    |  9  |    8    |  8   |     9      | **8.6** |
| Dashboard (Studies)                    |   9    |  8  |    8    |  7   |     9      | **8.2** |
| Persona Library                        |   8    |  8  |    9    |  8   |     8      | **8.2** |
| Study workflow — steps 1–5             |   8    |  8  |    9    |  7   |     8      | **8.0** |
| Interview workspace                    |   8    |  8  |    9    |  8   |     8      | **8.2** |
| Evidence Laboratory                    |   8    |  8  |    9    |  8   |     8      | **8.2** |
| Routing & Provenance                   |   8    |  8  |    9    |  8   |     8      | **8.2** |
| Behavioral testing                     |   7    |  7  |    8    |  6   |     8      | **7.2** |
| Audience segments                      |   7    |  7  |    8    |  7   |     8      | **7.4** |

Core workflow target was 9+; shell reached it, the study workflow and persona pages sit at 8.0–8.2. Behavioral testing and segments are below the 8 floor and are listed first in "what remains".

## Dimension scores (whole product)

| Dimension                | Score | Basis                                                                                                                                                                               |
| ------------------------ | :---: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Visual design            |  8.5  | One token system, one CTA gradient, scales for type/space/radius; glass reserved for chrome. Residual literal colours in ~5 views.                                                  |
| Information architecture |   9   | Workspace / Study / System grouping, active-study chip, breadcrumb, command menu. Labels unchanged (test contracts).                                                                |
| User experience          |  8.5  | Every empty state names the next action; study-less tabs explain _why_ a study is needed; returning users resume via chip or ⌘K.                                                    |
| Interaction design       |  8.5  | ⌘K with full keyboard model; stepper "Step N of 5"; spring buttons; Escape stacking protocol shared by all dialogs.                                                                 |
| Accessibility            |   8   | Skip link, single `main`, `aria-current`, labelled icon buttons, `role="meter"` bars, text-with-colour everywhere new. Chat bubbles and behavioral type cards still lack semantics. |
| Responsive design        |  8.5  | 390 px verified zero-overflow; drawer nav; grids use `min(Npx,100%)`; stepper collapses. Inspector's 8 tabs still scroll horizontally on phones.                                    |
| Performance              |   8   | +1 CSS file (~12 KB raw) and ~6 KB of primitives; no new dependencies; dashboard chunk 469 KB (was 394 KB before earlier hardening — PersonaLibraryView split is the lever).        |
| Product differentiation  |   9   | Evidence grounding, provenance, memory and routing are visible product features with progressive disclosure, not debug panels.                                                      |
| Competition readiness    |  8.5  | 10-second test: breadcrumb + eyebrow + title answer "what/where"; health pill answers "is it live"; ⌘K "routing" gets a judge to the technical story in one keystroke.              |

**Overall: 8.5 / 10**

## Journey checks

- **A — first-time user.** New Study composer → copilot → personas → interview → report. Tour hint, gated stepper with lock reasons, skeletons with real counts, honest "Starter script (not AI-generated)" banner, "No report yet" empty state. Pass.
- **B — returning user.** Dashboard lists studies with status; sidebar chip and ⌘K "Recent studies" reopen at the saved step; the chip stays visible while in Interviews/Evidence. Pass.
- **C — judge.** Health pill states Sample data / Demo mode / Backend connected; ⌘K → Routing & Provenance; architecture vs live status clearly separated; failed traces render "not served" and `—`. Pass. (Controlled failure demo depends on backend state, unchanged.)

## Review-lens findings (condensed)

- **Apple:** the shell is now quiet — three group labels, one accent rule, one gradient. Residual noise: persona cards still carry five chip styles.
- **Notion:** grouping + breadcrumb fixed "where am I"; the study chip is the single biggest IA win.
- **Linear:** ⌘K, `Ctrl+Enter` composer, Escape stacking. Missing: `g`-prefixed shortcuts and list keyboard navigation in the studies table.
- **UX researcher:** empty states explain object relationships (studies own interviews/evidence). Friction left: eight inspector tabs.
- **Accessibility:** skip link, landmarks, labels, meters added; chat bubbles/behavioral cards remain.
- **Judge:** reads as a product, not a template; health pill and sample-data banner prevent "is this real?" confusion.
- **Frontend engineer:** primitives are class-first so adoption is incremental; PersonaLibraryView (1.9k lines) and DashboardLayout (1.6k) still need splitting.
- **Hostile user:** "Where do I click?" — breadcrumb + eyebrow + CTA. "What happened?" — every error names what is safe and offers Retry with a request id. "Why does this persona believe this?" — ProvenanceChip → cited claim. Unanswered: "What do I do after the report?" (no post-report next step beyond Export).

## Changes made in this pass

- Token scales (`--fs-*`, `--sp-*`, `--r-*`), `--accent-gradient`, semantic status surfaces, provenance and trait hues (theme-paired).
- Primitive layer `src/components/ui/`: Button, PageHeader, EmptyState, Callout, Badge, ConfidenceBar, Skeleton, Metric, CommandMenu + `ui.css`.
- Sidebar regrouped into Workspace / Study / System with `aria-current`, active-study chip (title + step), muted study items when no study is open.
- Top bar: breadcrumb (group › page › study), greeting demoted, ⌘/Ctrl K command trigger, backend health pill (`role="status"`).
- Command menu: destinations, recent studies, theme toggle, sign-out; full keyboard model; Escape-stacking protocol.
- Skip link + single `main` landmark (workflow inner `main` → `div`).
- Stepper: accessible names, `Step N of 5` readout, numbers-only under 720 px.
- Persona cards: `article` with label, `minmax(min(320px,100%),1fr)` grid, tokenised trait/status colours, labelled icon actions, `role="img"` trait bars, hover owned by `.bx-lift`.
- Persona metric strip: no orphan card.
- Study-less empty state rebuilt on `EmptyState` with an explanation of what belongs to a study.
- Literal ambers/reds in the shell and Step 4 pills → status tokens.
- 18 new tests (`tests/ConsoleShell.test.tsx`): nav groups, `aria-current`, study chip, breadcrumb, skip link, health text, ⌘K open/filter/select/escape/empty/recent, primitive honesty states.

## What remains (ordered)

1. Behavioral testing: type cards to real buttons; adopt `Metric`/`EmptyState`; tokenise likelihood colours.
2. Chat bubbles (Step 1/Step 4): `role="listitem"`/`article` + author labels; `aria-live` on the copilot log.
3. Persona inspector: collapse 8 tabs into 4 sections with in-page anchors on phones; persist expanded evidence across tabs.
4. Finish literal-colour sweep: Step2Personas avatar gradient ×3 → `--accent-gradient`; Step5Report metric fills → status tokens; EvidenceLab indigo residue.
5. Copy-to-clipboard confirmations → `aria-live="polite"`.
6. Split PersonaLibraryView / DashboardLayout; lazy-load the inspector and behavioral views to pull the dashboard chunk back under 400 KB.
7. Post-report next step: "Start a follow-up study" / "Validate with real customers" CTA on Step 5.
