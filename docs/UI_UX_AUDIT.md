# BebshaX UI/UX Audit

## Pitch-Black Audit (2026-09-13)

**Completed frontend code gate; bounded browser confirmation with explicit gaps.**
The user renewed explicit multi-agent authorization after the earlier cloud
cancellation. Three independent code-audit groups covered public/auth/common,
all workflow/interview, and deeper research. Scoped TDD implementers were followed
by independent final code reviews, browser review and a verifier. This record
documents that completed parent pass; the close-out edits documentation only.

The pinned dark PAGE CANVAS is `#000000`, with neutral `#080808` secondary,
`#101010` card and `#191919` hover surfaces. No colored ambient/glowing page
background; light porcelain is unchanged. This overrides the old graphite
direction, not the distinction between canvas and component paint.

### Surface Coverage

This is the mounted **code-audit and regression-review inventory**, not a claim
that every dynamic state ran in a real browser. Mounting is controlled by
[App.tsx](../apps/frontend/src/App.tsx),
[AuthPage.tsx](../apps/frontend/src/components/auth/AuthPage.tsx) and
[DashboardLayout.tsx](../apps/frontend/src/components/dashboard/DashboardLayout.tsx).

| Mounted family | Features and controls in scope | Browser boundary |
| --- | --- | --- |
| Public site | All seven sections: brand introduction, actual product picture, study sequence, research boundaries, pricing, FAQ, closing action; desktop/mobile navigation, theme, account/sign-out, workspace actions, pricing controls, native FAQ and legal dialogs | Sections, controls, legal keyboard behavior and SAMPLE image intrinsics checked in both viewport/theme pairs; no live payment claim |
| Authentication | All six variants: sign-in, signup chooser, email signup, forgot password, verify OTP, reset-password OTP; labels, password reveal, back/switch controls, resend/countdown, validation, submit/error/retry, legal and named account main | Native forms, OTP editing and mock signup/signin/logout reached; no real delivery, OAuth or mobile-OS certification |
| Shared shell/common/UI | Workspace/Study/System navigation, recent/active study, command search/keyboard, account/theme/sign-out, mobile drawer, skip link/main, role-limited route, dialogs, form boundaries, alerts/loading/empty states, clipboard and prompt controls | Representative menus, focus, body layout and route denial captured; zero-control pending dialogs and composition edge cases use component tests |
| Studies | Composer, native study-type radios, explicit Start, examples, study CRUD, row/options menu, delete confirmation/cancel/error and retained selection | Fixture creation/list/options/cancel paths reached; interrupted dark-desktop options/delete flow remains a gap |
| Workflow steps 1-5 | 1: context/copilot/send and draft state; 2: native role checkboxes/counts, persona generation and batch resume; 3: script edit/regenerate; 4: persona selection/interview/send/synthesis; 5: report versions/generate/retry/copy/export/read-only; stepper, gating and modal recovery | Existing workflow and saved-example fixtures reached; pending-save/batch edge cases are unit-only; one dark-desktop send/report-refusal flow was interrupted |
| Persona library | Study selection, filters, generation/quota controls, cards/delete, regeneration, inspector tabs, complete attributes/provenance, supporting/contradicting evidence, source/excerpts, memory and interview/behavior/synthesis actions | Populated inspector/evidence and ordinary generation captured; late callback, auxiliary-load and pending-dialog cases use regressions |
| Interviews | List/filter/open, dedicated InterviewWorkspace, StartInterviewModal, transcript/composer, persona selection, memory, options and synthesis/retry | List/start and workflow interview states reached; populated dedicated workspace unavailable in existing mocks, error/empty view captured; deep component tests passed |
| Segments/datasets | Primary segments, dataset selection/upload controls, generation/refresh/retry, run selection, summaries, selected study/run provenance, evidence and persona navigation | Representative fixture views/controls reached; independent-load and provenance edge cases use component tests, not live data certification |
| Evidence laboratory | Sources, claims/provenance, research runs/status/retry, source controls, links/copy, full evidence/excerpts and study navigation | Fixture sources/claims/runs and ordinary links reached; unsafe-URL edge cases remain unit-only |
| Behavioral testing | List/filter/run selection, four-step type/population/configuration/preview wizard, create/run/retry, detail/reasoning, rerun scenario/target, polling, comparison and back navigation | Wizard and unavailable detail/comparison views reached; populated detail/comparison not seeded by existing mocks; deep component tests passed |
| Developer diagnostics | Direct developer/admin route guard, normal-user denial/Back to studies, request traces/expansion, candidates/failures/provenance, health/pools, evaluation and conditionally exposed Judge Lab | Role denial and mock developer/admin diagnostics checked; Back activation stopped in the H1 capture helper; unit back-navigation passed; no live judge/provider check |

