# Stage 2 final source-to-consumer acceptance candidate

## A. Decision and authority

MASTER STAGE: 2 — Truthful opportunity and lifecycle semantics.
CURRENT GATE: final source-to-consumer acceptance reconciliation.
NEXT GATE: REVIEW decision on Stage 2 exit.

Recommendation: **GO for Stage 2 closure with the explicit limitations below.** This is an unmerged acceptance candidate, not a declaration that REVIEW has accepted the exit. The master-plan reconciliation is already accepted and is not repeated here. All six original defects have a disposition. No runtime defect was identified in the bounded inspection. No application, test, policy, schema or workflow changes are proposed.

UNKNOWN satisfies this semantic gate when the available evidence does not establish a fact. Neither a current survey of Site 491/Allocation 45 nor a new completion/availability data source is necessary to accept the narrower behaviour. This record does not certify the real-world facts of those records.

## B. Exact identities

- Candidate parent / inspected master: `d253773a09690f27b150adb701c95f9aa3ee210f`, tree `df4c70a51896f96c2a8787bcdcd0a5dbcde733e3`. Refreshed from origin before creating this branch.
- Branch: `docs/stage2-final-acceptance`. Final commit/tree and PR are supplied in the publication handoff; the document deliberately does not attempt a self-referential commit hash.
- Original accepted implementation base: `28c2c16e3e715c806dfb33f7edfff65e2aaa5451`.
- Direct six-defect correction: `090fd06b4573fe82dd09d5460a17a109b07306d3`.
- Final Stage 2 candidate: `43e6ef32b8fa21ba42c5a8b0dca4247a49cd693c`; PR #6; merge `3d586a9ffc6edfe2c8d3ef45f7386bb7f3d27589`.
- Specification 028: PR #28; merge `8ec17e22e476209a88a1c162fb4b41a896a1af9e`.
- B1.1: PR #30; merge `c709bd7643161daab16db86b86509aabf289048d`.
- B2.0: PR #34; merge `7446c1218e2daca591a74918150863a89bb90d50`.
- B2.1: PR #35; merge/reported deployed application `a65ee9795fe58449ba826098480c75b7753d5767`; recorded Render deployment `dep-db4aog7lot8c738ddfug`.

The inspected reporting, UI, visuals, pipeline and enrichment paths have no changes between the recorded B2.1 application commit and this candidate's parent. This confirms code lineage for this review, not current deployment state. Later scraper/tooling changes are not activated or accepted by this record.

## C. Changed paths

Only this directory: `ACCEPTANCE.md`, `evidence.json`, `tests.log`, `journey.log`. Logs retain the unsuccessful test outcomes as well as passes. No new fixture was necessary: direct original-defect regression protection already exists. This is a documentation-only acceptance candidate.

## Retained source register and evidence qualification

**S1 — Original review supplied by the Product Owner:** `PropertyAIgent_Critical_Review_and_Improvement_Plan.docx`, SHA-256 `02295459d1cea262469edff9b4512a5f9d2b5cc2f127f8ffed35461edf03230b`. Relevant locations: section 6 D01–D05, section 5 broken discovery journey, Stage 2 GO/NO-GO, source register U3/U5 and synthetic probe appendix. The existing file was read locally; no live URL was opened.

S1 records these observations:

- D01: ten synthetic certificates dated 2020, grant in 2026, expected ten units produced complete. The source itself calls this a mocked probe, not council evidence.
- D02: a synthetic post-grant administrative filing produced underway, including when raw stored state was complete.
- D03/W01: the observed dashboard described Albion Mill St Marks Street Bolton BL3 6NR with a 23 October 2026 commencement deadline, linking to Site 491, whose destination said “Nothing substantive to show yet.” This proves the historical UI defect, not a lawful deadline or current physical state.
- D04: Elton Reservoir was described as cross-boundary because its Local Plan had multiple member councils. The observation does not prove the allocation's actual boundary.
- D05: Allocation 45 showed confirmed mapping and a confirmed visual summary while its primary image said needs review at 90% confidence. This proves the historical presentation contradiction, not whether the underlying boundary is correct.

