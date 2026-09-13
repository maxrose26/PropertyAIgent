# PropertyAIgent — Platform Architecture

This document describes the platform **functionally** — what each capability is for, what it does today, what it will do, and what it depends on — not the code layout. For the technical/module-level view of what exists today, see [ARCHITECTURE_STATUS_v2.md](ARCHITECTURE_STATUS_v2.md). For the vision these capabilities serve, see [PRODUCT_VISION.md](PRODUCT_VISION.md). For sequencing, see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).

The platform is organised into six capability areas, each building on verified evidence from the one before it:

`Planning Intelligence → Policy Intelligence → Market Intelligence → Development Economics → AI Decision Support → Workflow & Collaboration`

All six sit on top of one shared technical foundation — the **Evidence Platform** (§0 below) — rather than each re-implementing document handling, monitoring, extraction and review from scratch.

*(Added at the Product Vision & Roadmap Refresh, post–Opportunity Experience V2: a seventh section, §7 "Agentic Reasoning," sits alongside this stack, not after it in the same linear sequence — it is the cross-cutting discipline for how AI reasoning is allowed to consume the six capability areas' own structured facts, wherever in the stack that reasoning happens. See §7 for the full guardrail and the three agentic capabilities it currently justifies.)*

## The Acquisition-First Conceptual Architecture

*(Added at the Acquisition-First Roadmap Alignment. This is the same six-layer capability stack above, redrawn along the acquisition journey the Product Vision now states as the commercial outcome — see [PRODUCT_VISION.md](PRODUCT_VISION.md), "The Acquisition-First Commercial Outcome." It does not replace the six-layer stack; every box below is built from capability that already lives inside one of those six layers or the Evidence Platform beneath them.)*

```
PLANNING + OWNERSHIP + DEVELOPMENT EVIDENCE      BUILT   (§0, §1, §2 — Evidence Platform, Planning Intelligence, Policy Intelligence)
        ↓
TRUSTED OPERATIVE OPPORTUNITY FACTS              BUILT, CLOSED (Gate 2B, all six sub-gates — see "Trusted Opportunity Data" below)
        ↓
OPPORTUNITY DETECTION                            BUILT, CLOSED (Gate 1 + Gate 1C — opportunity universe, fingerprinting, change detection; corrected onto the trusted facts above by Gate 2B-2B.2/2B-2C)
        ↓
APPLICATION LIFECYCLE INTELLIGENCE               NEXT    (Gate 2B-0B — architecture investigation only, not yet implemented; promoted ahead of Gate 2C)
        ↓
ACQUISITION POSITION INTELLIGENCE                FUTURE  (Gate 2C — after Gate 2B-0B)
        ↓
BUYER MANDATE                                    PARTIAL (Buyer Profiles V1 built/closed — Gate 1; Buyer Mandate V2 extension FUTURE, after Gate 2C)
        ↓
DETERMINISTIC BUYER FIT                          BUILT   (`app.policy.buyer_matching.assess_buyer_fit`)
        ↓
AUTONOMOUS ACQUISITION AGENT                     FUTURE  (Gate 3 — Autonomous Acquisition Agent V1, after Buyer Mandate V2; see "The Autonomy Principle" in §7)
        ↓
PURSUE / VERIFY / MONITOR / NOT RELEVANT         FUTURE  (Gate 3's own output — names provisional)
        ↓
PRIORITISED BUYER OPPORTUNITY PIPELINE           FUTURE  (Gate 4 — Acquisition Prioritisation — explainable bands, not a premature numeric score)
        ↓
CONTINUOUS MONITORING + ALERTS + WORKFLOW        PARTIAL (deterministic change detection built — Gate 1/1C; Gate 5 — Acquisition Workflow & Monitoring — FUTURE, distinct from Gate 2B-0B's factual change detection)
        ↓
HUMAN ACQUISITION DECISION                       ALWAYS HUMAN (never automated — see "Evidence-First, Agent-Assisted, Human-Decided", PRODUCT_VISION.md)
```

**Buyer-specific opportunity universes (Product Owner architecture decision, post Gate 2B-0B investigation) — reading the diagram above in those terms:** the top three boxes (planning+ownership+development evidence → trusted operative opportunity facts → opportunity detection) together are the **Market Evidence Universe** and, at the "opportunity detection" box specifically, the **Shared Candidate Signal Universe/Layer** — buyer-independent, collected and verified exactly once. Everything from "Buyer Mandate" downward is where a **Buyer Opportunity Universe** (the buyer-specific reinterpretation of that same shared evidence) and, at "Pursue/Verify/Monitor/Not Relevant," the buyer's own **Active Acquisition Pipeline** are produced. PropertyAIgent must never duplicate the top three boxes per buyer — one factual change is detected once and evaluated differently downstream, per buyer. See [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), "Buyer-Specific Opportunity Universes," for the full terminology (Market Evidence Universe / Shared Candidate Signal Universe / Buyer Opportunity Universe / Active Acquisition Pipeline) and for why the current 389-record opportunity set must not be described as "the definitive Opportunity Universe." "Lifecycle Watch" (§7, below) is the shared capability family that keeps the top three boxes current for every buyer at once, rather than each Buyer Opportunity Universe re-deriving freshness independently.

The AI agent layer (Gate 3) does not replace this evidence architecture — it orchestrates trusted capabilities and interprets their commercial meaning. See "The Autonomy Principle" (§7) for the architecture this requires: agent decides what to investigate → trusted tool/capability retrieves evidence → deterministic/bounded extraction establishes facts → reconciliation establishes operative position → agent interprets commercial significance.

See [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) for the gate sequence that closes each NEXT/FUTURE gap, in order.

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
- **Production scheduling and scraper freshness** (Pilot Readiness PR-2, "Production Freshness & Core Data Integrity") — the per-council scraper (`app.pipeline.run_weekly`) is a single, reusable entry point invoked in a loop by `scripts/run_daily_councils.py`, one subprocess per council, isolated so one council failing never blocks the rest (Part 5). Production execution is two separate Render Cron Jobs defined in `render.yaml` (repository-side configuration only — the Blueprint must still be manually synced in the Render dashboard by an operator with access, and no code in this repository can confirm it is actually running; see that file's own header for the exact manual steps and required deployment order). Distinct from `scripts/register_weekly_task.ps1`, which remains a **local-development-only** mechanism (Windows Task Scheduler) predating the production Cron Jobs and not itself production infrastructure. Scraper *execution health* is tracked independently of *source activity* (`app.db.models.ScrapeRun`, one row per attempted council per run) — a council with a healthy run that finds zero new Applications is not the same fact as a council whose scraper has silently stopped running, and conflating the two was an identified pilot-readiness risk. `app.pipeline.freshness.classify_scraper_freshness` turns the most recent successful `ScrapeRun` into FRESH (≤48h) / WARNING (48–72h) / STALE (>72h) / UNKNOWN (no run evidence at all — never defaulted to STALE), surfaced on the Council Operations page's "Planning Application Scraper Health" table (`app.reporting.scraper_health`) — the operator-facing way to verify freshness without querying the database directly.
- **Daily Discovery / Intelligence Processing split** (Pilot Readiness PR-2 final pre-merge amendment, "Continuous Intelligence Processing") — the daily cron is deliberately split into two independent Cron Jobs rather than one, for fault isolation and cost control. **Daily Discovery** (`scripts/run_daily_councils.py`, 05:00 UTC) is deterministic discovery/document-collection/site-linking only (`--skip-extraction --skip-scheme-summary`, passed automatically to every `run_weekly.py` subprocess unless an operator opts in with `--include-ai-stages`) — it does not require `OPENAI_API_KEY` at all. **Intelligence Processing** (`scripts/run_intelligence_processing.py`, 07:00 UTC, two hours later so a normal Discovery run has time to finish first — though the two jobs are not otherwise coupled, and a failed or slow Discovery run never blocks Intelligence Processing from clearing whatever backlog already exists) reuses `run_weekly.py`'s own `stage_extraction`/`stage_generate_scheme_summaries` functions unchanged, bounded per run by `PROPERTYAIGENT_MAX_EXTRACTIONS_PER_RUN`/`PROPERTYAIGENT_MAX_SUMMARIES_PER_RUN` (default 20/20 each, applied across all councils combined, not per council) so a large backlog is drained over several bounded runs rather than in one unbounded burst of OpenAI spend. It reads `OPENAI_API_KEY` only when there is genuinely outstanding work to do this run (a zero-backlog run never touches that variable). Writes one `app.db.models.IntelligenceRun` row per invocation (attempted/succeeded/failed counts for both extraction and summaries, backlog remaining, timestamp) — the same append-only observability pattern as `ScrapeRun`, surfaced the same way (logs / Council Operations, not a new dashboard).
- **Database schema deployment: startup verification vs. explicit migration** (Pilot Readiness PR-2 final pre-merge amendment, "Database Migrations Must Not Be A Page-Load Side Effect") — `app.db.session.init_db()`, called on every ordinary process startup (first Streamlit page load per server process, every `run_weekly.py`/`run_daily_councils.py`/`run_intelligence_processing.py` invocation), no longer mutates a production (PostgreSQL) schema. On SQLite (local dev/tests) it still auto-creates any missing table/column, exactly as before — there is no real "customer" on a developer's own throwaway database. On PostgreSQL it performs a **read-only** check (`app.db.session.verify_schema`) and raises `SchemaVerificationError` loudly if the connected database is missing a table or column the current models declare, rather than silently altering production schema on a normal request. The actual schema evolution now only ever happens via the explicit, operator-invoked `python -m scripts.migrate_schema` (`app.db.session.migrate_schema` — idempotent, transactional, logs every table created/column added), with `python -m scripts.verify_schema` as a companion read-only sanity check (exit 0 = current, exit 1 names exactly what's missing). Required production deployment order: (1) make the migration command available (ship the code), (2) run `python -m scripts.migrate_schema`, (3) run `python -m scripts.verify_schema` to confirm, (4) start/restart the Streamlit web service, (5) allow the Cron Jobs to run. No Alembic or other migration framework was introduced — the underlying diff-and-`ALTER TABLE` mechanism predates this amendment (Pilot Readiness PR-2 pre-merge architecture check) and was already dialect-agnostic; this amendment only changes *when* it is allowed to run automatically. Production deployments should be verified by comparing the merged master SHA with the deployed production SHA (the running commit is shown in the Streamlit app footer via `RENDER_GIT_COMMIT`).
- **Render Cron Job Playwright build hotfix** — Daily Discovery's first real Blueprint sync failed at build time (`playwright install --with-deps chromium` tries to apt-get Chromium's OS-level shared libraries via a root/sudo/su escalation Render's native Python build container doesn't support interactively). Fixed by dropping `--with-deps` (`playwright install chromium` alone only downloads the binary over HTTP, no root involved) followed by a build-time canary, `python -m scripts.verify_browser_runtime`, that launches and closes headless Chromium so a still-missing OS shared library becomes an explicit build failure instead of a cryptic scrape failure discovered only at the next scheduled run. Playwright is required unconditionally for Daily Discovery — every council (`idox`/`idox_anite`/`arcus` `doc_system` alike) is scraped through the one shared Chromium session `run_weekly.py`'s own `main()` opens. Intelligence Processing's build deliberately installs no browser at all — it never launches one. See `render.yaml`'s own header for the full diagnosis and the documented Docker/official-Playwright-image escalation path if a still-missing shared library is ever found after this fix.

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
- Allocation-to-Site relationships (`AllocationSiteRelationship`) — an evidence-backed, human-reviewable many-to-many link between a Local Plan allocation and the real scraped Site(s) it corresponds to, with an explicit `auto_applied`/`confirmed`/`needs_confirmation`/`rejected` trust boundary; deterministic development-coverage arithmetic (identified/residual capacity, coverage percentage/classification) built on top of it.
- Ownership & Control evidence (`ControlRelationship`) — Site/Application-scoped, evidence-backed ownership/developer/applicant/promoter role intelligence, with the same trust-boundary treatment and a fixed, non-inferred role vocabulary (S106 Owner/Developer/Mortgagee, Certificate A "planning ownership declaration", etc.).
- **Applicant Intelligence (Gate 2A) — CLOSED.** `app.reporting.applicant_intelligence` / `app.reporting.applicant_identity`, persisted to `ApplicantIntelligence`. Entity-level (one resolved identity — a Companies-House-matched `Company` or a name-based identity — carries one classification, reused across every opportunity it appears on, never re-derived per application); reusable; evidence-grounded (OpenAI Responses API + native web_search, validated against a whitelist of evidence refs the model was actually given, with a deterministic evidence-sufficiency confidence ceiling applied afterward — a claim's confidence can only ever be downgraded, never upgraded, relative to what the model itself asserted); bounded (scoped to identities linked to a *current* planning-application opportunity — long-pending application, recent permission, undeveloped permission or approaching lapse; a strategic-land-only allocation is never researched); privacy-aware (an identity confidently shaped like a named individual takes a zero-cost, zero-web-research deterministic `PRIVATE`/`not_researched` path, never profiled). Primary taxonomy: `HOUSEBUILDER · DEVELOPER · PROMOTER · PUBLIC_SECTOR · HOUSING_ASSOCIATION · ESTATE · SPV · PRIVATE · FUND_INVESTOR · LANDOWNER_PROPERTY_COMPANY · CONTRACTOR · CHARITY_INSTITUTION · PROFESSIONAL_CONSULTANT · NOT_DETERMINED` — a separate `is_spv` flag and `parent_group` field capture *structure* (is this entity a special-purpose vehicle, does it have a known parent) independently of the *commercial role* `primary_type` describes. **Applicant Intelligence is not the Acquisition Agent** — it is platform intelligence the future Acquisition Position Intelligence (see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)) and Acquisition Agent reason *over*, the same relationship Strategic Land Intelligence has to the Opportunity Analyst. The full eligible production population (188 identities: 170 organisation-shaped, 18 private-person-shaped) has been bootstrapped and validated — see "Known V1 limitations" below.

  **Known Applicant Intelligence V1 limitations** (measured during production validation, not fixed in this documentation task — recorded so no downstream system relies on an assumption the evidence doesn't support):
  - **Parent/group structural completeness.** A real parent/group relationship is sometimes correctly identified in the model's own narrative and evidence but not populated into the structured `parent_group` field — production QA found only ~14% of apparent parent relationships captured structurally. **`parent_group = null` must never be read as "this entity has no parent/group relationship" — it means UNKNOWN / NOT ESTABLISHED**, not "independent."
  - **Confidence / evidence-ref under-linking.** The model can find genuinely strong external evidence but cite a weaker internal reference for the primary classification; the deterministic confidence ceiling then conservatively downgrades an otherwise-good classification. Accepted as safe-direction behaviour (a claim is never upgraded beyond what its cited evidence supports).
  - **Source authority is not the same as claim support.** A source *type* being authoritative (e.g. a Companies House record) does not automatically mean every claim attributed to it is strongly evidenced — production QA found one isolated case where a company's own registered SIC classification did not actually support the commercial role the model asserted from it, yet the confidence ceiling (which reasons about source-type tier, not per-claim semantic content) let a HIGH confidence through. This is a general principle, not a one-off Applicant Intelligence bug: **source authority and claim support are separate questions**, and this matters even more for Trusted Opportunity Data (Gate 2B, closed), which reconciles a similar mix of authoritative-but-not-always-conclusive sources.
  - **Source-type mistagging.** A small proportion of external sources are tagged a stronger category than warranted (e.g. a general-reference or social-media page tagged as an authoritative government/local-authority source). Future reasoning over this evidence should weigh actual provenance and claim support, not trust `source_type` blindly.
  - **Backlog processor overfetch window.** `process_applicant_intelligence_backlog`'s candidate selection overfetches a fixed multiple (`limit × 3`) of the requested batch size. Called repeatedly with a small `limit` once a large proportion of high-priority identities are already fresh, that fixed window can be entirely consumed by already-processed identities and never reach the remaining lower-priority tail. Worked around operationally during the production bootstrap by calling the same, unmodified function with a sufficiently large `limit`; this should be reviewed before any continuous/scheduled Applicant Intelligence processing is enabled.
  - **`NOT_DETERMINED` is an explicit unresolved state, not a terminal failure** (production population: ~38% of classified identities) — predominantly honest uncertainty (most either have no discoverable public evidence at all, or only a generic company-registry record too thin to support a specific role), not a systematic research failure. See "Unresolved Entity Principle" below for how this should be treated going forward.
- **AI Allocation Intelligence Summary** — built, merged to master through a nine-cycle reliability-hardening sequence (V1–V9), run against real production evidence across all eligible allocations, and accepted by the Product Owner as **pilot-complete**, with a small set of known, documented limitations left deliberately unresolved for this pilot (see "Allocation Intelligence" below and [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)). Automatic regeneration exists but ships disabled by default.
- Live coverage: Bury and Stockport fully onboarded with their own Local Plans; Places for Everyone's correct 9 participating authorities (Bolton, Bury, Manchester, Oldham, Rochdale, Salford, Tameside, Trafford, Wigan — corrected by Pilot Readiness PR-2, "PfE Authority Integrity", after PR-1's audit found Manchester missing and Stockport incorrectly included in `LocalPlanCouncil`; verified against the adopted plan document's own title page) are linked to the plan. Of the 8 authorities with no independent Local Plan of their own, 7 (Bolton, Oldham, Rochdale, Salford, Tameside, Trafford, Wigan) have their PfE allocations already onboarded; Manchester is correctly linked to the plan but has zero allocations ingested yet — a known PR-3 ("Greater Manchester Local Plan Coverage") item, deliberately not actioned in PR-2's metadata-only scope.

### Allocation Intelligence — product intent

The Product Owner's intent for AI Allocation Intelligence Summary (recorded here so a future implementation agent does not narrow it to a smaller "safe" version): a user opening an allocated Site should understand its important position at a glance, without reading the entire underlying allocation page. Where the platform's trusted evidence supports it, the summary should answer:

- What is this allocation, and what is its stated capacity?
- What planning/development activity has been identified against it, and how far has that activity progressed?
- What capacity appears accounted for, and what indicative capacity remains unaccounted for?
- Which Applications are materially relevant, and what is their planning status/outcome?
- Which developers, land promoters, applicants, owners or other parties appear involved, and what is the evidence-supported role for each?
- What material uncertainties exist?
- What should a land/acquisitions professional investigate next?

The deterministic data underneath remains fully available as the evidence/audit layer — the summary is an orientation layer in front of it, never a replacement for it. The success criterion is not merely factual accuracy: it is that the summary materially reduces how much a land professional has to scan and interpret manually. See `app/reporting/allocation_intelligence_summary.py` for the current implementation and its own grounding/validation architecture. Status: **pilot-complete / accepted** — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) §2.

### Unresolved Entity Review — future concept, not scheduled

`NOT_DETERMINED` (Applicant Intelligence, above) is a real, first-class product state — an honest "the evidence does not support a classification yet," never a terminal failure to be silently retried forever or hidden from view. A future **Unresolved Entity Review** (or **Deep Entity Resolution**) capability could selectively revisit unresolved entities with deeper, more targeted evidence research — triggered not on a blanket schedule but by something that actually changes the odds of success: new underlying evidence appearing, the entity's opportunity undergoing a material change, repeated classification failure, commercial importance of the specific opportunity, or an elapsed re-review period. This is a **selective escalation** model, not a free-running agent that repeatedly re-researches every unresolved entity regardless of whether anything new exists to find — the same "bounded, not continuous" discipline Applicant Intelligence itself already follows. Not an implementation gate; recorded so a future design starts from this framing rather than reconstructing it from scratch.

### Site Selection & Reporting — BUILT

*(Updated at the Product Vision & Roadmap Refresh, post–Opportunity Experience V2. This section previously read "not yet designed or built" — it has since been implemented, through four sequential gates: `specifications/011-allocation-shortlist-v1-gate-1.md` through `specifications/016-allocation-reporting-v1-gate-4-ai-web.md`. Those specifications are the historical record of how it was built and are left unchanged; this section is updated to describe what exists today.)*

A user can discover and filter allocated and emerging Local Plan allocations (`app/reporting/allocation_discovery.py`), add one or several to a session-scoped **Shortlist** (`app/ui/pages/3b_Shortlist.py`, `app/ui/shortlist.py`), and generate a decision-ready CSV or PDF report from that selection (`app/reporting/allocation_report.py`, `app/reporting/allocation_report_pdf.py`) — the allocation-level equivalent of the reporting the platform already provides for a Site. The report draws on the same deterministic evidence used elsewhere in this document: allocation identity, Local Plan/allocation status, residential capacity, identified planning activity, development coverage and residual/unaccounted capacity, party/ownership evidence where grounded, and (optionally, gated, never regenerated silently) the AI Allocation Intelligence summary and a Gate 4 "AI Executive Intelligence" narrative layer built the same evidence-grounded way as every other AI-narrated capability in this document. This is the same underlying data-assembly path (`build_allocation_report_context`) that the CSV export, the deterministic PDF, and the AI-enriched PDF all read from — one context builder per report, never a separate query path per output format.

Reused rather than rebuilt, as intended: `app/reporting/allocation_discovery.py`'s existing filtering architecture, and the Site-level report-generation pattern already proven by `app/reporting/site_profile.py`/`app/reporting/pdf_report.py`.

### Intelligence Hierarchy

The platform's planning/policy evidence is aggregated across five levels of increasing synthesis. This is a more granular breakdown of how Planning Intelligence (§1) and Policy Intelligence (this section) build toward AI Decision Support (§5), not a replacement for the six-layer capability stack in [PRODUCT_VISION.md](PRODUCT_VISION.md).

| Level | Question it answers | Status |
|---|---|---|
| 1. Application Intelligence | What is happening with this planning application? | **Implemented** — `SchemeIntelligence`, scheme reconciliation, AI scheme status summaries. |
| 2. Site Intelligence | What is happening across this physical development site? | **Implemented** — Site consolidation, phase tracking, build status, ownership/control evidence. |
| 3. Allocation Intelligence | What is happening against this Local Plan allocation? | **Pilot complete / accepted** — AI Allocation Intelligence Summary (see above); Product Owner quality gate passed, known limitations documented. |
| 4. Local Plan Delivery Intelligence | How are an authority's allocations progressing in practice, in aggregate? | **Planned** — see below; an enabling capability for Opportunity Discovery as well as a Policy Intelligence deliverable in its own right; sequenced after Allocated/Emerging Site Selection + Reporting (see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) §2). |
| 5. Opportunity Intelligence | What commercially relevant land/development opportunities does the combined evidence indicate? | **V1 built (deterministic)** — Opportunity Experience V2 (2026): a unified Dashboard discovery feed and Opportunity Profile over deterministic opportunity signals (`app/reporting/allocation_development_coverage.py`'s `build_opportunity_signal`, `app/reporting/opportunity_feed.py`). AI-assisted natural-language discovery, and Planning Potential / Opportunity Potential as *reasoned, agentic* judgements, remain future direction — see "Opportunity Intelligence — product direction" below for what's built versus what isn't. Distinct from, and does not pull forward, the full investment/pursue-recommendation output already scoped under AI Decision Support (§5) — that still depends on Market Intelligence and Development Economics, unchanged. |

**Future capabilities:**
- NPPF and national Planning Practice Guidance as a queryable, versioned policy layer (today the platform only tracks each council's own plans, not the national framework they sit inside).
- Supplementary Planning Documents and Design Codes, as their own monitored document type.
- Appeal decisions linked back to the policy they tested.
- Independent Local Plan monitoring for the 8 Greater Manchester authorities currently known to the platform only through Places for Everyone (Bolton, Manchester, Oldham, Rochdale, Salford, Tameside, Trafford, Wigan).
- **Local Plan Delivery Intelligence** (Intelligence Hierarchy Level 4) — aggregates the platform's existing Application → Site → Allocation evidence upward to Local Plan / Council level. Deterministic measures, kept distinct rather than collapsed into one "delivery" number: total residential allocation capacity; number of residential allocations; capacity with identified planning activity; capacity subject to submitted/pending Applications; capacity with planning permission; capacity associated with refused/withdrawn Applications where useful; allocation capacity with no identified planning activity; indicative residual allocation capacity; number/proportion of allocations with activity; equivalent measures for emerging/draft allocations kept separate from adopted ones. An AI interpretation layer on top would explain what the aggregate evidence means commercially (e.g. "X homes allocated across Y allocations; activity identified on Z representing A homes; B homes have granted permission; D allocations representing E homes have no identified activity"), including surfacing — without asserting unsupported causation — where emerging/draft allocations already show planning activity ahead of adoption (a pattern worth flagging as "worth investigating", never asserted as a causal story about council performance the evidence doesn't actually support). **Sequenced after Allocated/Emerging Site Selection + Reporting**, which itself follows Allocation Intelligence (Level 3) passing its Product Owner quality gate — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) §2.
- **Housing Supply Pressure Intelligence** (later enhancement, not an immediate requirement) — combining Local Plan Delivery Intelligence with authority-level housing-delivery evidence (Authority Monitoring Reports, housing trajectories, completions, five-year housing land supply, Housing Delivery Test results, Local Housing Need, examination/adoption evidence) to surface evidence-grounded observations connecting supply pressure to allocation-level activity. Deterministic evidence establishes the facts; AI interprets the combined evidence — the same discipline as every other AI-narrated layer in this document. Sequenced after Local Plan Delivery Intelligence, not before it. "Low housing delivery" is deliberately **not defined** by this document — that depends on which of the evidence sources above the platform actually has, or can reliably obtain, and is a question for the future audit that precedes this capability, not a definition invented ahead of it.

### Opportunity Intelligence — what's built, what's future direction

*(Updated at the Product Vision & Roadmap Refresh, post–Opportunity Experience V2. This section previously described Opportunity Intelligence entirely as unscheduled future direction. The deterministic core of it is now built; this section is rewritten to separate that from what remains genuinely future.)*

**Built — Opportunity Experience V2.** A unified Dashboard discovery feed and Opportunity Profile, covering two real opportunity types without conflating them: **Strategic land** (a Local Plan allocation, classified INVESTIGATE/MONITOR/LOWER_PRIORITY/INSUFFICIENT_EVIDENCE by `build_opportunity_signal`, never a numeric score) and **Planning/delivery** (an existing Site-level signal — approaching lapse, undeveloped permission — reshaped into the same card/profile presentation, never given an invented strategic-land classification). Each Opportunity's profile leads with why it was surfaced, key evidence, and what remains unknown, ahead of detailed investigation sections. See `app/reporting/opportunity_feed.py` and `app/ui/pages/3_Local_Plan_Sites.py`. This is deterministic, filter-and-classify intelligence — no agent, no LLM call, in the discovery or classification path itself.

**Future — AI-assisted Opportunity Discovery.** Letting a user describe the kind of opportunity they want in ordinary acquisition language (e.g. *"emerging residential sites with capacity for 50–100 homes in areas with low housing delivery"*) instead of using the platform's own filters — the platform would interpret that intent into transparent, structured, inspectable search criteria, retrieve matching opportunities deterministically, and only then apply AI interpretation/ranking on top of that grounded result set. The platform must never silently invent what a subjective term in the brief means and present its own interpretation as objective fact; see [PRODUCT_VISION.md](PRODUCT_VISION.md), "The same discipline applies to interpreting what a user is asking for." **Local Plan Delivery Intelligence is an enabling capability for this** — "emerging" maps to Local Plan/allocation status evidence Policy Intelligence already tracks, "50–100 units" maps to deterministic allocation capacity, and "low housing delivery" maps to the authority/Local Plan Delivery Intelligence evidence described above (once that future audit defines what's actually available).

