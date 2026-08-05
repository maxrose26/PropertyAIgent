# PropertyAIgent — Architecture Status (v1)

**As of:** Sprint 3G merge (`v0.3g-pfe-allocation-onboarding`), master commit `0a7a8f0`.

This document is a snapshot of what the platform currently does, as built. It is not a specification and does not describe future work in detail — see `specifications/` for the "what and why" behind each capability, and the **Future Roadmap** section below for headings only.

---

## 1. Overall Platform Architecture

PropertyAIgent is a Site-centred residential development intelligence platform for England and Wales, built around a small number of core domain objects (`specifications/004-core-domain-model.md`): **Site**, **Development**, **Planning Application**, **Policy** (Local Plans and Allocations), **Organisation**, **Person**, **Financial Model**, **Report**. Every intelligence layer enriches one or more of these objects; nothing exists in isolation.

The stack is a single local Python application: SQLite (`data/deal_finder.db`) via SQLAlchemy, a Streamlit UI (`app/ui/`), a set of independently-runnable pipeline stages (`app/pipeline/run_weekly.py` plus standalone CLI scripts under `app/*` and `scripts/`), and OpenAI structured-output calls for the specific extraction/classification steps that need them. There is no web server, no multi-tenant auth, and no cloud deployment — this is a single-user tool run via Windows Task Scheduler.

**Council coverage today:**
- **Application scraping** (Idox/Arcus portals): Bury, Stockport, Trafford, Rochdale, Manchester, Oldham, Tameside, Bolton, Wigan, Salford (10 Greater Manchester authorities, config-driven — `config/councils.yaml`).
- **Policy Intelligence** (Local Plans/allocations): Bury and Stockport fully onboarded with their own allocations; Bolton, Oldham, Rochdale, Salford, Tameside, Trafford and Wigan are linked to the *Places for Everyone* joint plan (via `LocalPlanCouncil`) and have their own PfE allocations onboarded, but have no independent Local Plan of their own ingested yet, and no application-scraping-driven Policy Intelligence activity.

---

## 2. Completed Subsystems

- **Application scraping** — config-driven Idox scraper (`app/scrapers/idox_portal.py`), Bury's legacy Anite document adapter, and an Arcus/Salesforce Experience Cloud scraper (Salford/Rochdale/Manchester) — all sharing one `Application`/`Document` schema regardless of source portal.
- **Document extraction** — PDF text extraction with a subprocess-timeout safety pattern (`app/extraction/pdf_text.py`), reused by every downstream text-reading module.
- **AI scheme extraction & reconciliation** — three structured-output LLM passes (entities, site development intelligence, affordable-housing classification) plus regex passes, merged by a priority-ordered reconciliation function with cross-checks (`app/extraction/`).
- **Site consolidation** — tiered, confidence-scored linking of multiple Applications to one physical `Site` (exact address, cited parent reference, portal-native related-application search, human-confirmed fuzzy match) (`app/pipeline/site_linking.py`).
- **Enrichment** — Companies House (name match, officers, PSC, cross-appointments), website discovery with a verification gate, Apollo/Hunter contact discovery with role-scoring, triggered on-demand per company via a credit system, never automatically for every scraped scheme.
- **Build-status tracking** — EPC Open Data lookups classify a Site's construction progress; postcodes.io geocoding for map display.
- **Natural-language search** — one structured-output LLM call parses a free-text query into the same filter shape the UI's own sidebar filters use.
- **Weekly orchestration** — `app/pipeline/run_weekly.py`, a resumable, stage-by-stage pipeline (scrape → link sites → documents → AI extraction → build status → geocode → scheme summaries), with a multi-year month-chunked backfill mode.

## 3. Completed AI Capabilities

Every AI call in the platform follows the same discipline: **deterministic before AI, evidence before AI, structured output only, never freeform generation of facts.**