**S2 — Versioned reproduction:** `docs/stage2-evidence/baseline-probes.json`, `candidate-probes.json`, and `verification/stage2_baseline_probe.py`. Synthetic SQLite/mocked inputs, no external source verification. Corrected results: D01 UNKNOWN/zero qualified certificates; D02 UNKNOWN with retained raw status; D03 assumed review date; W01 limited destination present; D04 no cross-boundary councils inferred; D05 both states needs-review.

**S3 — Accepted semantic contract and tests:** `specifications/023-stage2-commercial-evidence.md`, `docs/STAGE2_LOCAL_ACCEPTANCE.md`, original direct tests, and later accepted specifications where cited below. Original local acceptance explicitly leaves Site 491/Allocation 45 real-world verification pending. This record preserves that limit rather than silently converting synthetic examples into production facts.

**S4 — Historical deployment evidence:** `docs/PRODUCT_ROADMAP.md`, “Product Owner checkpoint — 9 October 2026: legacy freshness bootstrap”, records B2.1 production completion and exact identity above. No new production inspection was performed.

## D. D01 — CLOSED_WITH_EXPLICIT_LIMITATION

**Original defect / retained evidence:** S1 D01 and S2 reproduce excluded pre-grant EPCs being reintroduced, resulting in completion. Postcode counts also lack verified dwelling/scheme/phase identity.

**Evidence qualification:** the probe proves an unsafe inference; it does not prove any actual site complete or incomplete. EPC absence is not proof of no completions.

**Accepted implementation:** `090fd06…`, carried by Stage 2 final `43e6ef3…`/merge `3d586a9…`; `app/enrichment/epc_lookup.py`, `app/pipeline/lapse_tracking.py`, shared consumer labels.

**Semantic rule:** pre-grant, invalid/undated, duplicate or unscoped postcode evidence cannot establish completion. Retain returned evidence/reasons. Physical state remains UNKNOWN; raw legacy classifications are explicitly unverified context.

**Consumers / expected behaviour:** dashboard, Explore filtering/CSV, profile/inline detail, allocation matched-site context, reports and buyer explanation inputs must not promote raw EPC classifications to physical truth. The dashboard's raw-state label uses `BUILD_STATUS_LABELS`, including “Unverified legacy EPC completion classification”; Explore uses the canonical computed UNKNOWN. Completion exclusion is distinct from availability.

**Regression evidence:** `test_epcs_never_establish_unscoped_completion` (adversarial parameterisation), `test_admin_activity_never_promotes_or_overwrites_raw_status`, completion-filter tests in `test_stage2_commercial_evidence.py`; this selection passed. Code inspection checked the raw-label consumer, not just the producer.

**Historical production:** S4 establishes descendant deployment lineage, not a fresh EPC test in production.

**Residual limitation:** no reviewed dwelling/phase completion writer is introduced; old database classifications remain stored. This limitation does not reopen Stage 2 and grants no repair/backfill authority.

## E. D02 — CLOSED_WITH_EXPLICIT_LIMITATION

**Original defect / retained evidence:** S1 D02 and S2 show a condition/variation filing promoting unknown or raw complete to underway.

**Evidence qualification:** administrative evidence establishes planning activity only. It is not a physical-start observation; raw stored complete was not independently validated by the probe.

**Accepted implementation:** `090fd06…` and accepted Stage 2 lineage; `classify_build_status`, `compute_lapse_status`, `compute_phase_progress` and qualified feed/card wording.

**Semantic rule:** administrative filings neither prove physical commencement nor erase stronger independently scoped evidence. Current raw legacy status is preserved but not trusted. No filing is not evidence of no construction.

**Consumers / expected behaviour:** dashboard/feed, Explore/profile, allocation linked-site context, report and buyer explanations show planning activity or UNKNOWN physical state. Permission leads remain discoverable without a claim that land is uncommenced or available.