**Future — the Opportunity Analyst.** The agentic reasoning layer that sits above the now-built deterministic feed: *is this actually an opportunity worth investigating, why, what is uncertain, and what should I investigate next?* This is where NPPF's role, and Planning Potential vs. Opportunity Potential (below), actually get *used* — not new standalone features, but evidence the Opportunity Analyst reasons over. Full definition, scope and guardrails are in §7 ("Agentic Reasoning") below, not here — this section stays about the underlying intelligence; §7 is about the agent that interprets it.

**NPPF's role.** National planning policy is intentionally *not* planned as a standalone information feature or a generic policy-summary section a user browses. It sits behind the platform as part of the reasoning framework the future Opportunity Analyst / Planning Potential assessment draws on — Trusted Site Evidence + Local Plan Evidence + Planning Activity/History + Authority/Delivery Context + the relevant NPPF framework, combined, is what such reasoning works over. The existing "NPPF and national Planning Practice Guidance as a queryable, versioned policy layer" future capability above remains the right description of what gets *built*; this paragraph only clarifies the *purpose* it is eventually built for.

**Planning Potential vs. Opportunity Potential.** Two related but distinct future concepts, easy to conflate and important not to:
- *Planning Potential* — how supportive does the available planning/policy evidence appear for development? Reasoned from Site evidence, Local Plan/allocation evidence, planning activity/history, authority delivery context and the NPPF framework, together.
- *Opportunity Potential* — how attractive does this appear as a commercial development/acquisition opportunity? A different question that can point the opposite way: an adopted allocation with permission already granted to a major developer who controls most of the site may show *high* Planning Potential but *low* Opportunity Potential (there is little left to acquire); an emerging allocation with substantial capacity, limited activity and no known developer may show *uncertain or moderate* Planning Potential but *high* strategic Opportunity Potential.

