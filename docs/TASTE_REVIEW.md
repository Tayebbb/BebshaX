# BebshaX Taste Review (2026-09-07)

Final creative-direction pass on top of the premium UX transformation ([UX_QUALITY_REPORT.md](UX_QUALITY_REPORT.md)). Method: run the app in mock mode, look at every route at 1440 and 390 px in both themes, then apply the ten passes (architecture, hierarchy, interaction, content, responsive, accessibility, motion, performance, subtraction, final taste). The design-taste rulebook used for the landing page (eyebrow restraint, hero stack discipline, dash ban, tell inventory) was applied to the console only as a critique lens: the console is product UI, which that rulebook explicitly scopes out.

Design read: _redesign-preserve of a dense research console plus its marketing landing, for judges and researchers, calm / editorial / technically credible, existing teal token system, dials 5 / 3 / 5._

## What was weak

1. **Landing page rhythm was templated.** Every one of 14 sections opened with the same uppercase pill eyebrow ("The Console", "Core Capabilities", "What This Means For You", "Transparent Pricing ✨"). Twelve eyebrows on fourteen sections is the single most recognisable AI-built-page signature. Two sections used the identical eyebrow text.
2. **The hero carried too much.** Two stacked labels, a 50-word lede, and an animated scroll-cue mouse at the fold. The value proposition was buried under its own supporting copy.
3. **Em-dashes everywhere.** 22 in visible landing copy, doing the work that sentences should do.
4. **Persona Library opened as a metrics dashboard**, not a research library: four icon-in-a-box metric cards, a boxed filter bar, a jargon "Synthetic Agents" chip beside the title, and cards carrying seven chip styles (BD flag, version, CACHED, segment, "Synthetic Persona", origin country, sparkle-prefixed tagline) plus a boxed uppercase "BIG FIVE TRAITS" panel and a button labelled "Deep Dive Inspector".
5. **Routing & Provenance buried its own story.** Two marketing-flavoured "architecture" cards ("Operational Budget: Zero API Cost (Free Tier Aggregation)") sat at the top; the provenance traces, which are the product's technical differentiator, were the last section on the page. Every section was a box containing boxes, health dots glowed neon, and the two static cards repeated the same "architecture, not live status" disclaimer.
6. **Colour still carried meaning alone in places** (health dots, trait glyphs), and a few literals (`#F59E0B`, `rgba(239,68,68,…)`) survived the token sweep.

## What was changed

- **Landing hero:** one category label, three-line headline, a 17-word lede ("Pressure-test your idea against realistic customers in minutes, and see exactly where every answer came from."), one CTA, three grounding figures. Scroll cue removed.
- **Landing eyebrows:** 12 → 3 (hero label, "Five Guided Steps", "The Routing Layer"). Pricing headline rewritten from "Scale Synthetic Customer Research with Confidence" to "Pricing that starts at nothing". The "Step 01 in Action" sub-label was cut.
- **Landing copy:** all 22 em-dashes rewritten as periods, colons, commas or parentheses; two number ranges use a plain hyphen or "to".
- **Persona Library:** title without chip; metric cards → a typographic figure row (`<dl>`, numbers separated by hairlines, "1 of 1" instead of "1 / 1"); filter bar unboxed to a hairline; card tagline becomes an italic lead sentence; Big Five strip unboxed with a sentence-case label; BD flag chip removed (origin country already shown); primary action renamed "Open profile".
- **Routing & Provenance:** the two architecture cards became one quiet definition list under a single "architecture, not live status" label; provenance traces moved to the first section; health, pools and traces are hairline sections rather than boxes; health/pool cards use the standard card material; status dots are flat and paired with text; every literal colour is a token.
- **Persona cards, Step 4 pills, shell notices:** remaining literal ambers/reds/blues → status and trait tokens (light mode now gets darker, readable variants).

## What was removed

- 9 eyebrow pills and 1 sparkle icon (landing).
- Hero pill "Runs on free provider tiers, zero API keys required to start" (the claim is already the third hero figure and a TrustMetrics card).
- Scroll cue and its CSS.
- "Synthetic Agents" header chip, "BD" country chip, sparkle tagline icon, boxed Big Five panel, boxed filter bar, four icon metric boxes (Persona Library).
- Two "architecture" cards, one duplicated disclaimer, neon dot glow, section-level boxes (Routing & Provenance).

Net: landing chunk 198.7 → 194.5 kB, dashboard chunk 469.6 → 464.3 kB.

## What was redesigned

- Landing hero composition and section rhythm.
- Persona Library summary strip and persona card typography.
- Routing & Provenance page order and section architecture.

Kept deliberately: the three grounding figures inside the hero (they are the hero's third beat in the parallax choreography and the numbers are honest), the "Synthetic Persona" chip on every card (a tested honesty marker), and every test-asserted string. Two test labels changed with the product copy ("Deep Dive Inspector" → "Open profile"; the architecture disclaimer now appears once).

## Design principles

1. **Headlines carry the category.** No eyebrow unless it says something the headline cannot. Maximum one per three sections.
2. **Numbers are typography, not furniture.** A figure row with hairlines beats a strip of icon cards; "1 of 3" reads, "1 / 3" is a fraction.
3. **The story goes first.** On any system page, the thing that makes BebshaX different (the request trace, the evidence chip, the memory recall) comes before status and configuration.
4. **Boxes mark independence, hairlines mark sections.** A section is never a card; a card never contains cards.
5. **Colour never speaks alone.** Every dot, bar and badge is paired with a word.
6. **Sentences, not dashes.** A pause that needs an em-dash is two sentences.
7. **Honesty beats polish.** Sample-data banners, "not measured", "architecture, not live status", and the read-only notice stay exactly as loud as they are.

## Remaining compromises

- **Em-dashes inside the console.** Several are test contracts ("Not evidence-backed — inferred from your description", "How routing works — architecture, not live status") and part of a consistent product voice; rewriting ~200 strings for a typographic rule would churn tests without changing meaning. New copy avoids them.
- **Persona card chip row** still has three chips (segment, "Synthetic Persona", origin). The honesty chip is tested and earns its place; the other two are one more subtraction pass away.
- **Persona inspector** keeps eight tabs; on phones they scroll horizontally. Regrouping into four sections is the next structural change.
- **Behavioral testing and Audience segments** were not touched in this pass and remain the two weakest screens (type cards as `div onClick`, likelihood colours as literals).
- **Landing hero stats** sit inside the hero rather than below it. Moving them would rebuild the parallax scroll engine for a rule whose intent (no clutter) the composition already meets.
- **Lucide** remains the icon family; swapping ~300 icon usages for Phosphor would be churn with no product benefit.

Gates at hand-off: `tsc` 0 · vitest 244/244 · `vite build` 0 · `theme:check` 0.
