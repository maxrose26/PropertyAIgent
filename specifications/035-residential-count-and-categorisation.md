# 035. Residential count and categorisation: scheme admission independent of buyer profiles

Status: **specification and bounded implementation proposal for review. Nothing here is implemented, and no database admission, production behaviour, allowance policy, council request or Stage advancement is authorised by this document.** Specification version `residential-count-v2` (v2 separates proposed and approved counts; v1 was the proposed-only draft). Executable acceptance examples: `specifications/035-residential-count-examples.json`, checked by `tests/test_spec035_residential_count_examples.py` against the pure reference in `tests/spec035_reference.py`. Builds on 004, 024/025 (CountAssessment, subject decomposition), 028 (mandate fit), 029-stage4 (material discovery), 033/034 (observations and Phase 2). Stage 4 remains OPEN.

## 1. Intelligence layer and purpose
Planning Applications and Housing Mix, feeding the Site. The question this answers for every valid application is: **how many homes does it propose, on what evidence, and is that enough to treat it as a scheme?** It answers it once, for the platform, before any buyer is considered.

## 2. Product architecture (the clarification)
Three decisions, in this order, never merged:
1. **Retention (every valid application).** Discovery keeps every valid identity and its evidence (specification 029: the 10-unit threshold is not a discovery filter). Nothing below is a reason to discard or to prune (retention policy remains unresolved; interim rule: preserve everything).
2. **Scheme admission (platform-wide, buyer-independent).** An application is **admitted as a scheme** when a **supported, applicable proposed or approved residential dwelling count is at least the platform admission threshold** (configuration `unit_threshold`, 10 for every council today). Admission is a **size-eligibility** decision; planning status, category and every other admission condition are separate gates and are not decided by a count. Admission triggers ingestion into the scheme layer and deeper assessment (documents, extraction, site linking).
3. **Buyer matching (afterwards).** Mandates, buyer minimum and maximum sizes, tenure and geography (specification 028) apply to admitted schemes only and never influence admission. A scheme that no current buyer wants is still a scheme.
A valid application below the threshold is **retained and not promoted**: it stays an application with its evidence and count state, it is not a scheme, and it is promoted only by section 7. `Council.unit_threshold` is therefore the platform admission threshold, not a buyer parameter; its name stays, its meaning is stated here.

## 3. Count model: separate counts, each with its own basis (never one number)
Each count is a separate **CountAssessment-carried metric** (for the approved basis too) (the existing frozen carrier is reused unchanged: its `metric` is a free string, its precision vocabulary is `EXACT / APPROXIMATE / RANGE / UNKNOWN`). Each is either a number with provenance or `NOT_ESTABLISHED` with a reason code; **absence is never zero and nothing is inferred** ("the existing bungalow" is not "1").
| Metric | Meaning |
|---|---|
| `proposed_total_residential` | Dwellings the application **asks for** in its own scope (new build, conversion output, replacement dwellings). Basis `PROPOSED`. |
| `approved_total_residential` | Dwellings a **permission grants**. Basis `APPROVED`; needs permission evidence (section 3B). |
| `existing_residential` | Dwellings on the application site immediately before, when the text says so. Adjoining or neighbouring stock is not site stock. |
| `demolished_residential` | Existing dwellings lost: physically demolished or removed, or converted or replaced away (reason `DEMOLITION`, `CONVERSION_AWAY` or `REPLACEMENT`). |
| `net_residential` | `proposed_total - demolished` (the proposed basis), established **only** when both are established (an explicit "no dwellings created" or "none lost" counts as 0). Can be negative. Recorded for the buyer-facing layers; **not** the admission measure. |
Qualified quantities: wording such as "up to 50" or "not exceeding" records `proposed_total` as a **qualified maximum** (`UP_TO:N`), never as an exact total (reuse `qualified_residential_quantity`). Non-dwelling measures (bedrooms, beds, car-parking spaces, storeys, blocks, buildings, retail or commercial units) are never dwellings; they may be recorded as separate non-dwelling measures.

