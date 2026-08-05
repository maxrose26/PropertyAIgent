# PropertyAIgent — Architecture Status (v2)

**As of:** post-Sprint 3G, master commit `0d996c7` (v1 architecture checkpoint), plus two subsequent data-only visual-evidence backfills against Bury and Stockport (no code changes, no version tag — see §4).

This document is a snapshot of what the platform currently does, as built, plus the sprint-by-sprint history of how it got there. It supersedes [ARCHITECTURE_STATUS_v1.md](ARCHITECTURE_STATUS_v1.md), which remains in place as a historical record of the platform's state at the Sprint 3G merge.

For what each capability *means* functionally, see [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md) — this document deliberately does not re-describe capability purpose/future-scope in detail to avoid duplicating it. For the governing product vision and principles, see [PRODUCT_VISION.md](PRODUCT_VISION.md) and [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md).

---

## 1. Sprint History

### Sprint 1 — Policy Intelligence Foundation
Introduced the platform's Policy Intelligence data model: `LocalPlan`, `AllocationVersion`, `StatusHistory`, `MonitoredSource`, `PolicyChangeEvent`, and the extension of `LocalPlanSite`. Built the `app/policy` package (status normalisation, progression-signal derivation, change detection), rewrote `ingest_local_plan.py` to use the new model with non-destructive diffing, and wrote an idempotent migration/backfill script. Integrated Policy Intelligence into the Site Profile UI. Extended with review gating shortly after initial merge: `PolicyChangeEvent`/`MonitoredSource` extended for review, `app/policy/history.py` and `app/policy/review.py` (approve/reject) built, `ingest_local_plan.py` rewritten to gate ambiguous changes rather than apply them directly, `app/policy/monitor.py` built as the first runnable monitoring command, and council-first source registration (`config/policy_sources.yaml`) introduced.

### Sprint 2 — Multi-Council Policy Intelligence
Generalised the Council entity and source registration to be genuinely council-first rather than single-council-assumed. Onboarded Bury for real (its own Local Plan plus its Places for Everyone allocations), verified multi-council monitoring isolation, validated Stockport against Bury with normalisation improvements, and built the Council administration dashboard. Closed with a multi-council test suite.

### Sprint 3A — Site Profile & Map Presentation
Built `app/ui/site_headline.py` (headline and tooltip synthesis) and fixed an N+1 query pattern by adding a batched `load_applications_for_sites` helper, wiring a richer, batched Local Plan-aware tooltip into the map view.

### Sprint 3B — Policy Evidence Extraction, Report Monitoring & AI Summaries
The largest single sprint, delivered in three connected parts:
- **Policy evidence extraction** — extended `LocalPlan` fields, `PolicyChangeEvent` evidence and `LocalPlanFieldHistory`; built `app/extraction/plan_evidence.py` (page-aware extraction across four structured schemas), `app/policy/document_selection.py` (document-type routing and precedence) and `app/policy/evidence_validation.py` (deterministic validators); extended `review.py` and built the `extract_plan_evidence.py` pipeline/CLI; extended the Council Dashboard UI.
- **Report monitoring & cadence** — added the `MonitoredReport` model with cadence and change-event linkage, built `app/policy/report_discovery.py`, due-date-based monitoring cadence (including `monitor.py --force`), report-level precedence in document selection, trigger-only-on-change extraction gating, review-workflow support for report-level events, and report history/freshness UI.
- **AI Local Plan Summary** — added summary-persistence columns to `LocalPlan`, built the payload builder (`app/reporting/local_plan_summary.py`), an evidence-fingerprint regeneration gate, the generation prompt/schema, and Council Dashboard UI wiring.

All three parts were validated with real Stockport, Bury and Greater Manchester AMR/housing-land-supply documents before merge.

### Sprint 3C — Visual Evidence (v0.3c-site-plan-images)
Introduced the `VisualEvidence` model and a fixed image-type vocabulary, and built the full visual-evidence pipeline: deterministic candidate document selection, deterministic candidate page detection, subprocess-isolated and path-traversal-safe page rendering, AI vision classification, deterministic matching, and human review/primary-image selection — wired into a runnable CLI and into the Site Profile and Local Plan Sites UI pages. Followed shortly after by a small UI fix for allocation image discovery, and later by a batched image-status query and `app/ui/allocation_selector.py` (ordering, labelling, filtering, coverage helpers) for the Local Plan Sites page.

### Sprint 3D — Policy Document Coverage (v0.3d-policy-document-discovery)
Added `PolicyDocumentType` model fields and local-path tracking, built `app/policy/document_types.py`, `config/expected_policy_documents.yaml` and its loader, extended `report_discovery.py` to classify document type on discovery, and built the coverage engine (`app/policy/coverage.py`) and discovery module (`app/policy/document_discovery.py`), surfaced as a coverage dashboard on the Council Dashboard. Validated live against Stockport and Bury.

