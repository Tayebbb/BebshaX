# BebshaX Demo Mode Documentation (Phase 13 / H3)

This document describes the BebshaX Demo Mode, its configuration, seeded sample entities, and the upcoming data-source transparency labeling.

---

## 1. Overview

Demo Mode provides a deterministic, self-contained environment for showcasing BebshaX capabilities (synthetic persona generation, grounded interviews, research synthesis, and report generation) without requiring live external provider API calls or manual initial setup.

---

## 2. Configuration & Enabling Demo Mode

Demo Mode is controlled via the `BEBSHAX_DEMO_MODE` environment variable.

### In `.env` / Environment:
```bash
# Enable demo mode
BEBSHAX_DEMO_MODE=true
```

When `BEBSHAX_DEMO_MODE=false` (default in production and clean development), automatic demo data seeding is skipped on app startup.

---

## 3. Seeded Entities

When `BEBSHAX_DEMO_MODE=true` and the database is unpopulated (or when `seed_demo_data(sessionmaker, force=True)` is called), the following known-good baseline entities are seeded:

1. **Demo User:**
   - **Email:** `founder@bebshax.ai`
   - **Name:** `Sarah Chen`
   - **Role:** Founder / Study Author
   - **Auth Provider:** `email` (`is_verified=true`)

2. **Demo Business:**
   - **ID:** `biz_fintech_01`
   - **Name:** `Apex Courier Finance`
   - **Industry:** `Fintech & Gig Economy`
   - **Target Market:** `Urban delivery couriers & independent logistics contractors`
   - **Description:** Real-time earnings advance and micro-insurance platform for gig couriers.

3. **Grounded Personas & Evidence:**
   - **Persona:** `Tariq Ahmed (Delivery Fleet Lead)`
   - **Demographics:** Age 34, Dhaka & Chittagong logistics corridor
   - **Evidence Grounding:** Real courier survey excerpts and customer dialogue citations (`PersonaHub (Financial Segment)`, `EmpatheticDialogues`).

4. **Sample Studies & Conversation Logs:**
   - Sample interview sessions with pre-populated turn histories and provenance records.

---

## 4. "Cached" vs. "Live" Data Transparency

To maintain strict evaluation integrity and honesty:
- **`data_source: "cached"`**: Represents responses served directly from pre-seeded baseline fixtures or deterministic local mock pools.
- **`data_source: "live"`**: Represents live inference passes executed against routed LLM providers or local Ollama engines.

**Backend: implemented 2026-08-27.** `personas.data_source` (migration `9f0a1b2c3d4e`) is written at creation time and returned by every persona endpoint. `save_persona()` defaults to `"live"` — every caller but the seeder arrives after real inference — and `seed_demo_data()` passes `"cached"` explicitly.

The label is **stored, not derived**. Computing it from `demo_mode` at read time would be wrong: the flag flips independently of the rows already in the table, so a demo-mode toggle would silently relabel personas that a real model produced. Guarded by `tests/db/test_data_source_labelling.py` (4 tests), including one that fails if the seeder stops labelling.

**Frontend: outstanding, owned by Shehab.** The label reaches the API but nothing renders it yet, so a viewer still cannot tell seeded content from model output. H3's honesty requirement is met end to end only once a badge appears wherever personas are shown. Field semantics are frozen in [API_CONTRACT.md](API_CONTRACT.md).