## 3A. Count bases: proposed and approved are different facts
* **Proposed** is what an application asks for; **approved** is what a permission grants. Neither is a version of the other, neither is ranked against the other, and a later proposed revision never overwrites an approval (it sits beside it).
* **Dwelling count, planning status and construction progress are three separate facts.** A refused application keeps its proposed count; a granted permission's count says nothing about whether anything is built; construction progress never changes a count. None of the three is derived from, or overrides, another.
* Mixed-use schemes count **residential dwellings only** (section 3E).

## 3B. The count evidence record
Every count (either basis, every metric) is held as one or more append-only **evidence records**, never as a bare number:
| Field | Meaning |
|---|---|
| `basis`, `scope` | `PROPOSED` / `APPROVED`; the application reference and phase or parcel label (`whole` when the evidence covers the application as a whole) |
| `value`, `precision`, `qualifier` | an exact number, `UP_TO:N` (qualified maximum), approximate or a range; the wording qualifier ("outline", "up to") is preserved |
| `source_kind`, `source_ref`, `locator`, `quote` | where it came from: ledger item or receipt digest, document id and hash, field and character span, the literal words |
| `document_date`, `revision` | the **document's own date** (not the download time) and its revision identifier or content hash |
| `evidence_status` | `SUPPORTED`, `UNSUPPORTED_AS_APPROVED` (an approval claimed without permission evidence), `HISTORICAL` (explicitly superseded), `CONFLICTING` |
| `relations` | explicit relationships stated by supported evidence: `supersedes`, `revises`, `alternative_to`, part-of |
Rules:
* **Approval needs permission evidence.** Only a decision notice or an approved-plans schedule (the permission itself) can establish an approved count. An application form, proposal text, planning statement, officer recommendation or a later document merely citing a permission cannot; such a claim is kept as `UNSUPPORTED_AS_APPROVED` and is never shown as approved.
* **Preserve everything; the latest upload does not win.** Historical and alternative permissions are retained. A later date, a later upload or a larger figure never supersedes an earlier one. Supersession exists only where a supported record explicitly states it about the other ("revision B supersedes A"; "this permission varies permission 1"); an unsupported record cannot supersede a permission.
* **Resolution per basis and scope.** One record, or agreeing records: `RESOLVED` (or `QUALIFIED_MAXIMUM`). Distinct figures with no explicit relationship: `CONFLICT_UNRESOLVED`, and they stay unresolved until their scope or revision relationship is established. Declared separate permissions: `ALTERNATIVE_PERMISSIONS`, shown side by side. **Different scopes never conflict**; a combined total across phases exists only with explicit non-overlap evidence, otherwise the basis is `PER_SCOPE` and each phase stands on its own.
* Evidence is append-only and timestamped (specification 033): "first observed" is not "newly submitted". Section 8's source precedence applies **within** a basis only.

## 3C. User presentation: the headline quantity
Always one clearly labelled headline; a number is never shown without its basis.
| Situation | Headline |
|---|---|
| Approval established | `Approved: 49` prominently; a later proposed revision alongside: `Proposed revision: 52` (or `Proposed (relationship to the approval not established): 52` when no revision relationship is evidenced) |
| Qualified approval | `Approved (outline): up to 50` (qualifiers always preserved) |
| No established approval | `Proposed: 49`, or `Proposed (outline): up to 50` |
| Several phases | by phase, `Proposed by phase (Phase 1: 49, Phase 2: 52)`; a combined `Proposed: 101 (Phase 1: 49, Phase 2: 52)` only with non-overlap evidence |
| Relevant count unresolved (conflict or alternative permissions) | **`Unit count under review`** with the competing evidence listed (record, value, source, date, revision); the system never silently picks one |
| Nothing supported | `Unit count not established` |
Planning status and construction progress are shown as their own labelled facts next to the headline, never folded into it.

