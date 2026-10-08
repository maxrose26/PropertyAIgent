# Stage 2.6B Evidence Trust Remediation

Status: PREPARED FOR REVIEW — SPECIFICATION ONLY; no implementation, migration, data correction, paid calls or operational activation authorised.
Date: 8 October 2026. Proposed repository location: `specifications/029-stage26b-evidence-remediation.md`; number must be checked against remote specifications before publication. This deliverable does not publish or reserve that number remotely.

## Objective

Make the exact subject's planning evidence reliable enough for concise, qualified Scheme Intelligence Summaries and subsequent buyer investigation. Correct metric, scope and source eligibility before improving prose. Stage 2.6A is COMPLETE for its approved, qualified validation purpose. Stage 2.5C ranking remains ON HOLD. Stage 2.5B/Specification 028 and accepted Stage 1 security are not reopened.

## Business Value

Prevent buyers investigating a bridge, commercial building or porch replacement as though it were a newly consented housing scheme. Preserve useful approximate scale and legitimate component opportunities while refusing unsupported whole-scheme precision. Prioritise factual mistakes that change the apparent acquisition subject over cosmetic coverage or new AI infrastructure.

## User Story

As a buyer, I want to understand what development and quantity the evidence actually describes, what planning/legal position is supported and when it was verified, so that mandate compatibility guides proportionate investigation without implying control, availability or acquisition quality.

## Authority and evidence baseline

Authoritative product direction is the current instruction accepting Stage 2.6A, not older claims of continuous operations. Read-only source inspection used application baseline `8ec17e22e476209a88a1c162fb4b41a896a1af9e` available through local tooling descendant `7f9d13eb62402424e936cd919f4239b127f1189e` (tree `477dca035b55d191fc91b7ff851cba3fdad0070c`). No claim of a fresh remote-master or production-code verification is made.

Accepted audit pack: `Stage26A-Evidence-Audit-2026-10-08.zip`, SHA-256 `25c765339320d71e1892c88d67aaa93f98ada92f4080174c291f6685b73f724d`. Its source observations date to 8 October 2026. Sample25 families/32 subjects,10 councils,82 linked applications,46 intelligence records,382 document metadata records.23/25 accessible current cases;22/23 status agreements;14/20 comparable scale/scope agreements,6 discrepancies,5 unresolved. These denominators are not population accuracy or validation of all82 applications. Woodford records are correlated.

References: specifications023–028; `docs/PRODUCT_ROADMAP.md` current staged decisions and AH specialist-trust addendum; accepted Stage2.6A report/register/source snapshots. Attached July platform report and October1 critical review are historical context only. Their former EPC/administrative-filing physical-status inferences, continuous-operation descriptions and old security gaps must not override later accepted corrections or imply current defects. No historical gate is marked complete by this specification.

## Requirements

### 1. Root-cause investigation and evidence hierarchy

Distinguish five layers for every reproduced failure: source acquisition/version → extraction → reconciliation → stored application/site relationship and subject construction → presentation. The same downstream discrepancy may involve several layers. A missing input trace yields UNRESOLVED, not an extractor accusation.

| Case | Demonstrated observation | Required trace and candidate failure layer | What is not established |
|---|---|---|---|
| World of Pets site248/app578 | RM76 versus final116 | Trace selected dated RM/outline evidence, classifier total, regex candidates, final reconciliation, count eligibility and consumer subject. Compare version/scope, not reference recency alone. | That116 is definitively superseded, or that AI originally extracted wrongly |
| Stand Golf16/app18 |43 general homes+60 retirement apartments; stored total60 | Inspect component extraction and total/metric mapping; determine whether component60 was promoted at storage, subject adapter or display. |103 private/open-market homes, or an independently available retirement package |
| Woodford62/app186 |Bridge/crossing RM carries372 | Trace whether parent count was contextual extraction, relationship inheritance, substantive-role eligibility or consumer fallback. Inspect other linked application separately. | That372 is wrong for the wider parent or every Woodford subject |
| Walthew336/app526 |Commercial B2/B8 proposal carries47 residential | Trace use-class, quantity unit and source/app linkage before changing parser. | Exact numeric origin of47 |
| Strawberry Hill371/app552 |Acoustics building PlotA6 carries79 residential | Trace parent933 context, exact plot/application use and RM eligibility. |79's original source or parent availability |
| Cedar508/app1100 |Porches to56 existing homes treated as development scale | Trace existing-stock/action semantics and conversion/type classification. |56 new homes or zero homes existing on site |
| Bamford215/app296 |Final67 agrees49 apartments+18 bungalows; raw49 partial | Preserve successful reconciliation as positive control; trace component summation support. | A defect merely because raw and final differ |
| Failsworth28/app42 |Refused25Sep2026; stored pending | Trace last exact-reference success18Sep, invocation eligibility, disabled schedule, result handling and propagation. Existing suspension is an operational explanation to test. | A broken parser or freshness algorithm merely because ingestion is OFF |
| Southlink25/app29 |Current report Social Rent; stored affordable rent; pending portal | Compare dated tenure sources and extraction/reconciliation inputs; committee resolution stays separate from issued permission. | Original model error, grant, executed S106 or current title |