Legacy unmounted `AuthModal`, `ai-prompt-box` and its `demo`, and
`OpenRouterDiagnostic` were read/reference-checked by the code audits but are
explicitly excluded from runtime coverage. No missing or unmounted surface is
presented as browser-tested.

### Interaction Repairs

| Area | Completed repair |
| --- | --- |
| Theme and accessibility | Root, landing and interview CSS remove colored ambient/decorative gradients. Defined paired `--border-control` and `--focus-ring` meet the tested 3:1 control target; normal text targets 4.5:1. Auth has its named main. Mobile header declares 52px border-box with 44px targets; report Strategic Recommendations uses `--text-main` after the light 2.22:1 finding. |
| Auth and legal | OTP retains fixed slots for edit/backspace/partial or full paste/autofill and requires exactly six valid digits. Legal dialogs share labeling, focus trap and restoration; unsupported "Zero PII Leakage" copy was removed. A successful reset followed by sign-in failure retries sign-in only. |
| Shared interactions | IME composition does not trigger false Enter submission. Clipboard success requires a successful write; stale identity/timers are guarded/cleaned and manual copy remains available. Pending dialogs with no enabled controls retain focus. |
| Persona/workflow state | Native role checkboxes preserve counts; reselecting the active persona does not clear messages or conversation identity. Trash/synthesis controls have accessible labels and mobile 44px targets. Fresh-batch prerequisites do not block pending-batch resume. Generation success remains visible despite a pending/failed list read. Late regeneration/modal callbacks cannot reopen a closed or different inspector or a dismissed modal. |
| Evidence and segments | Complete SUPPORTING and CONTRADICTING evidence, provenance and excerpts remain visible. Only HTTP(S) URLs without C0/DEL/C1 controls become links; the full rejected URL stays plain text. Primary segments load independently of auxiliary failure, with selected run/study provenance pinned. |
| Behavioral and synthesis recovery | Reruns preserve the selected run's scenario/target. Create-success/run-failure retries only the saved run, avoiding duplicates. Reasoning cards are keyboard-accessible and restore focus. Retry restarts polling when the same run is still Running. Synthesis errors retry the correct operation. |
| Durable study drafts | Safe retry belongs to a real failed queue entry and is guarded by owner, study, revision, session and abort state. It retains the complete payload and canonical write order. Failed save blocks Regenerate until durable acknowledgment/discard; abort publishes UNSAVED for the current owner instead of permanent Saving. No late SAVED or cross-session publication; restored save-error copy does not misreport generation failure. |
| Permission boundary | Direct router URLs enforce developer/admin access, not just hidden navigation. This is frontend route coverage, not a new claim about live authentication or backend authorization. |

Regression anchors:
[AuthOtp](../apps/frontend/tests/AuthOtp.test.tsx),
[DialogA11y](../apps/frontend/tests/DialogA11y.test.tsx),
[StudioPersonas](../apps/frontend/tests/StudioPersonas.test.tsx),
[BehavioralTesting](../apps/frontend/tests/BehavioralTesting.test.tsx),
[FrontendStudyPersistence](../apps/frontend/tests/FrontendStudyPersistence.test.tsx),
[StudyCopilot](../apps/frontend/tests/StudyCopilot.test.tsx) and
[StudioTheme](../apps/frontend/tests/StudioTheme.test.ts).
Parent-composed draft checks passed first 47, then 53; the final four-file
focused run passed 143, followed by **1,100 passed / 0 failed / 0 skipped in
65 files** on a stable 189-file source/asset snapshot. TypeScript, Vite 8.2.2
build and theme check exited 0. No dependency was added; concurrent upgrades
were preserved.

### Browser Record And Limits

First inspection retained **774 PASS / 133 FAIL**: 130 incorrect light-must-be-
black harness assertions and three actual router UI assertions subsequently
fixed; all 93 dark root captures passed. Confirmation retained **1,143 PASS /
25 FAIL assertions**: three app assertions representing two issues, seven
harness errors and fifteen environment/artifact errors. Its 148 captures cover
1440x1000 and 390x844 in both themes; 2,320 valid bare-canvas RGB samples support
dark black/light porcelain. Invalid panel samples are not new passes.