## 3D. Search
* Three **count bases**: Approved, Proposed, Either. **Either is the discovery default.** The threshold is selectable (default 10).
* Each result states the **basis that caused the match** (`matched_by`), e.g. at a threshold of 50 a scheme approved at 49 with a proposed revision of 52 matches only by Proposed.
* Two result classes, never mixed: **Confirmed matches** (a supported exact count at or above the threshold, or conflicting figures that are *all* at or above it: size is established and the quantity is "under review") and **Possible matches** (a qualified maximum at or above the threshold, or competing figures that **straddle** the threshold, e.g. 9 versus 12). A possible match is never presented as confirmed.
* Results are **deduplicated by scheme identity**: one row per scheme with the best class, the union of causing bases, and every contributing application kept.

## 3E. Mixed use
Only **residential dwellings** count towards any residential metric. Commercial units are recorded separately as `non_residential_units` by kind (retail, office, ...) and are never added: "9 flats and 1 shop" is **9** residential dwellings and does not admit; "10 flats and 2 shops" is 10 and admits; the shops remain on the record.

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
| `ADMIT_SCHEME` | a supported, resolved `proposed` or `approved` residential count >= threshold in some scope, scheme-bearing role (size eligibility only) |
| `ADMIT_FOR_ASSESSMENT` | a qualified maximum (proposed or approved, e.g. "outline approval for up to 50") >= threshold, or unresolved conflicting or alternative figures (`COUNT_CONFLICT`) with at least one >= threshold; routed to assessment and never recorded as an exact confirmed total (decision D3) |
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
Every count carries: `source_kind` (`LISTING_PROPOSAL_TEXT`, `DETAIL_PROPOSAL_TEXT`, `APPLICATION_FORM_STRUCTURED`, `DECISION_NOTICE`, `PLANNING_STATEMENT`, `DOCUMENT_OTHER`), `source_ref` (ledger item key or receipt digest, document id and hash), `locator` (field and character span), the literal `quote`, `rule_version`, `observed_at` and `rank`. Precedence, applied **within a basis only** (proposed and approved are never ranked against each other; higher wins only when it is **supported**; ties and disagreements are never resolved silently): structured form total ("Total **proposed** residential units", never the adjacent "existing" field) > decision notice > proposal text > planning statement. Disagreement between supported sources is `material_conflict` (the existing `assess_positions` semantics), recorded with both sources, resolved only by new evidence. Evidence is append-only with timestamps; "first observed" is not "newly submitted" (specification 033).

## 9. Mapping to the current implementation
| Concern | Where it lives today | Observation |
|---|---|---|
| Legacy weekly admission | `app/pipeline/run_weekly.py` `stage_scrape`: persists only `qualify(...).qualifies` applications (plus progress signals and watchlist); `UNIT_GATE_PASSED`; `stage_confirm_units`; documents; extraction; `SchemeIntelligence` ("one row per qualifying 10+ application") | Below-threshold applications are **discarded** here; count = the largest candidate, not a total |
| Count extraction | `app/scrapers/unit_filter.py` `extract_unit_counts` / `qualify` / `classify_application_category`; the LLM extraction pass fills `SchemeIntelligence.total_units_final` | One number per application; no basis, scope, source or revision |
| Eligibility containment | `app/reporting/residential_count_eligibility.py` | Rejection tests only; never supplies a count |
| Count carrier and arithmetic | `app/reporting/residential_count.py` `CountAssessment` / `assess_positions` (frozen) | Reused unchanged as the carrier; has `scope_type`, `scope_label`, precision and `sources` but no basis |
| Fact reconciliation | `app/reporting/scheme_reconciliation.py` `FactPosition` (scope, `decision_date`, `planning_role`, `decided_state`), `OperativeFact` (`FACT_RESOLVED` / `FACT_NOT_DETERMINED` / `FACT_CONFLICT`), `resolve_planning_role` | Already models scope, decision date and unresolved conflict; reused as the pattern for the read model; has no proposed/approved basis dimension |
| Ledger screening | `app/ingestion/listing_screening.py` `screen_row` v1 (and the unmerged v2, PR 163) | Proposal text only, one qualifier count |
| Ledger to application | `app/ingestion/new_identity.py` -> `app/pipeline/discovery_admission.py` `admit_identity` (identity only, `discovery_pending`, `unit_facts NOT_WRITTEN`) | `stage_link_sites` skips `discovery_pending`; nothing promotes a pending row or writes counts |
| Storage of a count | `Application.estimated_unit_count` (one integer) and `SchemeIntelligence.total_units_final` (one integer); `Application.decision_issued_date` | See 9A |
| Documents | `Document` has `doc_type`, `downloaded_at`, `content_hash` | **No document date and no revision field**; the download time is not the document date |
| Consumers | 122 references in ~30 files, including `app/ui/common.py` (merged `total_units_final` for the headline), `app/ui/site_headline.py`, `app/reporting/entity_search.py`, `app/policy/buyer_matching.py`, `app/reporting/dashboard.py`, `app/ui/pages/0_Explore.py` | Every one reads a single scalar |
**Gap against the examples** (52 examples; the test asserts these lists). *Plain examples* (38, proposal text only): 19 differ from the legacy implementation. Legacy false negatives (supported total >= 10, not admitted): `E06 E07 E08 E10`. Legacy false positives (admitted without a supported total >= 10): `E17 E21 E22 E34 E35 E36`. Count differences: `E06 E07 E08 E10 E14 E17 E21 E22 E23 E24 E25 E26 E27 E28 E29 E33 E34 E35 E36`. The mixed-use examples `E41` (9 flats and 1 shop) and `E42` agree with the legacy count. *Evidence-model examples* (14: `E37 E38 E38b-E38m`): the legacy single scalar **cannot represent them at all** (basis, scope, source, revision, conflict, alternatives), so they are not scored as differences. Historical Bolton screening results stay as recorded (rule v1 is untouched).

