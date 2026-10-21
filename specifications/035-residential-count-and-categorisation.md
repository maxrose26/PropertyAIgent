# 035. Residential count and categorisation: scheme admission independent of buyer profiles

Status: **specification and bounded implementation proposal for review. Nothing here is implemented, and no database admission, production behaviour, allowance policy, council request or Stage advancement is authorised by this document.** Specification version `residential-count-v1`. Executable acceptance examples: `specifications/035-residential-count-examples.json`, checked by `tests/test_spec035_residential_count_examples.py`. Builds on 004, 024/025 (CountAssessment, subject decomposition), 028 (mandate fit), 029-stage4 (material discovery), 033/034 (observations and Phase 2). Stage 4 remains OPEN.

## 1. Intelligence layer and purpose
Planning Applications and Housing Mix, feeding the Site. The question this answers for every valid application is: **how many homes does it propose, on what evidence, and is that enough to treat it as a scheme?** It answers it once, for the platform, before any buyer is considered.

## 2. Product architecture (the clarification)
Three decisions, in this order, never merged:
1. **Retention (every valid application).** Discovery keeps every valid identity and its evidence (specification 029: the 10-unit threshold is not a discovery filter). Nothing below is a reason to discard or to prune (retention policy remains unresolved; interim rule: preserve everything).
2. **Scheme admission (platform-wide, buyer-independent).** An application is **admitted as a scheme** when its **supported proposed residential total is at least the platform admission threshold** (configuration `unit_threshold`, 10 for every council today). Admission triggers ingestion into the scheme layer and deeper assessment (documents, extraction, site linking).
3. **Buyer matching (afterwards).** Mandates, buyer minimum and maximum sizes, tenure and geography (specification 028) apply to admitted schemes only and never influence admission. A scheme that no current buyer wants is still a scheme.
A valid application below the threshold is **retained and not promoted**: it stays an application with its evidence and count state, it is not a scheme, and it is promoted only by section 7. `Council.unit_threshold` is therefore the platform admission threshold, not a buyer parameter; its name stays, its meaning is stated here.

## 3. Count model: four separate counts (never one number)
Each count is a separate **CountAssessment-carried metric** (the existing frozen carrier is reused unchanged: its `metric` is a free string, its precision vocabulary is `EXACT / APPROXIMATE / RANGE / UNKNOWN`). Each is either a number with provenance or `NOT_ESTABLISHED` with a reason code; **absence is never zero and nothing is inferred** ("the existing bungalow" is not "1").
| Metric | Meaning |
|---|---|
| `proposed_total_residential` | Dwellings the application would provide in total in its own scope (new build, conversion output, replacement dwellings). **The admission measure.** |
| `existing_residential` | Dwellings on the application site immediately before, when the text says so. Adjoining or neighbouring stock is not site stock. |
| `demolished_residential` | Existing dwellings lost: physically demolished or removed, or converted or replaced away (reason `DEMOLITION`, `CONVERSION_AWAY` or `REPLACEMENT`). |
| `net_residential` | `proposed_total - demolished`, established **only** when both are established (an explicit "no dwellings created" or "none lost" counts as 0). Can be negative. Recorded for the buyer-facing layers; **not** the admission measure. |
Qualified quantities: wording such as "up to 50" or "not exceeding" records `proposed_total` as a **qualified maximum** (`UP_TO:N`), never as an exact total (reuse `qualified_residential_quantity`). Non-dwelling measures (bedrooms, beds, car-parking spaces, storeys, blocks, buildings, retail or commercial units) are never dwellings; they may be recorded as separate non-dwelling measures.