- Scheme entity/intelligence extraction and affordable-housing classification (`gpt-4o-mini`, JSON-schema structured outputs).
- Local Plan allocation extraction from a site-allocations schedule (`app/extraction/local_plan.py`) — `policy_reference` is nullable end-to-end and the prompt explicitly forbids inventing a code.
- Local Plan evidence extraction (housing requirement, delivery, five-year land supply) from monitored reports (`app/extraction/plan_evidence.py`), each fact carrying a verbatim source excerpt.
- AI Local Plan Summary — a narrative synthesis of a plan's own verified evidence, gated by an evidence fingerprint so it never regenerates (and never spends AI cost) unless the underlying facts actually changed.
- AI scheme status summaries per Site, regenerated weekly, never on every page view.
- Visual classification (`gpt-4o-mini` vision) of rendered page images into a fixed `IMAGE_TYPES` vocabulary — the model classifies only what it can see; matching an image to a specific named Site/Allocation is always a separate, deterministic step from text evidence, never the vision model's own guess.

## 4. Completed Policy Intelligence Capabilities

- **Core model**: `LocalPlan` (plan-level metadata, status, housing requirement/delivery/five-year-supply evidence, AI summary) → `LocalPlanSite` ("Allocation" — one allocated site, with policy reference, capacity, status, progression signal) → optional `matched_site_id` linking an allocation to a scraped `Site`.
- **Joint-plan support** (`LocalPlanCouncil`) — a genuinely multi-authority plan (Places for Everyone: one adopted plan, 9 participating Greater Manchester authorities) is represented as exactly one `LocalPlan` row linked to every participating `Council` via an additive join table, never duplicated per authority. `LocalPlan.council_code` is retained as a backwards-compatible lead/legacy field.
- **Allocation-to-allocation relationships** (`AllocationRelationship`) — records that two `LocalPlanSite` rows (often across two different plans) refer to the same physical site (`same_physical_site`), reference one another (`referenced_by`), or are jointly delivered (`implemented_through_joint_plan`) — without ever merging the underlying records. Used for Bury's Seedfield/Walshaw/Elton Reservoir duplication (Sprint 3E) and for Places for Everyone's Northern Gateway (Sprint 3G).
- **Change protection** — every ingestion/monitoring path (`ingest_local_plan.py`, `app.policy.monitor`) writes ambiguous or status-changing facts as a `PolicyChangeEvent` with `review_status="needs_review"`, never mutating trusted state directly; `app.policy.review.approve_change/reject_change` are the only two functions allowed to resolve one, always snapshotting the pre-change value to history first.
- **Progression signal** — a deterministic, seven-value classification (`early_stage` → `adopted`/`stalled`/`removed`) restating what the plan/allocation status already say; never a prediction, and an adopted plan never silently promotes an unconfirmed allocation.
- **Places for Everyone onboarding** — all 34 real PfE allocations are now represented: Bury's original 3 (Sprint 2), plus 33 onboarded in Sprint 3G across Bolton/Oldham/Rochdale/Salford/Tameside/Trafford/Wigan and 5 genuinely cross-boundary allocations (Northern Gateway, Stakehill, Medipark, Timperley Wedge), each with full page-sourced provenance (policy reference, name, capacity, intended use, source page/URL).
- **Policy document coverage** (`app/policy/coverage.py`) — per-council, per-document-type tracking of Expected → Discovered → Downloaded → Registered → Current → Superseded → Ingested → Visual/Policy evidence extracted, surfaced on the Council Dashboard as "we are missing: X".
- **Deterministic policy-page/document discovery** (`app/policy/document_discovery.py`, `app/policy/document_types.py`) — keyword-based, never AI-crawled; ambiguous multi-candidate document matches are queued for review, never silently resolved.

## 5. Completed Planning Intelligence Capabilities

