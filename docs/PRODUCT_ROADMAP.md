# PropertyAIgent — Product Roadmap

Organised by **capability**, not by sprint — sprint-by-sprint history belongs to [ARCHITECTURE_STATUS_v2.md](ARCHITECTURE_STATUS_v2.md). This document answers "what's next and in what order," not "what happened when." For what each capability actually means, see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md); for the vision behind the ordering, see [PRODUCT_VISION.md](PRODUCT_VISION.md).

**Updated at the Product Vision & Roadmap Refresh (post–Opportunity Experience V2).** The capability stack below remains the right *dependency* order — Development Economics still cannot be built credibly ahead of Market Intelligence, for example — but this document no longer treats "next in the stack" as the same thing as "next thing to build." The Product Owner has explicitly paused further implementation to run **Phase 1 Opportunity Validation** first (see immediately below) and use its results as a genuine, evidence-based decision gate. The per-capability sections further down remain accurate, detailed reference material — current maturity, what's implemented, what's future, internal suggested order *within* a capability once it's chosen — but the old "Top-Level Sequencing Summary" that named Market Intelligence as the unconditional next major build has been replaced with the decision-gate structure below.

```
Planning Intelligence  →  Policy Intelligence  →  Market Intelligence  →
Development Economics  →  AI Decision Support  →  Workflow
```

---

## Completed / Current Platform

What exists today, in production, verified against the repository (see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) for full functional detail on each):

**Core planning intelligence** — planning application ingestion (10 Greater Manchester councils, multi-portal), planning-document intelligence, Site/entity consolidation, phase tracking, build status.

