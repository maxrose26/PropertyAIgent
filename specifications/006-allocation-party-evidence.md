# Allocation Party Evidence (Applicant/Developer/Promoter/Owner Intelligence)

## Objective

AI Allocation Intelligence Summary (`app/reporting/allocation_intelligence_summary.py`) currently synthesises capacity, planning activity/status, and ownership/control evidence for a Local Plan allocation - but never answers "who is behind this planning activity?", even where the platform already holds evidence of it. This spec closes that gap for the one genuinely missing, deterministic evidence source (Applicant), and confirms the wiring already exists for the others (Developer/Promoter/Agent), without ever letting a party be promoted into a stronger role than its evidence supports.

## Business Value

A land buyer/developer/land promoter reading an allocation's AI summary today gets capacity and planning-status intelligence but has to separately dig through the Ownership & Control UI or the raw Application register to find out who submitted the representative planning application. Surfacing this - correctly scoped, never inflated into a stronger claim - materially reduces that manual work, directly serving the "AI-intelligence-first" product principle (`docs/PRODUCT_VISION.md`).

## Requirements

- `RepresentativeApplicationDetail` (the trusted per-Site Application fact set already feeding `AllocationIntelligenceContext`) gains `applicant_name: str | None`, sourced from `Application.applicant_name_raw` for that SAME representative Application - never a different, non-representative Application, never `SchemeIntelligence`'s AI-derived entity fields.
- A non-informative portal placeholder value (confirmed in real production data: the literal string `"Not Available"`, generalised to standard equivalents - `"N/A"`, `"Unknown"`, etc.) cleans to `None`, never surfaced as a real name.
- Applicant evidence is validated by the SAME `referenced_entities` (name, role, site_scope) triple-grounding mechanism `OwnershipContextEntry` already uses - via a new `_allowed_applicant_tuples` allow-set unioned in at the `validate_summary_output` call site, not a parallel validation path.
- Role label is always exactly `"Applicant"` - the model may never self-report a stronger role (Developer/Owner/Promoter) for that same entity unless a SEPARATE, independently-evidenced `ControlRelationship`-sourced tuple grants it.
- Developer/Promoter/Agent: no code change required. `ControlRelationship.role` already reserves these values; `app.reporting.ownership_control` already has customer-facing labels for them; `AllocationIntelligenceContext.ownership_entities` already reads every non-rejected `ControlRelationship` row regardless of role. The only reason none of these appear in a summary today is that no extractor currently writes a `PROMOTER`/`AGENT`/`APPLICANT`(-via-ControlRelationship) row in production - a genuine data-coverage gap, not a wiring gap (confirmed by production audit - see below).
- Generalises the numeric-grounding validator to mask `context.allocation_reference` and `context.plan_status_label` as known trusted strings (root cause of the reported "unsupported numbers: 18, 2.33" false rejection on Heald Green West's own "HOM 2.33"/"Regulation 18" wording - both are rendered verbatim in the prompt but were never in the masking set).
- `compute_context_fingerprint` includes `applicant_name` so a later-discovered or corrected applicant triggers regeneration; a placeholder-vs-blank difference (both clean to the same `None`) must not.

## Non-Requirements

- No new `ControlRelationship`-writing extractor for Applicant/Promoter/Agent, and no backfill/population run against production data - this task changes zero production rows (Section 1's explicit constraint). A `ControlRelationship`-based `APPLICANT` role writer, reusing the exact reserved role vocabulary and idempotent writer (`app.enrichment.control_entities.create_control_relationship_if_absent`) already in place, is a legitimate, small future enhancement - see below.
- `SchemeIntelligence.applicant_company/developer/landowner/site_owner/planning_agent` (AI-inferred, no evidence-grounding of their own) are never read by this pathway. Using them here would launder an ungrounded inference through another AI's "evidence-grounded" context - exactly what the Product Owner's instruction ("do NOT infer the developer from the applicant name") rules out.
- No change to `app/reporting/ownership_control.py`'s own customer-facing role-label wording (used by the separate Site Profile/Application/Ownership & Control UI surfaces) - `"Applicant"` is a summary-specific label choice scoped to `allocation_intelligence_summary.py` only.
- Applicant is exposed only for a Site's representative Application (never every non-representative filing) - consistent with the existing precedent that only the representative Application carries a groundable status/decision fact, and avoids the "Application A, B, C x30" enumeration problem Section 6 of the task explicitly warns against.
- No SUMMARY_SCHEMA change - Applicant claims reuse the existing `referenced_entities` self-report shape exactly.

## Data Model

No schema/migration. `RepresentativeApplicationDetail` (a `dataclasses.dataclass`, not a DB model) gains one field. `ControlRelationship`'s existing bounded `role` vocabulary (`OWNER | APPLICANT | DEVELOPER | PROMOTER | AGENT | ...`) already accommodates every role this spec discusses.

## Architecture Considerations

**Investigation finding (full audit in the implementing session's own report):** `ControlRelationship` (Stage 4B) already has the schema, idempotent/contradiction-aware writer, and reserved role vocabulary needed for Applicant/Promoter/Agent - nothing currently writes those roles. `Application.applicant_name_raw` is solid deterministic evidence (portal-scraped, never AI-derived) that never reached `AllocationIntelligenceContext` before this change. Developer evidence sourced from a real S106 deed (`S106_DEFINED_DEVELOPER`) was ALREADY correctly wired end-to-end; production currently holds zero such rows (0 DEVELOPER-role `ControlRelationship` rows exist platform-wide), so this is a genuine data-coverage limitation, not a defect this task introduces or needs to fix.

**Smallest coherent architecture chosen:** extend the existing Application-level fact set (`RepresentativeApplicationDetail`) for Applicant, rather than inventing a new `ControlRelationship` writer, precisely because this task is authorised to change zero production data and a `ControlRelationship`-based approach would require a backfill run. `ApplicationCompany` was already explicitly rejected (Stage 4B) as an extension target for exactly this kind of evidence-grounded party fact - not reconsidered here.

**Production audit (287 allocations, read-only):** of 101 trusted allocation-linked Applications, 11 (~11%) carry `applicant_name_raw`. Of 27 trusted allocation-linked Sites, 1 carries any `ControlRelationship` evidence at all (a single Certificate A `OWNER` declaration). Platform-wide `ControlRelationship` role distribution: `OWNER: 97, MORTGAGEE: 4`, zero `DEVELOPER`/`PROMOTER`/`AGENT`/`APPLICANT` rows. This means most allocations will show little or no party evidence even after this change - an honest reflection of real data coverage, not a bug.

## Acceptance Criteria

- Applicant evidence reaches `AllocationIntelligenceContext` for a representative Application that has a real, non-placeholder `applicant_name_raw` (confirmed against real production data: East of Boothstown/id 66 now surfaces "Ms Annabel Baker").
- An applicant can never be validated as claiming a stronger role (Developer/Owner/Promoter) without independent evidence for that role.
- The `needs_confirmation`/`rejected` trust boundary applies to applicant evidence with the same structural guarantee (`representative_application is None`) that status/decision already has - no separate gating code needed.
- Heald Green West's own policy reference/plan-stage wording no longer produces a false "unsupported numbers" rejection; a genuinely invented number is still rejected.
- Full test suite passes with zero failures (2422/2422 at implementation time, up from a 2409 baseline - 13 new tests).

## Future Enhancements

- A deterministic `ControlRelationship`-role=`APPLICANT` extractor/backfill (reusing the existing writer/idempotency discipline), so applicant evidence becomes reusable platform-wide (Site Profile UI, buyer profiles, Local Plan Delivery Intelligence) rather than scoped to this one summary pathway - explicitly out of scope here because it requires a production backfill this task is not authorised to run.
- A real Promoter/Agent extractor - no source document pattern for either currently exists in this codebase.
- Reconciling the two different "Applicant"-shaped role-label strings that now coexist (`"Applicant"`, from this task's new pathway, vs. the pre-existing, still-hypothetical `"Applicant evidence"` fallback in `app.reporting.ownership_control`, reachable only if a `ControlRelationship` `APPLICANT`-role row is ever written) once/if the future enhancement above is built.
