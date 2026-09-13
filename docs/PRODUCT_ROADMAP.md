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

**Acquisition Monitoring Substrate** (Gate 1, Gate 1C, Gate 2A — all merged to master, all **CLOSED**) — Workspace ownership boundary; persistent Buyer Profiles and deterministic buyer fit; a stable, deterministic opportunity universe across five opportunity types (strategic land, long-pending application, recent permission, undeveloped permission, approaching lapse) with fingerprinting and change detection; entity-level, evidence-grounded Applicant Intelligence for planning-application-linked organisations, production-validated across the full eligible population.

**Trusted Opportunity Data** (Gate 2B-0A, 2B-1, 2B-2A, 2B-2B.1, 2B-2B.2, 2B-2C — all merged to master, all **CLOSED**; together the **Core Planning Trust Programme**, still open to the promoted follow-on Gate 2B-0B — see below) — the platform now reconciles planning evidence into a trusted operative position (which application/phase/scope actually controls each fact — never "most recent" or "most complete"), aligns every acquisition-signal consumer (approaching lapse, undeveloped permission, recent permission) onto that same trusted position instead of independently re-deriving it, and correctly scopes acquisition opportunities to whole-site/material-development-phase/parcel rather than individual dwelling plots. Production merge closing this programme: `1eb7e5fb1540127c20b0da88205b9f0e95120da1`. See "Acquisition-First Gate Sequence" below for full detail and what's next.

**Production deployment** — live at `propertyaigent.onrender.com`, on Render, deployed from `master`.

The platform has therefore reached: *planning intelligence → structured Local Plan/allocation intelligence → planning activity analysis → opportunity identification → opportunity discovery → opportunity investigation/profile → shortlist → buyer-matched, monitored, entity-enriched acquisition substrate → trusted operative planning facts governing every acquisition signal.* Local Plans, strategic allocations, opportunity identification, buyer profiles/fit, opportunity monitoring, Applicant Intelligence and Trusted Opportunity Data are no longer future concepts in this document — they are shipped capability, referenced as such throughout the sections below. The platform's stated commercial outcome is now acquisition-first — see "The Acquisition-First Direction" below.

**Product North Star (Product Owner decision, post Gate 2B-2C).** PropertyAIgent is evolving from a planning-search application into an AI-native acquisition intelligence platform: *"PropertyAIgent continuously turns fragmented planning, ownership and development evidence into ranked acquisition opportunities matched to a buyer's strategy."* Planning intelligence is the evidence foundation; acquisition intelligence is the product outcome. The primary unit of value is not a planning application, search result, document or Site record — it is a **qualified, buyer-specific acquisition opportunity**. The long-term experience should increasingly resemble an always-on acquisition researcher rather than a static planning database: a user defines an acquisition mandate and PropertyAIgent continuously searches for opportunities, monitors known ones, detects material changes, investigates relevant evidence, updates its understanding, reassesses buyer relevance, prioritises opportunities, recommends next actions, and surfaces only commercially meaningful changes. See [PRODUCT_VISION.md](PRODUCT_VISION.md) for the full statement and [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) for the target conceptual architecture this now drives. **Complementary statement (Product Owner decision, post Gate 2B-0B investigation):** *"PropertyAIgent maintains a continuously evolving acquisition opportunity universe for each buyer, generated from a shared trusted market evidence layer and monitored by a persistent acquisition agent."* This does not replace the North Star above — it makes explicit the buyer-specific-universe architecture ("Buyer-Specific Opportunity Universes," below) the North Star's "matched to a buyer's strategy" clause already implied.

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

### Foundation — Workspace / Product Architecture (Complete)

*(Not a numbered gate — a standing architectural decision that every gate below builds on, recorded here rather than as a retroactive "Gate 0.")* Planning and property evidence (applications, documents, Sites, Local Plan/allocation intelligence, Applicant Intelligence) is **globally reusable** — it does not belong to any one workspace and is never duplicated per-workspace. Buyer Profiles and their deterministic fit assessments are **workspace-specific** — they belong to the workspace that owns the acquisition mandate. Workflow and human-in-the-loop state (pursue/verify/monitor decisions, notes, actions taken) will likewise be workspace-specific once built (Gate 5). This boundary was established deliberately, and deliberately without a premature User/Organisation/auth redesign — the existing Workspace ownership boundary (delivered as part of Gate 1) is sufficient for the gates sequenced below; a fuller multi-user/permissions model remains out of scope until a real product need forces it.

### Completed Foundation

| Gate | Status | What it built |
|---|---|---|
| **Gate 1** — Acquisition Monitoring Substrate | **CLOSED** (merged to master) | Workspace ownership boundary; persistent, Workspace-owned Buyer Profiles (extending, not replacing, Buyer Profiles V1); stable opportunity identity (`app.reporting.opportunity_universe`); deterministic opportunity fingerprinting and change detection (`app.reporting.opportunity_change`: `BASELINE_EXISTING` / `NEW` / `MATERIALLY_CHANGED` / `UNCHANGED`); a buyer onboarding baseline. |
| **Gate 1C** — Planning Opportunity Trigger Expansion | **CLOSED** (merged to master) | Expanded the opportunity universe's planning/delivery detectors to `RECENT_PERMISSION` and `LONG_PENDING_APPLICATION`, alongside the existing `STRATEGIC_LAND`, `UNDEVELOPED_PERMISSION` and `APPROACHING_LAPSE` — five opportunity types, one deterministic universe, a standing weekly production cron. |
| **Gate 2A** — Applicant Intelligence V1 | **CLOSED** (merged to master; production bootstrap complete) | Entity-level, evidence-grounded organisation classification for planning-application-linked identities (see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2). **Production validation record:** full eligible population processed — 188 identities (170 organisation-shaped, 18 private-person-shaped); 169/170 organisations successfully classified, 1 in a safe, persistent validation-rejected state (not forced); all 18 private identities received deterministic no-web-research protection; zero duplicate identities; zero strategic-land-only research violations; live Applicant Intelligence UI verified in production; Opportunity Universe and Buyer Profiles unaffected. Known V1 limitations (parent/group completeness, confidence/evidence-ref linkage, source authority vs. claim support, source-type mistagging, backlog overfetch behaviour) are recorded in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §2, not fixed as part of closing this gate. |
| **Gate 2B** — Trusted Opportunity Data (six sub-gates) | **Core Planning Trust Programme Complete** (merged to master `1eb7e5f`) | See "Gate 2B — Trusted Opportunity Data (Core Planning Trust Programme Complete)" immediately below for full detail per sub-gate. |

### Next

**Gate 2B-0B — Application Lifecycle Intelligence** — *promoted follow-on trust capability, extending the same Gate 2B trust programme rather than starting a new one.* Ahead of Gate 2C, by Product Owner decision, post Gate 2B-2C. See "Gate 2B-0B" below.

## Gate 2B — Trusted Opportunity Data (Core Planning Trust Programme Complete)