A specific consequence of keeping these distinct: **the absence of a linked planning application must not automatically be treated as negative evidence.** For many allocations, no identified planning activity may itself be commercially significant — an early-mover opportunity ahead of others — and should potentially *increase* Opportunity Potential, while remaining neutral, contextual evidence (not a penalty) within Planning Potential. This document deliberately does not define scoring weights, thresholds, or a formula for either concept — that would be inventing an unsupported pseudo-quantification (e.g. "Allocated = +20 points," "83% chance of permission") the evidence does not actually justify, and would directly contradict §7's own "no opaque scoring" guardrail below. If and when either concept is built, it is Opportunity Analyst *reasoning*, expressed in evidenced prose with named uncertainties — not a deterministic points system.

**Buyer Profiles / the Buyer Analyst.** A later personalisation layer — the deterministic substrate (Buyer Profiles V1, `assess_buyer_fit`) is now built and closed (Gate 1, see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)); the agentic Buyer Analyst / Acquisition Agent interpretation above it is not. The architecture this document commits to is **buyer profile → deterministic suitability → agent interpretation**, never an opaque LLM-generated buyer score: a structured buyer profile (geography, scale, planning-risk appetite, development type, tenure, delivery horizon, brownfield/greenfield preference) is matched against an opportunity's own deterministic facts first, and only the *interpretation* of that match — why it fits, what the risks are — is agentic. An opportunity may legitimately be highly suitable for one buyer profile and unsuitable for another; there is no universal ranking underneath this. **Buyer Mandate V2** (see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)) extends this existing Buyer Profile domain with further acquisition-mandate criteria — it does not rebuild it.