The report contrast and 53px-header issues were fixed after capture with focused
regressions; failing screenshots were not relabeled and there was no third
broad browser round. Exact 52px full non-occlusion was not browser-reverified.
Native IME hardware and mobile paste/autofill remain uncertified. No full
backend/ML, live auth/OTP/provider/payment/database, exhaustive WCAG/screen-reader,
Lighthouse or field Core Web Vitals checks belong to this pass. No commit, push
or CI claim; external HEAD advancement and the neighboring 1,039-frontend/
2,938-backend live sweep belong to other work.

[UX_QUALITY_REPORT.md](UX_QUALITY_REPORT.md) is the current receipt and exclusions
record; [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) has exact paired tokens and
[TASTE_REVIEW.md](TASTE_REVIEW.md) records the six intentional font advisories,
not a repository-wide zero-warning claim. The isolated mock preview was left
at `http://127.0.0.1:5194`, with no environment-file loading/live API access;
the user's `5173`/`8000` services were untouched. Ignored local artifacts are
not portable; essential results are reproduced here.

## Historical Studio Redesign (2026-09-12)

The following studio scope, cancellation note and 744-test verdict are the
prior stage, not the renewed pitch-black audit above.

Scope: public site, authentication, shared shell and controls, study creation
and management, personas, the five-step workflow, evidence, segments,
interviews, behavioral tests, and developer routing diagnostics. Backend,
model, provider, database and security-policy changes were not part of this
design pass. Existing concurrent modernization work was preserved.

The requested UI/UX Pro Max search was narrowed from an irrelevant academic
site match to SaaS productivity. Its useful recommendations were a readable
self-hosted font, flat hierarchy, fast interactions and explicit state. Taste
guidance was applied to the public site; Impeccable's Operate guidance was used
for the research workspace. Earlier independent implementation, code and
browser reviews informed the fixes. The final continuation ran locally without
new cloud-agent delegation after the user canceled that operation.

| Finding | Resolution | Evidence |
| --- | --- | --- |
| Low-contrast secondary text and white text on bright teal | Opaque paired text tokens and a distinct accent-surface text token | [Theme regressions](../apps/frontend/tests/StudioTheme.test.ts) |
| Long, repetitive public-page story | Seven purposeful sections, visible product identity, actual sample workspace image, working navigation and FAQ | [Public-site regressions](../apps/frontend/tests/StudioLanding.test.tsx) |
| Changing study type submitted the entered idea | Native radios select only; explicit Start submits | [Study regressions](../apps/frontend/tests/StudioStudies.test.tsx) |
| Deletion lacked a safe confirmation/recovery path | Confirmation, cancel, busy/error handling and retained rows on failure | [Study regressions](../apps/frontend/tests/StudioStudies.test.tsx) |
| Persona inspector overflow and incomplete structured provenance | Responsive header/actions, wrapping tabs, complete source values and identifiers | [Persona regressions](../apps/frontend/tests/StudioPersonas.test.tsx) |
| Library-to-evidence navigation lost the selected study | The library selection is passed to the canonical study URL | [Shell regressions](../apps/frontend/tests/ConsoleShell.test.tsx) |
| Chat bubbles lacked consistent author/log semantics and accent contrast | Named logs/messages and accent-surface text; accessible send controls | [Step 1](../apps/frontend/src/components/dashboard/views/workflow/Step1Context.tsx), [Step 4](../apps/frontend/src/components/dashboard/views/workflow/Step4Interviews.tsx) |
| Step 3 actions clipped on narrow phones | Wrapping action row with reachable Start interviews | Exact 375px and 390px browser captures |
| Root-launched preview omitted Tailwind utilities | Configuration and content resolution anchored to the frontend directory | [PostCSS configuration](../apps/frontend/postcss.config.js), rendered evidence/segment grids |
| Failed reports stranded users or confused operations | Separate load/generation/copy recovery; saved versions and read-only permissions retained | [Report view](../apps/frontend/src/components/dashboard/views/workflow/Step5Report.tsx) |
| Inconsistent model-score units | Shared validated percentage formatter; unknown values are not fabricated | [Score regressions](../apps/frontend/tests/ReportScoreFormat.test.ts) |
| Long routing metadata overflowed or lost text | Shrinkable columns and full wrapping in collapsed/expanded traces | [Routing regressions](../apps/frontend/tests/RoutingProvenance.test.tsx) |
| Dialog focus trap included hidden/negative-tab-index controls | Explicit tabbability filtering and suspended lower-layer handlers | [Dialog regressions](../apps/frontend/tests/DialogA11y.test.tsx), 76 fresh browser checks |
| Decorative side borders and layout-property transitions | Divided risk/opportunity rows; four width transitions removed | Impeccable confirmation: only six font advisories remain |

