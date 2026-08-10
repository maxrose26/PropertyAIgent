# PropertyAIgent — Platform Architecture

This document describes the platform **functionally** — what each capability is for, what it does today, what it will do, and what it depends on — not the code layout. For the technical/module-level view of what exists today, see [ARCHITECTURE_STATUS_v2.md](ARCHITECTURE_STATUS_v2.md). For the vision these capabilities serve, see [PRODUCT_VISION.md](PRODUCT_VISION.md). For sequencing, see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).

The platform is organised into six capability areas, each building on verified evidence from the one before it:

`Planning Intelligence → Policy Intelligence → Market Intelligence → Development Economics → AI Decision Support → Workflow & Collaboration`

All six sit on top of one shared technical foundation — the **Evidence Platform** (§0 below) — rather than each re-implementing document handling, monitoring, extraction and review from scratch.

---

## 0. The Evidence Platform (Common Foundation)

**Purpose:** Provide the shared technical machinery that every capability above depends on to turn a source document into a trustworthy, traceable fact. This is not a seventh product capability — a user never "opens the Evidence Platform" the way they'd open Policy Intelligence — it is the common foundation the other six are built on, described here so its scope and boundaries are explicit rather than left implicit inside each capability's own section.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Planning Intel.  Policy Intel.  Market Intel.  Dev. Economics       │
│  AI Decision Support           Workflow & Collaboration              │
└───────────────────────────────┬───────────────────────────────────┘
                                 │  every capability consumes, none reimplements
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        THE EVIDENCE PLATFORM                         │
│                                                                        │
│  Document discovery  →  Source monitoring  →  AI extraction           │
│         │                                          │                  │
│         ▼                                          ▼                  │
│  Visual evidence                              Provenance              │
│  (page detection, render,                     (source, page, hash,    │
│   classify, match)                             method, confidence)    │
│         │                                          │                  │
│         └──────────────────┬───────────────────────┘                 │
│                             ▼                                         │
│                    Review workflows                                   │
│                (needs_review → approve/reject,                       │
│                 confirm/reject image)                                │
│                             │                                         │
│                             ▼                                         │
│                    Version history                                    │
│           (AllocationVersion, StatusHistory,                          │
│            LocalPlanFieldHistory — never overwritten)                │
└─────────────────────────────────────────────────────────────────────┘
```

**Current capabilities (all implemented, all already in production use):**

- **Document discovery** — deterministic, keyword-based discovery and classification of policy documents and reports (`app/policy/document_discovery.py`, `document_types.py`), never AI-crawled.
- **Source monitoring** — content-hash-based change detection for registered sources and reports, cadence-gated so a scheduled check does near-zero work when nothing is due (`app.policy.monitor`, `MonitoredSource`, `MonitoredReport`).
- **AI extraction** — structured-output-only extraction (scheme intelligence, policy evidence, allocation identifiers), never freeform generation of facts, always schema-validated.
- **Provenance** — every extracted or matched fact retains its source document, page, file hash, extraction method/model/prompt version and confidence, whether or not the fact resolved to a confident match.
- **Review workflows** — every ambiguous or trust-sensitive fact is written as a proposal (`PolicyChangeEvent`, or a row already carrying `review_status="needs_review"`), resolved only by a small number of explicit human-triggered functions (`approve_change`/`reject_change`, `confirm_image`/`reject_image`).
- **Version history** — approval always snapshots the pre-change value first (`AllocationVersion`, `LocalPlanStatusHistory`, `LocalPlanFieldHistory`); nothing is silently overwritten, and a changed source supersedes rather than replaces its prior evidence.
- **Visual evidence** — deterministic candidate-page detection, subprocess-isolated rendering, AI vision classification into a fixed type vocabulary, and deterministic (never AI-guessed) matching back to the object the image is evidence for.

**Dependencies:** None — this is the platform's technical bedrock, built once and consumed by every capability layer above it. Each of the six capability sections below notes, in its own "Dependencies," where it draws on the Evidence Platform rather than repeating this list per layer.

---

## 1. Planning Intelligence

**Purpose:** Understand what is happening on a Site — what has been applied for, approved, built, and by whom.

**Current capabilities:**
- Multi-year scraping of planning applications across 10 Greater Manchester councils, spanning three distinct portal systems (Idox, Idox+Anite for Bury's legacy document store, Arcus/Salesforce Experience Cloud for Salford/Rochdale/Manchester), config-driven per council rather than hardcoded.
- Unit-count qualification filtering, applied before documents are even downloaded, so effort is spent only on schemes that meet the platform's threshold.
- AI-assisted document extraction and reconciliation of scheme intelligence (unit counts, tenure split, development type, developer/agent) from planning documents, with a priority-ordered merge and cross-check between AI-derived, regex-derived and portal-native figures.
- Site consolidation — tiered, confidence-scored linking of multiple related planning applications (outline, reserved matters, discharge of conditions, EIA screening/scoping) to one physical Site, so a lead list shows one opportunity once, not three times.
- Phase tracking — grouping and labelling a multi-phase scheme's applications under its one Site.
- Build-status tracking via EPC Open Data lookups (has this Site actually been built out), and map geocoding via postcodes.io.
- Companies House enrichment (name matching, officers, PSC, cross-appointments) and on-demand contact discovery (Apollo/Hunter), scoped per company rather than run automatically for every scraped scheme.
- **Residential Mix Intelligence** (a specialist module within this layer, not a separate capability) — transforms a Site's already-reconciled scheme data into structured residential-composition evidence: affordable-homes count/percentage (stated vs. calculated, with an explicit review state for ambiguous or conflicting evidence — never a guessed unit count, never missing shown as zero), evidenced affordable tenure categories, and a deterministic "Structured summary" of these facts. Sourced entirely from the one current/preferred Application version for a Site (never blended across scheme versions) via the platform's existing scheme reconciliation, not a new extraction pipeline. **Phase 1** (current): structured mix, affordable provision, tenure, evidence, commentary — with bedroom mix and a quantified house/flat/bungalow split honestly reported as not yet extracted, since no such extraction exists on this platform today. **Future phases**: bedroom-mix and housing-type extraction; market comparison (Market Intelligence); Local Plan affordable-policy target comparison; mix sensitivity/optimisation (Development Economics). Designed for reuse beyond Site Profile — Reports, Planning Statements, Market Intelligence comparisons, Development Economics, AI Decision Support — none of which are built yet.
- **Production scheduling and scraper freshness** (Pilot Readiness PR-2, "Production Freshness & Core Data Integrity") — the per-council scraper (`app.pipeline.run_weekly`) is a single, reusable entry point invoked in a loop by `scripts/run_daily_councils.py`, one subprocess per council, isolated so one council failing never blocks the rest (Part 5). Production execution is a Render Cron Job defined in `render.yaml` (repository-side configuration only — the Blueprint must still be manually synced in the Render dashboard by an operator with access, and no code in this repository can confirm it is actually running; see that file's own header for the exact manual steps). Distinct from `scripts/register_weekly_task.ps1`, which remains a **local-development-only** mechanism (Windows Task Scheduler) predating the production Cron Job and not itself production infrastructure. Scraper *execution health* is tracked independently of *source activity* (`app.db.models.ScrapeRun`, one row per attempted council per run) — a council with a healthy run that finds zero new Applications is not the same fact as a council whose scraper has silently stopped running, and conflating the two was an identified pilot-readiness risk. `app.pipeline.freshness.classify_scraper_freshness` turns the most recent successful `ScrapeRun` into FRESH (≤48h) / WARNING (48–72h) / STALE (>72h) / UNKNOWN (no run evidence at all — never defaulted to STALE), surfaced on the Council Operations page's "Planning Application Scraper Health" table (`app.reporting.scraper_health`) — the operator-facing way to verify freshness without querying the database directly.

**Future capabilities:**
- Appeals history as a first-class signal (a refused/appealed site is a different opportunity than a clean one).
- Constraint layers — Green Belt, flood risk, conservation areas, listed buildings, biodiversity — as their own queryable intelligence, not just narrative mentions inside a policy document.
- Portal-native commencement/discharge-of-conditions signals used as a second, independent build-status check alongside EPC data.
- National rollout beyond Greater Manchester's 10 councils.
- Residential Mix Intelligence Phase 2+: structured bedroom-mix and house/flat/bungalow-type extraction, market comparison, Local Plan affordable-policy target comparison, mix sensitivity/optimisation (see above).

**Dependencies:** The Evidence Platform (§0) for document discovery, AI extraction and provenance. Beyond that, none — this is the platform's foundation capability layer. Every other layer either enriches a Site that Planning Intelligence first identified, or (for Policy Intelligence's allocations) supplies the raw material a Site can later be matched against.

---

## 2. Policy Intelligence

**Purpose:** Understand the planning policy position — what a Local Plan or joint development plan says is intended for this Site or the area around it, and how confident that is.

**Current capabilities:**
- A `LocalPlan` → `LocalPlanSite` ("Allocation") model capturing plan-level status, housing requirement/delivery/five-year-supply evidence, and per-allocation policy reference, capacity, status and progression signal.
- Joint-plan support — a genuinely multi-authority plan (Places for Everyone: 9 Greater Manchester authorities, one adopted plan) is represented once and linked to every participating council, never duplicated per authority.
- Allocation-to-allocation relationships, recording that two allocations (often across two different plans) refer to the same physical site, reference one another, or are jointly delivered — without ever merging the underlying records.
- Change protection — every ingestion or monitoring pass writes ambiguous or status-changing facts as a reviewable proposal, never mutating trusted state directly; only two explicit human-triggered functions can resolve one.
- Ongoing monitoring — content-hash-based change detection for registered policy sources and reports, cadence-gated so a scheduled run does near-zero work when nothing is due.
- Policy document coverage tracking (Expected → Discovered → Downloaded → Registered → Ingested → Evidence Extracted) surfaced as "what are we missing" per council.
- AI Local Plan Summary — a narrative synthesis of a plan's own verified evidence, regenerated only when the underlying evidence actually changes.
- Visual evidence — deterministic detection of allocation-bearing pages in policy PDFs, AI classification of what a rendered page shows, and deterministic (never AI-guessed) matching of a page to the specific allocation it belongs to.
- Live coverage: Bury and Stockport fully onboarded with their own Local Plans; Places for Everyone's correct 9 participating authorities (Bolton, Bury, Manchester, Oldham, Rochdale, Salford, Tameside, Trafford, Wigan — corrected by Pilot Readiness PR-2, "PfE Authority Integrity", after PR-1's audit found Manchester missing and Stockport incorrectly included in `LocalPlanCouncil`; verified against the adopted plan document's own title page) are linked to the plan. Of the 8 authorities with no independent Local Plan of their own, 7 (Bolton, Oldham, Rochdale, Salford, Tameside, Trafford, Wigan) have their PfE allocations already onboarded; Manchester is correctly linked to the plan but has zero allocations ingested yet — a known PR-3 ("Greater Manchester Local Plan Coverage") item, deliberately not actioned in PR-2's metadata-only scope.

**Future capabilities:**
- NPPF and national Planning Practice Guidance as a queryable, versioned policy layer (today the platform only tracks each council's own plans, not the national framework they sit inside).
- Supplementary Planning Documents and Design Codes, as their own monitored document type.
- Appeal decisions linked back to the policy they tested.
- Independent Local Plan monitoring for the 8 Greater Manchester authorities currently known to the platform only through Places for Everyone (Bolton, Manchester, Oldham, Rochdale, Salford, Tameside, Trafford, Wigan).

**Dependencies:** The Evidence Platform (§0) — this layer is the Evidence Platform's heaviest consumer today (monitoring, review workflow, version history and visual evidence were all built primarily to serve Policy Intelligence first). Also builds on Planning Intelligence's Site records (an allocation is only actionable once it can be matched to, or distinguished from, a real scraped Site) but is independently valuable even before that match exists — an allocation is real policy intent whether or not an application has been submitted against it yet.

---

## 3. Market Intelligence

**Purpose:** Understand what can be built and what it is worth.

**Current capabilities:** None. This layer has not yet been built. No sales, rental, land-value, or comparable-scheme data currently flows into the platform.

**Future capabilities:**
- Residential and commercial sales values (new-build and general market).
- Land Registry Price Paid Data as a land-value and disposal-comparable source.
- Rental evidence and sales-rate/absorption data for build-to-rent and for-sale schemes.
- Development comparables — genuinely similar nearby schemes, their product mix, and their outcomes.
- Land values, build costs, and regional cost adjustments as structured, queryable figures rather than narrative.
- **Ownership Intelligence** — a future specialist module within this layer (recorded by `specifications/005-entity-search-allocation-refinement.md`'s Sprint 4.5b Product Owner amendment; canonical location per that amendment's Part 3 — this is the source of truth, not `specifications/001-platform-vision.md`, which is historical/superseded). Purpose: identify registered land/title ownership relevant to a Development Site or Local Plan allocation, support land assembly and acquisition research, and connect corporate proprietors to future Company Intelligence. Dependency chain: reliable Site/allocation geometry → HM Land Registry title polygon intersection → spatial intersection → title identification → proprietor evidence → Ownership Intelligence. Current limitations, explicit rather than implied: allocation polygon geometry is not available platform-wide; some allocations only carry a point coordinate (`LocalPlanSite.latitude`/`longitude`); a point coordinate alone is not sufficiently reliable for ownership attribution (it can fall inside the wrong title's boundary near any parcel edge); ownership matching is therefore **not yet implemented** — this is architecture/documentation only, not scheduled work. Not a seventh top-level platform capability — it enriches the existing Site/Policy domain objects, per the domain model's own "Future Expansion" principle.

**Dependencies:** The Evidence Platform (§0), for the same document discovery/monitoring/extraction/provenance machinery already proven by Policy Intelligence. Also builds on Planning Intelligence (what physically exists nearby, to compare against) and Policy Intelligence (what a Site is actually allocated/permitted for, which determines which comparables are even relevant). Market Intelligence is itself a hard dependency of Development Economics below — no residual appraisal is credible without real values and costs behind it.

---

## 4. Development Economics

**Purpose:** Determine whether a development is commercially viable.

**Current capabilities:** None. This layer has not yet been built.

**Future capabilities:**
- Residual land value appraisal and Gross Development Value (GDV) calculation.
- Developer profit and sensitivity analysis (cost, value and timing flex).
- Planning obligations modelling — CIL, Section 106, affordable housing requirements, Biodiversity Net Gain, education/highways/open-space/monitoring contributions.
- Full viability assessments, output in a form that mirrors what a real viability report contains.

**Dependencies — this is a composite layer, not a standalone one.** Beyond the Evidence Platform (§0) itself, Development Economics only produces a credible answer when it draws on all three capability layers beneath it together:

- **Planning Intelligence** — what is actually being proposed or could be proposed (units, mix, scale).
- **Policy Intelligence** — what obligations and policy requirements actually apply to this Site (affordable housing %, CIL rate, planning constraints that add cost).
- **Market Intelligence** — what it will sell/let for, and what it will cost to build.

Development Economics must never be designed, built, or described as a standalone capability that could exist without Market Intelligence underneath it — a residual appraisal with invented or unsourced values and costs is worse than no appraisal at all, since it would look authoritative without being evidenced.

---

## 5. AI Decision Support

**Purpose:** Interpret evidence rather than replace professional judgement.

**Current capabilities (embryonic form of this layer):**
- AI Local Plan Summary — already a real instance of "AI interprets verified evidence into prose," gated so it only regenerates when evidence changes.
- AI scheme status summaries per Site, generated from already-reconciled scheme intelligence.
- Visual page classification — AI interprets what a rendered image shows, strictly bounded to a fixed vocabulary, never used to decide *which* Site or allocation it belongs to (that step stays deterministic).

These are narrow, single-purpose predecessors of the full AI Decision Support layer envisioned below — proof that the "interpret verified evidence, never invent it" discipline works in production, not yet the cross-layer synthesis this capability is meant to become.

**Future capabilities:**
- Planning assessments and planning balance — weighing the evidence Policy Intelligence has already gathered, not originating new policy claims.
- Planning strategy, planning statements and supporting statements for a real submission.
- Executive reports, Call for Sites submissions, and site promotion documents.
- Investment/pursue recommendations synthesised across Planning, Policy, Market and Development Economics evidence.

Every output at this layer must explain its conclusion using evidence gathered by the layers beneath it, with a traceable path back to source — never a claim the earlier layers cannot support.

**Dependencies:** Planning Intelligence, Policy Intelligence, Market Intelligence and Development Economics, in that order — AI Decision Support is the synthesis layer sitting on top of all four, and its outputs are only as trustworthy as the evidence underneath them. Also depends directly on the Evidence Platform's (§0) provenance and AI-extraction discipline: every synthesis output here must cite evidence the same way every lower-layer fact already does.

---

## 6. Workflow & Collaboration

**Purpose:** Let a team act on the evidence and judgement the other five layers have produced.

**Current capabilities:** None as a customer-facing layer. (The platform's internal human-review workflow — approving or rejecting an ambiguous fact, confirming or rejecting a matched image — is a *data-quality* mechanism inside Policy Intelligence and Planning Intelligence, not this operational layer; see [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) for that review discipline.)

**Future capabilities:**
- Saved sites and watchlists.
- Lightweight CRM around the companies and contacts Planning Intelligence already discovers.
- Task tracking against a Site or a pipeline of Sites.
- Client-facing reporting, and team collaboration on a shared pipeline.

**Dependencies:** Every capability layer beneath it, and — for its review/task-state needs specifically — the Evidence Platform's (§0) existing review-workflow pattern is the likely model to extend rather than replace. Workflow & Collaboration has nothing to operate on until there is real Site intelligence, evidence and (eventually) judgement to act on — it is deliberately the last layer built, not the first.