### Trusted Opportunity Data — Gate 2B, Core Planning Trust Programme Complete (six sub-gates closed, Gate 2B-0B promoted as the next capability within the same programme)

*(Added at the Acquisition-First Roadmap Alignment; revised at Gate 2B-0A; re-sequenced at Gate 2B-0A closure; extended through Gate 2B-2A/2B-2B.1/2B-2B.2/2B-2C. Gate 2B is "Trusted Opportunity Data" — deliberately separate responsibilities, never collapsed into one system. All six sub-gates below are now closed, merged and deployed; Gate 2B-0B — originally deferred, now promoted and re-scoped — is the next active gate, ahead of Gate 2C.)*

```
Council portals + planning documents
        ↓
2B-0A     APPLICATION FRESHNESS VERIFICATION      re-verify a known application's own record            [CLOSED]
        ↓
2B-1      SCHEME/APPLICATION/PHASE RECONCILIATION  which application/phase/version controls each fact   [CLOSED]
        ↓
2B-2A     TRUSTED OPERATIVE PLANNING FACTS         computed, scope-aware read layer over 2B-1            [CLOSED]
        ↓
2B-2B.1   TRUSTED CONSUMER ALIGNMENT               downstream buyer-facing consumers migrated onto 2B-2A [CLOSED]
        ↓
2B-2B.2   ACQUISITION OPPORTUNITY SCOPE ALIGNMENT  opportunities scoped whole-site/phase/parcel, never a plot [CLOSED]
        ↓
2B-2C     PLANNING SIGNAL CONSUMER ALIGNMENT       lapse/recent-permission/undeveloped signals trusted   [CLOSED]
        ↓
Trusted Opportunity Data                            — production merge `1eb7e5fb1540127c20b0da88205b9f0e95120da1`
        ↓
2B-0B     APPLICATION LIFECYCLE INTELLIGENCE       durable lifecycle-change detection, history, propagation [NEXT]
        ↓
Buyer/Acquisition Intelligence                      (Gate 2C onward)
        ↓
AUTONOMOUS ACQUISITION AGENT                        (Gate 3 — see §7, "The Autonomy Principle")
```

