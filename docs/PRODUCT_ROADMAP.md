# PropertyAIgent — Product Roadmap

Organised by **capability**, not by sprint — sprint-by-sprint history belongs to [ARCHITECTURE_STATUS_v2.md](ARCHITECTURE_STATUS_v2.md). This document answers "what's next and in what order," not "what happened when." For what each capability actually means, see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md); for the vision behind the ordering, see [PRODUCT_VISION.md](PRODUCT_VISION.md).

The roadmap follows the platform's capability stack, and the stack's dependency order **is** the suggested implementation order at the top level:

```
Planning Intelligence  →  Policy Intelligence  →  Market Intelligence  →
Development Economics  →  AI Decision Support  →  Workflow
```

Each capability section below gives its own internal suggested order too, since "build Market Intelligence" is itself several separable pieces of work.

---

## 1. Planning Intelligence

**Current maturity:** Mature. This is the platform's most-built-out layer, in continuous production use across 10 councils.

**Implemented functionality:** Multi-portal scraping (Idox, Idox+Anite, Arcus), unit-count qualification filtering, AI-assisted scheme extraction and reconciliation, site consolidation (application → Site linking), phase tracking, build-status via EPC lookups, map geocoding, on-demand Companies House/Apollo/Hunter enrichment.

**Future functionality:** Appeals history; constraint layers (Green Belt, flood risk, conservation areas, listed buildings, biodiversity) as structured, queryable data rather than narrative; portal-native commencement/discharge-of-conditions as a second build-status signal; national rollout beyond Greater Manchester.

**Dependencies:** None — the foundation layer.

**Suggested implementation order:**
1. Constraint layers (Green Belt / flood risk / conservation areas) — highest leverage, since Development Economics will eventually need these as cost/risk inputs.
2. Appeals history.
3. Second build-status signal (commencement/discharge-of-conditions).
4. National rollout (an expansion of existing capability, not new capability — lowest technical risk, but largest scope).

---

## 2. Policy Intelligence

**Current maturity:** Mature for the councils it covers; narrow in national scope.

**Implemented functionality:** `LocalPlan`/`LocalPlanSite` model with status, evidence and progression tracking; joint-plan support (Places for Everyone); allocation-to-allocation relationships; change-protected ingestion and monitoring; policy document coverage tracking; AI Local Plan Summary; visual evidence extraction and deterministic allocation matching. Bury and Stockport have their own Local Plans onboarded; all 9 Places for Everyone authorities have their PfE allocations onboarded.

**Future functionality:** NPPF and national Planning Practice Guidance as a versioned policy layer; Supplementary Planning Documents and Design Codes as monitored document types; appeal decisions linked to the policy they tested; independent Local Plan monitoring for the 7 GM authorities currently known only through Places for Everyone.

**Dependencies:** Planning Intelligence's Site records, for the eventual Allocation↔Site match (not a hard blocker — an allocation is real evidence on its own).

**Suggested implementation order:**
1. Independent Local Plan monitoring for the remaining 7 Greater Manchester authorities — closes the biggest known coverage gap using patterns that already exist (Bury/Stockport are the proof of concept).
2. Supplementary Planning Documents and Design Codes — natural extension of the existing document-coverage/monitoring machinery.
3. NPPF / national PPG as a versioned reference layer — needed before AI Decision Support can honestly cite national policy, not just local policy.
4. Appeal decisions.

---

## 3. Market Intelligence

**Current maturity:** Not started.

**Implemented functionality:** None.

**Future functionality:** Residential and commercial sales values; Land Registry Price Paid Data; new-build values and premiums; rental evidence; sales rates/absorption; development comparables; land values; build costs and regional cost adjustments; Ownership Intelligence (registered land/title ownership research — see `docs/PLATFORM_ARCHITECTURE.md` §3 for the full architecture note; blocked on reliable Site/allocation geometry, so deliberately not placed in the implementation order below).

**Dependencies:** Planning Intelligence (what exists nearby to compare against) and Policy Intelligence (what a Site is actually allocated/permitted for, which determines relevant comparables).

