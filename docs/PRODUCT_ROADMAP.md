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

**Acquisition Monitoring Substrate** (Gate 1, Gate 1C, Gate 2A — all merged to master, all **CLOSED**) — Workspace ownership boundary; persistent Buyer Profiles and deterministic buyer fit; a stable, deterministic opportunity universe across five opportunity types (strategic land, long-pending application, recent permission, undeveloped permission, approaching lapse) with fingerprinting and change detection; entity-level, evidence-grounded Applicant Intelligence for planning-application-linked organisations, production-validated across the full eligible population. See "Acquisition-First Gate Sequence" below for what's next.

**Production deployment** — live at `propertyaigent.onrender.com`, on Render, deployed from `master`.

The platform has therefore reached: *planning intelligence → structured Local Plan/allocation intelligence → planning activity analysis → opportunity identification → opportunity discovery → opportunity investigation/profile → shortlist → buyer-matched, monitored, entity-enriched acquisition substrate.* Local Plans, strategic allocations, opportunity identification, buyer profiles/fit, opportunity monitoring and Applicant Intelligence are no longer future concepts in this document — they are shipped capability, referenced as such throughout the sections below. The platform's stated commercial outcome is now acquisition-first — see "The Acquisition-First Direction" below.

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

**Factual update, post-refresh (Product Owner decision, recorded here without rewriting the gate structure above):** "Buyer Profiles + Deterministic Fit V1" was subsequently chosen and implemented - four pilot profiles (Nesten Homes, Strategic Land Buyer, National Housebuilder, Housing Association), deterministic `assess_buyer_fit` (`STRONG_FIT`/`NOT_SUITABLE`/`INSUFFICIENT_EVIDENCE` + an orthogonal investigative-exception flag, no LLM, no numeric score), and a personalised Dashboard/Opportunity Profile feed built on the widened-candidate-pool architecture described in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7 - merged to master (commit `0d1b564`). This decision gate is now **resolved and superseded** by the Acquisition-First direction below: **Gate 1 (Acquisition Monitoring Substrate)**, **Gate 1C (Planning Opportunity Trigger Expansion)** and **Gate 2A (Applicant Intelligence V1)** have since all been implemented and merged to master, closing the substrate this decision gate was pointing toward. See "Acquisition-First Gate Sequence" below for what's built, what's next, and the Opportunity Analyst/Buyer Analyst agentic capabilities' own current status.

## The Acquisition-First Direction

*(Product Owner decision, Acquisition-First Roadmap Alignment.)* The commercial outcome this roadmap now serves is stated explicitly in [PRODUCT_VISION.md](PRODUCT_VISION.md), "The Acquisition-First Commercial Outcome": PropertyAIgent continuously turns fragmented planning, ownership and development evidence into ranked acquisition opportunities matched to a buyer's strategy. Planning intelligence — everything in the capability stack above and the sections below — remains the trusted evidence layer; it is no longer the end product. The **primary unit of product value is the qualified buyer-specific acquisition opportunity**, not the planning application or the search result. This does not discard anything already built — every gate below extends existing architecture (Buyer Profiles, the opportunity universe, Applicant Intelligence) rather than replacing it.

### Live Acquisition-Focused Product Review — findings behind Gate 2B

Recent acquisition-focused validation of the live platform found PropertyAIgent is currently **stronger at identifying planning activity than at identifying genuinely actionable acquisition opportunities**: scheme-level values can conflict across applications/phases/versions; proposed and approved units/affordable-housing figures can be mixed; planning statuses can go stale; an externally-approved scheme can still show as awaiting decision; a planning-fit site may already be committed to a developer; availability/control is materially less clear than planning status; current Explore filtering does not fully represent a real acquisition mandate; and Dashboard emphasis remains more data/coverage-oriented than acquisition-action-oriented. These findings are the direct evidence behind sequencing Gate 2B (Operative Scheme Intelligence) next.

## Acquisition-First Gate Sequence

### Completed Foundation