- **Application freshness verification** (Gate 2B-0A) — **CLOSED** — implemented, deployed (`4b98b46`), and production-validated through a bounded Oldham cohort (10 eligible applications selected by the real selector, all `VERIFIED_UNCHANGED`, `status_verified_at` correctly advanced, no facts fabricated, no false material-change event, scope contained). See "Planning Status Verification" below.
- **Scheme / Application / Phase Reconciliation** (Gate 2B-1) — **CLOSED** (merged `e51f74b`, 2026-09-10; read-only production-validated against seven Astra Sites). `app.reporting.scheme_reconciliation.reconcile_scheme` — deterministic, fact-level, **computed/read-oriented and non-persisted** (no operative-fact table), non-destructive, provenance-aware, fail-safe. Within an already-consolidated `Site` it resolves a `planning_role` per application (distinct from `application_category`: qualification/filtering vs lifecycle participation + which facts it may control), a decided-state overlay, and phase/scope (reusing `phase_tracking`), then determines per-fact eligibility, ranks eligible sources (recency tie-break only), keeps approved/proposed/superseded separate, surfaces unresolved same-scope conflicts, and delegates affordable-housing scope reconciliation to `affordable_housing_scope`. `app.reporting.site_profile` consumes it for the header, the "Total homes" tile, and the residential-mix representative application — with no legacy fallback after a valid `not_determined`. `pick_representative_application` / `aggregate_scheme_fields` remained unchanged for every other caller at this point (opportunity universe/fingerprints — corrected onto the same trusted foundation by 2B-2B.2/2B-2C below; review pages, allocation coverage — still unmigrated). Hard non-substantive guardrail (EIA screening/scoping, condition discharge, certificates, external consultations, ancillary/technical amendments cannot establish substantive permission or operative residential quantum); residential-only "no new inference" safeguard; S73 fact-specific safeguard. No `ApplicationRelationship` table was needed. No schema migration.
- **Trusted Operative Planning Facts** (Gate 2B-2A) — **CLOSED**. `app.reporting.scheme_reconciliation.build_operative_planning_facts(applications) -> OperativePlanningFacts` — the resolved-facts question 2B-1 left open ("computed service vs persisted") is answered: computed, non-persisted, scope-aware, no Scheme/OperativeScheme table introduced. Structurally separates the **current consented position** (never manufactured from a pending/ancillary application — `exists` reads False rather than guessing) from **current active planning position(s)** (zero, one or several, one per distinct scope, never collapsed by "latest wins"). Scope-aware via `group_applications_by_operative_scope`/`is_material_development_parcel` — a named "plot" group is a peer acquisition-level scope only if it independently states its own qualifying-scale unit count, never inferred from the token's own shape (real production evidence confirmed the token shape alone cannot distinguish an individual dwelling plot from a genuine development parcel). Affordable-housing scope reconciliation made decided-state-aware, closing the 2B-1 carried-forward item (Stockport Rugby Club no longer surfaces a 50%/45-unit AH position sourced from a withdrawn hybrid). Adds **relationship confidence** (site-link method/confidence — `high`/`review_required`/`unknown`, never a new numeric score) and **freshness** (`status_verified_at`/`independently_verified`) as first-class provenance dimensions, kept structurally separate from **evidence confidence** — see "Trust Dimensions," [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md). The World of Pets `114619/RES/24` extraction-quality issue remains a separate, still-open backlog item.
- **Trusted Consumer Alignment** (Gate 2B-2B.1) — **CLOSED**. Migrated downstream buyer-facing consumers (Buyer Fit planning-state resolution, Site Profile Structured Summary, Affordable Homes tile) from the legacy `pick_representative_application`/`aggregate_scheme_fields` selection onto Trusted Operative Planning Facts; removed a hardcoded `PERMISSION_GRANTED` fallback; corrected a live production AH percentage/unit-count conflation defect (Brixham Road), with two closure hotfixes.
- **Acquisition Opportunity Scope Alignment** (Gate 2B-2B.2) — **CLOSED**. Migrated *acquisition opportunity generation itself* — not just presentation — onto the same operative-scope model 2B-2A introduced: an individual dwelling plot filing can no longer become its own standalone acquisition opportunity inheriting the whole site's unit count (confirmed real defects at Lacy Street, Barton Road and four further production sites, all corrected). Introduced `app.reporting.opportunity_monitoring_transition` — a narrow, dry-run-first, manifest-driven mechanism so a software scope/fact correction is never misreported as a genuine `NEW`/`MATERIALLY_CHANGED` market event to `app.reporting.opportunity_change`. Reused, unmodified, by Gate 2B-2C.
- **Planning Signal Consumer Alignment** (Gate 2B-2C) — **CLOSED**, production merge `1eb7e5fb1540127c20b0da88205b9f0e95120da1`. `app.reporting.scheme_reconciliation.resolve_operative_lapse_anchor` — the one trusted, role-aware "which application governs implementation/lapse" answer, reused (never re-derived) by both `compute_lapse_status` (whole-site) and `compute_phase_progress` (phase/parcel-scoped). Fixes a confirmed defect where `compute_lapse_status`/`compute_phase_progress` independently selected the most recently *decided* "approve"/"grant"-worded application with no role awareness — a later NMA, condition discharge or S73/variation could become the lapse-clock anchor, or wrongly suppress genuine post-permission progress evidence, purely by being the most recent grant-worded filing (World of Pets, and 56 further production sites). A pre-merge semantic review distinguished `NOT_GRANTED` (no application granted at all — an ordinary, stable fact) from `NOT_DETERMINED` (something granted, not trustworthy as the operative permission) via `OperativeLapseAnchor.any_granted`, eliminating ~125 spurious fingerprint relabellings the first pass introduced. S73/variation requires no special-cased "never resets the clock" logic — it was already excluded from Gate 2B-2A's substantive-role set. Production impact at closure: 407→389 total opportunities, 178→160 planning_delivery; 11/18 `RECENT_PERMISSION` and 8 `UNDEVELOPED_PERMISSION`/`APPROACHING_LAPSE` opportunities confirmed false and removed; zero unrelated fingerprint fields touched. Comprehensive statutory outline/reserved-matters commencement-period modelling remains explicitly deferred.
- **Application Lifecycle Intelligence** (Gate 2B-0B) — **NEXT, architecture investigation only**. Promoted ahead of Gate 2C by Product Owner decision, post Gate 2B-2C: the platform can now reliably answer "what does the evidence mean?" but not yet "has it changed since we last checked?" Broadened from the original narrower "Application Lifecycle History" framing — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), "Gate 2B-0B — Application Lifecycle Intelligence (NEXT)" for the full lifecycle-event list, history requirement, monitoring-cadence principle, and required architecture-investigation scope. Builds on 2B-0A's freshness signal, does not rebuild it. **No schema or implementation is authorised until that investigation is reviewed by the Product Owner.**
- **Monitoring Agent / Autonomous Acquisition Agent** (Gate 3, roadmap only — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)) — the genuinely agentic capability sitting above Gate 2B-0B. It must never itself scrape a portal or decide planning truth; it consumes 2B-0B's trusted lifecycle changes and answers "what changed that matters" (buyer-specifically, once Buyer Mandate V2 exists). Same "agent reads, deterministic layers write" discipline as every other agentic capability in this document (§7) — see "The Autonomy Principle" there for the specific architecture Gate 2B-0B's own capabilities must expose for this agent to consume.

Conceptual only for Gate 2B-0B and the Monitoring/Acquisition Agent — the technical shape of each is deliberately undecided here beyond what's stated; Gate 2B-0B's own architecture investigation (not yet run) is what determines further design, not this document. See [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) for the gate sequence.

### Opportunity Dimensions and Trust Dimensions — kept structurally separate