### Sprint 3E — Joint Plan Support
Added `LocalPlanCouncil` so a genuinely multi-authority plan (Places for Everyone: one adopted plan, 9 participating councils) is represented as exactly one `LocalPlan` row linked to every participating council, never duplicated per authority. Added `AllocationRelationship` to record that two `LocalPlanSite` rows — often across two different plans — describe the same physical site, reference one another, or are jointly delivered, without ever merging the underlying records. Used to resolve Bury's Seedfield/Walshaw/Elton Reservoir duplication.

### Sprint 3F — Allocation Policy Page Extraction (v0.3f-allocation-page-extraction)
Built `app/visuals/allocation_identifiers.py` (deterministic, regex-based extraction of JPA/HOM/HS-style allocation codes and "Policy JP Allocation N" phrasing, normalised for comparison while retaining the verbatim printed text), extended `page_detection.py` with a dedicated allocation-policy-page signal (never disqualified by high text density), and extended `matching.py` with `match_allocation_reference`'s full deterministic priority chain (exact reference → normalised reference → exact title → weaker suggestion → needs review), including allocation-group logic so "JPA1.1"/"JPA1.2"/"JPA1" are recognised as the same real-world allocation for ambiguity-counting without weakening the exact-match comparison itself. Two real bugs were found and fixed during live validation against Places for Everyone: a pattern double-counting "Policy JP Allocation 7" and "JPA 7" as different allocations, and false confidence on Table-11.1-style pages that print many allocation codes at once.

### Sprint 3G — Places for Everyone Allocation Onboarding (v0.3g-pfe-allocation-onboarding)
Onboarded all remaining Places for Everyone allocations via `config/pfe_allocation_onboarding.yaml` (28 single-authority allocations across Bolton/Oldham/Rochdale/Salford/Tameside/Trafford/Wigan, plus 5 genuinely cross-boundary allocations) and `app/policy/pfe_allocation_onboarding.py` (idempotent, find-or-create, full `AllocationVersion` snapshotting, `AllocationRelationship` creation for Northern Gateway). Added `match_stored_identifiers` (re-matching against already-extracted, already-stored detected references/titles, zero rendering or Vision cost) and `rematch_local_plan_evidence` (a full re-match pass plus a bounded secondary-page-proximity suggestion pass that never auto-links) to `pipeline.py`. A dry-run/real-run secondary-page count mismatch was found and fixed during this sprint (dry-run previously undercounted suggestions because pass-1 matches weren't tracked independently of ORM mutation). Merged to `master`, tagged `v0.3g-pfe-allocation-onboarding`.

---

## 2. Current Platform Capabilities

Full functional detail lives in [PLATFORM_ARCHITECTURE.md](PLATFORM_ARCHITECTURE.md). In summary, as of this document:

- **Planning Intelligence** — mature; 10-council multi-portal scraping, AI-assisted extraction/reconciliation, site consolidation, phase tracking, build-status, on-demand enrichment.
- **Policy Intelligence** — mature for covered councils; Bury and Stockport fully onboarded with their own Local Plans, all 9 Places for Everyone authorities onboarded with their PfE allocations, full change-protected monitoring, document coverage tracking, AI Local Plan Summaries, and deterministic visual-evidence extraction and matching.
- **Market Intelligence** — not started.
- **Development Economics** — not started.
- **AI Decision Support** — embryonic; narrow, production-proven instances exist (AI Local Plan Summary, AI scheme summaries, bounded visual classification), but no cross-layer synthesis yet.
- **Workflow & Collaboration** — not started as a customer-facing layer.

## 3. Council Coverage

- **Application scraping:** Bury, Stockport, Trafford, Rochdale, Manchester, Oldham, Tameside, Bolton, Wigan, Salford (10 Greater Manchester authorities, config-driven).
- **Policy Intelligence:** Bury and Stockport fully onboarded with their own Local Plan allocations; Bolton, Oldham, Rochdale, Salford, Tameside, Trafford and Wigan linked to Places for Everyone via `LocalPlanCouncil` with their PfE allocations onboarded, but with no independent Local Plan of their own ingested yet.

## 4. Since the v1 Checkpoint

Two data-only visual-evidence backfill runs were performed against master's already-merged Sprint 3F/3G code (no branch, no code change, no version tag — both runs found the existing logic behaved correctly against genuinely new data):

- **Bury Local Plan** — run under current Sprint 3F allocation-page detection. Found 11 new candidate pages; correctly left two multi-allocation identifier pages unlinked (ambiguous, ≥2 real candidates each); confirmed, by direct visual inspection, that Bury's own Local Plan PDF contains no genuine allocation-specific map — only its one borough-wide "Local Plan Key Diagram" (not allocation-specific) and an abstract PfE spatial-strategy schematic. Allocation image coverage unchanged (1 of 7, via Northern Gateway's separate masterplan source).
- **Stockport Local Plan** — run for the first time under Sprint 3F logic (previously only processed under the older Sprint 3C-only signals). Found 8 new candidate pages; correctly left 4 multi-allocation schedule pages unlinked; found one genuine unambiguous text-based match (`HOM 2.12` / Compstall Mills). Confirmed, by direct visual inspection and the plan's own text ("boundaries of these sites are shown on the Policies Map"), that Stockport's Local Plan PDF contains no individual allocation maps either — site boundaries live only in the separate, already-onboarded, borough-wide Policies Map. Allocation image coverage improved from 0 of 37 to 1 of 37.