- Multi-year application scraping with unit-count qualification filtering, across 10 councils and 3 distinct portal systems (Idox, Idox+Anite, Arcus).
- Phase tracking — grouping and labelling multi-phase schemes (outline, reserved matters, discharge of conditions) under one Site.
- Site-level headline/tooltip synthesis for map and search display, batched (never N+1) against the applications and Local Plan allocations touching each Site.

## 6. Completed Visual Evidence Capabilities

- **Pipeline**: deterministic candidate document selection → deterministic candidate page detection (text signals, drawing-sheet heuristics, and — since Sprint 3F — a dedicated allocation-policy-page signal that is never disqualified by high text density) → page rendering to image + thumbnail (subprocess-isolated, path-traversal-safe, idempotent by source-file hash) → AI vision classification into a fixed type vocabulary → deterministic matching to a Site/Application/Allocation.
- **Matching priority chain** (`app/visuals/matching.py`): exact policy reference → normalised policy reference → exact allocation title → weaker substring "review suggestion" → needs review. Never guesses; an ambiguous or multi-allocation page (e.g. a plan's own allocations table) is always surfaced for review, never auto-linked, even when only one candidate happens to already exist in the database.
- **Deterministic identifier extraction** (`app/visuals/allocation_identifiers.py`) — regex-based, no AI, recognising JPA/HOM/HS-style codes and "Policy JP Allocation N" phrasing, normalised for comparison while the verbatim printed text is always retained.
- **Re-matching without re-rendering** (Sprint 3G) — once new `LocalPlanSite` rows exist, `app.visuals.pipeline.rematch_local_plan_evidence` re-runs matching against every already-extracted image's stored `detected_allocation_reference`/`detected_allocation_title`, with zero rendering and zero Vision API calls.
- **Secondary-page suggestions** — a page with no identifier of its own, sitting within a bounded window after an already-matched allocation's title page, is recorded as a review suggestion (`match_method="page_proximity_suggestion"`) but never auto-linked by proximity alone.
- **Primary-image selection** — a human-confirmed image always outranks any unreviewed one regardless of type; within confirmed images, ranking follows an explicit type-priority order; a rejected image can never become primary.
- **Full provenance retained on every row** — source document, page number, detected reference/title, document hash, render hash, classification confidence, match method/confidence, review status. A changed source document supersedes its old images (`status="superseded"`), never deletes or overwrites them.
- **Live coverage**: 156 Places for Everyone allocation-policy pages extracted; 37 distinct allocations (out of 34 real PfE allocations plus Northern Gateway's Bury-side rows) now carry at least one image.

## 7. Monitoring Capabilities

- `app.policy.monitor` checks every active `MonitoredSource` for a council (content-hash based), and discovers/rechecks `MonitoredReport` documents under already-registered index pages — both cadence-gated (`next_check_due`) so a scheduled run does near-zero work when nothing is due, and both queue a `PolicyChangeEvent` rather than acting automatically on a detected change.
- Sources and reports are registered per-council, config-driven (`config/policy_sources.yaml`), idempotent (found-or-created), and a joint plan's real source is registered under exactly one council — linking additional councils to the plan via `LocalPlanCouncil` never re-registers or re-checks that source under them.
- Superseded editions of a report/source are retained, never deleted, mirroring the Visual Evidence supersession pattern.

## 8. Review Workflow

A single, consistent review discipline runs through every subsystem that produces an uncertain fact:

1. Ingestion/monitoring/extraction never writes an ambiguous or trust-sensitive change directly — it writes a proposal (`PolicyChangeEvent`, or a `VisualEvidence`/`AllocationRelationship` row already carrying `review_status="needs_review"`).
2. A human resolves it via one of a small number of explicit functions (`approve_change`/`reject_change`, `confirm_image`/`reject_image`, `mark_primary`) — nothing else in the codebase is allowed to move a row out of `needs_review`.
3. Approval always snapshots the pre-change value to history first (`AllocationVersion`, `LocalPlanStatusHistory`, `LocalPlanFieldHistory`).
4. A rejection is permanent against future reprocessing — even `--force` never reconsiders it.
5. A confirmed fact is never silently overwritten by a later automated pass (rematching, re-ingestion) — confirmed rows are always skipped.

---

## 9. Known Limitations

- **`LocalPlanSite` is single-council per row.** A genuinely cross-boundary allocation gets one real council attributed to it (backed by evidence) plus an `AllocationRelationship` to any counterpart row, rather than a native multi-council field on one row.
- **Cross-boundary council attribution is evidence-based, not always explicit.** Five Places for Everyone allocations (Northern Gateway's two parts, Stakehill, Medipark, Timperley Wedge) are attributed to a council via real-world place-name/cross-reference evidence rather than one explicit sentence in the plan naming the authority — deliberately left `review_status="needs_confirmation"`.
- **`matched_site_id` is a single nullable FK** — an allocation can be linked to at most one Application-derived `Site`, even though a real allocation can in principle be delivered as several physical Sites (documented since the Sprint 1 CTO review, not yet resolved).
- **Only Bury and Stockport have their own independently-ingested Local Plan with a self-authored site-allocations schedule.** The other 7 GM authorities are only known to this platform through their Places for Everyone allocations; no independent Local Plan monitoring exists for them yet.
- **18 Places for Everyone images carry a detected reference that matches no onboarded allocation** (e.g. text mentioning a non-PfE authority, or a genuinely unresolved ambiguous page) — correctly left unmatched, not a defect.
- **Some rendered pages fail outright** (Sprint 3F: 18 of 174 candidate Places for Everyone pages, concentrated in one large appendix) — logged as errors, not investigated further; not blocking, since candidate detection and matching for every other page were unaffected.
- **No real payment/billing** — the "credits" system is a personal spend-throttle only.
- **Single-user, no authentication, no multi-tenancy, local SQLite only.**

## 10. Deferred Work

Recognised, real gaps that are not yet built but are directly adjacent to what exists:

- A genuine many-to-many `LocalPlanSite` ↔ `Site` relationship table (full/partial/phased, with confidence), replacing the single `matched_site_id` FK.
- Independent Local Plan ingestion/monitoring for Bolton, Oldham, Rochdale, Salford, Tameside, Trafford and Wigan (each has only Places for Everyone allocations today).
- Resolving the remaining `needs_confirmation` cross-boundary allocations with an explicit human decision.
- Investigating the 18 rendering failures from Sprint 3F's Places for Everyone extraction.
- A borough-level geocoding fallback for allocations whose free-text place name fails to geocode (noted since Sprint 2).

## 11. Future Roadmap (headings only — not started, not scoped this document)

- **GIS** — allocation boundary polygons, spatial layers, automated Site↔Allocation overlap computation.
- **Market Intelligence** — comparables, absorption, demand data.
- **Comparable Schemes / Development Intelligence** — the `Development` domain object (product, sales, buyer profile, specification) as a first-class entity distinct from `Site`.
- **Product Experience** — any redesign of the Streamlit UI, a hosted/multi-user product surface, authentication.
- **Financial Intelligence** — the `Financial Model` domain object and appraisal-input mapping.
- **Investment Intelligence** — synthesised, cross-layer "is this worth pursuing" output.
- **Constraint layers** — Green Belt, flood risk, conservation areas, heritage, biodiversity as their own intelligence layers.
- **National rollout** — onboarding councils and joint plans outside Greater Manchester.

---

## 12. Current Version Milestone

**v0.3g-pfe-allocation-onboarding** — Places for Everyone Allocation Onboarding (Sprint 3G), merged to `master` at commit `0a7a8f0`. Full sprint history: `v0.3c-site-plan-images` → allocation image discovery UI fix → `v0.3d-policy-document-discovery` → `v0.3e-joint-plan-support` → `v0.3f-allocation-page-extraction` → `v0.3g-pfe-allocation-onboarding`.