**Strategic land / Local Plan (LPDI)** — Local Plan and allocation intelligence; controlled, citation-verified evidence extraction; multi-plan attribution (Places for Everyone); Local Plan lifecycle/status handling; allocation extraction and AI Allocation Intelligence Summary (pilot-complete/accepted); numeric-scope and multi-section evidence safety; a real production remediation (a false Oldham housing-requirement figure, found and corrected through this programme's own safety gates).

**Allocation ↔ Site relationships** — `AllocationSiteRelationship` trust boundary; deterministic planning-activity/development-coverage arithmetic; false-match corroboration safety (the real Trafford Waters/Pomona case); deterministic strategic opportunity signal (`build_opportunity_signal`: INVESTIGATE/MONITOR/LOWER_PRIORITY/INSUFFICIENT_EVIDENCE, never a score).

**Opportunity product** — Site Selection & Reporting (Shortlist, CSV/PDF export, AI Executive Intelligence); Opportunity Experience V2 (unified Dashboard discovery feed across strategic-land and planning/delivery opportunities, restructured Opportunity Profile).

**Production deployment** — live at `propertyaigent.onrender.com`, on Render, deployed from `master`.

The platform has therefore reached: *planning intelligence → structured Local Plan/allocation intelligence → planning activity analysis → opportunity identification → opportunity discovery → opportunity investigation/profile → shortlist.* Local Plans, strategic allocations and opportunity identification are no longer future concepts in this document — they are shipped capability, referenced as such throughout the sections below.

## Current Validation Milestone — Phase 1 Opportunity Validation

**The Product Owner has explicitly decided not to start another implementation workstream yet.** The immediate next milestone is validation, not code.

**What:** Review approximately 10–15 genuine opportunities from the live platform, as a residential land professional actually would. For each, capture:

1. Would I investigate/pursue this?
2. Why or why not?
3. What evidence drove that judgement?
4. What information is missing?
5. What would I investigate next?
6. What would change my view?
7. Which existing Property AIgent signal was useful?
8. Which existing information was irrelevant/noisy?

**Why this, and why now:** This exercise serves two purposes at once. First, **product requirements** — identifying which missing intelligence most frequently blocks a useful acquisition decision, from real cases rather than assumption. Second, **Opportunity Analyst requirements discovery** — capturing real professional reasoning patterns (evidence → judgement → next investigation) before designing an agent to reproduce them. The Opportunity Analyst (see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7) is **not** built before this exercise runs, precisely so its design is grounded in real reasoning rather than an assumed one.

### Validation hypotheses (to test, not to pre-select)

Wharfside — the first opportunity reviewed under Opportunity Experience V2 (Trafford AN1, INVESTIGATE, 145 ha, 8,400 plan-period / 15,000 wider capacity, no identified planning activity, ownership/control unknown) — already generated one real product question: *"When can these units actually be delivered from?"* This is recorded as a **hypothesis to test across the full validation sample, not a conclusion to build against from one case:**

- **Delivery timing / phasing** may be a high-value missing intelligence dimension.
- **Ownership / control** may repeatedly block assessment of otherwise-attractive opportunities.
- **Infrastructure / dependencies** (e.g. what has to happen before a strategic allocation can actually deliver) may repeatedly matter.
- **Allocation certainty** (how likely is this allocation to survive to adoption unchanged) may repeatedly matter for emerging-plan opportunities.
- **Planning history** context (e.g. has this site been through a refused application before) may repeatedly change the read on an opportunity.
- **Market context** may repeatedly be the missing piece even at a purely "is this worth investigating" stage, not just at Phase 2's deeper appraisal stage.
- **Developer control** (who already controls how much of a large allocation) may repeatedly determine whether there's anything left to acquire.
- **Accessibility / contactability** (can the right party actually be reached) may repeatedly be the practical blocker, independent of how good the opportunity looks on paper.

None of these is promoted into a build decision here. The validation exercise either confirms a hypothesis repeats across the sample, or shows it doesn't — and the decision gate below acts on what actually repeats.

## Roadmap Decision Gate

The next implementation workstream is chosen **after** Phase 1 Opportunity Validation, by what the validation evidence actually shows — not predetermined here. Candidates, none pre-selected as the winner:

| Next workstream | Chosen if validation shows… |
|---|---|
| Delivery / Phasing Intelligence | Delivery timing repeatedly blocks decision-making |
| Ownership & Control Intelligence | Attractive opportunities repeatedly can't be assessed because control/ownership is unclear |
| Strategic Land Intelligence V2 | Allocations alone prove too narrow/late, and policy-led (unallocated) opportunities are needed |
| Opportunity Analyst V1 | The underlying intelligence is already rich enough that the primary remaining burden is interpreting it |
| Buyer Profiles + Deterministic Fit V1 | Opportunities are individually understandable, but buyer suitability becomes the key unmet need |
| Opportunity Discovery/Search V3 | Users can understand opportunities individually but can't efficiently discover/compare them at scale |

This is a genuine decision gate, not a formality — if the validation sample shows a different, unlisted gap most often, that gap is what gets built next, not whichever of the above looks most appealing in the abstract.

**Factual update, post-refresh (Product Owner decision, recorded here without rewriting the gate structure above):** "Buyer Profiles + Deterministic Fit V1" was subsequently chosen and implemented - four pilot profiles (Nesten Homes, Strategic Land Buyer, National Housebuilder, Housing Association), deterministic `assess_buyer_fit` (`STRONG_FIT`/`NOT_SUITABLE`/`INSUFFICIENT_EVIDENCE` + an orthogonal investigative-exception flag, no LLM, no numeric score), and a personalised Dashboard/Opportunity Profile feed built on the widened-candidate-pool architecture described in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7 - merged to master (commit `0d1b564`). A follow-on **Gate 1: Acquisition Monitoring Substrate** has since been implemented on a feature branch (Workspace ownership boundary, persistent Buyer Profiles, stable opportunity identity, deterministic opportunity fingerprinting/change detection, and a buyer onboarding baseline) as the prerequisite substrate for a future Selective Acquisition Agent (Opportunity Analyst / Buyer Analyst, §7 below) - **awaiting Product Owner review, not yet merged or deployed.** The Opportunity Analyst/Buyer Analyst agentic capabilities themselves remain unbuilt; see §7's own status table.

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

**Current maturity:** Mature for the councils it covers; narrow in national scope. Its AI reasoning capability is expanding beyond plan-level summaries into allocation-level and (planned) delivery-level intelligence — see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2 "Intelligence Hierarchy" for the full picture.

**Implemented functionality:** `LocalPlan`/`LocalPlanSite` model with status, evidence and progression tracking; joint-plan support (Places for Everyone); allocation-to-allocation relationships; change-protected ingestion and monitoring; policy document coverage tracking; AI Local Plan Summary; visual evidence extraction and deterministic allocation matching; `AllocationSiteRelationship` (Allocation↔Site trust boundary) and `ControlRelationship` (Site/Application-scoped ownership evidence). Bury and Stockport have their own Local Plans onboarded; all 9 Places for Everyone authorities have their PfE allocations onboarded.

**Pilot complete / accepted:** AI Allocation Intelligence Summary — implemented, tested, merged to master through a nine-cycle reliability-hardening sequence (V1–V9), and run against real production evidence across all eligible allocations. Accepted by the Product Owner as pilot-complete, with a small set of known, documented limitations that remain deliberately unresolved for this pilot (compound/joint applicant names, title-variant duplicate applicant names, and a narrow self-reported site-scope quote-style mismatch — see `specifications/010-allocation-intelligence-v9-final-pilot-reliability.md` for the full closure statement).

**Built since that pilot gate, in sequence:** Numeric-scope/multi-section evidence safety and a real production remediation (a false Oldham housing-requirement figure); allocation ↔ Site/Application planning-activity coverage and the deterministic strategic opportunity signal (`build_opportunity_signal`); **Allocated/Emerging Site Selection + Reporting** (Shortlist, CSV/PDF export, AI Executive Intelligence — `specifications/011` through `specifications/016`, all pilot-complete); **Opportunity Experience V2** (the unified Dashboard discovery feed and Opportunity Profile — see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2 "Opportunity Intelligence"). This is what the Product Owner's current **Phase 1 Opportunity Validation** milestone (top of this document) is now validating against real opportunities, before any further Policy Intelligence workstream is chosen.

**Future functionality:** NPPF and national Planning Practice Guidance as a versioned policy layer, positioned as part of the platform's planning-reasoning framework rather than a standalone information feature (see `PLATFORM_ARCHITECTURE.md` §2, "Opportunity Intelligence"); Supplementary Planning Documents and Design Codes as monitored document types; appeal decisions linked to the policy they tested; independent Local Plan monitoring for the 8 GM authorities currently known only through Places for Everyone (corrected from 7 by Pilot Readiness PR-2's PfE authority-membership fix — see `docs/PLATFORM_ARCHITECTURE.md` §2); **Local Plan Delivery Intelligence** (Intelligence Hierarchy Level 4 — aggregate Application→Site→Allocation evidence to Local Plan/Council level; see `PLATFORM_ARCHITECTURE.md` §2 for the full deterministic-metrics list); **Housing Supply Pressure Intelligence** (a later enhancement combining Delivery Intelligence with AMR/housing-trajectory/five-year-supply evidence, not an immediate requirement); the **Opportunity Analyst** (agentic reasoning over this layer's own evidence — see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7).

**Dependencies:** Planning Intelligence's Site records, for the eventual Allocation↔Site match (not a hard blocker — an allocation is real evidence on its own).

**Suggested implementation order (superseded — see the Roadmap Decision Gate at the top of this document):** the numbered list below predates Opportunity Experience V2 and the Product Owner's decision to validate before choosing the next workstream; it is kept as historical context for the reasoning that led here, not as a live plan. Item 1 is now built; items 2 onward remain candidates the decision gate may or may not select.
1. ~~Allocated/Emerging Site Selection + Reporting~~ — **built** (see above).
2. Local Plan Delivery Intelligence — the logical next intelligence layer once Site Selection + Reporting exists, reusing the same evidence-grounded AI architecture at Council/Local Plan aggregate level, and doubling as an enabling capability for AI-assisted Opportunity Discovery (see `PLATFORM_ARCHITECTURE.md` §2).
3. Independent Local Plan monitoring for the remaining 8 Greater Manchester authorities — closes the biggest known coverage gap using patterns that already exist (Bury/Stockport are the proof of concept).
4. Supplementary Planning Documents and Design Codes — natural extension of the existing document-coverage/monitoring machinery.
5. NPPF / national PPG as a versioned reference layer — needed before AI Decision Support (or a future Planning Potential assessment) can honestly cite national policy, not just local policy.
6. Appeal decisions.
7. Housing Supply Pressure Intelligence — sits after Local Plan Delivery Intelligence, as a supporting later capability, not a precondition for it.

Beyond this list, Opportunity Intelligence (Intelligence Hierarchy Level 5, `PLATFORM_ARCHITECTURE.md` §2) is now **partially built** — see "Built since that pilot gate" above. What remains genuinely future within it — AI-assisted natural-language Opportunity Discovery, the Opportunity Analyst, Planning Potential / Opportunity Potential reasoning, then the Buyer Analyst — is recorded in full in `PLATFORM_ARCHITECTURE.md` §2 and §7, but none of it is scheduled work, and nothing in this section is permission to start building any of it now; the Roadmap Decision Gate at the top of this document governs that.

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

**Dependencies:** Planning Intelligence, Policy Intelligence, Market Intelligence and Development Economics, in that order. Every output here must cite evidence the layers beneath it already established. Note: "Opportunity Intelligence" (Intelligence Hierarchy Level 5, `PLATFORM_ARCHITECTURE.md` §2 — the strategic destination Policy Intelligence's allocation/delivery evidence is eventually building toward) is not a shortcut into this capability; the full pursue/don't-pursue and investment-recommendation outputs below still require Market Intelligence and Development Economics, unchanged.

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

## Phase 1 Remaining Capabilities

Candidates the Roadmap Decision Gate chooses between — **not** a committed sequence. Each is a live option only if Phase 1 Opportunity Validation shows it's the real blocker:

- Delivery / Phasing Intelligence
- Ownership & Control Intelligence (deeper than today's Site/Application-scoped `ControlRelationship`)
- Local Plan Delivery Intelligence (Intelligence Hierarchy Level 4)
- Strategic Land Intelligence V2 (policy-led/unallocated opportunities, spatial strategy, Green Belt change, evidence-base documents — see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2)
- Independent Local Plan monitoring for the remaining 8 Greater Manchester authorities
- Opportunity Discovery/Search V3 (a genuine cross-type "all opportunities" browse experience, and allocation-aware global search — both identified but deferred by Opportunity Experience V2's own final report)
- NPPF as a versioned reference layer

## Phase 1.5 — Buyer-Fit

Sequenced after Phase 1 opportunities are individually well understood, not before:

- ~~Structured Buyer Profiles~~ (geography, scale, planning-risk appetite, development type, tenure, delivery horizon, brownfield/greenfield preference) - **implemented as Buyer Profiles V1** (four pilot profiles; unit/affordable-unit scale, planning appetite, development-type and wholly-affordable exclusion polarity - geography/tenure/brownfield-greenfield preference were explicitly out of scope for the pilot and remain future work)
- ~~Deterministic buyer-fit logic against those profiles~~ - **implemented** (`app.policy.buyer_matching.assess_buyer_fit`)
- Buyer Profiles are now **persistent and Workspace-owned** (Gate 1: Acquisition Monitoring Substrate, feature branch, awaiting Product Owner review) rather than code/config-only, as the substrate for a future selective agent
- **Opportunity Analyst V1**, if validation shows the underlying intelligence is already rich enough that interpretation is the main remaining burden - **not yet built**
- **Buyer Analyst V1**, once deterministic fit exists to interpret — never before it, and never as an opaque LLM-generated score - deterministic fit now exists (above); the agentic interpretation layer itself is **not yet built**

## Phase 2 — Market, Comparables & Investment Intelligence

Deliberately does not move forward regardless of how promising agentic reasoning looks elsewhere — this depends on real, licensed market data existing first:

```
Legitimate market/comparable data source
        ↓
Structured comparable evidence
        ↓
Deterministic matching/calculation (£/sq ft, GDV, cost assumptions)
        ↓
Residual land value / development appraisal
        ↓
Market & Investment Analyst (agentic interpretation)
```

An LLM browsing public listing/portal sites for pricing is explicitly **not** an acceptable substitute for a legitimate structured data source (Land Registry Price Paid Data, a licensed comparables provider) — see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §3/§4/§7. Market Intelligence and Development Economics remain firmly Phase 2 unless a future validation exercise produces compelling evidence otherwise; agent enthusiasm is not that evidence.

## Longer Term

A continuous agent-assisted acquisition workflow: the platform surfaces opportunities on an ongoing basis (conceptually, "12 opportunities identified for you this week" — see [PRODUCT_VISION.md](PRODUCT_VISION.md), "Long-Term Ambition"), each already carrying reasons, evidence, planning status, strategic-land context, monitoring changes, buyer fit and recommended next investigations — with search and the underlying Site/Application/allocation database as essential, no-longer-primary infrastructure beneath it. Not designed, not scheduled — recorded as direction only.

## Product Maturity Map

Maturity is reported against real repository evidence, not against whether a function or model exists — a function existing is not the same as a capability being built to a standard a user actually relies on.

| Capability | Maturity | Phase | Notes |
|---|---|---|---|
| Planning applications | **Built** | 1 | 10-council multi-portal scraping, in continuous production use |
| Planning document intelligence | **Built** | 1 | AI-assisted extraction/reconciliation, schema-validated |
| Site/entity consolidation | **Built** | 1 | Tiered, confidence-scored Application→Site linking |
| Local Plan intelligence | **Built to strong V1** | 1 | LPDI programme; joint-plan support; change-protected monitoring |
| Controlled evidence extraction | **Built** | 1 | Citation verification, numeric-scope safety, real production remediation proven |
| Allocation intelligence | **Built to V1** | 1 | AI Allocation Intelligence Summary, pilot-complete/accepted, known limitations documented |
| Planning activity coverage | **Built to V1** | 1 | Deterministic allocation↔Site/Application coverage arithmetic |
| Strategic opportunity identification | **Built to V1** | 1 | `build_opportunity_signal` — INVESTIGATE/MONITOR/LOWER_PRIORITY/INSUFFICIENT_EVIDENCE, no score |
| Opportunity discovery | **Built** | 1 | Opportunity Experience V2 — unified Dashboard feed |
| Opportunity Profile | **Built** | 1 | Restructured around why/evidence/unknowns, ahead of detailed investigation |
| Shortlist | **Built** | 1 | Session-scoped selection → CSV/PDF report, AI Executive Intelligence |
| Delivery/phasing intelligence | **Not yet built** | 1 (candidate) | Validation hypothesis, not yet confirmed as the priority |
| Ownership/control intelligence | **Foundation exists** | 1 (candidate) | `ControlRelationship` is Site/Application-scoped; no title/registry resolution |
| Monitoring | **Foundation exists** | 1 (candidate) | Deterministic source/content-change detection exists for policy; no opportunity-level "does this change matter" reasoning |
| NPPF/policy-led opportunity intelligence | **Not yet built** | 1 (candidate) / 1.5 | Only `buffer_percentage` exists today; no versioned national-policy layer |
| Buyer profiles | **Not yet built** | 1.5 | Conceptually scoped ([PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7); not designed |
| Buyer fit | **Not yet built** | 1.5 | Depends on buyer profiles existing first |
| Opportunity Analyst | **Not yet built** | 1.5 | Depends on Phase 1 Opportunity Validation's findings; not built ahead of it |
| Planning due diligence | **Not yet built** | 1.5 | A deeper mode of the Opportunity Analyst, not a separate agent |
| Market/comparables | **Not started** | 2 | No sales, rental or comparable data flows into the platform today |
| Development appraisal | **Not started** | 2 | Hard-blocked on Market Intelligence existing first |
| Market/Investment Analyst | **Not started** | 2 | Depends on structured market evidence + deterministic appraisal existing first |