**Suggested implementation order:**
1. Land Registry Price Paid Data — free, structured, and the fastest route to real land-value and disposal comparables.
2. Development comparables (nearby, genuinely similar schemes already visible through Planning Intelligence) — reuses existing Site data before any new external source is integrated.
3. New-build sales values and rental evidence — likely the first genuinely new paid data source the platform integrates.
4. Sales rates / absorption and regional build-cost adjustments — the most synthesis-heavy pieces, best built once the raw values above already exist to derive them from.

This is the platform's **next major build** after closing the remaining Policy Intelligence coverage gaps — it is the direct blocker for Development Economics, which cannot be built credibly without it.

---

## 4. Development Economics

**Current maturity:** Not started.

**Implemented functionality:** None.

**Future functionality:** Residual appraisal, GDV, developer profit, sensitivity analysis; planning obligations modelling (CIL, Section 106, affordable housing, BNG, education/highways/open-space/monitoring contributions); full viability assessments.

**Dependencies:** Planning Intelligence + Policy Intelligence + Market Intelligence, all three together. **This capability must never be built or scoped ahead of Market Intelligence** — a residual appraisal without real values and costs behind it is not a smaller version of this capability, it is not this capability at all.

**Suggested implementation order:**
1. Planning obligations modelling (CIL/S106/affordable housing) — can start as soon as Policy Intelligence's obligation data exists, and is independently useful before a full appraisal engine exists.
2. Basic residual appraisal (GDV − costs − profit → residual land value) — the first point at which Market Intelligence's values/costs and Policy Intelligence's obligations combine into a single output.
3. Sensitivity analysis on top of the basic appraisal.
4. Full viability assessment output, formatted to mirror a real viability report.

---

## 5. AI Decision Support

**Current maturity:** Embryonic — narrow, production-proven instances exist; the full synthesis layer does not.

**Implemented functionality:** AI Local Plan Summary (evidence-gated narrative synthesis); AI scheme status summaries; AI visual classification (bounded to a fixed type vocabulary, never used for matching).

**Future functionality:** Planning assessments and planning balance; planning strategy, planning statements and supporting statements; executive reports; Call for Sites submissions; site promotion documents; pursue/don't-pursue recommendations.

**Dependencies:** Planning Intelligence, Policy Intelligence, Market Intelligence and Development Economics, in that order. Every output here must cite evidence the layers beneath it already established.

**Suggested implementation order:**
1. Planning assessment / planning balance narrative — needs only Planning + Policy Intelligence, so it can start before Market Intelligence/Development Economics are complete, as long as it's scoped to planning judgement only (not viability).
2. Executive/summary reports that stitch together whatever layers exist at the time — inherently incremental, gets more complete as later layers land.
3. Planning statements / supporting statements — needs the planning-assessment narrative above as its foundation.
4. Full investment/pursue recommendations and site promotion documents — the highest-synthesis outputs, sequenced last since they need all four evidence layers to be credible.

---

## 6. Workflow & Collaboration

**Current maturity:** Not started (as a customer-facing layer).

**Implemented functionality:** None. (The platform's internal ambiguous-fact review workflow is a data-quality mechanism, not this capability — see [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md).)

**Future functionality:** Saved sites and watchlists; lightweight CRM over existing company/contact data; task tracking; client reporting; team collaboration.

**Dependencies:** Every layer above it — there is nothing to save, watch, or report on without real Site intelligence already existing.

**Suggested implementation order:**
1. Saved sites / watchlists — the simplest, lowest-dependency piece, usable the moment any Site intelligence exists.
2. Lightweight CRM — reuses Planning Intelligence's already-discovered companies/contacts.
3. Task tracking against a Site.
4. Client reporting and team collaboration — the most product-surface-heavy pieces, appropriately sequenced last.

---

## Top-Level Sequencing Summary

| Order | Capability | Status |
|---|---|---|
| 1 | Planning Intelligence | Mature, in production |
| 2 | Policy Intelligence | Mature for covered councils, gaps in national scope |
| 3 | Market Intelligence | **Next major build** |
| 4 | Development Economics | Blocked on Market Intelligence |
| 5 | AI Decision Support | Embryonic; full synthesis blocked on 3 and 4 |
| 6 | Workflow & Collaboration | Not started; deliberately last |