| Gate | Status | What it built |
|---|---|---|
| **Gate 1** — Acquisition Monitoring Substrate | **CLOSED** (merged to master) | Workspace ownership boundary; persistent, Workspace-owned Buyer Profiles (extending, not replacing, Buyer Profiles V1); stable opportunity identity (`app.reporting.opportunity_universe`); deterministic opportunity fingerprinting and change detection (`app.reporting.opportunity_change`: `BASELINE_EXISTING` / `NEW` / `MATERIALLY_CHANGED` / `UNCHANGED`); a buyer onboarding baseline. |
| **Gate 1C** — Planning Opportunity Trigger Expansion | **CLOSED** (merged to master) | Expanded the opportunity universe's planning/delivery detectors to `RECENT_PERMISSION` and `LONG_PENDING_APPLICATION`, alongside the existing `STRATEGIC_LAND`, `UNDEVELOPED_PERMISSION` and `APPROACHING_LAPSE` — five opportunity types, one deterministic universe, a standing weekly production cron. |
| **Gate 2A** — Applicant Intelligence V1 | **CLOSED** (merged to master; production bootstrap complete) | Entity-level, evidence-grounded organisation classification for planning-application-linked identities (see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2). **Production validation record:** full eligible population processed — 188 identities (170 organisation-shaped, 18 private-person-shaped); 169/170 organisations successfully classified, 1 in a safe, persistent validation-rejected state (not forced); all 18 private identities received deterministic no-web-research protection; zero duplicate identities; zero strategic-land-only research violations; live Applicant Intelligence UI verified in production; Opportunity Universe and Buyer Profiles unaffected. Known V1 limitations (parent/group completeness, confidence/evidence-ref linkage, source authority vs. claim support, source-type mistagging, backlog overfetch behaviour) are recorded in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2, not fixed as part of closing this gate. |

### Next

**Gate 2B — Trusted Opportunity Data.**

*(Product Owner decision, Gate 2B-0A closure: Gate 2B is a sequence of deliberately separate sub-gates, not one monolithic build. The freshness dimension (2B-0A) is now closed. The Product Owner has re-sequenced the remainder: **operative reconciliation (2B-1) takes priority over lifecycle history (2B-0B)** — 2B-0A already answers "has this known application changed?", but the more important unresolved commercial question is "which application, phase or proposal version actually defines the current acquisition opportunity?", repeatedly demonstrated as a real problem by the Astra live reviews. Lifecycle history is useful but does not help if the platform is tracking or presenting the wrong application as operative. None of the sub-gates below is Gate 2C, Buyer Mandate V2, or the Acquisition Agent — all of those remain sequenced strictly after Gate 2B closes. Numerical gate naming does not dictate implementation priority where the commercial dependency differs.)*

```
Council portals + planning documents
        ↓
2B-0A  Planning Freshness Infrastructure          CLOSED — re-verify a known application's own record
        ↓
2B-1   Scheme / Application / Phase Reconciliation  NEXT — which application/phase/version controls each scheme-level fact
        ↓
2B-2   Operative Scheme Facts / Evidence Resolution      — the resolved operative fact set, with provenance/confidence/conflicts
        ↓
2B-0B  Application Lifecycle History               LATER — richer previous→new transition history, where useful
        ↓
Trusted Opportunity Data
        ↓
Buyer / Acquisition Intelligence                   (Gate 2C onward, unchanged sequencing — see "After 2B")
        ↓
Monitoring Agent / Alerts                          (Weekly Planning/Acquisition Monitoring Agent — see "Later")
```

**2B-0A — Planning Freshness Infrastructure. CLOSED.** Implemented, deployed and production-validated through a bounded Oldham cohort. Direct status verification safely re-fetches eligible unresolved applications, records verification freshness and detects material application changes. Scheduled platform-wide activation remains operationally gated pending resolution/verification of the production daily-scrape scheduler. Rich lifecycle history and scheme-level reconciliation remain separate subsequent gates.

*Detail:* `Application.status_verified_at` (additive schema field), deterministic verification tiers (contradiction signal / long-pending opportunity / other opportunity / other pending) at 7/14/30/60-day cadence, a 10-per-council-per-run bound with a starvation-fairness reservation, and an extended (never rewritten) related-application-discovery eligibility. Deployed at `4b98b46` (web service verified on that commit); the status-verification stage is **fail-closed** — dormant in scheduled production until an operator sets `PLANNING_STATUS_VERIFICATION_ENABLED`, with `run_weekly --include-status-verification` for a single controlled run. Production validation record: one authorised Oldham cohort, 10 eligible applications selected by the real selector (1 Tier 1 + 9 Tier 2), all `VERIFIED_UNCHANGED`, `status_verified_at` correctly advanced, no planning facts fabricated, no false material-change event, no unintended downstream processing, only the authorised council touched, portal/circuit-breaker handling wired and test-covered. See [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md), "Planning Status Verification," and the Gate 2B-A investigation root-cause findings this closes (173 pending applications >6 months old with zero refresh activity; 100% of long_pending_application opportunities >90 days unverified). **Capability freshness verification is complete; the broader Application Lifecycle Intelligence vision is not — 2B-0A did not solve historical lifecycle transitions, operative scheme reconciliation, or buyer-facing change alerts.**