Code-confirmed investigation hooks (not proven case-specific causes): `housing_mix.extract_housing_mix` chooses structured total/portal-nearest/max candidate; tenure keyword collection can span policy text. `reconcile.reconcile_scheme` prioritises classifier `total_units_context` over other count candidates. `scheme_reconciliation._resolve_approved_units` accepts eligible `total_units_final` positions before `residential_count.assess_positions`, whose contract assumes already-current same-scope evidence. Numerical agreement therefore does not establish residential meaning. Existing `resolve_planning_role` uses proposal text; the audit excluded stored proposal bodies, so its exact production execution was not replicated.

Evidence hierarchy is fact-specific, never one global newest-document winner:

1. Exact application/subject identity and explicit relationship first; an unrelated authoritative document is ineligible.
2. Issued decision notice and applicable conditions for permission status/timing; official exact-reference register is authoritative for its observed current administrative status. If these disagree, retain both and mark conflict.
3. Approved plans/schedules and applicable varied decisions for approved quantity/scope. Explicit variation linkage, approval and affected terms are required for supersession; pending/refused changes do not replace approved evidence.
4. Executed, applicable legal agreement/deed and any effective variation for secured AH obligations; grant alone and draft agreements are insufficient.
5. Dated application/committee material for proposed/committee-supported facts, never promoted to issued/secured facts.
6. Extracted facts and portal estimates retain their source tier, precision and uncertainty. Search snippets, AI narratives, reference alphabet order and applicant identity cannot establish authority.

Later-dated sources can add context without superseding existing permissions. Equal-authority contradictions remain visible. Older supporting evidence is retained as historical, not silently deleted.

### 2. Shared in-memory fact contract

Extend existing fact/count adapters only where needed; do not introduce a parallel matcher, universal knowledge graph or generic export framework. An eligible fact carries:

- exact existing subject identity, application identity and scope (whole/phase/sub-phase/parcel/component/unclear), with parent context separate;
- metric and unit: proposed/approved new dwellings, existing dwellings affected, net addition when explicitly supported, private, affordable, bedrooms/bedspaces, commercial area or other quantity;
- value/bounds/precision through existing CountAssessment; eligibility separate from EXACT/APPROXIMATE/RANGE/UNKNOWN;
- source reference, locator, date/version/hash where available, observation/verification time and fact state: proposed, committee-supported, approved, secured, historical, conflicting or unknown as appropriate to that fact;
- explicit supporting relationship and qualification; no invented provenance, confidence percentage, scope ID or package identity.

These are read-contract requirements, not approval for new columns. Missing fields become unavailable/qualified. Existing `all_use_units` must not imply a housing total or mandate metric. Do not generalise the currently approved100/101/102 approximation exception or permit ranges for arbitrary point conflicts. Keep100/180 unresolved; no averaging. Rounded display counts never prove hard-boundary compliance.

### 3. P0 residential metric and subject-scope containment