**Regression evidence:** `test_admin_activity_never_promotes_or_overwrites_raw_status` covers both categories, raw states and input orders; `test_granted_phase_lead_survives_admin_activity` retains useful permission leads and rejects admin-only permission claims. Both passed.

**Historical production:** S4 lineage only.

**Residual limitation:** actual physical progress is unverified. There is no new independently verified physical-status producer. Do not require one merely to close this defect.

## F. D03 — CLOSED_WITH_EXPLICIT_LIMITATION

**Original defect / retained evidence:** S1 describes exact deadline language from grant-plus-three-years, availability conflated with incomplete development and Reserved Matters implying closed opportunity/whole-permission legal protection. S2 retains the original/corrected date labels.

**Evidence qualification:** the retained 23 October 2026 UI date is an observed claim, not a statutory finding. No decision-condition or landowner availability verification is implied.

**Accepted implementation:** `090fd06…`/Stage 2 accepted lineage; lapse helper, dashboard/feed, `app/ui/common.py`, search masks and PDF prompt/labels. B2.1 contributes freshness qualifications only.

**Semantic rule:** estimated dates identify their basis; grant-plus-three-years is an assumed review date, not lawful lapse, seller pressure or availability. Reserved Matters alone establishes none of ownership, disposal, availability or whole-permission protection. UNKNOWN availability cannot satisfy an explicit availability filter.

**Consumers / expected behaviour:** dashboard review-date leads show assumption; profile retains anchor/basis and verification need; Explore/CSV use qualified lapse labels and assumed-date column; reports include legal-lapse/availability limitations; deterministic transaction signal remains UNKNOWN for an assumed deadline. Spec028 explanations cannot strengthen the underlying fact.

**Regression evidence:** missing/invalid-date, explicit availability, same-scoped assumed-date destination and PDF prompt/PDF extraction tests in commercial evidence; `test_assumed_near_date_does_not_establish_statutory_deadline` and distant-date equivalent in transaction signals; all passed.

**Historical production:** S4 lineage only. No current legal or commercial availability claim is made.

**Residual limitation:** current legal implementation and market availability remain unknown; an explicit availability search can legitimately return no evidenced matches. These are evidence limitations, not missing Stage 2 semantic implementation.

## G. D04 — CLOSED_WITH_EXPLICIT_LIMITATION

**Original defect / retained evidence:** S1's Elton Reservoir observation and S2's synthetic multi-council plan reproduction.

**Evidence qualification:** Local Plan membership is established by the stored plan relationships; it is not allocation-level geography or a supported allocation/site association.

**Accepted implementation:** `090fd06…`/Stage 2 accepted lineage, `app/reporting/allocation_discovery.py` and allocation profile.

**Semantic rule:** joint-plan membership and allocation-specific boundary evidence are separate. `allocation_cross_boundary` remains None and `cross_boundary_councils` empty in this contract; joint-plan membership alone cannot match cross-boundary filtering.

**Consumers / expected behaviour:** allocation discovery cards, filters and profile say joint-plan participation and boundary unverified. Allocation report context does not manufacture cross-boundary geography from plan membership. No inspected dashboard/Spec028 consumer independently upgrades that relationship.

**Regression evidence:** `test_joint_plan_does_not_establish_allocation_geography`, allocation joint-plan filter/query tests and report selection passed; code inspection verified profile qualification and report context.

**Historical production:** S4 lineage only.

**Residual limitation:** actual Elton Reservoir geography is not newly verified. No allocation boundary or relationship repair is authorised or needed for the UNKNOWN behaviour.

## H. D05 / Allocation 45 — CLOSED_WITH_EXPLICIT_LIMITATION

**Original defect / retained evidence:** S1 U5 records the Allocation 45 contradiction; S2 reproduces a machine-selected primary with 90% confidence and needs-review status being summarised as confirmed.