> **Operational activation dependency (not unfinished 2B-0A development).** Platform-wide scheduled verification (`PLANNING_STATUS_VERIFICATION_ENABLED=true`) must NOT be enabled until the production scheduled pipeline is separately proven healthy — the historical `propertyaigent-daily-scrape` run failure remains an unresolved operational issue, and adding a new workload inside a scheduler with a known unresolved fault would make future failures harder to diagnose. The status-verification capability itself has passed; this is a deployment-environment gate, tracked separately from Gate 2B feature work.

**2B-1 — Scheme / Application / Phase Reconciliation.** *(NEXT — gate definition approved by the Product Owner 2026-09-10; implementation on a dedicated feature branch, not yet started.)*

**Controlling objective:** *"PropertyAIgent can deterministically identify which application, phase or proposal version is eligible to control each acquisition-relevant scheme fact, distinguish substantive from non-substantive planning records, preserve approved, proposed and superseded positions, and surface unresolved conflicts rather than relying on generic 'most complete / most recent' application selection."*

**V1 characteristics:** deterministic; explainable; **fact-level** (not one new `current_application_id`); **computed / read-oriented** (no persisted `SchemeOperativeFacts` table in 2B-1 — persistence/versioning of the reconciled layer is deferred to 2B-2); non-destructive (no bulk rewrite of historic records); provenance-aware; fail-safe where evidence is insufficient (explicitly declines to state a value rather than guessing).

**Primary defect it fixes:** `app.ui.common.pick_representative_application()` ("most complete extraction + most recently received") feeding `aggregate_scheme_fields()` ("first non-null value in that order") lets a non-substantive or superseded application become the controlling source of scheme facts merely because it is newer or more fully extracted. 2B-1 replaces/wraps that selection at the scheme-fact boundary with deterministic fact-level eligibility + ranking. This is **not** duplicate-site consolidation — `app.pipeline.site_linking` already merges references into one physical `Site`; 2B-1 works *within* a consolidated Site.