1. **Problem:** six demonstrated scope/metric/count discrepancies, plus unresolved Bredbury372 and Stockport Exchange1.
2. **Investigation:** complete the layer trace in section1 using retained authorised inputs where available. If source bodies are unavailable, demonstrate the guard using minimal verified public excerpts; retain origin unresolved. Additional protected inputs require separate access authority.
3. **Hierarchy:** exact subject and intended metric before approved-versus-proposed authority. Approved RM for a bridge does not make parent homes residential evidence for that application.
4. **Responsibility:** deterministic eligibility and reconciliation; no model call required to reject demonstrably ineligible quantities. A parser may propose candidates only; no broad keyword filter or site-ID hardcoding. Ambiguous proposal wording yields unknown, not automatic nonresidential rejection.
5. **Architecture:** `residential_count`, `scheme_reconciliation`, existing subject/phase/relationship constructors and shared profile/dashboard adapters. Guard both approved and active/proposed paths before CountAssessment; test legacy scalar/fallback paths so excluded counts cannot re-enter elsewhere.
6. **Persistence:** first slice computes qualified facts in memory, retaining raw storage unchanged. Do not manufacture verification from total_units_final.
7. **Migration/backfill:** none for containment. A later correction manifest must identify exact application/field/source/version and prior value; no whole-site blanket rewrite.
8. **Freshness:** relevant source-version change invalidates its fact; later application alone is not supersession. Child/parent scope and overlap evidence remain independent.
9. **Security/privacy:** existing authorised buyer/subject reads only; no unbounded document-body loading, new identity or broader role grants.
10. **Acceptance:** six negative cases contained at every affected consumer, Bamford67 preserved; unsupported or wrong-metric count is not qualified residential scale. For116/76 without version proof show conflict/unknown; adopt76 only when the eligible current RM scope/source is established. Stand Golf may display103 total plus60 retirement component, never60 as entire proposal or103 as private homes.
11. **Regressions:** parent2000/phase180/subphase72; overlapping phases; several eligible phase subjects; pending/refused variation; exact102; approved approximate100–102; material100/180; unknown-not-zero; existing-stock works; bedrooms versus dwellings; commercial quantities; supportive source selection and independent AH attribution.
12. **Rollback:** restore prior code only if it does not re-expose known misleading claims. Otherwise suppress affected trusted quantity presentation pending repair. Raw evidence remains intact; stop release if safe fallback cannot be demonstrated.
13. **Cost:** offline deterministic tests only; no new per-request queries/model calls. Record exact bounded query counts before/after using existing loaded relationships.
14. **Unknowns:** original bad-count origin and current rendered propagation in every sample case; complete parcel/control relationships. Do not silently reconstruct opportunities.

### 4. P1 planning-status freshness and provenance

1. **Problem:** Failsworth stale pending status; successful-verification coverage22/82. Suspended ingestion means no design can promise continuously current data.
2. **Investigation:** inspect `status_verification` selection/invocation and exact-reference parser/upsert path, material-change propagation and failures. Reproduce recorded pending→refused event offline before asserting a code defect.
3. **Hierarchy:** issued notice/current exact-reference register; committee resolution distinct. Appeal lodging is not appeal success; inspect official appeal decision only when linked and supported by existing adapters. Unsupported appeal outcomes remain unresolved.
4. **Responsibility:** deterministic bounded retrieval/parse and update semantics through existing mechanism; no LLM to decide legal status. No new crawler/scheduler.
5. **Architecture:** `verify_application_status`, `run_status_verification`, `_upsert_scraped_application`, material-change/lifecycle mechanisms, `evidence_refresh`, existing freshness presentation. Enforce returned reference+council identity before updating. Wrong reference, incomplete parse or conflicting authoritative records fail closed and remain retryable.
6. **Persistence:** reuse `status_verified_at` strictly for successful direct retrieval+parse; document `documents_last_checked_at` and `evidence_refresh_last_checked_at` are successful document-check timestamps, not generic attempts. `evidence_refresh_last_outcome` records attempt outcome. Use existing execution outcomes/logs for status attempts; if durable attempt timestamp is absent, display unavailable rather than overload a success field. Inspect transaction boundaries: the current verifier commits upsert then success timestamp separately. Specify an atomic fact/status plus successful-verification update where feasible; otherwise prove coherent prior-watermark semantics with no false success. Inject failure between the existing two commits. A partially persisted fact must never be represented as a fully verified refresh, and recovery must be idempotent.
7. **Migration/backfill:** no inferred timestamps from last_seen/updated_at, no retrospective success stamping. Reuse existing fields first; any proven missing persistence requirement returns to REVIEW with a minimal separate delta.
8. **Monitoring:** present “verified as of [date]”, “verification unavailable/failed” and operational pause distinctly. No invented freshness SLA. Future scheduling cadence, egress cap and retry budget require Stage4 acceptance. Timestamp-only checks do not produce material-opportunity changes.
9. **Security:** existing command permissions, allowlisted source navigation, TLS and redirect protections; no browser-security bypass, production calls in CI or secret output.
10. **Acceptance:** mocked pending→granted/refused/withdrawn updates exact record and available issued date, preserving prior evidence history; supported appeal decision supersession keeps provenance. Timeout/404/wrong reference/parse failure leaves prior fact+success timestamp unchanged, records outcome and never fabricates withdrawn status. Same-value successful check advances verification only. Atomic failure cannot leave false-success status.
11. **Regressions:** Failsworth refused25Sep, Southlink still pending after committee resolution, no-change success, two applications with similar references, temporary portal failure, appeal pending/allowed/dismissed where supported.
12. **Rollback:** disable future refresh invocation and retain last accepted dated fact; do not restore pending over a verified refusal. Code rollback must continue reading existing evidence. Planned data changes need field-specific reversal records.
13. **Cost:** existing bounded direct checks, no model. Measure requests/bytes/retries before future activation; no automatic full-corpus catch-up.
14. **Unknowns:** why Failsworth was not rechecked after18Sep, current parser support across all councils/appeals, appropriate operational cadence. A paused system can expose dated status honestly, not eliminate staleness.