*(Product Owner decision, post Gate 2B-2C — full detail in [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), "Opportunity Dimensions" and "Trust Dimensions.")* Two families of dimension exist, and neither family's members are ever mixed with each other or collapsed into one field or one score:

- **Trust dimensions** (already built, Gate 2B-2A): evidence confidence, evidence freshness, relationship confidence.
- **Opportunity dimensions** (partially built): Buyer Fit (built, Gate 1), Opportunity Type (built, Gate 1C), Evidence Confidence (built, Gate 2B-2A), Planning Readiness (not yet named as a field), Acquisition Readiness (depends on Gate 2C), Buyer Recommendation (depends on Gate 3).

An opportunity's `Opportunity Type` never encodes its `Acquisition Position`; `Acquisition Position` never encodes a `Buyer Recommendation`; a `Buyer Recommendation` is always specific to one buyer mandate, never a property of the opportunity itself. See "No Opaque Scoring" and "Buyer Suitability Is Contextual, Not Universal," [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md).

#### Planning Status Verification — CLOSED (Gate 2B-0A: implemented, deployed, production-validated), deployed fail-closed

`app.pipeline.status_verification` (on master; deployed and verified at `4b98b46`) directly re-fetches an already-known Application's own authoritative portal record by exact reference — reusing, unmodified, `app.scrapers.{idox,arcus}_portal.fetch_application_by_reference` and `app.pipeline.run_weekly._upsert_scraped_application` (already generic, already runs `app.pipeline.material_change` detection) — rather than the existing month-range search, which can never revisit a past month, or the existing related-application search, which requires a granted anchor. Root cause this closes (Gate 2B-A investigation, production-confirmed): 173 pending applications >6 months old with zero refresh activity of any kind; 100% of `long_pending_application` opportunities >90 days unverified. **Production validation:** one authorised Oldham cohort (2026-09-10) — 10 eligible applications selected by the real selector (1 Tier 1 + 9 Tier 2), all `VERIFIED_UNCHANGED`; `status_verified_at` advanced only for completed verifications; `status`/`decision`/`evidence_refresh_required`/opportunity fingerprint untouched; the 10-per-council cap and starvation-fairness reservation held; only the authorised council processed; circuit breaker wired and test-covered. **Operational activation dependency:** platform-wide scheduled verification (`PLANNING_STATUS_VERIFICATION_ENABLED=true`) is held until the production daily-scrape scheduler is separately proven healthy — a deployment-environment gate, not unfinished 2B-0A work.

**Deployed capability, separate activation (Gate 2B-0A production activation control).** Deploying the stage does not activate it. `run_weekly.main()` runs it only when `app.pipeline.status_verification.status_verification_stage_should_run` returns true, which is fail-closed: `--skip-status-verification` always suppresses it (unchanged meaning); otherwise it runs only if the `PLANNING_STATUS_VERIFICATION_ENABLED` environment variable is explicitly truthy (`1`/`true`/`yes`/`on`) — the scheduled/default production path — **or** `--include-status-verification` is passed — a single deliberate controlled run that never enables scheduled platform-wide execution. Absent the variable and the override, the stage is dormant and the run logs that it was deliberately not executed. `scripts.run_daily_councils` passes neither, so the daily discovery cron stays dormant until an operator sets the variable. This is intentionally one environment variable and one CLI override — not a feature-flag framework, not a database-backed flag.

Deterministic, 4-tier eligibility (contradiction signal — a decision notice or an `approval` recommendation already sits unreconciled internally; long-pending opportunity; other opportunity; other pending), 7/14/30/60-day cadence measured from **freshness** (`Application.status_verified_at`, a new additive field), never from application age, with a starvation-protection fairness rule and a 10-per-council-per-run bound. `status_verified_at` is deliberately distinct from `last_seen_at` (proven, by production data, to advance on any unrelated ORM update — never a proof of verification), `related_search_checked_at` (a different portal call — citation search, not a re-fetch) and `evidence_refresh_last_checked_at` (document refresh only, never touches status/decision). Never added to the opportunity fingerprint (`app.reporting.opportunity_universe`) — a verification *event* is not a planning *change*, and must never manufacture a false `MATERIALLY_CHANGED`.

Related-application discovery (`stage_fetch_related_applications`) gained one new, narrow anchor-selection fallback in the same change: a site with no granted application, but which the current Opportunity Universe already recognises as an unresolved planning-application opportunity, now also qualifies — closing a second structural blind spot (an unresolved opportunity could previously never have a later/superseding filing discovered for it at all) — using the same existing `related_search_checked_at` cooldown, never a new timestamp, and never conflated with status verification's own eligibility.

Acquisition qualification needs the platform to distinguish **raw/historic evidence** (every application, phase, document version and revision the platform has ever seen, preserved in full — never destructively overwritten) from the **current operative position** (what the evidence, reconciled, actually establishes right now). Conceptually:

```
Application / document / phase / version evidence
        ↓
RECONCILIATION
        ↓
OPERATIVE OPPORTUNITY FACTS  (homes, affordable housing, planning status — with source, evidence date, confidence, conflicts/provenance)
```

A scheme that proposed 210 homes, was revised to 196, and was granted permission for 184 has three genuine, non-conflicting historical facts and one **operative** fact (184) — the platform must be able to state the operative figure *and* show its own reconciliation trail, never silently pick a number without recording why. **Where the evidence does not justify stating an operative value, the system must explicitly decline to state one rather than silently choose between conflicting evidence** — this is the Gate 2B-1 exit condition (see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)).

**Acquisition Position Intelligence** (Gate 2C, after Gate 2B) is the next layer up: what the evidence establishes about whether/how an opportunity could realistically be acquired — known owner, applicant, developer/controller, promoter, delivery-partner and option/promotional-control evidence, construction/commencement evidence, disposal/marketing evidence, JV/partnership and funding signals. **Availability must never be inferred from silence** — see "Unknown Must Remain Unknown," [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md), which governs this capability directly. Potential future acquisition-position states (names provisional, not an implementation commitment): `AVAILABLE / POTENTIALLY_AVAILABLE / UNKNOWN / CONTROLLED / COMMITTED` — kept as a conceptually distinct state model from opportunity *type* (strategic land, long-pending application, …) and from a future buyer *recommendation* (`PURSUE / VERIFY / MONITOR / NOT RELEVANT`); these three concepts must never be collapsed into one enum.

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

---

## 7. Agentic Reasoning

*(New at the Product Vision & Roadmap Refresh, post–Opportunity Experience V2. This section formalises where genuine agentic reasoning belongs in the six-layer stack above, distinguishes it from platform intelligence that must not become an agent, and names the three agentic capabilities currently justified by real product need — no more. None of what follows is an approved implementation workstream; see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) for the actual decision gate that determines what, if anything, gets built next.)*

**Purpose:** Interpret and reason over the platform's own deterministic intelligence to answer a judgement question a human still has to decide — never to become a second, competing source of the facts underneath that judgement.

### The architecture

```
Data sources
     ↓
Evidence / provenance          (the Evidence Platform, §0)
     ↓
Structured intelligence        (Planning, Policy, Market Intelligence, §§1-3)
     ↓
Deterministic engines          (matching, coverage, classification, calculation)
     ↓
Agentic investigation          (Opportunity Analyst · Buyer Analyst · Market & Investment Analyst)
     ↓
Evidence-backed recommendation
     ↓
Human acquisition decision
```

### The Autonomy Principle — orchestration vs. fact creation

*(Product Owner decision, post Gate 2B-2C.)* PropertyAIgent should become increasingly autonomous — the intended long-term experience is *"give PropertyAIgent an acquisition strategy and it behaves like an always-on acquisition researcher."* This does **not** mean an unconstrained LLM becomes the system of record. Distinguish:

- **Autonomous orchestration** — an agent may decide which opportunities deserve investigation, which schemes need fresher evidence, when an opportunity should be re-checked, whether a new document deserves analysis, whether additional ownership/control evidence is required, whether a planning change is commercially material, whether an opportunity should be promoted or downgraded, which buyer is likely to care, and what to investigate next.
- **Authoritative fact creation** — must remain evidence-backed, provenance-aware, reproducible, auditable and confidence-aware, exactly as every deterministic layer in §§0-6 already is.