## 4. Counting rules (R-)
* **R-ATTACH.** A number is a dwelling count only when it is attached to a dwelling noun (dwelling, house, flat, apartment, maisonette, bungalow, townhouse, home, or residential/self-contained/affordable/retirement/extra-care/student unit). It is not a count when it describes bedrooms, storeys, spaces, persons or blocks ("4 no. apartment blocks" counts blocks).
* **R-UNITS.** A bare "units" counts as dwellings only inside an explicitly residential clause and with no other unit type in the clause.
* **R-SUM.** Explicitly joined components of one creation clause, or of separate creation clauses, are **added** ("5 houses and 5 flats" = 10; "9 dwellings and conversion of barn to 2 dwellings" = 11). Components that are not both attached creation counts are never added; a doubtful case is `NOT_ESTABLISHED`, not a guess.
* **R-PRODUCT.** An explicit per-block count multiplied by an explicit block count ("2 blocks of 6 flats each" = 12).
* **R-EXISTING.** A mention is about existing, removed, approved, wider-scheme or parent dwellings when existing/removal/approval/wider wording precedes it in its clause with no creating wording in between, when a transformation ("change of use from/of", "conversion of", "alterations to") precedes it with nothing introducing the new use, or when it is not housing supply (holiday, temporary, caravan, lodge). Such mentions feed `existing` or `demolished` or the parent context, never `proposed_total`.
* **R-HOUSING.** Holiday, temporary, caravan/lodge, hotel, serviced and short-let accommodation, and C2 bed counts, are not dwelling supply (`RETAIN_NOT_RESIDENTIAL_SUPPLY`). Specialist housing that is genuinely self-contained dwellings (extra-care apartments) counts; decision D4.
* **R-CONTEXT.** A figure from policy context, a wider allocation, a parent permission or the planning-statement boilerplate (existing `_is_policy_target_context`) is context, never this application's total.
* **R-UNUSABLE.** A blank, unknown or truncated proposal establishes nothing (`RETAIN_UNUSABLE_PROPOSAL`).
* **R-BOUND.** Wording analysis is linear in the proposal length (bounded at 8192 characters); a pathological input must not stall a run (the existing `extract_unit_count` is cubic on long digit runs: a separate fix, precondition P0 in section 9).

## 5. Categorisation and scheme role
Category reuses the existing `classify_application_category` vocabulary (`primary_residential`, `outline_application`, `reserved_matters`, `variation_or_amendment`, `condition_discharge_or_details`, `external_consultation`, `screening_or_scoping_opinion`, `build_to_rent`, `affordable_or_specialist_housing`, `mixed_use`, `non_target_admin_or_minor`, `unknown`). A **scheme role** is added next to it:
| Role | Typical categories | Own proposed total? | Can admit as a scheme? |
|---|---|---|---|
| `NEW_SCHEME` | primary_residential, outline, mixed_use, build_to_rent, affordable_or_specialist | yes, when stated | yes |
| `PHASE_OF_PARENT` | reserved_matters, phases/parcels | its own phase count only | yes, as a phase linked to its parent |
| `AMENDMENT_OF_PARENT` | variation_or_amendment, non-material amendment, s73 | **no** | never alone; linked to the parent |
| `DISCHARGE_OF_PARENT` | condition_discharge_or_details | **no** | never alone; linked (a progress signal for the parent) |
| `PRE_APPLICATION_SIGNAL` | screening_or_scoping_opinion | **no** | no; watchlist (existing behaviour) |
External consultations are retained as related records of the other council's application (existing `external_consultation`).

## 6. Admission outcomes (the single vocabulary)
| Outcome | When |
|---|---|
| `ADMIT_SCHEME` | supported `proposed_total_residential` >= threshold, scheme-bearing role |
| `ADMIT_FOR_ASSESSMENT` | a qualified maximum >= threshold, or supported sources disagree (`COUNT_CONFLICT`) with at least one source >= threshold; never recorded as an exact total (decision D3) |
| `ROUTE_COUNT_UNCONFIRMED` | clearly residential, no supported count: routed to the **existing** unit-confirmation stage; not a scheme until a supported total exists |
| `RETAIN_BELOW_THRESHOLD` | supported total below threshold: valid, retained, **not promoted** |
| `RETAIN_NOT_RESIDENTIAL_SUPPLY` | no dwellings created (hotel, retail, holiday homes, plant, alterations to existing flats, care beds) |
| `RETAIN_RELATED_TO_PARENT` | amendment or discharge; carries the parent link and parent context count |
| `RETAIN_WATCHLIST` | screening or scoping opinion |
| `RETAIN_UNUSABLE_PROPOSAL` | R-UNUSABLE |
Every outcome carries a fixed reason code, the rule version and the evidence it rests on.