### 5. P1 affordable-housing truth

1. **Problem:** Southlink Social Rent/current-report divergence, Failsworth conditioned/pending inconsistency, World of Pets count/percentage inconsistency; no secured provision validated.
2. **Investigation:** locate exact tenure passages, dates and whether project-specific or policy background; compare raw classifier, housing-mix and final fields, then AH scope selection. Do not assume all text containing Social Rent is a project commitment.
3. **Hierarchy:** applicable executed obligation/variation for secured facts; issued condition for what that condition actually requires; committee agreement for committee-supported facts; proposal for proposed facts. “Subject to S106”, draft agreement, resolution or generic condition does not establish execution/security. Where validity/discharge/legal effect is unclear, qualify rather than issue a legal conclusion.
4. **Responsibility:** deterministic state/provenance/scope selection and arithmetic; AI necessity not demonstrated. Extractors may suggest cited tenure candidates but cannot promote legal state.
5. **Architecture:** `affordable_housing_scope`, decided-state partitions, percentage reconciliation, `reconcile`, existing AH presenters. Preserve AH-specific identity selection independently of generic count provenance; no P0-A schema/security integration.
6. **Persistence:** in-memory qualified AH position with obligation state, exact denominator+metric+scope+version, tenure evidence, on/off-site/contribution and funding qualifiers when supported. Existing persisted scalar is reported evidence, not documentary proof. Proposed and secured positions can coexist; security is not inferred from a higher-ranked label.
7. **Migration/backfill:** none in first slice; preserve raw/final/historical values. A later targeted tenure correction needs source-version evidence and explicit write approval, not a synonym replacement across the corpus.
8. **Freshness:** source/legal variation invalidates only affected scoped claims; refusal affects live proposal context without erasing history. Absence of a retrieved deed is “not verified”, not proof no agreement exists.
9. **Security/privacy:** preserve P0-A/AH qualification, reader isolation and production grant boundaries. No buyer-private data or personal contacts in fixtures.
10. **Acceptance:** Southlink source-qualified125 Social Rent+11 Rent to Buy+11 Shared Ownership,147 proposed total, remains unverified as secured; Failsworth68 proposed does not become secured after refusal.34/116 versus45% exposes denominator/version conflict, no silent rewrite. Explicit no-on-site requirement distinct from off-site contribution and absent evidence.
11. **Regressions:** phase versus parent AH, zero versus unknown, revised viability obligations, mixed tenure, grant-dependent provision, overlapping phases, same count different versions, AH package absent. AH30/private70 aligns with total100 only for identical eligible scope/version; tenure must not establish an acquisition package.
12. **Rollback:** retain provenance/history and suppress unverified secured labels; no rollback that restores unsafe legal assertions. Do not alter separate AH migrations.
13. **Cost:** deterministic guards first, zero required AI calls. Later legal-document review costs need a separately bounded proposal.
14. **Unknowns:** executed obligations for sampled schemes, current Southlink title/legal transfer, historical tenure inputs and affected consumer paths.

### 6. P2 controlled scheme typology

1. **Problem:**10/46 dedicated typology values include generic/unknown entries; type fields mix land use, built form and tenure.
2. **Investigation:** map existing proposal/extracted fields and current source excerpts to the correct subject; assess ambiguity and field conflicts before adding extraction.
3. **Hierarchy:** scoped approved/proposed descriptions/plans, then source-linked extracted evidence; no typology inferred from affordable percentage, buyer identity or broad site label.
4. **Responsibility:** deterministic explicit mappings first; unknown is valid. No model for name guessing. Existing extraction reuse only when provenance adequate.
5. **Architecture:** add a request-local presentation adapter beside qualified facts, not a replacement matcher development_type vocabulary.
6. **Persistence/model:** presentation category = HOUSES, APARTMENTS, MIXED_HOUSES_APARTMENTS, MIXED_USE, RETIREMENT_SPECIALIST, STUDENT_ACCOMMODATION, OTHER_NON_RESIDENTIAL, UNKNOWN. Preserve orthogonal evidence facets: built form, use mix, specialist subtype and tenure. Retirement apartments retain apartment form; mixed-use retains residential component detail. Deterministic precedence for primary display: evidenced student/specialist first, then mixed residential/nonresidential use, then built form; retain facets so primary label does not erase facts. Ambiguous or contradictory scope yields UNKNOWN/conflict, not first-match guessing.
7. **Migration/backfill:** no rewrite of development_type or matcher input under presentation-only approval. Any later canonical persisted taxonomy needs separate compatibility review.
8. **Freshness:** change classification only with scoped source change, not a newer scrape timestamp.
9. **Security:** no extra remote reads on page load; existing access checks precede presentation.
10. **Acceptance:** Southlink mixed houses/apartments; London Road apartments despite conflicting legacy label; Bamford retirement with apartments+bungalows retained; Walthew nonresidential; Cedar houses as existing stock/work activity, never new housing creation. Student bedspaces never counted as dwellings without explicit metric support.
11. **Regressions:** all eight categories, generic “residential” unknown-form case, specialist mixed-use, parent/phase differing forms and conflicting evidence.
12. **Rollback:** disable adapter display safely to “type unverified”; preserve source fields.
13. **Cost:** no AI or new query requirement; measure coverage gained versus false certainty in held-out examples.
14. **Unknowns:** unsampled student cases and legally complex specialist use classification; no assumption this audit validates them.