*(Gate 2B is a sequence of deliberately separate sub-gates, not one monolithic build. The six sub-gates below — 2B-0A through 2B-2C — are **CLOSED**, merged to master and deployed to production: together they form the core planning-trust programme. Gate 2B-0B — originally deferred as "Application Lifecycle History" — is a **promoted follow-on trust capability** within this same programme, not a separate gate after it: see "Gate 2B-0B — Application Lifecycle Intelligence (NEXT)" below.)*

```
Council portals + planning documents
        ↓
2B-0A     Planning Freshness Infrastructure           CLOSED — re-verify a known application's own record
        ↓
2B-1      Scheme / Application / Phase Reconciliation CLOSED — which application/phase/version controls each scheme-level fact
        ↓
2B-2A     Trusted Operative Planning Facts            CLOSED — computed, non-persisted, scope-aware read layer over 2B-1's reconciliation
        ↓
2B-2B.1   Trusted Consumer Alignment                  CLOSED — downstream buyer-facing consumers migrated onto Trusted Operative Planning Facts
        ↓
2B-2B.2   Acquisition Opportunity Scope Alignment      CLOSED — acquisition opportunities scoped to whole-site/material-phase/parcel, never an individual plot
        ↓
2B-2C     Planning Signal Consumer Alignment          CLOSED — lapse/recent-permission/undeveloped-permission signals use the trusted substantive permission, never a naive "latest grant"
        ↓
Trusted Opportunity Data                              — the full programme above; production merge `1eb7e5fb1540127c20b0da88205b9f0e95120da1`
        ↓
2B-0B     Application Lifecycle Intelligence          NEXT — durably detect, retain and propagate meaningful lifecycle transitions
        ↓
Buyer / Acquisition Intelligence                      (Gate 2C onward — see "After 2B")
        ↓
Autonomous Acquisition Agent + Monitoring/Alerts       (Gate 3 / Gate 5 — see "Later")
```

**2B-0A — Planning Freshness Infrastructure. CLOSED.** Implemented, deployed and production-validated through a bounded Oldham cohort. Direct status verification safely re-fetches eligible unresolved applications, records verification freshness and detects material application changes. Scheduled platform-wide activation remains operationally gated pending resolution/verification of the production daily-scrape scheduler. Rich lifecycle history and scheme-level reconciliation remain separate subsequent gates.

*Detail:* `Application.status_verified_at` (additive schema field), deterministic verification tiers (contradiction signal / long-pending opportunity / other opportunity / other pending) at 7/14/30/60-day cadence, a 10-per-council-per-run bound with a starvation-fairness reservation, and an extended (never rewritten) related-application-discovery eligibility. Deployed at `4b98b46` (web service verified on that commit); the status-verification stage is **fail-closed** — dormant in scheduled production until an operator sets `PLANNING_STATUS_VERIFICATION_ENABLED`, with `run_weekly --include-status-verification` for a single controlled run. Production validation record: one authorised Oldham cohort, 10 eligible applications selected by the real selector (1 Tier 1 + 9 Tier 2), all `VERIFIED_UNCHANGED`, `status_verified_at` correctly advanced, no planning facts fabricated, no false material-change event, no unintended downstream processing, only the authorised council touched, portal/circuit-breaker handling wired and test-covered. See [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md), "Planning Status Verification," and the Gate 2B-A investigation root-cause findings this closes (173 pending applications >6 months old with zero refresh activity; 100% of long_pending_application opportunities >90 days unverified). **Capability freshness verification is complete; the broader Application Lifecycle Intelligence vision is not — 2B-0A did not solve historical lifecycle transitions, operative scheme reconciliation, or buyer-facing change alerts.**

> **Operational activation dependency (not unfinished 2B-0A development).** Platform-wide scheduled verification (`PLANNING_STATUS_VERIFICATION_ENABLED=true`) must NOT be enabled until the production scheduled pipeline is separately proven healthy — the historical `propertyaigent-daily-scrape` run failure remains an unresolved operational issue, and adding a new workload inside a scheduler with a known unresolved fault would make future failures harder to diagnose. The status-verification capability itself has passed; this is a deployment-environment gate, tracked separately from Gate 2B feature work.

**2B-1 — Scheme / Application / Phase Reconciliation. CLOSED.** Implemented (`app.reporting.scheme_reconciliation`), merged to master (`e51f74b`, 2026-09-10) and validated read-only against seven real Astra-review production Sites. Deterministic, computed/read-oriented, non-persisted, fact-level reconciliation now determines which application/phase/proposal version is eligible to control each scheme fact at the Site Profile boundary — replacing the generic "most complete / most recent" `pick_representative_application` selection. `planning_role` (distinct from `application_category`), decided-state overlay, per-fact eligibility + deterministic ranking (recency tie-break only), approved/proposed/superseded kept separate, hard non-substantive guardrail (EIA screening/scoping, condition discharge, certificates, external consultations, ancillary/technical amendments barred from substantive facts), residential-only "no new inference" safeguard, S73 fact-specific safeguard, same-scope conflict surfacing, delegated affordable-housing scope reconciliation. No schema migration; no persisted operative-fact layer (that is Gate 2B-2). **Carried-forward limitations (see "Carried-forward from Gate 2B-1" below).**

*(Original approved gate definition retained below for the record.)*

**2B-1 — Scheme / Application / Phase Reconciliation.** *(Gate definition approved by the Product Owner 2026-09-10.)*

**Controlling objective:** *"PropertyAIgent can deterministically identify which application, phase or proposal version is eligible to control each acquisition-relevant scheme fact, distinguish substantive from non-substantive planning records, preserve approved, proposed and superseded positions, and surface unresolved conflicts rather than relying on generic 'most complete / most recent' application selection."*

**V1 characteristics:** deterministic; explainable; **fact-level** (not one new `current_application_id`); **computed / read-oriented** (no persisted `SchemeOperativeFacts` table in 2B-1 — persistence/versioning of the reconciled layer is deferred to 2B-2); non-destructive (no bulk rewrite of historic records); provenance-aware; fail-safe where evidence is insufficient (explicitly declines to state a value rather than guessing).

**Primary defect it fixes:** `app.ui.common.pick_representative_application()` ("most complete extraction + most recently received") feeding `aggregate_scheme_fields()` ("first non-null value in that order") lets a non-substantive or superseded application become the controlling source of scheme facts merely because it is newer or more fully extracted. 2B-1 replaces/wraps that selection at the scheme-fact boundary with deterministic fact-level eligibility + ranking. This is **not** duplicate-site consolidation — `app.pipeline.site_linking` already merges references into one physical `Site`; 2B-1 works *within* a consolidated Site.