Both runs confirm the same underlying finding: **neither council's own Local Plan document contains per-allocation maps** — allocation boundaries live in each council's separate Policies Map, which is already a distinct, already-onboarded document type. This is a genuine content characteristic of these two source documents, not a pipeline gap.

## 5. Known Limitations

- **`LocalPlanSite` is single-council per row.** A genuinely cross-boundary allocation gets one real council attributed to it (backed by evidence) plus an `AllocationRelationship` to any counterpart row, rather than a native multi-council field on one row.
- **Cross-boundary council attribution is evidence-based, not always explicit.** Five Places for Everyone allocations (Northern Gateway's two parts, Stakehill, Medipark, Timperley Wedge) are attributed to a council via real-world place-name/cross-reference evidence rather than one explicit sentence in the plan naming the authority — deliberately left `review_status="needs_confirmation"`.
- **`matched_site_id` is a single nullable FK** — an allocation can be linked to at most one Application-derived Site, even though a real allocation can in principle be delivered as several physical Sites.
- **Only Bury and Stockport have their own independently-ingested Local Plan with a self-authored site-allocations schedule.** The other 7 GM authorities are only known to this platform through their Places for Everyone allocations.
- **18 Places for Everyone images carry a detected reference that matches no onboarded allocation** — correctly left unmatched, not a defect.
- **Some rendered pages fail outright** (18 of 174 candidate Places for Everyone pages, concentrated in one large appendix) — logged as errors, not blocking, since candidate detection and matching for every other page were unaffected.
- **Allocation-specific maps do not exist in either onboarded council's own Local Plan document** (§4) — boundary visuals for Bury and Stockport allocations depend entirely on each council's separate Policies Map, which is not yet deterministically page-matched to individual allocations the way policy-text pages are.
- **No Market Intelligence, Development Economics, or full AI Decision Support layer exists yet** — see [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md).
- **No real payment/billing** — the "credits" system is a personal spend-throttle only.
- **Single-user, no authentication, no multi-tenancy, local SQLite only.**

## 6. Recommended Next Phase

Per [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), the platform's Planning Intelligence and Policy Intelligence layers are mature enough that further investment there has diminishing near-term return relative to starting **Market Intelligence** — the next capability in the stack, and the direct, non-optional dependency for Development Economics. Land Registry Price Paid Data is the recommended first slice: free, structured, and immediately useful as a land-value/disposal comparable before any paid data source is integrated.

Independently, closing the remaining Policy Intelligence coverage gap (independent Local Plan monitoring for the 7 Greater Manchester authorities currently known only through Places for Everyone) remains a low-risk, high-confidence extension of an already-proven pattern (Bury/Stockport), and can proceed in parallel with Market Intelligence work without contention.

## 7. Current Version Milestone

**Post-`v0.3g-pfe-allocation-onboarding`**, plus the `docs/ARCHITECTURE_STATUS_v1.md` checkpoint (master commit `0d996c7`) and two subsequent data-only visual-evidence backfills (Bury, Stockport — no version tag, no code change). Full sprint history: Sprint 1 (Policy Intelligence Foundation) → Sprint 2 (Multi-Council Policy Intelligence) → Sprint 3A (Site Profile & Map) → Sprint 3B (Policy Evidence Extraction, Report Monitoring & AI Summaries) → `v0.3c-site-plan-images` (Sprint 3C, Visual Evidence) → `v0.3d-policy-document-discovery` (Sprint 3D) → Sprint 3E (Joint Plan Support) → `v0.3f-allocation-page-extraction` (Sprint 3F) → `v0.3g-pfe-allocation-onboarding` (Sprint 3G) → **Sprint 4.0 (this document): Product Vision & Strategic Roadmap, documentation only.**