**Evidence qualification:** historical UI observation plus synthetic mechanism reproduction. No current Allocation 45 image, geometry or reviewer decision was queried.

**Accepted implementation:** `090fd06…`/Stage 2 accepted lineage; `app/visuals/site_view.py`, allocation discovery/profile and shared gallery badges.

**Semantic rule:** only explicit `review_status=confirmed` supports confirmation. Primary selection and confidence do not. Rejected visuals are excluded. If confirmed and pending visuals coexist, confirmed visual is primary; each pending item retains its own qualification. An overall confirmed state is not confirmation of every attached image or development progress.

**Consumers / expected behaviour:** status builder and summary agree; card/profile use the same summary; gallery badge independently reads the same review status. A lone high-confidence pending image remains suggested/needs review. Plan-wide fallback is expressly not an allocation-specific confirmed boundary. Reports inspected do not emit a separate contradictory visual-confirmation claim.

**Regression evidence:** `test_visual_machine_selection_is_not_confirmation`; allocation discovery tests for confirmed-primary precedence, rejected evidence, empty evidence and plan-wide fallback; visual selection tests passed. Five visual-generation tests failed before exercising their assertions at the disabled paid-action boundary (see N); no display test failed.

**Historical production:** descendant lineage only; no claim Allocation 45 was revisited in production.

**Residual limitation:** current named-record state and correctness of the boundary remain unverified. This is not a Stage 2 blocker: the accepted behaviour represents existing review state truthfully. Whole-journey map/accessibility work remains Stage 6, not a reason to defer this semantic closure.

## I. W01 / Site 491 — CLOSED_WITH_EXPLICIT_LIMITATION

**Original defect / retained evidence:** S1 U3 records the Albion Mill dashboard-to-empty-profile journey; S2 reproduces a surfaced review-date lead whose applications are excluded from the substantive display set.

**Evidence qualification:** historical observed journey plus synthetic failure-shape reproduction. No production Site 491 record was fetched, recreated or relabelled as current fact.

**Accepted implementation:** `090fd06…`/Stage 2 accepted lineage; `app/reporting/profile_destination.py` and `app/ui/pages/1_Scheme_Detail.py`. Spec028 later preserves exact subject/buyer explanation, rather than substituting family/site evidence.

**Semantic rule:** a surfaced narrowed permission/review-date investigation claim opens the same subject, exact originating evidence where held, assumption and limitation. Missing full scheme detail does not warrant a fabricated substantive profile. A wrong-site reference cannot substitute evidence. No source identity/date basis means no substantiated urgency claim.

**Consumers / expected behaviour:** dashboard links retain site/reference/scope; profile shows same identity, source link, assumed review basis and explicit missing-detail warning. Wider-site evidence is labelled as wider-site; selected buyer/back navigation is retained. Spec028 wrong-buyer/tampered-subject explanation is withheld. This supports investigation of the narrowed claim, not a claim that a rich scheme dossier exists.

**Regression evidence:** `test_assumed_date_opportunity_opens_same_scoped_evidence` includes wrong-site rejection; `test_dashboard_to_same_profile_source_and_return_preserves_buyer` passes both limited and full paths, actual offline rendering and subject/buyer tampering; `test_spec028_profile.py` and explanation presentation tests passed.

**Historical production:** S4 lineage only; current Site 491 rendering unknown.

**Residual limitation:** source documents are not newly fetched or authenticated; missing substantive detail remains explicit. Stage 6 full discovery/filter/map continuity remains open separately. No Stage 2 claim is carried forward under that label.

## J. Consumer parity matrix