### 9A. Does a single `estimated_unit_count` have to be replaced?
**Yes, as the source of truth; no, as a column.** One integer cannot hold a proposed and an approved figure, several phases, a conflict, a qualified maximum, a source, a document date or a revision, and the 14 evidence examples cannot be expressed in it. It also silently chooses (the largest candidate, or the last write). Proposal: keep `estimated_unit_count` and `total_units_final` for backward compatibility as **derived caches** with a stated meaning: *the supported, resolved, single-scope exact headline quantity, else NULL* (NULL for conflicts, qualified maximums and per-phase states, never a guess), recomputed from the evidence records; every consumer migrates to the read model one at a time; no consumer is changed by this specification. Historical values already in those columns are left as they are and are labelled legacy-unqualified.

## 10. Implications and bounded implementation proposal (for review; nothing built)
| Area | Implication |
|---|---|
| Extraction | Counts must be extracted **per record with their quote, locator, document id, document date and revision**, separately for the proposed basis (application form, proposal text, planning statement) and the approved basis (decision notice, approved-plans schedule). Today's LLM pass returns one total; a targeted decision-notice extraction is a separate approval (no model change is authorised here). Document date needs capturing (portal document list or the notice header); `content_hash` already gives a revision identity. |
| Storage | An append-only evidence store (below); the single scalars become derived caches. Resolution (RESOLVED / QUALIFIED / CONFLICT / ALTERNATIVES / PER_SCOPE) is computed on read, not stored, so a new relationship statement re-resolves history without editing it. |
| Scheme admission | Size eligibility from either basis, resolved and >= threshold (`ADMIT_SCHEME`); conflicts, alternatives and qualified maximums route to assessment; planning status and other conditions stay separate gates. |
| Search | Basis selector (Approved / Proposed / Either, default Either), `matched_by` on every result, Confirmed versus Possible sections, dedupe by scheme identity. Needs the read model and an indexed projection; a separate approval. |
| Display | The labelled headline and the "Unit count under review" evidence list replace the unlabelled number in the site headline, profile, explore list and reports. A separate approval. |
**P0 precondition** (already started separately): make `extract_unit_count` linear on long digit runs.
**Phase A: pure assessment, no database change.** (1) `app/ingestion/count_assessment.py`: the reference model of `tests/spec035_reference.py` as production code, plus the proposal-text counting rules of section 4, producing evidence records and the four metrics from the listing proposal (PROPOSED basis, `LISTING_PROPOSAL_TEXT`); the 52 examples are its acceptance tests and the gap sets in the test become the evidence that they close. (2) Screening rule v3: the v1 result unchanged plus an additive `count_assessment` block; opt-in; no caller selects it until approved. PR 163's v2 is superseded (its attachment logic is reused). (3) Ledger: the block rides in the existing SCREENING checkpoint (no schema, ACL or function change); below-threshold results are already retained.
**Phase B: database (each step its own approval; none started).** B1: one additive append-only table `application_count_evidence` (application id, basis, scope, value, precision, qualifier, source kind and reference, document id, document date, revision, evidence status, relations, rule version, observed-at, ledger item key) and a nullable `document_date` and `revision` on `Document` (or an equivalent evidence-side capture); no change to existing columns. B2: decision-notice extraction into APPROVED-basis records. B3: the read model and the derived-cache semantics for `estimated_unit_count` / `total_units_final`. B4: the admission gate (`new_identity.execute` accepts `ADMIT_SCHEME` / `ADMIT_FOR_ASSESSMENT`) and the promotion step through the existing B2 hand-off. **Phase C (separate specifications and approvals):** search and display.
**Not changed by any phase:** the worker function or its allowance policy, resource ceilings, council requests, scheduling, buyer mandates or fit logic, the frozen `CountAssessment` and `residential_count_eligibility` modules, every historical result, the sparse-day acquisition work and the owner-review roadmap.