Final verification: **744 tests in 64 files, zero failures/skips**, stable source
fingerprint throughout the run, TypeScript/Vite build passed, and theme drift
check reported zero files. See [UX_QUALITY_REPORT.md](UX_QUALITY_REPORT.md) for
browser coverage and exclusions, and [TASTE_REVIEW.md](TASTE_REVIEW.md) for the
deliberate visual decisions. This is a frontend verification result, not a
production-readiness or full accessibility certification.

## Historical Audit (2026-09-07)

The remaining sections preserve the earlier baseline. Their proposed work,
deferred items and line numbers describe September 7, not the current verdict.

Phase-0 audit of the console frontend (`apps/frontend/src`, ~40k lines) before the premium product-experience pass. Findings come from three parallel read-only reviews (entry/dashboard/personas · study workflow · interview/routing/behavioral) plus a live inspection of the running app in mock mode at 1440, 1024 and 390 px, both themes. Line references were accurate at audit time.

The redesign that followed is logged in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) (Maintenance 2026-09-07); the resulting system is specified in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) and scored in [UX_QUALITY_REPORT.md](UX_QUALITY_REPORT.md).

## 1. Current UX problems

| #   | Finding                                                                                                                                                                                                                 | Where                                | Severity       |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | -------------- |
| U1  | Navigation is a flat list of eight equal items. Nothing tells the user that Interviews / Behavioral Testing / Evidence / Segments are _inside a study_ while New Study / Dashboard / Persona Library / Routing are not. | `DashboardLayout.tsx` navItems       | High           |
| U2  | No "where am I" signal beyond the highlighted nav row: no breadcrumb, no active-study indicator. Opening a study-scoped tab without a study renders an empty state but the sidebar gives no hint why.                   | `DashboardLayout.tsx` header         | High           |
| U3  | Header above every non-workflow view is only a greeting ("Good morning, X") — the generic dashboard opener with zero information value.                                                                                 | `DashboardLayout.tsx` L1040–1060     | Medium         |
| U4  | No keyboard jump/command surface; every destination needs the mouse and the sidebar.                                                                                                                                    | shell                                | Medium         |
| U5  | Backend liveness is only visible as a bottom-centre banner when _down_; there is no always-on health signal.                                                                                                            | shell                                | Low            |
| U6  | Persona card actions: "Deep Dive Inspector" is a full-width heavy button; the two icon-only buttons beside it have `title` but no accessible name.                                                                      | `PersonaLibraryView.tsx` L1040–1080  | Medium         |
| U7  | Study-workflow stepper wraps to two rows at ≈1250 px and gives no "Step N of 5" readout when labels are hidden on small screens.                                                                                        | `StudyWorkflowView.tsx` stepper      | Medium         |
| U8  | Two `<main>` landmarks on the workflow route (shell + workflow).                                                                                                                                                        | `StudyWorkflowView.tsx`              | Low            |
| U9  | Kebab/row dual click targets on the study list (row is clickable, title is also a button).                                                                                                                              | `StudiesDashboardView.tsx` L307/L341 | Low (deferred) |
| U10 | Inspector modal with 8 tabs scrolls horizontally on phones; expanded evidence state is lost between tabs.                                                                                                               | `PersonaLibraryView.tsx` inspector   | Low (deferred) |

## 2. Current visual problems