| Consumer | Relevant requirements | Checked contract and evidence | Result / limit |
|---|---|---|---|
| Dashboard/feed | D01–D03, W01 | Qualified raw labels; canonical date rules; scoped destination; commercial tests and rendered journey | No contradiction found; no live browser inspection |
| Explore/search/CSV | D01–D03 | Canonical build/lapse values, evidence-aware filters, qualified date column; commercial and operative-filter tests | No contradiction found; not a performance acceptance |
| Site profile/inline detail | D01–D03, W01 | Same-subject origin/limited path, assumed basis, physical/availability caveats; two rendered journeys | No contradiction found; limited profile remains limited |
| Allocation discovery/profile | D02–D05 | Shared linked-state semantics, joint-plan distinction, summary/primary/gallery consistency; discovery and visual tests plus code inspection | No contradiction found; no live Allocation 45 verification |
| Reports/exports | D01–D04 | Explore canonical row fields, PDF labels/prompt and extracted PDF text, allocation report context/CSV/PDF | No contradiction found; no live or paid narrative generation |
| Specification 028 explanations | D01–D03, W01 | Exact subject and buyer, inherited evidence qualifications, reject mismatched identity | No contradiction found; not blanket proof of intelligence quality |

Not every requirement applies to every consumer. Absence of an exported visual/geography claim is not a requirement to add that field. Allocation report tests do not constitute AH acceptance. Inspection is bounded, not exhaustive certification of all possible data states.

## K. Contribution of later accepted work

- B1/B1.1 contain residential/count/scope errors so a narrow original claim is not undermined by an unrelated whole-site or false residential count. They are supporting context, not primary proof of D01–D05.
- B2.0 preserves exact-reference accepted factual state, field states and failure/conflict semantics. It does not make an unsuccessful request a successful verification.
- B2.1 qualifies verification age and withholds stale/incompatible narrative. Its current focused and rendered selections passed; it does not supply real-time truth or close refresh/discovery.
- Spec028 and family/subject identity preserve the specific surfaced subject and active buyer through explanation/destination. Its tests directly strengthen W01; they do not independently verify planning facts.

## L–M. AH and freshness boundaries

Stage 3 AH remains separate and unclosed. This record does not approve AH counts, imports, migrations, reader activation or consumer parity beyond compatibility already accepted elsewhere.

Stage 2 freshness presentation remains distinct from Stage 4 operational known-reference refresh and new-application discovery. Stage 4 retains bounded execution/recovery, exact-source acceptance, explicit GM capability/coverage and unresolved source access. Ten-council pilot readiness cannot be established by these synthetic cases. Recurring monitoring/activation remains Stage 9 under its existing dependencies.

## N. Offline/local verification

Tests ran against the exact candidate parent using the existing syscall-denial runners, env-i, synthetic admission and SQLite only. The retained virtualenv's missing Python launcher was restored to `/usr/bin/python3.12`; dependencies were not reinstalled. No repository changes were made for this repair.

Commands, from the candidate worktree (PY is the absolute local interpreter; OUT is a scratch evidence prefix):

```sh
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PY" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin tests/test_stage2_commercial_evidence.py tests/test_stage2_unit_phasing.py tests/test_allocation_discovery.py tests/test_allocation_report.py tests/test_allocation_report_pdf.py tests/test_stage26b_b21.py tests/test_spec028_profile.py tests/test_visual_evidence.py tests/test_explore_operative_filters.py tests/test_opportunity_transaction_signals.py --junitxml="$OUT-tests.xml"
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PY" verification/stage2_ui_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin tests/test_stage2_profile_journey.py tests/test_stage26b_b21_rendered.py tests/test_mandate_explanation_presentation.py --junitxml="$OUT-journey.xml"
```

| Selection | Passed | Failed | Errors / skipped |
|---|---:|---:|---:|
| Focused semantics and relevant regressions | 512 | 5 | 0 / 0 |
| Rendered journeys, freshness and explanations | 10 | 0 | 0 / 0 |

This is **not an all-green broad run**. All five failures are enumerated in `evidence.json` and retained in `tests.log`. They call mocked visual classification/generation through a guarded paid-action boundary; the historical adapter's `PAID_ACTIONS` omits `visual.classify`, so `AccessDenied: This paid action is disabled` occurs before their mocked work. The production-lineage test and security paths are unchanged. This is an identified harness/scope incompatibility, not evidence of a remaining D05 display contradiction. No enablement, bypass, test deletion or fixture repair was performed. Visual generation is outside this gate. Existing direct D05 producer/consumer regressions passed. REVIEW can accept this explicit exclusion without representing the broader suite as green.