## 7. Promotion of a retained application (no automatic promotion)
A retained application becomes a scheme only through a **new, recorded assessment** (never an edit): (a) new supported evidence raises its own proposed total to the threshold (a form total, a decision notice, a document); (b) a **verified** parent relationship shows it is a phase of an admitted scheme (the existing explicit-wording and citation rules apply; wording alone is an unverified lead, as in the current `EXPLICIT_WORDING_UNVERIFIED_LEAD`); or (c) a Site-layer reconciliation (existing `scheme_reconciliation`) shows several applications are one scheme. A later complete capture or detail page is linked to, never substituted for, the earlier observation (specification 033). Small applications that happen to sit on a large site are **not** summed by admission: aggregation is a Site question.

## 8. Evidence provenance
Every count carries: `source_kind` (`LISTING_PROPOSAL_TEXT`, `DETAIL_PROPOSAL_TEXT`, `APPLICATION_FORM_STRUCTURED`, `DECISION_NOTICE`, `PLANNING_STATEMENT`, `DOCUMENT_OTHER`), `source_ref` (ledger item key or receipt digest, document id and hash), `locator` (field and character span), the literal `quote`, `rule_version`, `observed_at` and `rank`. Precedence (higher wins only when it is **supported**; ties and disagreements are never resolved silently): structured form total ("Total **proposed** residential units", never the adjacent "existing" field) > decision notice > proposal text > planning statement. Disagreement between supported sources is `material_conflict` (the existing `assess_positions` semantics), recorded with both sources, resolved only by new evidence. Evidence is append-only with timestamps; "first observed" is not "newly submitted" (specification 033).

## 9. Mapping to the current implementation
| Concern | Where it lives today | Observation |
|---|---|---|
| Legacy weekly admission | `app/pipeline/run_weekly.py` `stage_scrape`: persists only `qualify(...).qualifies` applications (plus progress signals and watchlist); `UNIT_GATE_PASSED`; `stage_confirm_units`; documents; extraction; `SchemeIntelligence` ("one row per qualifying 10+ application") | Below-threshold applications are **discarded** here; count = the largest candidate, not a total |
| Count extraction | `app/scrapers/unit_filter.py` `extract_unit_counts` / `qualify` / `classify_application_category` (max of candidates; categories; threshold parameter) | Takes the largest number, so it misses summed components, counts removed/existing dwellings, beds and holiday homes as units |
| Eligibility containment | `app/reporting/residential_count_eligibility.py` (qualified quantity, component-not-whole, ancillary works) | Rejection tests only; never supplies a count |
| Count carrier and arithmetic | `app/reporting/residential_count.py` `CountAssessment` / `assess_positions` (frozen for v6-v8 oracles) | Reused unchanged as the carrier |
| Ledger screening | `app/ingestion/listing_screening.py` `screen_row` v1 (and the unmerged v2 size assessment, PR 163) | v1: disposition from the same qualifier; v2 is conservative and does not sum |
| Ledger to application | `app/ingestion/new_identity.py` `execute` (disposition gate `SUPPORTED_PROCESSING_PRIORITY` / related) -> `app/pipeline/discovery_admission.py` `admit_identity` (identity only, `unit_confirmation_status='discovery_pending'`, `unit_facts NOT_WRITTEN`) | `stage_link_sites` skips `discovery_pending`; nothing promotes a pending row to a scheme or writes counts |
| Application to scheme | `SchemeIntelligence` rows come from `stage_extraction` / `intelligence_refresh` for confirmed applications | No count-assessment object exists between screening and `estimated_unit_count` |
**Gap against the examples** (38 examples; 21 differ; the lists are asserted by the test): *legacy false negatives* (supported total >= 10, not admitted): `E06 E07 E08 E10` (sums and products). *Legacy false positives* (admitted without a supported total >= 10): `E17 E21 E22 E34 E35 E36` (change of use away from housing, care beds, holiday homes, replacement below threshold, wider-scheme figure, alterations to existing flats). *Count differences* (the legacy number is not the proposed total): `E06 E07 E08 E10 E14 E17 E21 E22 E23 E24 E25 E26 E27 E28 E29 E33 E34 E35 E36 E37 E38`. Agreement: 17 examples including all simple "erection of N dwellings" cases, conversion output, number words, and the 49-apartment Bolton scheme. Historical Bolton screening results stay as recorded (rule v1 is untouched).