The resulting architecture, which Gate 2B-0B's own capabilities must be built to support:

```
Agent decides what to investigate
     ↓
Trusted tool/capability retrieves evidence
     ↓
Deterministic / bounded extraction establishes facts
     ↓
Reconciliation establishes operative position
     ↓
Agent interprets commercial significance
```

Conceptually, the capabilities such an agent invokes (Gate 2B-0B builds these; names are conceptual only, not an API to implement merely because it is named here): `verify_application()`, `discover_related_applications()`, `check_new_documents()`, `extract_changed_facts()`, `reconcile_planning_position()`, `detect_development_progress()`, `emit_change_event()`. Example autonomous reasoning this enables, none of it implemented yet: *"this high-priority opportunity has not been verified recently" → request verification*; *"this committee report is new" → request document extraction*; *"planning position materially improved" → investigate acquisition/control position*; *"this scheme has commenced" → reassess buyer relevance*. Autonomy belongs at the orchestration and commercial-reasoning layers; factual planning states remain evidence-backed — this is the same discipline "Evidence-First, Agent-Assisted, Human-Decided" ([PRODUCT_VISION.md](PRODUCT_VISION.md)) already requires, restated as an explicit architecture for the autonomous-agent era.

Everything above the "Deterministic engines" line is a *consumer* of everything below it. An agent reads facts, evidence and classifications the deterministic layers already established; it reasons over them, cites them, and flags what's missing; it does not write them. See [PRODUCT_VISION.md](PRODUCT_VISION.md), "Evidence-First, Agent-Assisted, Human-Decided," for the governing principle this section implements, including the non-negotiable rule that uncertainty must be preserved, never silently resolved into a false positive or negative (`UNCERTAIN` planning activity must never be restated as "no activity"; unknown ownership must never be restated as "available").

### Lifecycle Watch — a shared capability family, distinct from the Acquisition Agent

*(Product Owner architecture decision, following review of the Gate 2B-0B architecture investigation.)* Do not create a separate autonomous LLM agent for every planning stage, and do not create a separate council-portal-scraping agent per buyer. Instead, distinguish two things kept structurally apart throughout this architecture:

- **Acquisition Agent** — buyer-specific commercial reasoning/orchestration (Gate 3). Answers *"what does this mean for this buyer?"*
- **Lifecycle Watchers / capabilities** — shared, bounded, buyer-independent monitoring capabilities that establish factual changes (Gate 2B-0B and its future extensions). Answer *"what has happened?"*

The Acquisition Agent invokes or prioritises Lifecycle Watch capabilities; it never re-implements them, and Lifecycle Watch never decides commercial significance. This mirrors, at the monitoring layer, the same "agent reads, deterministic layers write" discipline "The Autonomy Principle" above already establishes for evidence generally.

**Conceptual capability families** (architectural concepts, not authorisation to build five new services or agents — Gate 2B-0B builds the shared infrastructure underneath all of them; each family is populated incrementally, only as evidence and need justify it):

- **Planning Decision Watch** — status, officer recommendation, committee process, formal decision (the awaiting-decision lifecycle, below).
- **S106 / Legal Agreement Watch** — not currently modelled as discrete lifecycle facts (confirmed by the Gate 2B-0B investigation); recorded here as an important future capability, not built now.
- **Post-Permission Watch** — discharge of conditions, Reserved Matters, S73, NMA, commencement evidence, revised scheme/phasing, later amendments.
- **Development / Delivery Watch** — construction/build progress and completion evidence.
- **Local Plan / Strategic Land Watch** — the pre-application lifecycle (below), owned by the existing Policy Intelligence / Local Plan infrastructure, not forced into an application-centric model.

**State-aware monitoring.** Monitoring strategy should depend on the operative development/planning state, not use one universal refresh cadence forever. The conceptual lifecycle a planning application may move through (not every development follows every state, and this describes monitoring *concerns*, not a database enum or a rigid state machine to be implemented merely because this diagram exists):

```
APPLICATION SUBMITTED
        ↓
AWAITING DECISION
        ↓
OFFICER RECOMMENDATION
        ↓
COMMITTEE / DECISION PROCESS
        ↓
RESOLUTION TO APPROVE
        ↓
S106 / LEGAL AGREEMENT
        ↓
FORMAL PERMISSION
        ↓
CONDITIONS / RESERVED MATTERS / AMENDMENTS
        ↓
COMMENCEMENT
        ↓
UNDER CONSTRUCTION
        ↓
PARTIAL / FULL DELIVERY
```

**Awaiting-decision monitoring.** For a pending application, relevant monitoring may eventually include: authoritative application status; new/revised documents; officer recommendation; committee date; committee report; committee resolution; formal decision; revised unit numbers; revised affordable-housing position. Monitoring intensity may reasonably increase as an application approaches a decision — e.g. ordinary pending → officer recommendation approve → committee scheduled → committee resolution approve subject to S106 — a progression that may materially increase acquisition relevance for some buyers before formal permission is even issued. Gate 2B-0B's existing four-tier verification cadence (7/14/30/60 days, keyed on contradiction-signal/opportunity-kind) is the first, already-built instance of exactly this state-awareness principle — future tiers extend it, they do not replace it.

**S106 / legal agreement watch, in more detail.** The Gate 2B-0B investigation confirmed committee information and S106/legal-agreement progression are not currently modelled as discrete lifecycle facts. For acquisition purposes, distinguish conceptually between `OFFICER_RECOMMENDATION_TO_APPROVE`, `COMMITTEE_RESOLUTION_TO_APPROVE`, `RESOLUTION_TO_APPROVE_SUBJECT_TO_S106`, `S106_EXECUTED`, and `FORMAL_DECISION_NOTICE_ISSUED` — these can have materially different acquisition significance to different buyers. Do not build a comprehensive legal-agreement subsystem now; Gate 2B-0B's lifecycle-event model must simply not be designed in a way that prevents these events being added later (see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), Gate 2B-0B's "Event-model extensibility" note).

**Post-permission watch, in more detail.** Once permission is formally granted, the monitoring objective changes — repeatedly asking only "has permission been granted?" is no longer sufficient. Relevant future evidence: S106/legal-agreement status where applicable; discharge of conditions; Reserved Matters; S73; NMA; commencement evidence; revised scheme/phasing; later amendments; development progress. This reuses the existing trusted planning-role/reconciliation architecture (`app.reporting.scheme_reconciliation`, §"Trusted Opportunity Data" above) unchanged: a new NMA or S73 must **not** automatically be interpreted as a new substantive acquisition opportunity — already guaranteed today by Gate 2B-2A's `SUBSTANTIVE_ROLES` exclusion and Gate 2B-2C's role-aware anchor resolution, confirmed unaffected by this amendment.

**Development/delivery watch, in more detail.** Development progress is factual evidence — it is **not** universally positive or negative. A traditional land buyer may find `UNDERWAY` materially reduces acquisition relevance; a fund/BTR buyer may find `UNDERWAY` increases it; a Housing Association may find construction progression creates an affordable-unit/package acquisition opportunity. Lifecycle Watch establishes *what has happened*; the Buyer Acquisition Agent determines *what it means for this buyer* — this separation is preserved throughout the architecture, exactly as "The Development/Delivery-State Principle" in [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) already requires. `NEARING_COMPLETION` continues to not exist without adequate evidence.

**Strategic land lifecycle.** Strategic land's monitoring lifecycle is different from a planning application's and must not be forced into an application-centric model:

```
PROMOTED / SUBMITTED SITE
        ↓
EMERGING ALLOCATION
        ↓
DRAFT ALLOCATION
        ↓
EXAMINATION / MODIFICATION
        ↓
ADOPTED ALLOCATION
        ↓
PLANNING / DELIVERY ACTIVITY
```

The existing Local Plan / Policy Intelligence infrastructure (§2 below) should eventually function as the trusted watcher for this lifecycle, the same way Gate 2B-0B is the trusted watcher for the application lifecycle above — not a shared engine, two lifecycle-appropriate watchers feeding the same downstream Lifecycle Watch concept.

### Platform Intelligence vs. Agentic Reasoning

Not every proposed "agent" is actually an agent. A capability that primarily builds, matches or maintains structured evidence is **platform intelligence** — it belongs in the deterministic layers above, and a future agent consumes its output; it is not itself a personality wrapped around an LLM call.

