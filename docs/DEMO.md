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

## 4. "Cached" vs. "Live" Data Transparency (Piece 2 Roadmap)

To maintain strict evaluation integrity and honesty:
- **`data_source: "cached"`**: Represents responses served directly from pre-seeded baseline fixtures or deterministic local mock pools.
- **`data_source: "live"`**: Represents live inference passes executed against routed LLM providers or local Ollama engines.

*(Note: Piece 2 UI badge integration is coordinated with Shehab).*