### 7. P2 permission deadline and physical status contract

1. **Problem:** no verified operative deadline/commencement and0/25 known physical states. Absence is not an extraction failure by itself.
2. **Investigation:** establish exact permission instrument, condition text, decision date, RM submission/approval limits, dependencies, variations/extensions and scoped commencement evidence. Audit existing assumption-based path separately.
3. **Hierarchy:** operative notice/condition and evidenced amendments, authoritative implementation evidence with scope/date, then qualified professional/documentary reports. News/EPC/admin filings may be context but cannot independently prove lawful commencement, whole-site completion or availability.
4. **Responsibility:** deterministic date calculation only after condition/dependency eligibility; AI cannot make legal lapse determinations. Six calendar months means calendar addition, clamped at month-end, not180days. Boundary includes audit date through that date; expired evidenced deadlines are a separate “deadline passed—legal position unverified” state, not legal lapse.
5. **Architecture:** reuse `resolve_operative_lapse_anchor` and `lapse_tracking` as inspected boundaries. Keep existing labelled three-year assumption separate; do not silently relabel it verified. Stage2.6B defines this contract and offline acceptance only; live signal activation requires a later explicit gate.
6. **Persistence:** proposed request-local fields: permission ref/version, condition locator, deadline expression/date, dependencies, evidence state; independent lawful and physical status evidence with scope/date. No new persisted legal-status field or migration authorised. If source lineage cannot fit existing structures, return minimal persistence need to REVIEW.
7. **Migration/backfill:** never mass-derive dates from approval+3years or convert unknown to uncommenced. No backfill until exact instruments individually established.
8. **Monitoring:** date-driven expiry can make a future summary stale without changing source bytes; keep summary validity date separate from opportunity fingerprints. No scheduled alerts implemented here.
9. **Security:** approved document provenance only; no title searches or privileged body exports by implication.
10. **Acceptance:** verified operative deadline within six months + lawful commencement NOT VERIFIED produces only the proposed “Potential lapse risk — investigate” test output. Verified lawful commencement disables that condition; disputed commencement yields qualified investigation. Missing condition/permission/date cannot qualify. Lawful and physical evidence are independent, not a single boolean.
11. **Regressions:** leap-year/month-end, outline/RM alternative timing, missing RM approval, later unrelated consent, variation without deadline effect, partial phase commencement, EPC-only, conditions-discharge-only, disputed commencement and undated evidence.
12. **Rollback:** retain unknown and labelled assumptions; withdraw new verified-signal presentation if qualification breaks. No legal-status mutation to reverse.
13. **Cost:** zero model calls in contract/tests; later original-notice collection and interpretation needs scoped budget.
14. **Unknowns:** actual deadlines/lawful commencement in the audit cohort. No claim the six-month signal's commercial effectiveness is validated.

### 8. AI summary contracts — defined, generation deferred

**Scheme Intelligence Summary:** input is the shared qualified fact projection for the exact acquisition subject, not a flattened whole-site scalar merge. May describe scoped typology, eligible count and precision, operative versus active planning position, proposed/secured AH separately, independent physical/lawful status, qualified deadline evidence, uncertainty and verification dates. Every factual clause must be attributable to an eligible supplied fact/source. Unknown sections say unavailable or are concisely omitted without implying absence. No ownership/availability/acquisition recommendation invented. Wider parent context explicitly labelled and not substituted for subject facts.

**Buyer Opportunity Summary:** consume the existing authorised buyer+mandate+subject assessment and Specification028 causal trace. Explain authoritative positives, actual classification causes, contextual limitations and partial/missing reasons separately. Never infer reasons from a label, recompute policy or alter fit, ranking, ownership/control/availability or recommendation. Related-subject evidence cannot supply representative reasons. Buyer switch invalidates identity/context before reading cached text. No second matching engine.