**Implementation order (approved):** (1) resolve application **`planning_role`** — a concept kept *distinct* from the existing `application_category` (`application_category` = qualification/filtering/business classification; `planning_role` = how the application participates in the planning lifecycle and whether it may control particular scheme facts), reusing and extending existing classifiers, not a parallel taxonomy; (2) resolve phase/scope (reuse `app.pipeline.phase_tracking`); (3) determine which applications are **eligible** to supply each fact; (4) rank eligible fact sources deterministically; (5) preserve proposed vs approved vs superseded positions separately; (6) surface unresolved same-scope conflicts (reuse/generalise `app.reporting.affordable_housing_scope`'s scope + authority-rank + `ScopeConflict` pattern); (7) wire the direct presentation layers that currently depend on `pick_representative_application()`/`aggregate_scheme_fields()` (`site_profile.py`, `residential_mix.py`, and other direct scheme-fact consumers) to the new reconciliation. An explicit persisted `ApplicationRelationship` table is introduced **only if** a required acceptance case cannot be solved safely without typed relationships — and if so, kept narrow to `reserved_matters_of` / `varies_or_s73_of` / `amends` / `supersedes` / `condition_discharge_of` / `screening_or_scoping_for` / `related_uncertain`; no broader planning-graph framework.

**Facts in scope (eligibility/source selection for each):** operative planning status; operative permission/application reference; current proposed residential units; approved residential units where consent exists; residential-only unit count; houses/apartments/specialist/other-use mix; affordable housing units; affordable housing percentage; affordable tenure position where available; whole-site vs phase scope; current relevant phase; acquisition-relevant scheme scope. No application is assumed to supply all of these.

**Non-substantive guardrail (hard requirement):** EIA screening / EIA scoping / condition discharge / certificates / external consultations / ancillary applications / technical amendments must not establish substantive planning permission or operative residential quantum unless the resolved `planning_role` specifically permits the relevant fact. EIA screening cannot create "permission granted"; condition discharge cannot overwrite the underlying permission's unit count; an NMA cannot create a new development opportunity; a reserved-matters application may refine detailed unit/mix facts for its own phase; an S73 may modify specific facts without creating a duplicate scheme opportunity.

**Approved vs proposed vs superseded:** never collapsed. E.g. 116 homes (historic/wider/superseded) and 76 homes (later approved operative scheme) are both retained; the later approved position controls the approved acquisition fact, the historic figure stays traceable.

**Conflict handling:** deterministic resolution where authority is clearly stronger, otherwise explicit conflict / verification-required. No "Frankenstein" facts (affordable unit count from one application, percentage from another) — related values forming one coherent position come from the same application/scope unless an explicit deterministic rule justifies otherwise.

**Acceptance cases (core fixtures/tests):** Former Burnage Cricket Club (0 vs 13 affordable — operative approved AH controls where supported, or the disagreement is surfaced with provenance; a technical/condition filing cannot silently supply 0); Stockport Rugby Club (≈60 homes + care/extra-care vs unexplained 90 — residential separated from specialist accommodation, no undifferentiated wider total as *the* housing opportunity); Pennington's Stables (EIA screening cannot establish permission-to-build or become the operative substantive application); World of Pets (116 historic/wider vs 76 later approved — later operative approved scheme controls, older figure traceable but non-overriding); Brixham Road (conflicting AH count vs % — coherent same-source position where possible, else surface the conflict); Hazelhurst Farm (phase-specific vs wider-site AH obligation kept distinct, not flattened); plus London Road, Victoria House, Hopes Carr for operative planning-state selection over generic recency.

**Explicitly deferred (not this gate):** persisted/versioned operative-fact layer (→ 2B-2); lifecycle transition history (→ 2B-0B); AI-assisted reconciliation (2B-1 is deterministic); portal-native phase model; cross-`Site` reconciliation; broad `opportunity_universe`/fingerprint/material-change rewrite (touch downstream consumers only where correctness requires it — flag anything larger for 2B-2); all buyer/acquisition scoring, comparables, valuation, residual appraisal, financial modelling, monitoring alerts, dashboard redesign, Buyer Profile rebuild; any platform-wide retrospective production correction/reprocessing (separately authorised after the rules are proven — testing against selected real production cases is fine).

**Prerequisite:** the completed Gate 2B repository & architecture investigation is the design basis; the implementation agent re-inspects the relevant modules rather than assuming the notes are complete.

**2B-2 — Operative Scheme Facts / Evidence Resolution.** *(AFTER 2B-1 — not yet defined.)* Formalises and exposes 2B-1's reconciled operative facts as a **stable, reusable layer** (persistence, versioning, evidence-date/confidence surfacing) for UI, monitoring, buyer qualification and downstream consumers — the "OPERATIVE OPPORTUNITY FACTS" layer in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md). 2B-1 proves the reconciliation rules on a computed/read-oriented basis first; 2B-2 hardens a persistent schema around them. Where the evidence does not justify an operative value, the system explicitly declines to state one. Scope and technical shape deliberately undecided until 2B-1 lands.

**2B-0B — Application Lifecycle History.** *(LATER — re-sequenced after 2B-1/2B-2 by Product Owner decision at Gate 2B-0A closure.)* A richer lifecycle-history capability where useful: preserves and exposes commercially meaningful planning transitions (awaiting decision → officer recommendation → committee resolution → permission granted → conditions discharged → commencement evidence) as previous-state → new-state pairs with detected-at timestamps and per-transition provenance, rather than 2B-0A's current-value refresh silently overwriting them. Useful for change alerting and audit, but deliberately **not** a prerequisite for trustworthy operative facts — 2B-1 addresses the more urgent commercial risk (tracking the wrong application as operative). Depends on 2B-0A's fresh-evidence signal as its trigger; never re-implements verification.

### After 2B

- **Gate 2C — Acquisition Position Intelligence.** What the evidence establishes about whether/how an opportunity could realistically be acquired (owner, applicant, developer/controller, promoter, delivery partner, option/promotional control, construction/commencement, disposal/marketing, JV/funding signals). Availability must never be inferred from silence — see [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md), "Unknown Must Remain Unknown." Potential states (`AVAILABLE` / `POTENTIALLY_AVAILABLE` / `UNKNOWN` / `CONTROLLED` / `COMMITTED`) are provisional, not locked — see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md).
- **Buyer Mandate V2.** *Extends* the existing Buyer Profile domain (Gate 1) — geography, min/max units, maximum AH, product preference, planning-stage appetite, BTR/build-for-sale, brownfield/greenfield, and other acquisition criteria where evidence exists — into a reusable acquisition mandate driving filtering, matching, agent reasoning, monitoring and alerts. Not solved solely through an advanced-filter UI; natural-language interpretation may eventually create/edit the structured mandate (see [PRODUCT_VISION.md](PRODUCT_VISION.md), "The same discipline applies to interpreting what a user is asking for").
- **Acquisition Agent V1.** One reusable acquisition-reasoning capability parameterised by **Buyer Profile × Opportunity** — not a separately engineered agent per buyer. Reasons over Buyer Mandate, Operative Scheme Intelligence, Applicant Intelligence, Acquisition Position, deterministic Buyer Fit and opportunity-change evidence. Potential recommendation states (provisional): `PURSUE / VERIFY / MONITOR / NOT RELEVANT`. This is the acquisition-first evolution of the Buyer Analyst already scoped in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7, not a second, separate agent.
- **Acquisition Prioritisation.** Explainable dimensions/bands first (Buyer Fit, Planning Readiness, Acquisition Readiness, Evidence Confidence) — no premature numeric score. Any future score belongs to **buyer × opportunity**, never to the opportunity universally (see [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md), "No Opaque Scoring").
- **Acquisition Workflow & Monitoring.** Persistent buyer opportunity state, saved shortlists, comparison, preserved Explore/filter context, evidence-rich exports, change-driven reassessment, new-match acquisition briefs, material-change alerts, committed/closed-opportunity handling, an action-oriented dashboard — built on the existing Gate 1/1C change-detection infrastructure, not a rebuild of it.