| #   | Finding                                                                                                                                                                                                           | Evidence                                                                       |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| V1  | **No type scale.** 15+ distinct `fontSize` values in PersonaLibraryView alone (0.7, 0.72, 0.74, 0.75, 0.78, 0.8, 0.82, 0.84, 0.86, 0.88, 0.9, 0.92, 0.95, 1.05, 1.4, 1.85 rem).                                   | audit grep                                                                     |
| V2  | **No radius scale.** 4/5/6/8/10/12/14/16/18/20/22 px all in use.                                                                                                                                                  | audit grep                                                                     |
| V3  | The primary CTA gradient `linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)` is re-typed ≥10× and does not flip for light mode.                                                                                   | Step2Personas ×3, PersonaLibraryView ×2, DashboardLayout, StudyWorkflowView ×5 |
| V4  | Big Five trait hues (`#38BDF8 #F59E0B #A855F7 #EC4899`) and status ambers/reds (`#F59E0B`, `rgba(245,158,11,…)`, `rgba(239,68,68,…)`) are literals — invisible to the theme codemod and washed-out in light mode. | PersonaLibraryView ×11, Step4Interviews, DashboardLayout                       |
| V5  | Persona card hover shadow is a literal `0 8px 24px rgba(0,0,0,.4)` set from JS, duplicating what `.bx-lift` already does.                                                                                         | PersonaLibraryView L831                                                        |
| V6  | Four metric cards in a 3-column grid leave an orphan card (a "Total X" dashboard pattern).                                                                                                                        | PersonaLibraryView metrics                                                     |
| V7  | Sidebar section label ("RECENT STUDIES") is styled differently from everything else in the rail.                                                                                                                  | DashboardLayout                                                                |

What is **good** and was preserved: the teal/cyan token system with a light theme and a codemod drift gate; the Liquid Glass chrome material; the editorial Studies dashboard; NewStudyView's guided composer; `ProvenanceChip`/`EvidenceBadge`/`TemplateBadge`; `RequestIdTag`; `MemoryDisclosure`/`RouteDisclosure`; the honest `—` for unmeasured numbers; CountUp; shape-true skeletons whose count equals the selected role counts; step gating; `useDialogA11y`.

## 3. Workflow problems

- W1 — Returning users cannot get back into the study they were working in without scanning "Recent Studies"; there is no current-study affordance.
- W2 — Study-scoped tabs opened cold say "No study selected" but did not explain _why_ studies matter or which objects belong to one.
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

| #   | Finding                                                                          | Fix status                                  |
| --- | -------------------------------------------------------------------------------- | ------------------------------------------- |
| A1  | No skip link; ~20 tab stops before content.                                      | Fixed (`Skip to main content` → `#bx-main`) |
| A2  | Icon-only Interview / Behavior buttons on persona cards have no accessible name. | Fixed (`aria-label` with persona name)      |
| A3  | Primary nav uses colour + weight for the active item; no `aria-current`.         | Fixed (`aria-current="page"` + left rule)   |
| A4  | Two `<main>` landmarks on the workflow route.                                    | Fixed                                       |
| A5  | Big Five bars are colour-only glyphs with a `title`.                             | Fixed (`role="img"` + `aria-label`)         |
| A6  | Stepper buttons announce as "2 Personas".                                        | Fixed ("Step 2: Personas (done)")           |
| A7  | Chat bubbles in Step 1 / Step 4 are `<div>`s without roles.                      | Deferred                                    |
| A8  | Behavioral test-type cards are `div onClick`.                                    | Deferred (known, in repo memory)            |
| A9  | Backend health only visible as colour in some places.                            | Fixed (text pill, `role="status"`)          |

Already correct: dialog protocol (Escape stacking, focus trap, focus return), `role="alert"`/`role="status"` on errors/loaders, `role="log"` on the interview thread, `role="meter"`-style honest metrics.

## 6. Responsive problems

| #   | Finding                                                                                                 | Fix status                                              |
| --- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| R1  | Persona grid `minmax(350px, 1fr)` → single column at 1024 px content widths and overflow risk < 370 px. | Fixed (`minmax(min(320px,100%),1fr)`)                   |
| R2  | Metrics `minmax(220px,1fr)` → orphan 4th card.                                                          | Fixed (`minmax(min(190px,100%),1fr)`)                   |
| R3  | Stepper labels crowd at < 720 px.                                                                       | Fixed (numbers only + "Step N of 5")                    |
| R4  | Top-bar chrome truncates the breadcrumb when the greeting is present.                                   | Fixed (greeting hidden < 1280 px, trigger width capped) |
| R5  | Sidebar 240 px truncates "Routing & Provenance".                                                        | Fixed (256 px)                                          |

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