| Capability | Kind | Where it lives | Why |
|---|---|---|---|
| Opportunity Analyst | **Agentic** | Consumes Policy Intelligence §2 (Opportunity Intelligence) | Genuinely requires judgement over already-established facts — is this worth investigating, why, what's uncertain |
| Buyer Analyst | **Agentic** | Consumes structured buyer profiles + opportunity facts | Interpretation of a deterministic fit result is judgement; the fit result itself is not |
| Market & Investment Analyst | **Agentic** | Consumes Market Intelligence §3 + Development Economics §4 | Same pattern: structured comparables/appraisal facts first, interpretation second |
| Strategic Land Intelligence | **Platform intelligence** | Policy Intelligence §2 | Building/maintaining allocation, plan-stage, spatial-strategy evidence is evidence work, not reasoning — it *feeds* the Opportunity Analyst |
| Ownership & Control Intelligence | **Platform intelligence** | Market Intelligence §3 (Ownership Intelligence) | Identity resolution and ownership evidence must stay deterministic and auditable; an agent may later interpret an *ambiguous* relationship, but does not establish ownership facts itself |
| Opportunity Monitoring | **Platform intelligence (core), agentic (interpretation only)** | Evidence Platform §0 pattern, extended | Change detection must stay deterministic infrastructure (source monitoring → diff → significance → alert); an agent may later answer "does this change materially alter the opportunity?" on top of a real, already-detected change — it does not replace the detection. **The platform-intelligence core is built and closed** (Gate 1: Acquisition Monitoring Substrate; Gate 1C: Planning Opportunity Trigger Expansion — both merged to master) — `app.reporting.opportunity_universe` gives every current opportunity a stable logical identity and a deterministic fingerprint across all five opportunity types (strategic land, long-pending application, recent permission, undeveloped permission, approaching lapse); `app.reporting.opportunity_change` classifies BASELINE_EXISTING / NEW / MATERIALLY_CHANGED / UNCHANGED with reason codes, running on a weekly production cron. The agentic interpretation layer above it (a Selective Acquisition Agent) remains unbuilt. |
| Applicant Intelligence | **Platform intelligence** | Policy Intelligence §2 (Ownership & Control) | Entity-level organisation classification built from evidence-grounded AI research is evidence work, not judgement — it *feeds* the future Acquisition Position Intelligence and Acquisition Agent, exactly as Strategic Land Intelligence feeds the Opportunity Analyst. **Built and closed (Gate 2A)** — see §2 below. |
| Planning Due Diligence | **Agentic (a mode, not a separate agent)** | A deeper investigation mode of the Opportunity Analyst | The same reasoning over the same evidence, run in more depth on request — not a second customer-facing agent with its own identity |
| Evidence Investigator | **Long-term concept, undesigned** | Would sit between the Opportunity Analyst and the Evidence Platform | Documented in outline only (below) — not scheduled, not architected |

### A. Opportunity Analyst

**Likely Phase 1 agentic capability** (subject to the Phase 1 Opportunity Validation decision gate — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)).

**Core question:** *Is this actually an opportunity worth investigating, why, what is uncertain, and what should I investigate next?*

Reasons over the platform's own existing structured intelligence: allocation status, planning activity, application history, delivery/progression signals, Local Plan evidence, policy, ownership/control evidence, development evidence, monitoring changes, and evidence gaps. Output: why the opportunity warrants investigation, important risks, important unknowns, the evidence supporting its reasoning, and recommended next investigations — never an invented fact, never a resolved uncertainty. Initially an **on-demand investigation capability**, not autonomous acquisition decision-making. Planning Due Diligence is a deeper mode of this same capability, not a separate customer-facing agent.

### B. Buyer Analyst

**Likely late Phase 1 / Phase 1.5** — sequenced after opportunities themselves are well enough understood that suitability, not comprehension, is the primary unmet need.

**Core question:** *Who is this opportunity valuable to, and why?*

Sits above structured buyer profiles (geography, unit/site scale, planning-risk appetite, planning status, development type, tenure, delivery horizon, brownfield/greenfield preference) and deterministic suitability logic. Architecture: **buyer profile → deterministic suitability → agent interpretation**, never an LLM producing an arbitrary buyer score. No opaque, generic Opportunity Score is introduced anywhere in this architecture — an opportunity may legitimately be highly suitable for one buyer and unsuitable for another, and the platform's output must show that contextual difference, not average it away.

**Implementation status:** the deterministic layer this agent will sit above is built and closed - Buyer Profiles V1 (four pilot profiles) and `app.policy.buyer_matching.assess_buyer_fit`, merged to master, plus persistent, Workspace-owned Buyer Profiles and a deterministic onboarding baseline (Gate 1: Acquisition Monitoring Substrate, merged to master). The Buyer Analyst's own agentic interpretation layer is not yet built — the acquisition-first roadmap now sequences it as **Buyer Mandate V2 → Acquisition Agent V1** (extending, never rebuilding, this same Buyer Profile substrate — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)).

### C. Market / Investment Analyst

**Phase 2.** Must not distract from current Phase 1 opportunity sourcing.

**Core question:** *What does the market and financial evidence imply for this opportunity?*

Sits above structured sales/rental comparables, comparable relevance, £/sq ft, transaction evidence, market assumptions, GDV, development appraisal and residual land value (Market Intelligence §3, Development Economics §4) — the same **structured evidence → deterministic calculation → agent interpretation** pattern as the other two. A key dependency is access to reliable, commercially permissible market/comparable data; an LLM browsing public portals for pricing is not an acceptable substitute for a legitimate structured data source (see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) §3).

### Near/Mid-Term Agent Priority

*(Added at the Acquisition-First Roadmap Alignment; updated post Gate 2B-2C — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) for the gate sequence this drives.)* Not every one of these needs to be a standalone autonomous agent from day one:

1. **Planning Verification** — Trusted Opportunity Data (Gate 2B, all six sub-gates) is now **built and closed** — the bounded evidence/reconciliation capability this priority named is done; Gate 2B-0B (Application Lifecycle Intelligence) extends it to durable change detection, still deterministic infrastructure, not a customer-facing agent in its own right.
2. **Acquisition Intelligence** — structured evidence extraction (Applicant Intelligence, built/closed — Gate 2A; Acquisition Position Intelligence, Gate 2C, sequenced after Gate 2B-0B) with agentic reasoning (the Buyer Analyst / Gate 3 Autonomous Acquisition Agent above) layered on afterward, not built together.
3. **Opportunity Monitoring** — the deterministic change-detection infrastructure (Gate 1/1C) is built and closed, and Gate 2B-2C corrected the facts it detects changes against; Gate 2B-0B extends detection to durable lifecycle history; only the interpretation of a detected change ("does this matter for this buyer's mandate?") — Gate 3 — is agentic.

Later: the Market & Investment Analyst (§C above) and a future Development Appraisal Agent remain sequenced behind real market data existing — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), "Phase 2."

### Grokbot — long-term concept, not designed here

A possible future conversational front door/orchestrator to Property AIgent's intelligence, sitting above the agentic capabilities in this section rather than replacing any of them — not implemented today, and not designed in this document. If built, it would call into this same stack as tools/capabilities (Opportunity Intelligence, Buyer Profile/Fit, Operative Scheme Intelligence, Policy Intelligence, Applicant Intelligence, Acquisition Position, Ownership Intelligence, Planning History), never establish facts of its own — the same "agent reads, deterministic layers write" discipline as every other agent in this section.

### Evidence Investigator — long-term concept, not designed

A possible future extension, documented so it isn't reconstructed from scratch later, not because it is planned work. Concept: when the Opportunity Analyst identifies a genuine evidence gap (e.g. delivery timing unknown, ownership/control unknown), it could request a **bounded** evidence investigation — search trusted, permitted sources for that specific gap — rather than reasoning further on an assumption. Conceptually: *Opportunity Analyst → identifies gap → bounded Evidence Investigator → retrieves permitted evidence → evidence is extracted/cited/validated through the existing Evidence Platform (§0) → structured intelligence updated or queued for human review → Opportunity Analyst reassesses.* This would not necessarily be a customer-facing "agent" in its own right. No implementation architecture, data-source list, or scope boundary is decided here.