## 10. Bounded implementation proposal (for review; nothing built)
**P0 precondition (separate task already started):** make `extract_unit_count` linear on long digit runs; screening must not stall.
**Phase A: pure assessment, no database change.**
1. One new pure module `app/ingestion/count_assessment.py`: `assess_proposal(text, *, application_type=None, evidence=(), threshold)` returning the four metrics (each a `CountAssessment`-carried value or `NOT_ESTABLISHED` + reason), category, scheme role, parent context, admission outcome, reason and provenance. It reuses `qualify`/`classify_application_category`, `residential_count_eligibility` patterns and the PR 163 attachment logic, adds R-SUM and R-PRODUCT, and is pinned by the 38 examples (every example must reach its expected outcome; the gap lists in the test become empty).
2. Screening rule **v3** (`manchester-listing-screen-assessment-v3`): the v1 result unchanged plus an additive `count_assessment` block. v1 stays the default; v3 is opt-in per run through the existing owner-registered configuration; no caller selects it until approved. Recommendation: PR 163's v2 is superseded by v3 and need not merge (its attachment logic is reused); merging it as an interim opt-in remains harmless and is the Product Owner's call (decision D7).
3. Ledger: the SCREENING child checkpoint carries the block (existing checkpoint payload; no schema, ACL or function change; the ledger already retains below-threshold results append-only, so **retention needs no new mechanism**). A read-side report lists admission outcomes and the recorded-versus-recomputed comparison, labelled separately.
**Phase B: database admission (needs its own approval; do not start):**
4. Disposition-to-admission gate in `new_identity.execute` accepts `ADMIT_SCHEME` / `ADMIT_FOR_ASSESSMENT` (the same `admit_identity` identity-only path: still `discovery_pending`).
5. A bounded promotion step, through the existing B2 hand-off, writes `estimated_unit_count` (the supported proposed total, EXACT only) and moves a `discovery_pending` row to the existing `confirmed_qualifying` status so the existing document, extraction and site-link stages pick it up unchanged. `ADMIT_FOR_ASSESSMENT` rows are held at a distinct status for review. No new table; the existing `String(30)` status column suffices; `estimated_unit_count` is the only fact column written; protected fields untouched.
6. Retained below-threshold applications: **R1 (recommended):** stay in the ledger and observation history only (already durable, queryable, promotable by a new assessment); **R2:** also create `Application` rows with a `retained_below_threshold` status (a database admission change affecting every Application-reading surface; not recommended first).
**Not changed by any phase:** schema, ACLs, the worker function or its allowance policy, resource ceilings, council requests, scheduling, buyer mandates or fit logic, the frozen `CountAssessment` and `residential_count_eligibility` modules, and every historical result.

## 11. Preservation of historical results
Rule versions are immutable and every stored result keeps the version that made it. No automatic re-screening. A re-assessment under v3 is a **new** ledger item linked to the old one by the existing append-only history; the old result is never edited, re-identified or deleted. Local recomputation is always labelled "local recomputation", beside the recorded values, as in the 24-scheme review. Archived Bolton audit and receipt identities are unaffected (specification 033 backward-compatibility tests).

## 12. Acceptance
(1) All examples reach their expected outcome under v3 (the gap sets in the test shrink to empty in the implementing change). (2) v1 output is byte-identical to master on the archived 24 Bolton records and the example texts. (3) No example is admitted on a parent, wider-scheme or existing-stock figure. (4) Adversarial 8192-character inputs complete within the bound. (5) Net arithmetic and the four-count separation hold for every example. (6) Phase B tests (disposable PostgreSQL) cover promotion, idempotence, rollback to `discovery_pending`, and that no protected field changes.

## 13. Decisions for the Product Owner
* **D1** Confirm the admission measure is the **proposed gross total** (so "demolish 14 flats, build 12 houses" admits at 12 with net -2), and that a negative net does not stop admission.
* **D2** Confirm retention location: R1 (ledger and observation history only; recommended) or R2 (Application rows).
* **D3** "Up to N" and conflicting sources: admit **for assessment** (recommended) rather than as a scheme or not at all.
* **D4** Specialist housing: self-contained extra-care apartments count; care-home beds, student cluster beds and hotel rooms do not (recommended). Confirm build-to-rent counts as dwellings.
* **D5** Site-level aggregation of several small applications stays a Site question, not admission (recommended).
* **D6** Treat `unit_threshold` as the platform admission threshold (documentation only; no rename).
* **D7** Fate of PR 163 (supersede by v3, or merge as interim opt-in).