### Later

**Weekly Planning/Acquisition Monitoring Agent.** *(ROADMAP ONLY — not designed, not scheduled, not to be implemented ahead of the Trusted Opportunity Data gates it depends on.)* Consumes 2B-0B's lifecycle changes and 2B-1's reconciled opportunity data to answer "what changed this week that matters?" — and, once Buyer Mandate V2 exists, "what changed this week that matters to Buyer X?" Potential output: newly granted opportunities, committee progression, S106 progression, revised schemes, newly discovered related applications, approaching-lapse changes, commencement indicators, buyer-fit changes, priority acquisition actions. **The agent must never itself scrape or determine planning truth** — it is a consumer of the deterministic lifecycle/reconciliation layers beneath it, the same "agent reads, deterministic layers write" discipline as every other agentic capability in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7.

**Comparable Evidence Agent**, then **Development Appraisal Agent** — unchanged from the existing "Phase 2" sequencing below: detailed valuation/appraisal (GDV, cost plans, residual land value, development finance, IRR, profit-on-cost) is not the near-term commercial priority. The near-term priority remains **identify → qualify → match → monitor**, not full development appraisal; establishing whether a genuine acquisition route exists comes first.

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

## Phase 1.5 — Buyer-Fit (historical record — superseded by the Acquisition-First Gate Sequence above)