## 11. Preservation of historical results
Rule versions are immutable and every stored result keeps the version that made it. No automatic re-screening. A re-assessment under v3 is a **new** ledger item linked to the old one by the append-only history; the old result is never edited, re-identified or deleted. Evidence records are append-only; superseded records stay as `HISTORICAL`. Local recomputation is always labelled "local recomputation", beside the recorded values. Archived Bolton audit and receipt identities are unaffected (specification 033 backward-compatibility tests). Existing `estimated_unit_count` and `total_units_final` values are never rewritten by this work.

## 12. Acceptance
(1) All 52 examples reach their expected outcome under the implementation (the gap sets in the test shrink to empty in the implementing change). (2) The evidence model reproduces every hand-written bases, headline and search expectation, including the mutation checks (an unsupported source cannot establish approval; nothing resolves a conflict by date, upload order, record order or size; an unsupported record cannot supersede a permission). (3) v1 output is byte-identical to master on the archived 24 Bolton records and the example texts. (4) No example is admitted on a parent, wider-scheme, existing-stock or commercial-unit figure. (5) Adversarial 8192-character inputs complete within the bound. (6) Phase B tests (disposable PostgreSQL) cover append-only behaviour, idempotence, rollback, and that no protected field changes.

## 13. Decisions for the Product Owner
* **D1** Confirm the admission measure is the supported **gross** count (so "demolish 14 flats, build 12 houses" admits at 12 with net -2), and that a negative net does not stop admission.
* **D2** Below-threshold retention: ledger and observation history only (recommended) or also `Application` rows.
* **D3** Qualified maximums and unresolved conflicts or alternatives admit **for assessment** (recommended), and conflicts whose figures are all at or above the threshold count as a **confirmed size match with the quantity under review** in search (recommended).
* **D4** Specialist housing: self-contained extra-care apartments count; care-home beds, student cluster beds and hotel rooms do not. Confirm build-to-rent counts.
* **D5** Aggregating several small applications on one site stays a Site question, not admission.
* **D6** `unit_threshold` is the platform admission threshold (documentation only; no rename).
* **D7** PR 163: supersede by v3 (recommended) or merge as an interim opt-in.
* **D8** Demote `estimated_unit_count` and `total_units_final` to derived caches (section 9A).
* **D9** Storage: ledger-only evidence for Phase A, then the additive evidence table in B1 (recommended), or an alternative store.
* **D10** Who may declare a supersession or alternative-permission relationship: only explicit statements in supported documents (recommended), or also a reviewer declaration recorded as evidence (`REVIEWER_DECLARATION`, never silent).
* **D11** Which sources count as permission evidence beyond the decision notice and approved-plans schedule (for example an s106 or a condition schedule that restates the approved quantity).
