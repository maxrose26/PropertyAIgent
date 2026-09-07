# PropertyAIgent — Platform Architecture

This document describes the platform **functionally** — what each capability is for, what it does today, what it will do, and what it depends on — not the code layout. For the technical/module-level view of what exists today, see [ARCHITECTURE_STATUS_v2.md](ARCHITECTURE_STATUS_v2.md). For the vision these capabilities serve, see [PRODUCT_VISION.md](PRODUCT_VISION.md). For sequencing, see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).

The platform is organised into six capability areas, each building on verified evidence from the one before it:

`Planning Intelligence → Policy Intelligence → Market Intelligence → Development Economics → AI Decision Support → Workflow & Collaboration`

All six sit on top of one shared technical foundation — the **Evidence Platform** (§0 below) — rather than each re-implementing document handling, monitoring, extraction and review from scratch.

*(Added at the Product Vision & Roadmap Refresh, post–Opportunity Experience V2: a seventh section, §7 "Agentic Reasoning," sits alongside this stack, not after it in the same linear sequence — it is the cross-cutting discipline for how AI reasoning is allowed to consume the six capability areas' own structured facts, wherever in the stack that reasoning happens. See §7 for the full guardrail and the three agentic capabilities it currently justifies.)*

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
- **Database schema deployment: startup verification vs. explicit migration** (Pilot Readiness PR-2 final pre-merge amendment, "Database Migrations Must Not Be A Page-Load Side Effect") — `app.db.session.init_db()`, called on every ordinary process startup (first Streamlit page load per server process, every `run_weekly.py`/`run_daily_councils.py`/`run_intelligence_processing.py` invocation), no longer mutates a production (PostgreSQL) schema. On SQLite (local dev/tests) it still auto-creates any missing table/column, exactly as before — there is no real "customer" on a developer's own throwaway database. On PostgreSQL it performs a **read-only** check (`app.db.session.verify_schema`) and raises `SchemaVerificationError` loudly if the connected database is missing a table or column the current models declare, rather than silently altering production schema on a normal request. The actual schema evolution now only ever happens via the explicit, operator-invoked `python -m scripts.migrate_schema` (`app.db.session.migrate_schema` — idempotent, transactional, logs every table created/column added), with `python -m scripts.verify_schema` as a companion read-only sanity check (exit 0 = current, exit 1 names exactly what's missing). Required production deployment order: (1) make the migration command available (ship the code), (2) run `python -m scripts.migrate_schema`, (3) run `python -m scripts.verify_schema` to confirm, (4) start/restart the Streamlit web service, (5) allow the Cron Jobs to run. No Alembic or other migration framework was introduced — the underlying diff-and-`ALTER TABLE` mechanism predates this amendment (Pilot Readiness PR-2 pre-merge architecture check) and was already dialect-agnostic; this amendment only changes *when* it is allowed to run automatically.
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

**Buyer Profiles / the Buyer Analyst.** A later personalisation layer, intentionally not designed here — full framing is in §7 below. The architecture this document commits to is **buyer profile → deterministic suitability → agent interpretation**, never an opaque LLM-generated buyer score: a structured buyer profile (geography, scale, planning-risk appetite, development type, tenure, delivery horizon, brownfield/greenfield preference) is matched against an opportunity's own deterministic facts first, and only the *interpretation* of that match — why it fits, what the risks are — is agentic. An opportunity may legitimately be highly suitable for one buyer profile and unsuitable for another; there is no universal ranking underneath this. Buyer Profiles are sequenced after opportunity intelligence itself is rich enough that the primary unmet need becomes suitability, not understanding.

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

Everything above the "Deterministic engines" line is a *consumer* of everything below it. An agent reads facts, evidence and classifications the deterministic layers already established; it reasons over them, cites them, and flags what's missing; it does not write them. See [PRODUCT_VISION.md](PRODUCT_VISION.md), "Evidence-First, Agent-Assisted, Human-Decided," for the governing principle this section implements, including the non-negotiable rule that uncertainty must be preserved, never silently resolved into a false positive or negative (`UNCERTAIN` planning activity must never be restated as "no activity"; unknown ownership must never be restated as "available").