Prefer deterministic concise templates for accepted facts initially. Any optional later model is a constrained wording layer with supplied references, output schema and claim validator; it is not authorised by this specification preparation, and generation is not part of the proposed first containment release. No model call on dashboard/profile page load, cache miss, invalidation or exception. Missing/stale generated summary falls back to qualified deterministic facts or unavailable, never unversioned stored AI narrative.

**Versioning and invalidation:** a separate summary dependency identity includes summary contract/renderer versions; existing subject and, for buyer output, buyer/mandate identity+revision, matching-policy version and assessment/trace content; normalized scoped fact values/states/precision; source IDs/versions, successful-verification times when narrated; conflicts, provenance and any expiry/time-window boundary. Optional future model/prompt version recorded independently. This key is NEVER inserted into existing matcher, acquisition, monitoring or benchmark fingerprints. Reordering equivalent inputs does not invalidate; material facts, qualification/scope/source changes do. A verification-only change updates any narrated as-of text without forcing a model call. Generation completion must compare input revision again; discard stale-race output. Authorisation is checked on every retrieval, and shared scheme facts must not contain buyer-private explanations.

No current persistence model is claimed to satisfy this future cache. Existing summary storage/accepted stale-narrative suppression remains unchanged until a separately reviewed implementation explicitly proves compatibility. New cache tables are out of scope by default.

## Data Model and migration implications

The first feasible slice is computed containment, not a database clean-up programme. Reuse Application status/verification fields, SchemeIntelligence raw/final fields, document IDs/hash metadata, fact positions/CountAssessment and existing AH scope contracts. Data absence in the audit projection is not proof a column or function is missing.

Three distinct decisions must not be bundled: (a) calculated eligibility corrections; (b) targeted stored-data repairs; (c) future durable provenance/summary/deadline storage. Only(a) is recommended for first implementation consideration, after offline diagnosis. If it cannot be delivered without schema or subject identity changes, stop at that requirement with an explicit delta and return to REVIEW.

Policy v8 logic/mandates and fingerprint ALGORITHMS remain frozen. Correct facts may legitimately change assessments, eligible subjects/family membership/order or fingerprint VALUES. The first slice must preview and enumerate those effects offline; no production recomputation or baseline rewrite authorised. No forced preservation of a false result, and no silent production behavioural transition. Existing subject IDs must not be repurposed; identity construction changes require separate approval. Frozen benchmarks remain frozen; audit fixtures are a new evidence-evaluation set, not retroactive benchmark edits.

## User Experience

Examples: “76 homes — Reserved Matters parcel; older116-home evidence unresolved”; “103 proposed homes, including60 retirement apartments”; “Works to56 existing homes — new-home count not established”; “Refused25 September2026; source verified8 October2026”; “147 proposed affordable homes; executed obligation not verified”. Do not emit76 as current resolved if supporting eligibility/version is still unresolved. Counts elsewhere must carry the same metric/scope qualification. Exact source date is never replaced with render time.

Expose material conflicts and source links beside facts. Preserve approximate discovery and unknown-not-zero semantics. No new score, wider redesign or taxonomy of buyer recommendations. Render dashboard, opportunity card, related subject, profile and relevant export paths with consistent fact attribution; explain partial reasons as Specification028 requires. Keyboard access, readable labels, responsive layouts and accessible expansions remain regression requirements.

## Architecture Considerations and staged acceptance

| Slice | Deliverable after separate implementation approval | Dependencies and gate |
|---|---|---|
| B0 |Qualified fixtures and reproducible layer trace; no production access/write |Verify case/source identity, label unresolved origins, negative and positive controls; no gate waits for unavailable evidence if conservative containment is demonstrably safe |
| B1 P0 |Small request-local source/metric/scope eligibility correction across trusted consumers |B0; offline differential report and independent review; separate approval of any changed buyer outputs before release |
| B2 freshness |Reuse exact-reference verifier, fix only demonstrated defects, expose truthful as-of state |B0; may be developed separately fromB1 but no refresh-driven reprocessing beforeB1 acceptance; invocation remains disabled pending operational authority |
| B3 AH |Qualified states, source/denominator/tenure reconciliation and display |B1 andB0 source cases; no AH/P0-A integration or production backfill |
| B4 typology |Controlled scoped presentation mapping |B1; independent gate, no matcher-type remapping |
| B5 deadlines |Offline condition/deadline/physical-status contract and tests |B0 provenance; separate acceptance; production signal remains deferred |
| Summary follow-up |Qualified deterministic summary presentation first; optional generation considered later |Every included field's relevant slice accepted; omitted/unverified domains remain qualified. No requirement to delay all useful deterministic facts until every domain is complete |

