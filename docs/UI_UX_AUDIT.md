# BebshaX — UI/UX Audit (2026-09-07)

Phase-0 audit of the console frontend (`apps/frontend/src`, ~40k lines) before the premium product-experience pass. Findings come from three parallel read-only reviews (entry/dashboard/personas · study workflow · interview/routing/behavioral) plus a live inspection of the running app in mock mode at 1440, 1024 and 390 px, both themes. Line references were accurate at audit time.

The redesign that followed is logged in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) (Maintenance 2026-09-07); the resulting system is specified in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) and scored in [UX_QUALITY_REPORT.md](UX_QUALITY_REPORT.md).

## 1. Current UX problems

| # | Finding | Where | Severity |
|---|---------|-------|----------|
| U1 | Navigation is a flat list of eight equal items. Nothing tells the user that Interviews / Behavioral Testing / Evidence / Segments are *inside a study* while New Study / Dashboard / Persona Library / Routing are not. | `DashboardLayout.tsx` navItems | High |
| U2 | No "where am I" signal beyond the highlighted nav row: no breadcrumb, no active-study indicator. Opening a study-scoped tab without a study renders an empty state but the sidebar gives no hint why. | `DashboardLayout.tsx` header | High |
| U3 | Header above every non-workflow view is only a greeting ("Good morning, X") — the generic dashboard opener with zero information value. | `DashboardLayout.tsx` L1040–1060 | Medium |
| U4 | No keyboard jump/command surface; every destination needs the mouse and the sidebar. | shell | Medium |
| U5 | Backend liveness is only visible as a bottom-centre banner when *down*; there is no always-on health signal. | shell | Low |
| U6 | Persona card actions: "Deep Dive Inspector" is a full-width heavy button; the two icon-only buttons beside it have `title` but no accessible name. | `PersonaLibraryView.tsx` L1040–1080 | Medium |
| U7 | Study-workflow stepper wraps to two rows at ≈1250 px and gives no "Step N of 5" readout when labels are hidden on small screens. | `StudyWorkflowView.tsx` stepper | Medium |
| U8 | Two `<main>` landmarks on the workflow route (shell + workflow). | `StudyWorkflowView.tsx` | Low |
| U9 | Kebab/row dual click targets on the study list (row is clickable, title is also a button). | `StudiesDashboardView.tsx` L307/L341 | Low (deferred) |
| U10 | Inspector modal with 8 tabs scrolls horizontally on phones; expanded evidence state is lost between tabs. | `PersonaLibraryView.tsx` inspector | Low (deferred) |

## 2. Current visual problems

| # | Finding | Evidence |
|---|---------|----------|
| V1 | **No type scale.** 15+ distinct `fontSize` values in PersonaLibraryView alone (0.7, 0.72, 0.74, 0.75, 0.78, 0.8, 0.82, 0.84, 0.86, 0.88, 0.9, 0.92, 0.95, 1.05, 1.4, 1.85 rem). | audit grep |
| V2 | **No radius scale.** 4/5/6/8/10/12/14/16/18/20/22 px all in use. | audit grep |
| V3 | The primary CTA gradient `linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)` is re-typed ≥10× and does not flip for light mode. | Step2Personas ×3, PersonaLibraryView ×2, DashboardLayout, StudyWorkflowView ×5 |
| V4 | Big Five trait hues (`#38BDF8 #F59E0B #A855F7 #EC4899`) and status ambers/reds (`#F59E0B`, `rgba(245,158,11,…)`, `rgba(239,68,68,…)`) are literals — invisible to the theme codemod and washed-out in light mode. | PersonaLibraryView ×11, Step4Interviews, DashboardLayout |
| V5 | Persona card hover shadow is a literal `0 8px 24px rgba(0,0,0,.4)` set from JS, duplicating what `.bx-lift` already does. | PersonaLibraryView L831 |
| V6 | Four metric cards in a 3-column grid leave an orphan card (a "Total X" dashboard pattern). | PersonaLibraryView metrics |
| V7 | Sidebar section label ("RECENT STUDIES") is styled differently from everything else in the rail. | DashboardLayout |

What is **good** and was preserved: the teal/cyan token system with a light theme and a codemod drift gate; the Liquid Glass chrome material; the editorial Studies dashboard; NewStudyView's guided composer; `ProvenanceChip`/`EvidenceBadge`/`TemplateBadge`; `RequestIdTag`; `MemoryDisclosure`/`RouteDisclosure`; the honest `—` for unmeasured numbers; CountUp; shape-true skeletons whose count equals the selected role counts; step gating; `useDialogA11y`.

## 3. Workflow problems

- W1 — Returning users cannot get back into the study they were working in without scanning "Recent Studies"; there is no current-study affordance.
- W2 — Study-scoped tabs opened cold say "No study selected" but did not explain *why* studies matter or which objects belong to one.
- W3 — Judges cannot jump from any screen to Routing & Provenance without knowing it is at the bottom of the rail.