**Implementation order (approved):** (1) resolve application **`planning_role`** — a concept kept *distinct* from the existing `application_category` (`application_category` = qualification/filtering/business classification; `planning_role` = how the application participates in the planning lifecycle and whether it may control particular scheme facts), reusing and extending existing classifiers, not a parallel taxonomy; (2) resolve phase/scope (reuse `app.pipeline.phase_tracking`); (3) determine which applications are **eligible** to supply each fact; (4) rank eligible fact sources deterministically; (5) preserve proposed vs approved vs superseded positions separately; (6) surface unresolved same-scope conflicts (reuse/generalise `app.reporting.affordable_housing_scope`'s scope + authority-rank + `ScopeConflict` pattern); (7) wire the direct presentation layers that currently depend on `pick_representative_application()`/`aggregate_scheme_fields()` (`site_profile.py`, `residential_mix.py`, and other direct scheme-fact consumers) to the new reconciliation. An explicit persisted `ApplicationRelationship` table is introduced **only if** a required acceptance case cannot be solved safely without typed relationships — and if so, kept narrow to `reserved_matters_of` / `varies_or_s73_of` / `amends` / `supersedes` / `condition_discharge_of` / `screening_or_scoping_for` / `related_uncertain`; no broader planning-graph framework.

**Facts in scope (eligibility/source selection for each):** operative planning status; operative permission/application reference; current proposed residential units; approved residential units where consent exists; residential-only unit count; houses/apartments/specialist/other-use mix; affordable housing units; affordable housing percentage; affordable tenure position where available; whole-site vs phase scope; current relevant phase; acquisition-relevant scheme scope. No application is assumed to supply all of these.

**Non-substantive guardrail (hard requirement):** EIA screening / EIA scoping / condition discharge / certificates / external consultations / ancillary applications / technical amendments must not establish substantive planning permission or operative residential quantum unless the resolved `planning_role` specifically permits the relevant fact. EIA screening cannot create "permission granted"; condition discharge cannot overwrite the underlying permission's unit count; an NMA cannot create a new development opportunity; a reserved-matters application may refine detailed unit/mix facts for its own phase; an S73 may modify specific facts without creating a duplicate scheme opportunity.

**Approved vs proposed vs superseded:** never collapsed. E.g. 116 homes (historic/wider/superseded) and 76 homes (later approved operative scheme) are both retained; the later approved position controls the approved acquisition fact, the historic figure stays traceable.

**Safeguard — residential-only unit count is not a new inference (Product Owner, final approval).** 2B-1 is a reconciliation gate, not a new extraction gate. Resolve a residential-only operative quantum **only where the existing extracted evidence already supports a deterministic distinction** between general residential dwellings and specialist accommodation (care beds, extra-care, supported living, other non-standard residential uses). Where it does not, preserve the wider/all-use figure separately and **explicitly decline to state a residential-only operative value** (`not determined` / explicit scope-or-conflict state) — never a new NLP heuristic, AI extraction pass, or speculative interpretation, and never a fabricated clean housing number to satisfy an acceptance fixture (Stockport Rugby Club especially).

**Safeguard — Section 73 / variation authority is fact-specific, not application-wide (Product Owner, final approval).** A later S73 / variation application must **not** automatically supersede all facts from the underlying permission merely because it is newer. It becomes operative for a specific scheme fact **only where the existing evidence explicitly demonstrates that the application varies that fact** — e.g. if it clearly changes the approved unit count it may control approved units; if it changes layout with no evidence AH changed, the underlying permission/S106 continues to control AH; if the evidence is unclear whether a given fact changed, preserve the existing operative fact and/or surface uncertainty rather than inferring supersession. This reinforces the fact-level (not global `current_application_id`) requirement.

**Conflict handling:** deterministic resolution where authority is clearly stronger, otherwise explicit conflict / verification-required. No "Frankenstein" facts (affordable unit count from one application, percentage from another) — related values forming one coherent position come from the same application/scope unless an explicit deterministic rule justifies otherwise.

**Acceptance cases (core fixtures/tests):** Former Burnage Cricket Club (0 vs 13 affordable — operative approved AH controls where supported, or the disagreement is surfaced with provenance; a technical/condition filing cannot silently supply 0); Stockport Rugby Club (≈60 homes + care/extra-care vs unexplained 90 — residential separated from specialist accommodation, no undifferentiated wider total as *the* housing opportunity); Pennington's Stables (EIA screening cannot establish permission-to-build or become the operative substantive application); World of Pets (116 historic/wider vs 76 later approved — later operative approved scheme controls, older figure traceable but non-overriding); Brixham Road (conflicting AH count vs % — coherent same-source position where possible, else surface the conflict); Hazelhurst Farm (phase-specific vs wider-site AH obligation kept distinct, not flattened); plus London Road, Victoria House, Hopes Carr for operative planning-state selection over generic recency.

**Explicitly deferred (not this gate):** persisted/versioned operative-fact layer (→ 2B-2); lifecycle transition history (→ 2B-0B); AI-assisted reconciliation (2B-1 is deterministic); portal-native phase model; cross-`Site` reconciliation; broad `opportunity_universe`/fingerprint/material-change rewrite (touch downstream consumers only where correctness requires it — flag anything larger for 2B-2); all buyer/acquisition scoring, comparables, valuation, residual appraisal, financial modelling, monitoring alerts, dashboard redesign, Buyer Profile rebuild; any platform-wide retrospective production correction/reprocessing (separately authorised after the rules are proven — testing against selected real production cases is fine).

**Prerequisite:** the completed Gate 2B repository & architecture investigation is the design basis; the implementation agent re-inspects the relevant modules rather than assuming the notes are complete.

**Carried-forward from Gate 2B-1 (into Gate 2B-2 / evidence-quality work):**
- **Affordable-housing scope reconciliation is not decided-state-aware.** `app.reporting.affordable_housing_scope` surfaces an AH position from an application regardless of whether that application is withdrawn/refused. Confirmed in production: Stockport Rugby Club (Site 88) still shows a 50% / 45-unit AH position sourced from a withdrawn hybrid. Making the operative AH position decided-state-aware is a **trusted-operative-facts / AH reconciliation requirement** for Gate 2B-2.
- **Upstream extraction-quality (separate backlog, not 2B-1 or 2B-2):** World of Pets (Site 248) — `114619/RES/24`'s `SchemeIntelligence.total_units_final = 116` contradicts its own proposal ("erection of 76 residential dwellings"). Gate 2B-1 correctly selects that Reserved Matters application as operative; the wrong number originates in its extracted intelligence. Needs a targeted evidence refresh / re-extraction and a detector for "extracted unit quantum conflicts with the explicit proposal-text figure". Do not fix inside Gate 2B-1 or Gate 2B-2.
- **All-use vs residential-only presentation:** where residential-only quantum is `not_determined` (a specialist / C2 component is evidenced) but approved/proposed is resolved, the "Total homes" tile shows the resolved all-use approved figure (e.g. Hazelhurst Farm, Site 179: "400 (approved)") with the residential-only caveat in the reconciliation trail. Accepted for Gate 2B-1; a future 2B-2 UI could present the distinction more explicitly.

**2B-2A — Trusted Operative Planning Facts. CLOSED.** Resolved the open "computed service vs persisted" architecture question the original 2B-2 entry left undecided: **computed, non-persisted, scope-aware** — no Scheme/OperativeScheme table was introduced; `Site` remains the sole persisted identity anchor. `app.reporting.scheme_reconciliation.build_operative_planning_facts(applications) -> OperativePlanningFacts` structurally separates the **current consented position** (never manufactured from a pending/ancillary application) from **current active planning position(s)** (zero, one or several, one per distinct scope, never collapsed by "latest wins"); adds scope-awareness (`group_applications_by_operative_scope`, `is_material_development_parcel` — a named "plot" group is a peer acquisition-level scope only if it independently states its own qualifying-scale unit count, never inferred from the token's own shape); makes affordable-housing scope reconciliation decided-state-aware, closing the Gate 2B-1 carried-forward item above; adds relationship confidence (site-link method/confidence, never a new numeric score) and freshness (`status_verified_at`/`independently_verified`) as first-class, separately-tracked provenance dimensions — never collapsed with evidence confidence into one generic score. The World of Pets 116-vs-76 extraction-quality item remains a separate, still-open backlog item, unaffected by this or any subsequent 2B-2x gate.

**2B-2B.1 — Trusted Consumer Alignment. CLOSED.** Migrated downstream buyer-facing consumers (Buyer Fit planning-state resolution, Site Profile Structured Summary, Affordable Homes tile) from the legacy "most complete / most recent" selection onto Trusted Operative Planning Facts, removing a hardcoded `PERMISSION_GRANTED` fallback and correcting AH percentage/unit-count conflation defects found live in production (Brixham Road). Two closure hotfixes (Structured Summary, Affordable Homes tile) merged and deployed in the same gate.

**2B-2B.2 — Acquisition Opportunity Scope Alignment. CLOSED.** Migrated *acquisition opportunity generation itself* (not just presentation) onto the same operative-scope model 2B-2A introduced: an individual dwelling plot filing (a later NMA/condition-discharge citing "Plot 25") can no longer become its own standalone acquisition opportunity inheriting the whole site's unit count — confirmed real defects at Lacy Street, Barton Road and four further production sites, all corrected; a genuine development phase or material development parcel is unaffected and still becomes its own opportunity where evidence supports it. Included a narrow, dry-run-first controlled monitoring-transition mechanism (`app.reporting.opportunity_monitoring_transition`) so a software scope/fact correction is never misreported to `app.reporting.opportunity_change` as a genuine `NEW`/`MATERIALLY_CHANGED` market event — the same mechanism reused, unmodified, by every subsequent Gate 2B-2x closure.

**2B-2C — Planning Signal Consumer Alignment. CLOSED.** The commencement/lapse clock, the "has this started" development-progress check, and the recent-permission/undeveloped-permission/approaching-lapse detectors all previously selected their own "operative granted permission" independently and naively — the most recently *decided* application whose decision text merely said "approve"/"grant", with no awareness of planning role. A later NMA, condition discharge, or S73/variation could therefore become the permission that starts or resets the lapse clock, or wrongly suppress genuine post-permission progress evidence, purely by being the most recently decided grant-worded filing (confirmed production defect: World of Pets, and 56 further sites). `app.reporting.scheme_reconciliation.resolve_operative_lapse_anchor` now provides one trusted, role-aware anchor, reused (never re-derived) by `compute_lapse_status` and `compute_phase_progress` alike. A pre-merge semantic review further distinguished `NOT_GRANTED` (no application has been granted at all — a stable, ordinary fact) from `NOT_DETERMINED` (something was granted but is not trustworthy as the operative permission) — eliminating ~125 spurious fingerprint relabellings the first pass had introduced. Production impact at closure: 407 → 389 total opportunities, 178 → 160 planning_delivery, 229 strategic_land unchanged; 11 of 18 `RECENT_PERMISSION` opportunities and 8 `UNDEVELOPED_PERMISSION`/`APPROACHING_LAPSE` opportunities confirmed as false signals and removed; zero unrelated fingerprint fields touched on any surviving opportunity. S73/variation applications require no special-cased code to avoid manufacturing a fresh three-year clock — they were already excluded from the substantive-role set Gate 2B-2A introduced. Comprehensive statutory outline/reserved-matters commencement-period modelling remains explicitly deferred (the platform's uniform +3-year default was found to already resolve correctly for every production case checked, by coincidence of a later Reserved Matters approval naturally outranking its own outline). Production merge: `1eb7e5fb1540127c20b0da88205b9f0e95120da1`.

### Gate 2B-0B — Application Lifecycle Intelligence (NEXT)

*(Promoted ahead of deep Gate 2C implementation — Product Owner decision, post Gate 2B-2C. Originally scoped narrowly as "Application Lifecycle History"; re-scoped and broadened at promotion.)*

**Reason for promotion:** the platform has substantially improved its ability to answer *"what does the planning evidence mean?"* (Gate 2B-1 through 2B-2C). It must now reliably answer *"has that evidence changed since we last checked?"* — without this, sophisticated acquisition intelligence risks being built on stale scheme states.

**Objective:** create the trusted lifecycle infrastructure that lets PropertyAIgent continuously monitor relevant known planning applications/schemes and detect material factual changes.

```
Known application / opportunity
        ↓
Lifecycle watch
        ↓
Authoritative source re-check
        ↓
Change detection
        ↓
Current state + historical transition
        ↓
New/changed document ingestion
        ↓
Relevant extraction
        ↓
Planning reconciliation
        ↓
Updated Trusted Operative Planning Facts
        ↓
Updated opportunity signals
        ↓
Trusted change event
        ↓
(later) Autonomous Acquisition Agent
```

**Lifecycle events** the system should eventually detect, where authoritative council evidence permits (not every council exposes every field): planning status change; officer recommendation; committee date/report/recommendation/resolution; formal decision; decision date/notice; S106/legal agreement progression; revised plans/documents/residential quantum/affordable housing/tenure; related or superseding application; Reserved Matters; S73 variation; NMA; discharge of conditions; commencement evidence; development-progress evidence; later delivery/completion evidence where trustworthy.

**History requirement (known current gap).** Material lifecycle states must not merely be overwritten where the transition has commercial value — the platform should retain enough to reconstruct old state → new state → detected-at → authoritative source → evidence/provenance, and eventually answer: "What changed on this scheme?" "When did we first detect it?" "What evidence caused the change?" "What was the previous state?" "Which schemes moved materially closer to permission this week?"

**Builds on 2B-0A, does not rebuild it.** 2B-0A already answers "can we directly verify the current status?" 2B-0B extends this to "can we durably detect, retain and propagate meaningful lifecycle transitions?"

**Monitoring cadence.** Not brute-force historical rescraping. Monitoring should ultimately become stage-aware, risk-aware, opportunity-aware and (where appropriate) buyer-relevance-aware — e.g. a high-priority pending opportunity or an imminent committee/decision date verified relatively frequently; an ordinary pending scheme verified periodically; a permissioned undeveloped site verified at lower planning-frequency plus appropriate development-progress monitoring; an under-construction scheme monitored for development/delivery evidence specifically. Exact cadence is an architecture decision for this gate.

**Lifecycle watch and autonomous agents.** PropertyAIgent is not opposed to autonomous agents — autonomous acquisition intelligence is part of the target product (see the Product North Star above and [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7). The distinction: **lifecycle intelligence infrastructure** owns trusted factual change detection; the **autonomous acquisition agent** (Gate 3, later) orchestrates trusted capabilities and interprets commercial significance. Gate 2B-0B therefore builds capabilities a future agent can invoke, conceptually: `verify_application()`, `discover_related_applications()`, `check_new_documents()`, `extract_changed_facts()`, `reconcile_planning_position()`, `detect_development_progress()`, `emit_change_event()` — names conceptual only, not an API to build merely because it is named here. Autonomy belongs at the orchestration and commercial-reasoning layers; factual planning states remain evidence-backed.

**Required architecture investigation (not yet authorised for implementation)** must establish: current status-refresh architecture; existing status verification capabilities; current scheduler/cadence; existing related-application discovery; document refresh behaviour; which lifecycle fields are currently mutable; which history already exists; which important history is missing; how material changes should be represented; Application-level vs Site/scheme-level lifecycle responsibilities; how change events propagate into reconciliation; how monitoring fingerprints should react; how stale evidence should be prioritised; how future autonomous agents should invoke lifecycle capabilities; where deterministic logic ends and bounded AI begins; production scale/performance constraints. **No schema or implementation is approved until that investigation is reviewed by the Product Owner.**

**Investigation completed; Product Owner review outcome: APPROVED WITH AMENDMENTS.** The investigation confirmed, directly against production: 1,437 Applications, 379 pending, only 13 ever directly verified, 367/379 pending never directly verified; existing verification infrastructure (Gate 2B-0A) is deployed but dormant because `PLANNING_STATUS_VERIFICATION_ENABLED` is not enabled in the scheduled production job; Application field history is absent (no `ApplicationHistory`/`ApplicationFieldHistory` table exists); a planning document revised at the same URL/name is currently undetectable because `Document` has no content hash; lifecycle propagation currently relies heavily on independently scheduled stages (verification → material-change → evidence-refresh → intelligence-refresh → weekly opportunity sync), each cadence-gated separately rather than event-chained; the weekly opportunity sync can introduce up to approximately six days of downstream lag even when every upstream stage worked perfectly.

**Amended Gate 2B-0B V1 (Product Owner-approved scope, replacing the investigation's own proposed V1 where they differ):**

- **P0 — Status verification activation.** Resolve the existing scheduler-health operational prerequisite, then safely activate the existing `PLANNING_STATUS_VERIFICATION_ENABLED` capability. Do not redesign verification if the existing implementation is healthy.
- **P0 — Application lifecycle history.** Introduce the narrow `ApplicationLifecycleEvent` concept the investigation recommended: old state → new state → detected at → authoritative source → supporting evidence/provenance. Append-only; not generic event sourcing. Initial event scope stays Application-level — do **not** create history rows for every `SchemeIntelligence` field mutation.
- **P0 — Document revision detection.** Content-hash-based detection so a planning document revised at the same URL/name is not invisible, reusing the existing `MonitoredReport.content_hash` precedent.
- **P0 — Bounded downstream reassessment.** Amends the investigation's own recommendation to leave all downstream propagation to the weekly global sync. No Kafka, no generic event bus, no microservices, no agent — but establish a small deterministic semantic: a material lifecycle change makes the affected site eligible for downstream reassessment sooner than the next Monday sync. The exact smallest safe mechanism is an implementation-time design decision using existing architecture, not specified here. The weekly full sync remains as a safety/reconciliation mechanism regardless.
- **P1 — State-aware cadence extension.** Only after the existing 7/14/30/60-day verification cadence is operational and proven: extend monitoring for permissioned/undeveloped, post-permission-activity and later development states. Cadence stays deterministic and auditable — no LLM-driven scheduling.

**Explicitly deferred from this amended V1:** EPC trend history; comprehensive construction-progression tracking; a fund/BTR detector; agent-triggered out-of-cycle verification; a comprehensive committee/S106 subsystem; Buyer Mandate V2 implementation; Acquisition Agent implementation.

**Event-model extensibility (record now, do not implement now).** Although committee/S106-specific modelling is explicitly deferred, `ApplicationLifecycleEvent`'s design must not foreclose later events such as `OFFICER_RECOMMENDATION_CHANGED`, `COMMITTEE_DATE_ADDED`, `COMMITTEE_REPORT_ADDED`, `COMMITTEE_RESOLUTION_ADDED`, `RESOLUTION_SUBJECT_TO_S106`, `S106_EXECUTED`, `DECISION_NOTICE_ADDED`, `NEW_RELATED_APPLICATION`, `RESERVED_MATTERS_FOUND`, `S73_FOUND`, `NMA_FOUND`, `CONDITION_DISCHARGE_FOUND`, `COMMENCEMENT_EVIDENCE_FOUND` — the point is extensibility of the event-type vocabulary, not building this taxonomy now.

**Gate 2B-0B remains buyer-independent** (reaffirmed by this amendment): its purpose is the shared lifecycle nervous system — authoritative re-verification, document/evidence change detection, append-only lifecycle history, trusted downstream reassessment. It must not determine whether a change is commercially positive or negative for a specific buyer; that judgement belongs to the future Acquisition Agent (Gate 3) consuming Lifecycle Watch (see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7). See "Buyer-Specific Opportunity Universes" above for the full architecture this feeds.

### After 2B-0B

*(Sequenced after Gate 2B-0B closes, not immediately after Gate 2B-2C — Product Owner decision, post Gate 2B-2C. None of these is authorised to start now.)*

- **Gate 2C — Acquisition Position Intelligence.** Core question: *"Is there a plausible acquisition route?"* — deliberately **buyer-independent factual intelligence**, never "is this a good acquisition opportunity?" (that question is buyer-specific and belongs downstream, to the Buyer Opportunity Universe/Acquisition Agent — see "Buyer-Specific Opportunity Universes" above). What the evidence establishes about whether/how an opportunity could realistically be acquired: ownership; applicant identity; developer involvement; promoter involvement; option/control relationships; known development partner; whether a scheme appears committed; whether control is unclear; whether there may still be an acquisition route. Availability must never be inferred from silence — see [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md), "Unknown Must Remain Unknown"; use `AVAILABLE` very cautiously. Initial taxonomy (provisional, not locked): `AVAILABLE` / `POTENTIALLY_AVAILABLE` / `UNKNOWN` / `CONTROLLED` / `COMMITTED` — kept structurally separate from Buyer Fit and Planning Readiness (see "Opportunity Dimensions" below).
- **Buyer Mandate V2.** *After Gate 2C.* Extends, never rebuilds, the existing Buyer Profile domain (Gate 1) to progressively support geography, unit range, planning appetite, affordable-housing appetite, development type, brownfield/greenfield preference, consented-vs-strategic-land appetite, development/delivery-stage appetite, tenure/product, BTR-vs-sale, investment strategy where relevant, and exclusion criteria. Long-term interaction: user natural language ("I want consented or near-consented housing sites in Greater Manchester, 50–150 units, preferably below 40% affordable") → structured Buyer Mandate → user inspects/corrects → reusable Acquisition Agent configuration. Do not make the user configure dozens of technical planning fields manually — see [PRODUCT_VISION.md](PRODUCT_VISION.md), "The same discipline applies to interpreting what a user is asking for". **Newly recorded architectural importance (post Gate 2B-0B investigation):** Buyer Mandate V2 is now more than a future usability improvement — the future Buyer Opportunity Universe (see "Buyer-Specific Opportunity Universes" above) *depends* on the mandate being expressive enough to describe an acquisition strategy precisely. The Product Owner has flagged that the **contract/architecture of Buyer Mandate V2 may need to be investigated before Gate 2C is fully finalised**, since buyer-specific opportunity evaluation depends on it — this does not reorder the gates below without further Product Owner approval, it only flags a design dependency to watch when Gate 2C is scoped in detail.
- **Gate 3 — Autonomous Acquisition Agent V1.** A major strategic product gate. Each Buyer Mandate should be capable of powering a persistent Acquisition Agent — one reusable capability, `AcquisitionAgent(buyer_mandate, opportunity)`, never a separately engineered agent per buyer. Consumes trusted evidence and tools to answer: why is this an opportunity for this buyer; what has changed; what is still unknown; what should be investigated next; what should the buyer do. Target recommendation states (provisional): `PURSUE` / `VERIFY` / `MONITOR` / `NOT RELEVANT`. **Agent autonomy:** the agent should eventually be able to autonomously monitor its buyer's opportunity universe, identify opportunities needing fresher evidence, request bounded evidence checks, react to lifecycle change events (Gate 2B-0B), investigate unresolved acquisition questions, reassess Buyer Fit and Acquisition Position, reprioritise opportunities, determine whether a change is commercially material, suppress irrelevant noise, and recommend next actions — event-driven and change-driven, never required to repeatedly analyse the entire database with an LLM. This is the acquisition-first evolution of the Buyer Analyst already scoped in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7, not a second, separate agent. **Target orchestration model** (Product Owner decision, post Gate 2B-0B investigation): Buyer Mandate → Persistent Acquisition Agent → maintains the Buyer Opportunity Universe → consumes trusted market/lifecycle changes (from Lifecycle Watch, see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7) → determines which opportunities require investigation → invokes bounded trusted capabilities (conceptually `verify_application()` / `check_new_documents()` / `discover_related_applications()` / `reconcile_planning_position()` / `check_acquisition_position()` / `detect_development_progress()`, names conceptual only) → reassesses buyer relevance → `PURSUE`/`VERIFY`/`MONITOR`/`NOT RELEVANT`. Factual results the agent consumes always remain evidence-backed and auditable — the agent never becomes the system of record (see "The Autonomy Principle" above).
- **Gate 4 — Acquisition Prioritisation.** *After Gate 3.* Primary question: *"What should this buyer pursue first?"* Explainable dimensions/bands first (Buyer Fit, Planning Readiness, Acquisition Readiness, Evidence Confidence, Freshness, material recent change) — no premature numeric score; any future score belongs to **buyer × opportunity**, never to the opportunity universally (see [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md), "No Opaque Scoring"). A user should always be able to understand "why is opportunity A above opportunity B?"
- **Gate 5 — Acquisition Workflow & Monitoring.** *After Gate 4.* The buyer-facing persistent workflow layer: changed-opportunity feed, alerts, buyer-specific monitoring, acquisition-agent summaries, opportunity watchlists, investigation queues, pursue/verify/monitor workflow, review history, material-change explanations, "what changed since I last looked?", a weekly acquisition brief. **Distinct from Gate 2B-0B:** Gate 2B-0B asks *"did factual evidence change?"*; Gate 5 asks *"what should the buyer know or do because it changed?"* — Gate 5 does not duplicate Gate 2B-0B's lifecycle-detection responsibility, it consumes it. Built on the existing Gate 1/1C change-detection infrastructure, not a rebuild of it.

### Buyer-Specific Opportunity Universes — the long-term architecture

*(Product Owner architecture decision, following Product Owner review of the Gate 2B-0B architecture investigation.)* PropertyAIgent must no longer conceptually treat one global "Opportunity Universe" as the definitive set of opportunities for every user. An acquisition opportunity is inherently strategy-dependent: a development may be highly attractive to a regional housebuilder, too small for a national housebuilder, too advanced for a land buyer, increasingly attractive to a fund once construction begins, relevant to a Housing Association because of its affordable-housing component, or attractive to a strategic land promoter before any planning application exists at all. The long-term target architecture is:

```
SHARED MARKET EVIDENCE UNIVERSE
        ↓
TRUSTED FACTS + LIFECYCLE EVENTS
        ↓
SHARED CANDIDATE SIGNAL LAYER
        ↓
BUYER MANDATE
        ↓
PERSISTENT ACQUISITION AGENT
        ↓
BUYER-SPECIFIC OPPORTUNITY UNIVERSE
        ↓
PURSUE / VERIFY / MONITOR / NOT RELEVANT
        ↓
CONTINUOUS RE-EVALUATION
```

The governing principle is **collect/verify factual evidence once, interpret it for many buyers** — PropertyAIgent must never duplicate planning/market collection per buyer, and must never run a separate council-portal scraping process per Buyer Mandate. One factual change (e.g. a committee report recommending approval for an 82-unit scheme) is detected, ingested, extracted and reconciled exactly once; it is then evaluated differently downstream — potentially a strong opportunity for a regional housebuilder, not relevant for a national housebuilder below target scale, and a "monitor" candidate for a fund pre-construction — without three separate collection pipelines.

**Terminology (conceptual distinction, not a code/module rename):**

| Term | Meaning | Current status |
|---|---|---|
| **A. Market Evidence Universe** | All relevant shared planning, policy, ownership and development evidence known to PropertyAIgent | Built — everything under "Planning Intelligence," "Policy Intelligence," Gate 2B |
| **B. Shared Candidate Signal Universe / Layer** | Buyer-independent developments/sites displaying potentially acquisition-relevant signals | The current 389-record set (`app.reporting.opportunity_universe`) is closest to this concept |
| **C. Buyer Opportunity Universe** | The set of developments/opportunities currently considered relevant to one specific Buyer Mandate | Not yet built — this is the actual long-term product-level "Opportunity Universe"; depends on Buyer Mandate V2 and the Autonomous Acquisition Agent |
| **D. Active Acquisition Pipeline** | The subset of a buyer's Opportunity Universe currently classified for active attention (`PURSUE`/`VERIFY`/`MONITOR`) | Not yet built — depends on Gate 3/Gate 4 |

**The current 389 must not be described as "all schemes" or as "the definitive Opportunity Universe."** It is buyer-independent acquisition signal (concept B above), generated by the existing V1 detectors, current validated composition 389 total (160 planning/delivery, 229 strategic land; planning/delivery breaking down as 140 long-pending applications, 7 recent permissions, 5 approaching-lapse, 8 undeveloped-permission phase opportunities). No code or module is renamed to reflect this terminology now (`app.reporting.opportunity_universe` keeps its existing name) — this is a conceptual/documentation distinction, to be reflected in code only if and when a future gate is authorised to do so.

**Consequence for opportunity detection — global signal detectors ≠ complete definition of opportunity.** The existing V1 detectors (long pending, recent permission, approaching lapse, undeveloped permission, strategic land) remain useful, real signals and are **not removed**. But they must not become the permanent, total definition of what can be an acquisition opportunity: a recently submitted 80-unit application is none of the five existing detector kinds, yet may be highly relevant to a buyer seeking 50-150-unit residential schemes in that geography, willing to acquire pre-permission. The future Buyer Acquisition Agent (Gate 3) must be capable of identifying buyer-specific relevance from the broader Market Evidence Universe (A), not solely from the Shared Candidate Signal Layer (B) — see [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md), "Buyer Suitability Is Contextual, Not Universal," now extended by this decision from *scoring* an opportunity per buyer to *opportunity membership itself* being buyer-relative.

**Persistent Acquisition Agent principle.** Each Buyer Mandate should eventually have a persistent *logical* Acquisition Agent — "persistent" means the product retains enough state to maintain the buyer's acquisition intelligence over time, not that an LLM process runs continuously. Conceptually this state may include: the Buyer Mandate; the current Buyer Opportunity Universe; previous assessments; opportunities being monitored; outstanding verification/investigation requests; lifecycle changes since the last assessment; next-check priorities; recommendation history. Exact persistence/schema is **not approved by this documentation update** — this is a future implementation gate's own design decision. Target product behaviour: *"Since your last review: 3 opportunities entered your mandate, 2 materially improved, 1 deteriorated, and 4 monitored schemes had no meaningful change."* See [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7, "Lifecycle Watch," for the shared capability family this agent would consume rather than duplicate.

### Opportunity Dimensions — kept structurally separate, never mixed

*(Product Owner decision, post Gate 2B-2C — do not prematurely collapse any of these into one generic numerical opportunity score.)*

| Dimension | Values | Notes |
|---|---|---|
| **Buyer Fit** | `STRONG` / `POTENTIAL` / `WEAK` / `NOT SUITABLE` / `INSUFFICIENT EVIDENCE` | Built (Gate 1) as `STRONG_FIT`/`NOT_SUITABLE`/`INSUFFICIENT_EVIDENCE`; the fuller band set above is future refinement, not yet implemented |
| **Planning Readiness** | `EARLY` / `PROGRESSING` / `NEAR DECISION` / `PERMISSIONED` / `DELIVERY` | Not yet a named field — today's planning_state/lapse/build_status facts (Gate 2B) are the evidence it would be derived from |
| **Acquisition Readiness** | `HIGH` / `POTENTIAL` / `UNCLEAR` / `LOW` / `COMMITTED` | Depends on Gate 2C's Acquisition Position Intelligence |
| **Evidence Confidence** | `HIGH` / `MEDIUM` / `LOW` | Already a first-class, separately-tracked dimension in Trusted Operative Planning Facts (Gate 2B-2A) — never collapsed with freshness or relationship confidence |
| **Buyer Recommendation** | `PURSUE` / `VERIFY` / `MONITOR` / `NOT RELEVANT` | Gate 3 (Autonomous Acquisition Agent V1) output — an agent interpretation, never a fact |
| **Opportunity Type** | strategic land / long pending / recent permission / undeveloped permission / approaching lapse / future types | Built (Gate 1C) — a discovery-signal classification, not a complete acquisition judgement |

None of these fields is ever mixed into another. An opportunity's `Opportunity Type` never encodes its `Acquisition Position`; its `Acquisition Position` never encodes a `Buyer Recommendation`; a `Buyer Recommendation` is always specific to one buyer mandate, never a property of the opportunity itself.

### Trust Dimensions — kept structurally separate, never collapsed into one score

*(Already implemented, Gate 2B-2A — restated here as a standing principle for every future gate.)* **Evidence confidence** (high/medium/low), **evidence freshness** (how recently the authoritative evidence was verified — `status_verified_at`, never `last_seen_at`), and **relationship confidence** (how confidently an application/document/phase relates to the same operative development position — site-link method/confidence) are three separate dimensions, never combined into one generic confidence score. See [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md), "Trusted Opportunity Data".

### The Autonomy Principle

*(Product Owner decision, post Gate 2B-2C.)* PropertyAIgent should become increasingly autonomous — the intended long-term experience is *"give PropertyAIgent an acquisition strategy and it behaves like an always-on acquisition researcher."* This requires distinguishing **autonomous orchestration** from **authoritative fact creation**. The autonomous agent (Gate 3) may decide which opportunities deserve investigation, which schemes need fresher evidence, when to re-check, whether a new document deserves analysis, whether a planning change matters commercially, whether an opportunity should be promoted/downgraded, which buyer is likely to care, and what to investigate next. But the underlying factual states must remain evidence-backed, provenance-aware, reproducible, auditable and confidence-aware. Architecture: **agent decides what to investigate → trusted tool/capability retrieves evidence → deterministic/bounded extraction establishes facts → reconciliation establishes operative position → agent interprets commercial significance.** An unconstrained LLM must never become the system of record — see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7 for the full architecture this extends.

### Strategic Land Remains Core

The focus on planning applications and lapse/permission signals (Gate 2B) must not crowd out strategic land. PropertyAIgent continues to identify opportunities through adopted and emerging Local Plans, allocations, call-for-sites evidence, housing land supply, the Housing Delivery Test, NPPF/policy context, Green Belt/Grey Belt where relevant, and planning-policy change. Strategic land opportunities must eventually be assessed against Buyer Mandates in the same acquisition framework as planning-application-derived opportunities. **Planning permission is not required for every acquisition strategy.** NPPF/national and local policy intelligence remains an evidence layer supporting opportunity interpretation, not a destination in itself — see "Policy Intelligence" below; PropertyAIgent is not a generic planning-policy chatbot.

### Human-in-the-Loop

Increasing autonomy does not remove the acquisition professional. PropertyAIgent should automate search, monitoring, evidence collection, reconciliation, initial investigation, reassessment, prioritisation and recommended next action. The human remains responsible for consequential commercial decisions: contacting landowners, making offers, agreeing terms, committing capital, appointing advisers, acquisition approval. **AI does the continuous research. The human makes the commercial decision.**

### Commercial Product Experience

The eventual homepage/dashboard should increasingly answer *"what should I pursue today?"*, not *"how many database records do we have?"* — best current opportunities, newly discovered opportunities, materially changed opportunities, opportunities requiring verification, opportunities moving closer to acquisition, reasons for recommendation, evidence confidence, next actions. Database coverage remains operationally important but must not dominate the buyer experience.

### Later

**Comparable Evidence Agent.** Collects and structures relevant residential sales comparables, land comparables, rental comparables and investment evidence where appropriate. Not built before a plausible acquisition opportunity exists.

**Development Appraisal Agent.** Supports GDV, build-cost assumptions, affordable-housing effects, finance, developer margin, residual land value, scenario analysis. Deep financial appraisal remains later-stage — must not distract from opportunity identification and acquisition qualification.

**Delivery / Investment Acquisition Intelligence.** Future buyer types may include investment funds, BTR investors/operators, forward-funding buyers, forward-purchase buyers, housing associations, institutional investors — requiring stronger evidence around construction commencement, build progress, delivery programme, completion, tenure, uncommitted units, developer, funding/control, occupancy/stabilisation where relevant. Not implemented prematurely — see "The Development/Delivery-State Principle" in [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md).

**Weekly Planning/Acquisition Monitoring Agent** — *(superseded by the explicit Gate 2B-0B → Gate 3 → Gate 5 sequencing above; retained here only as the original roadmap-only concept this sequencing now formalises.)* Consumes Gate 2B-0B's lifecycle changes and Gate 2B's reconciled opportunity data to answer "what changed this week that matters?" — and, once Buyer Mandate V2 exists, "what changed this week that matters to Buyer X?" **The agent must never itself scrape or determine planning truth** — it is a consumer of the deterministic lifecycle/reconciliation layers beneath it, the same "agent reads, deterministic layers write" discipline as every other agentic capability in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) §7.

### Explicit Architectural Deferrals

*(Product Owner decision, post Gate 2B-2C — continue to defer unless specifically promoted through a future Product Owner gate.)* Persisted Scheme entity; a giant generic opportunity score; comprehensive development appraisal; a full comparable engine; universal autonomous web browsing; brute-force LLM analysis of the entire database; premature microservices architecture; a generic agent framework; a complete statutory planning-law engine; full phase-level construction tracking without evidence; a `NEARING_COMPLETION` state without supporting evidence; a full User/Organisation/auth redesign; speculative `AVAILABLE` classification; a giant advanced-filter Buyer Profile UI. Build only what advances acquisition intelligence.

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
| Scheme / Application / Phase Reconciliation | **CLOSED — merged (`e51f74b`, 2026-09-10), production-validated read-only against 7 Astra Sites** | Gate 2B-1 | `app.reporting.scheme_reconciliation` — deterministic, fact-level, computed/read-oriented, non-persisted; `planning_role` distinct from `application_category`; non-substantive guardrail; approved/proposed/superseded kept separate; residential-only + S73 safeguards; conflicts resolved by stronger evidence or surfaced. Carried-forward: AH scope not decided-state-aware; World of Pets extraction-quality (separate) |
| Trusted Operative Planning Facts | **CLOSED** | Gate 2B-2A | `build_operative_planning_facts` — computed, non-persisted, scope-aware; consented vs active positions; decided-state-aware AH; relationship confidence + freshness as separate provenance dimensions; individual dwelling plots never promoted as acquisition peers |
| Trusted Consumer Alignment | **CLOSED** | Gate 2B-2B.1 | Buyer Fit, Site Profile Structured Summary and Affordable Homes tile migrated onto Trusted Operative Planning Facts; hardcoded `PERMISSION_GRANTED` fallback removed |
| Acquisition Opportunity Scope Alignment | **CLOSED** | Gate 2B-2B.2 | Acquisition opportunities scoped to whole-site/material-phase/parcel, never an individual dwelling plot; controlled monitoring-transition mechanism (`app.reporting.opportunity_monitoring_transition`) introduced |
| Planning Signal Consumer Alignment | **CLOSED — merged `1eb7e5f`** | Gate 2B-2C | `resolve_operative_lapse_anchor` — lapse/recent-permission/undeveloped-permission/approaching-lapse signals use the trusted substantive permission; `NOT_GRANTED` vs `NOT_DETERMINED` distinguished; 11 false RECENT_PERMISSION + 8 false UNDEVELOPED_PERMISSION/APPROACHING_LAPSE opportunities corrected |
| Application Lifecycle Intelligence | **NEXT — architecture investigation required** | Gate 2B-0B | Promoted ahead of Gate 2C; durable lifecycle-change detection/history/propagation, building on 2B-0A; no schema/implementation authorised yet |
| Acquisition Position Intelligence | **Not yet built** | Gate 2C | After Gate 2B-0B; availability must never be inferred from silence |
| Opportunity Analyst | **Not yet built** | 1.5 / superseded by Acquisition Agent V1 | Depends on Phase 1 Opportunity Validation's findings; not built ahead of it |
| Planning due diligence | **Not yet built** | 1.5 | A deeper mode of the Opportunity Analyst, not a separate agent |
| Buyer Mandate V2 | **Not yet built** | After Gate 2C | Extends Buyer Profiles V1 into a reusable, natural-language-inspectable acquisition mandate |
| Acquisition Agent V1 | **Not yet built** | Gate 3, after Buyer Mandate V2 | One reusable `AcquisitionAgent(buyer_mandate, opportunity)` capability — the acquisition-first evolution of the Buyer/Opportunity Analyst concepts above |
| Acquisition Prioritisation | **Not yet built** | Gate 4, after Gate 3 | Explainable dimensions/bands (Buyer Fit, Planning Readiness, Acquisition Readiness, Evidence Confidence) — no premature numeric score |
| Acquisition Workflow & Monitoring | **Not yet built** | Gate 5, after Gate 4 | Buyer-facing "what should I know or do" layer, distinct from Gate 2B-0B's factual change detection |
| Market/comparables | **Not started** | 2 | No sales, rental or comparable data flows into the platform today |
| Development appraisal | **Not started** | 2 | Hard-blocked on Market Intelligence existing first |
| Market/Investment Analyst | **Not started** | 2 | Depends on structured market evidence + deterministic appraisal existing first |

---

## Recommended Next Task

**Gate 2B-0B — Application Lifecycle Intelligence (architecture investigation only).** Gate 2B is fully closed (2B-0A through 2B-2C, production merge `1eb7e5fb1540127c20b0da88205b9f0e95120da1`, live at `propertyaigent.onrender.com`). Promoted ahead of Gate 2C by Product Owner decision: the platform can now reliably answer "what does the planning evidence mean?" but not yet "has that evidence changed since we last checked?" The next task is an architecture investigation only — see "Gate 2B-0B — Application Lifecycle Intelligence (NEXT)" above for the full required-investigation scope. **Do not implement Gate 2B-0B yet; no schema or code change is authorised until that investigation is reviewed by the Product Owner.** Separately: platform-wide scheduled status verification stays fail-closed until the production daily-scrape scheduler is proven healthy (operational dependency, not Gate 2B feature work).