### Platform Intelligence vs. Agentic Reasoning

Not every proposed "agent" is actually an agent. A capability that primarily builds, matches or maintains structured evidence is **platform intelligence** — it belongs in the deterministic layers above, and a future agent consumes its output; it is not itself a personality wrapped around an LLM call.

| Capability | Kind | Where it lives | Why |
|---|---|---|---|
| Opportunity Analyst | **Agentic** | Consumes Policy Intelligence §2 (Opportunity Intelligence) | Genuinely requires judgement over already-established facts — is this worth investigating, why, what's uncertain |
| Buyer Analyst | **Agentic** | Consumes structured buyer profiles + opportunity facts | Interpretation of a deterministic fit result is judgement; the fit result itself is not |
| Market & Investment Analyst | **Agentic** | Consumes Market Intelligence §3 + Development Economics §4 | Same pattern: structured comparables/appraisal facts first, interpretation second |
| Strategic Land Intelligence | **Platform intelligence** | Policy Intelligence §2 | Building/maintaining allocation, plan-stage, spatial-strategy evidence is evidence work, not reasoning — it *feeds* the Opportunity Analyst |
| Ownership & Control Intelligence | **Platform intelligence** | Market Intelligence §3 (Ownership Intelligence) | Identity resolution and ownership evidence must stay deterministic and auditable; an agent may later interpret an *ambiguous* relationship, but does not establish ownership facts itself |
| Opportunity Monitoring | **Platform intelligence (core), agentic (interpretation only)** | Evidence Platform §0 pattern, extended | Change detection must stay deterministic infrastructure (source monitoring → diff → significance → alert); an agent may later answer "does this change materially alter the opportunity?" on top of a real, already-detected change — it does not replace the detection. **The platform-intelligence core is now implemented** (Gate 1: Acquisition Monitoring Substrate, feature branch, awaiting Product Owner review) — `app.reporting.opportunity_universe` gives every current opportunity a stable logical identity and a deterministic fingerprint; `app.reporting.opportunity_change` classifies NEW / MATERIALLY_CHANGED / UNCHANGED with reason codes. The agentic interpretation layer above it (a Selective Acquisition Agent) remains unbuilt. |
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

**Implementation status:** the deterministic layer this agent will sit above is built - Buyer Profiles V1 (four pilot profiles) and `app.policy.buyer_matching.assess_buyer_fit`, merged to master, plus persistent, Workspace-owned Buyer Profiles and a deterministic onboarding baseline (Gate 1: Acquisition Monitoring Substrate, feature branch, awaiting Product Owner review). The Buyer Analyst's own agentic interpretation layer is not yet built.

### C. Market / Investment Analyst

**Phase 2.** Must not distract from current Phase 1 opportunity sourcing.

**Core question:** *What does the market and financial evidence imply for this opportunity?*

Sits above structured sales/rental comparables, comparable relevance, £/sq ft, transaction evidence, market assumptions, GDV, development appraisal and residual land value (Market Intelligence §3, Development Economics §4) — the same **structured evidence → deterministic calculation → agent interpretation** pattern as the other two. A key dependency is access to reliable, commercially permissible market/comparable data; an LLM browsing public portals for pricing is not an acceptable substitute for a legitimate structured data source (see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) §3).

### Evidence Investigator — long-term concept, not designed

A possible future extension, documented so it isn't reconstructed from scratch later, not because it is planned work. Concept: when the Opportunity Analyst identifies a genuine evidence gap (e.g. delivery timing unknown, ownership/control unknown), it could request a **bounded** evidence investigation — search trusted, permitted sources for that specific gap — rather than reasoning further on an assumption. Conceptually: *Opportunity Analyst → identifies gap → bounded Evidence Investigator → retrieves permitted evidence → evidence is extracted/cited/validated through the existing Evidence Platform (§0) → structured intelligence updated or queued for human review → Opportunity Analyst reassesses.* This would not necessarily be a customer-facing "agent" in its own right. No implementation architecture, data-source list, or scope boundary is decided here.