Historical 1,182 selected Stage 2 results remain historical and overlapping, not added to today's counts. No new tests were required; no full-suite claim or model call is made.

## O–P. Hosted CI and production qualification

Publication triggers existing repository workflows; exact candidate hosted results must be read separately and reported in the handoff. This file does not claim a hosted pass before publication. No new workflow or manual operational workflow dispatch is authorised. Documentation publication is not deployment.

HISTORICAL PRODUCTION EVIDENCE: S4 records the exact B2.1 deployment above. Inspected semantic consumer paths match that code lineage.
CURRENT PRODUCTION STATE UNKNOWN: no route, database, council, Render service or runtime setting was queried. No current named-record fact or live rendering is asserted. A recorded deployment is not a repeated production test.

## Q–R. Limitations and independent review

A separate reviewer performed bounded read-only offline inspection of dashboard raw labels, Explore canonical values, site origin/limited/full paths, allocation geography/visuals, shared review badges, PDF labels/prompts and summary restrictions. It found no genuine runtime defect and recommended GO with explicit named-record limitations. It did not independently rerun tests or inspect production.

The reviewer specifically challenged two overclaims: a raw complete label is acceptable only because the displayed label explicitly marks it unverified; a limited Site 491-shaped route supports the narrowed investigation claim, not a rich substantive profile. Both qualifications are retained above. Source snapshots remain dated; no full geometric validation, legal determination, current availability, fresh-source coverage or live UI certification is claimed.

## S–U. Dispositions, carry-forwards and requested decision

| Requirement | Final candidate disposition |
|---|---|
| D01 | CLOSED_WITH_EXPLICIT_LIMITATION |
| D02 | CLOSED_WITH_EXPLICIT_LIMITATION |
| D03 | CLOSED_WITH_EXPLICIT_LIMITATION |
| D04 | CLOSED_WITH_EXPLICIT_LIMITATION |
| D05 / Allocation 45 | CLOSED_WITH_EXPLICIT_LIMITATION |
| W01 / Site 491 | CLOSED_WITH_EXPLICIT_LIMITATION |

No original Stage 2 defect is hidden in a later-stage carry-forward. The limitations qualify what is known; they do not permit consumers to overstate it.

Exact external obligations preserved:

- Stage 3: existing separate AH source/consumer/security approval chain remains open.
- Stage 4: functioning bounded known-reference refresh, new discovery and explicit material GM coverage/recovery evidence remain unresolved; UNKNOWN presentation is not a substitute.
- Stage 5: bounded reads, report generation cost and measured export/performance acceptance remain open; no semantic report defect was found here.
- Stage 6: complete buyer journey, global filters/navigation, map recovery and accessibility acceptance remain open; Site 491's narrowed evidence route is accounted for here.
- Stages 7–10 retain the accepted master-plan dependencies; no activation, model selection, new intelligence or pilot programme is initiated.
- Five blocked legacy visual-generation tests are preserved as test-harness evidence for any future authorised work touching that generation path, not made a prerequisite to Stage 2 exit.

**Precise next decision:** REVIEW accepts or rejects these six explicit dispositions and test qualifications; if accepted, records Stage 2 CLOSED and separately decides entry to the existing Stage 4 core gate under the accepted dependency logic. AH remains separate at Stage 3. No next-stage implementation is authorised by this candidate; no replacement roadmap is proposed.

## V. Actions deliberately not taken

No runtime semantic fix, schema/policy/test/workflow change, production access or repair, source request, scraping, refresh/discovery, model call, ranking change, AH implementation/integration, monitoring activation, deployment, merge or next-stage work. Only the authorised documentation candidate is published remotely. Existing exploratory PRs and roadmap files are unchanged.