P0 containment must precede targeted reprocessing and any trusted generated summary rollout: otherwise improved prose can make the wrong subject look more credible. Full B0 input forensics can continue after safe conservative containment where origin remains unresolved. Do not make all five domains a single deployment.

## Acceptance Criteria

AC01. Reproducible source-linked record for each demonstrated case identifies verified observation versus unresolved origin; fixture hash, date and exact app reference present; no unsupported truth label.
AC02. Six discrepancy cases cannot supply the wrong metric/scope as trusted residential count via approved, active, parent, fallback, card/profile or export paths. Bamford67 and legitimate child counts remain.
AC03. Unknown is never0;100/101/102 approximation and hard-bound safety unchanged;100/180 not averaged; pending/refused variation never supersedes approved count; explicit overlap controls preserved.
AC04. World of Pets current76 is accepted only with exact eligible RM/source/version proof; otherwise conflict. Stand Golf103 split retains60 specialist; Woodford bridge, nonresidential and existing-stock quantities cannot impersonate new homes.
AC05. Failsworth source fixture changes status to refused25Sep with provenance in prospective offline refresh; Southlink committee resolution alone does not produce granted. Supported withdrawal/appeal outcomes have exact-reference/state-transition tests.
AC06. Failed/wrong-reference/partial check does not advance successful verification or replace facts. Same-value success advances success time only. Attempt and successful-check timestamps remain semantically distinct.
AC07. Southlink Social Rent is not normalised to affordable rent; proposed/committee-supported/secured are distinct. S106 draft/grant/condition alone cannot establish executed security. Count/denominator/source conflicts remain visible.
AC08. All eight typology states plus orthogonal mixed/specialist facets tested; no changes to matcher development-type rules; ambiguous source yields unknown.
AC09. Verified deadline requires exact instrument/condition/dependencies. Six-calendar-month boundary tests pass; EPC/admin filings/approval+3years never produce verified lawful commencement or legal lapse. Signal not activated.
AC10. Both summary input contracts preserve subject/buyer and source truth; partial causal explanation remains partial. No model invoked by page load, invalidation, cache miss or test; no unsupported recommendation/control claim.
AC11. Dedicated summary dependency/version key has deterministic order and invalidation/race tests; no fingerprint ALGORITHM or benchmark edits. Unchanged already-qualified matcher inputs preserve existing v8 matching behaviour and algorithmic fingerprint/identity results. Corrections may change raw-input-to-qualified-input eligibility even with identical stored raw records; enumerate every resulting assessment, family/order and fingerprint-value difference for separate release approval. Do not describe those effects as new production data or hide them inside a presentation change.
AC12. Existing Stage1 access, buyer switching, document security and AH isolation pass. No new schema/grant or private data leakage. Validator remains inactive; admin-audit exception does not become production runtime access.
AC13. Actual rendered dashboard/profile/related-subject/export tests verify qualified facts, responsive layout and keyboard/screen-reader labels. Legacy narratives cannot bypass gates. No unbounded or per-card extra evidence/model work.
AC14. Each slice has exact head/base, changed paths, focused tests, relevant regressions, both hosted gates and independent review; required failures/skips block acceptance. Rollback rehearsal never restores known misleading claims; operational services remain disabled.

## Validation Dataset and verification requirements

Retain all25 case IDs and32-subject snapshot context as an evaluation manifest, not all as ground truth. Per fact record: case/app/subject IDs, field/metric/scope, stored observation, verified source statement, evidence category, source URL/date/locator/version/hash where available, observed-at, expected safe result, origin confidence, limitations and licence/retention basis. Preserve five unresolved count cases as unresolved tests; two inaccessible sources as access-limitation cases. Never turn absence of current source into incorrect-data truth. Historical source assertions remain tied to their observation date, not forever-current expected status.

Keep original audit pack immutable, checksum-verified. Use minimal paraphrased facts/short permitted excerpts and synthetic object wrappers for offline fixtures. Council document availability is not blanket republication permission; review reuse terms before committing full documents or copied text. No full bodies/PII/credentials/private buyer records in Git. Data fixtures are additive beside frozen policy benchmarks. Include counterexamples and held-out synthetic scopes to prevent site-ID/reference hardcoding. Repository fixture format, file names and metadata validation to be delivered in B0, not implemented in this task.

Required future commands in an isolated offline environment, with the actual chosen interpreter/evidence directory recorded:

```
bash verification/web_ah/check.sh "$TEST_PYTHON" "$EVIDENCE_DIR/ah"
bash verification/stage2/check.sh "$TEST_PYTHON" "$EVIDENCE_DIR/stage2"
```

These are existing baseline workflow commands, not evidence of tests run for this specification. Extend existing offline CI for new slice tests after implementation authorisation, without production credentials/network/model access. Relevant existing suites include `test_stage2_unit_phasing`, `test_scheme_reconciliation`, `test_planning_status_verification`, `test_material_planning_change_detection`, `test_evidence_driven_intelligence_refresh`, `test_affordable_housing_scope`, `test_ah_scope_consumers`, `test_extraction_fidelity`, `test_residential_mix`, `test_spec028_differential`, subject/family/v8 fingerprint tests and Stage1 verification suites. Run only legitimate slice commands, not production launchers or paid integration tests. Compare identical already-qualified matcher inputs across the six-field BuyerFitAssessment and algorithmic fingerprints with baseline. Separately compare identical raw fixtures before/after eligibility correction and report all resulting qualified-input and downstream changes; no unexplained differences permitted. Record tests passed/failed/error/skipped/deselected and suite selection; do not call selected coverage every repository test.

## Release, backfill and rollback strategy

No production backfill is necessary to prove B1 conservative containment. Future targeted correction requires a reviewed dry-run manifest: exact rows/fields, prior values, new source/version-qualified values, expected affected subjects/buyers, affected summaries, expected material changes, code identity, row/query/time/byte caps, idempotence key and reversal data. Reprocessing selected inputs must never automatically invoke all existing AI stages. Separate deterministic reconciliation from extraction and model generation. No catch-all full-corpus job.

Release each slice only after independent acceptance, ordinary PR/CI and separate merge/deployment authority. Capture old code and compatible read contract; test rollback offline. Keep cron/monitoring off through release. Any data repair requires independent write approval; code rollback does not erase corrected source facts. Do not restore stale pending status to undo software. If compatibility cannot preserve safe read behaviour, hold release. Do not rerun GateB, rebaseline, re-onboard or suppress legitimate material changes to fake invariance; return precise transition need to REVIEW.

## Cost and operational implications

Specification and initial deterministic slices require zero model calls. Runtime reads should reuse the request's existing scoped data, with query counts bounded and measured against baseline. Evidence retrieval cost is network requests/bytes plus database egress; no monetary savings or Free-capacity claims are supported by this audit. Future cost proposal must state number/size of documents, retrieval/retry caps, input/output tokens, model and current official prices, maximum spend, deterministic-only option, stopping thresholds and expected correction yield. No estimate in pounds is invented before those inputs exist.

Continuous correctness cannot be guaranteed with all crons suspended. This specification provides honest as-of status and safe refresh semantics; later Stage4 operational acceptance decides cadence, retries/backoff, rate/egress controls, observability and activation. Monitoring is a downstream consumer, not authority to modify this gate's fingerprints or start scheduled work.

## Non-Requirements

No commercial ranking/scoring, autonomous acquisition recommendation, ownership/title/control enrichment programme, CRM, comparables, valuation/appraisal, national expansion, model retraining/fine-tuning, wholesale AI reprocessing, new multi-agent infrastructure, scheduled activation, Stage2.5C implementation, production evidence access or mutation, migration, role activation/credential work, cron changes, deployment, GateB/rebaseline/re-onboarding or summary generation. No P0-A schema integration. The inactive validator is future infrastructure, not a prerequisite; no live role recheck was necessary for preparing this specification.

## Future Enhancements

Ownership/control/availability remain later acquisition-evidence dependencies. A dated applicant can provide a lead to investigate but not verified title/control. Later deep verification may inspect legal instruments and resolve qualified unknowns; it must not become a prerequisite for surfacing every useful discovery lead. Commercial ranking requires separate evidence-quality and buyer-validation acceptance. Existing Acquisition Agent foundations remain reusable later, not activated by this proposal.

## REVIEW decisions requested

1. Accept this staged contract and approve B0 plus B1 OFFLINE implementation/verification as the first bounded slice, with no production reads/writes, model calls, matcher/identity algorithm changes or deployment.
2. Require a separate evidence-impact acceptance before B1 production use if corrected inputs change fit/family membership/order/fingerprint values; implementation must not hide those effects.
3. Accept B2–B5 and summary contracts as specification direction only; authorise each implementation/release independently. Preserve separate schema/backfill/access/operational gates where evidenced necessary.
4. Keep Stage2.5C and scheduled activation on hold. Do not authorise prompt changes or paid reprocessing absent a demonstrated input-level cause and bounded cost proposal.