- ~~Structured Buyer Profiles~~ (geography, scale, planning-risk appetite, development type, tenure, delivery horizon, brownfield/greenfield preference) - **implemented as Buyer Profiles V1** (four pilot profiles; unit/affordable-unit scale, planning appetite, development-type and wholly-affordable exclusion polarity - geography/tenure/brownfield-greenfield preference were explicitly out of scope for the pilot and remain future work)
- ~~Deterministic buyer-fit logic against those profiles~~ - **implemented** (`app.policy.buyer_matching.assess_buyer_fit`)
- ~~Buyer Profiles persistent and Workspace-owned~~ - **implemented and closed** (Gate 1: Acquisition Monitoring Substrate, merged to master)
- Opportunity Analyst V1 / Buyer Analyst V1 - see "Acquisition-First Gate Sequence" above (**Acquisition Agent V1**, after Gate 2B/2C/Buyer Mandate V2) for their current sequencing; neither is built yet

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
| Ownership/control intelligence | **Foundation exists** | 1 (candidate) | `ControlRelationship` is Site/Application-scoped; no title/registry resolution. Strengthened by Applicant Intelligence (below) at the organisation level, though this remains distinct from title/registry ownership resolution. |
| Opportunity identity & change detection | **Built, CLOSED** | Gate 1 / 1C | `app.reporting.opportunity_universe` (5 opportunity types, deterministic fingerprinting) + `app.reporting.opportunity_change` (`BASELINE_EXISTING`/`NEW`/`MATERIALLY_CHANGED`/`UNCHANGED`), weekly production cron |
| Monitoring (opportunity-level "does this matter" reasoning) | **Foundation built (deterministic); agentic interpretation not yet built** | Gate 1/1C built; agentic layer NEXT-after-2B | Opportunity-level change detection is now built and closed (above); an agent answering "does this change matter for this buyer's mandate" is not yet built |
| NPPF/policy-led opportunity intelligence | **Not yet built** | 1 (candidate) / 1.5 | Only `buffer_percentage` exists today; no versioned national-policy layer |
| Buyer profiles | **Built, CLOSED** | Gate 1 | Four pilot profiles (Buyer Profiles V1), now persistent and Workspace-owned (Gate 1) — geography/tenure/brownfield-greenfield preference remain future work under Buyer Mandate V2 |
| Buyer fit | **Built** | Gate 1 (extends Buyer Profiles V1) | `app.policy.buyer_matching.assess_buyer_fit` — deterministic, no LLM, no numeric score |
| Applicant Intelligence | **Built, CLOSED** | Gate 2A | Entity-level, evidence-grounded organisation classification for planning-application-linked identities; full eligible production population (188 identities) bootstrapped and validated; known V1 limitations documented in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2 |
| Planning freshness infrastructure | **CLOSED — implemented, deployed (`4b98b46`), production-validated (Oldham cohort)** | Gate 2B-0A | `Application.status_verified_at`, tiered direct re-verification, extended related-discovery eligibility; deployed fail-closed — platform-wide scheduled activation held as an operational dependency (see Gate 2B section) |
| Scheme / Application / Phase Reconciliation | **Gate definition approved 2026-09-10; implementation not yet started** | Gate 2B-1 (NEXT) | Deterministic, fact-level, computed/read-oriented (no persisted fact table in V1); `planning_role` distinct from `application_category`; non-substantive guardrail; approved/proposed/superseded kept separate; conflicts resolved by stronger evidence or surfaced |
| Operative Scheme Facts / Evidence Resolution | **Not yet built** | Gate 2B-2 | Resolved operative fact set (homes, AH, status, phase) with source/evidence-date/confidence/conflicts — consumes 2B-1 |
| Application lifecycle history | **Not yet built (re-sequenced after 2B-1/2B-2)** | Gate 2B-0B | Preserves/exposes meaningful planning transitions as previous→new pairs with provenance — depends on 2B-0A |
| Acquisition Position Intelligence | **Not yet built** | Gate 2C | Depends on Gate 2B; availability must never be inferred from silence |
| Opportunity Analyst | **Not yet built** | 1.5 / superseded by Acquisition Agent V1 | Depends on Phase 1 Opportunity Validation's findings; not built ahead of it |
| Planning due diligence | **Not yet built** | 1.5 | A deeper mode of the Opportunity Analyst, not a separate agent |
| Acquisition Agent V1 | **Not yet built** | After Gate 2B/2C/Buyer Mandate V2 | One reusable Buyer Profile × Opportunity reasoning capability — the acquisition-first evolution of the Buyer/Opportunity Analyst concepts above |
| Market/comparables | **Not started** | 2 | No sales, rental or comparable data flows into the platform today |
| Development appraisal | **Not started** | 2 | Hard-blocked on Market Intelligence existing first |
| Market/Investment Analyst | **Not started** | 2 | Depends on structured market evidence + deterministic appraisal existing first |

---

## Recommended Next Task

**Gate 2B-1 — Scheme / Application / Phase Reconciliation.** Gate 2B-0A is closed (implemented, deployed at `4b98b46`, production-validated through the Oldham cohort). The 2B-1 gate definition is approved (2026-09-10) — deterministic, fact-level, computed/read-oriented V1; `planning_role` distinct from `application_category`; non-substantive guardrail; approved/proposed/superseded kept separate; conflicts resolved by stronger evidence or surfaced; driven by the real Astra regression cases; persistence deferred to 2B-2. Implementation runs on a dedicated feature branch, not merged/deployed, no production-data changes. Separately: platform-wide scheduled status verification stays fail-closed until the production daily-scrape scheduler is proven healthy (operational dependency, not Gate 2B feature work).