## 4. Information-architecture problems

Eight sibling items conflate three scopes. Proposed (and implemented) grouping:

```
Workspace   New Study · Dashboard · Persona Library
Study       [active study chip]  Interviews · Behavioral Testing · Evidence Laboratory · Audience Segments
System      Routing & Provenance
```

Labels were kept verbatim (they are test contracts and already meaningful); the grouping, the active-study chip and a breadcrumb supply the missing hierarchy.

## 5. Accessibility problems

| # | Finding | Fix status |
|---|---------|-----------|
| A1 | No skip link; ~20 tab stops before content. | Fixed (`Skip to main content` → `#bx-main`) |
| A2 | Icon-only Interview / Behavior buttons on persona cards have no accessible name. | Fixed (`aria-label` with persona name) |
| A3 | Primary nav uses colour + weight for the active item; no `aria-current`. | Fixed (`aria-current="page"` + left rule) |
| A4 | Two `<main>` landmarks on the workflow route. | Fixed |
| A5 | Big Five bars are colour-only glyphs with a `title`. | Fixed (`role="img"` + `aria-label`) |
| A6 | Stepper buttons announce as "2 Personas". | Fixed ("Step 2: Personas (done)") |
| A7 | Chat bubbles in Step 1 / Step 4 are `<div>`s without roles. | Deferred |
| A8 | Behavioral test-type cards are `div onClick`. | Deferred (known, in repo memory) |
| A9 | Backend health only visible as colour in some places. | Fixed (text pill, `role="status"`) |

Already correct: dialog protocol (Escape stacking, focus trap, focus return), `role="alert"`/`role="status"` on errors/loaders, `role="log"` on the interview thread, `role="meter"`-style honest metrics.

## 6. Responsive problems

| # | Finding | Fix status |
|---|---------|-----------|
| R1 | Persona grid `minmax(350px, 1fr)` → single column at 1024 px content widths and overflow risk < 370 px. | Fixed (`minmax(min(320px,100%),1fr)`) |
| R2 | Metrics `minmax(220px,1fr)` → orphan 4th card. | Fixed (`minmax(min(190px,100%),1fr)`) |
| R3 | Stepper labels crowd at < 720 px. | Fixed (numbers only + "Step N of 5") |
| R4 | Top-bar chrome truncates the breadcrumb when the greeting is present. | Fixed (greeting hidden < 1280 px, trigger width capped) |
| R5 | Sidebar 240 px truncates "Routing & Provenance". | Fixed (256 px) |

Verified at 390 px: no horizontal overflow on Dashboard; drawer nav; icon-only command trigger.

## 7. Component inconsistencies

Every button, badge, empty state and callout was hand-built inline with its own padding, radius and colour. There was no reusable primitive layer, so identical concepts (empty state, error callout, status badge) differed screen to screen. See [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) §Components for the primitives introduced.

## 8. Proposed design system

Kept: colour tokens, glass material, fonts. Added: type scale (`--fs-*`), spacing scale (`--sp-*`), radius scale (`--r-*`), `--accent-gradient`, semantic status surfaces (`--status-{success,warn,error,info}-{bg,border}`), provenance hues, theme-aware trait hues; a class-based primitive layer (`src/components/ui/ui.css`) with thin React wrappers.

The `ui-ux-pro-max --design-system` run for this brief suggested an institutional-navy palette with Inter. **Rejected**: BebshaX already has a coherent, test-gated teal system across 40k lines; replacing the palette would have been a superficial reskin with high regression cost. The generator's structural advice (restraint, one gradient, tokenised scales, scroll reveals ≤ 16 px, no fast animation) was adopted.

## 9. Proposed navigation structure

Implemented as in §4 plus: a top bar (breadcrumb · greeting · **⌘/Ctrl K** command menu · backend health), a study chip that doubles as "return to where I was" (shows current step while in the workflow), and a skip link.

## 10. Proposed user journeys

- **First-time user:** New Study composer → copilot goal → personas → interview → report. The tour hint and empty states now point to the next action at every step.
- **Returning user:** Dashboard or ⌘K → recent study → workflow resumes at the saved step; the study chip keeps the context visible while visiting Interviews/Evidence.
- **Judge:** ⌘K "routing" → Routing & Provenance; health pill shows backend/demo state at all times; honest sample-data banner unchanged.

## 11. Priority of improvements

1. Shell IA (groups, chip, breadcrumb, command menu, skip link) — done.
2. Tokens + primitives — done; adoption started (shell empty state, persona cards, stepper).
3. Persona card a11y/responsive — done.
4. Remaining literal colours in Step2Personas/Step5Report/EvidenceLab; chat-bubble semantics; behavioral type cards keyboard access; inspector tab overflow — next.
5. StudiesDashboardView dual click target; PersonaLibraryView split (1.9k lines) — later.
