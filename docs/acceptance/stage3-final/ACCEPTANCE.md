# Stage 3 final retained-source AH acceptance candidate

## A. Gate and recommendation

MASTER STAGE: 3 — AH evidence consistency.
CURRENT GATE: source-reviewed AH expectations and consumer-parity acceptance.
NEXT GATE: REVIEW decision on the specific retained-evidence gaps below.

**STAGE 3 NO-GO — SOURCE EVIDENCE INSUFFICIENT.** This is a completed bounded acceptance investigation, not a runtime-defect finding. All ten original cases are frozen below. No easier case is substituted. Existing safe UNKNOWN behaviour is supported by regression evidence, but it cannot certify a source review that is absent. Nine cases cannot yet receive full original AH acceptance; Focus can receive a proposed limited disposition only. REVIEW has not accepted this candidate or its limitations.

Stage 2 remains ACCEPTED AS CLOSED at PR #57 head 6ec6b65b66b59730ab27471529ffcad30010d448. Its merge remains separately unauthorised. No Stage 4 work is initiated.

## B–C. Candidate and scope

Base: d253773a09690f27b150adb701c95f9aa3ee210f (remote master checked before work).
Branch: docs/stage3-ah-final-acceptance.
Only changed path: docs/acceptance/stage3-final/ACCEPTANCE.md.
Final remote commit/tree and hosted results are reported in the handoff. No runtime, fixture, test, schema or workflow edits. No new tests were justified where the missing input is source evidence rather than an untested invented expectation.

## Evidence register and classification

- R1: original PropertyAIgent_Critical_Review_and_Improvement_Plan.docx, Stage 3. Required cases and acceptance authority; not independent verification of their planning facts.
- R2: docs/PRODUCT_ROADMAP_ADDENDUM_AFFORDABLE_HOUSING_VERIFICATION.md, initial P0 cases. Historical review/defect descriptions, not the underlying source passages.
- R3: retained metadata-snapshot.json from the B1.1 preview, captured 2026-10-08T14:48:25.927351+00:00, SHA256 44630ae955f3e75d1010516a017bd3d856f740665d255a0ea810abe6ad9f964a. **Retained database metadata**, used solely to bind identities. It is neither a new production query nor SOURCE-OBSERVED evidence. No private snapshot, buyer information or database export is republished.
- R4: retained stage26a-final/stage26a-current-sources.json, SHA256 5ccec2c546f44cfd0766e241d1e20c7e010511610d7b8ee1a2c6c90c3768e5c5, and versioned tests/fixtures/stage26b/case-index.json. Dated **SOURCE-OBSERVED EVIDENCE** for selected proposal/scope facts, not complete AH passages. Public source URLs/hashes are retained in the existing index; none was opened here.
- R5: docs/AH_APPLICATION_SCOPE_LIVE_MAPPING.md, 30 September 2026. Explicitly separates **HISTORICAL UI OBSERVATION**, a retained description of the October 2024 Focus source, and **SYNTHETIC FIXTURE** contrasts. The underlying complete Focus document/Condition40 is not independently reviewed here.
- R6: docs/AH_COUNT_FIRST_CONTRACT.md and current AHClaim/AHAssessment. Accepted semantic contract.
- T1: verification/test_ah_count_threshold.py; test_ah_kpi_selection.py; test_ah_classification_presentation.py; test_ah_tenure_presentation.py.
- T2: tests/test_ah_scope_consumers.py; tests/test_wholly_affordable_state.py.
- T3: tests/test_gate2b2b1_trusted_consumer_alignment.py; tests/test_affordable_housing_scope.py.

Tests are SYNTHETIC FIXTURE evidence. Expected safe behaviour below is a DERIVED EXPECTATION from the contract, unless a retained source observation is explicitly identified. A fixture's plausible numbers, reference or source ID do not independently establish source truth.

Implementation lineage: preserved AH read/consumer protections at 804d6a60a4000a9abe423bb09bda2d03a5aabc08, retained in inspected base; wholly-affordable scope/reset corrections at 19cf85b7d28e91806ebb0894ad46032ead029e2c, integrated through PR #9. B1.1, B2.1 and Specification028 are supporting containment/freshness/identity work, not blanket AH source acceptance.

## D. Frozen ten-case identity manifest

| Case | Retained site/application identity | Scope/version qualification |
|---|---|---|
| Cross Lane / former Ship | site531; app1177 PA/2023/0556 | Main application; condition filings1244–1247 and access1248 remain separate |
| Woodford Garden Village Extension | site102; app109 DC/094533 | Extension outline; NOT Aerodrome sites62/67 |
| Viadux Phase2 | site560; app1293 139715/FO/2024 | Plot2a/2b mixed-use proposal; no accepted residential/AH denominator inferred |
| Stretford Mall | site261; app341 118672/RES/26; parent353 103844/HYB/21; variation776 112534/VAR/23 | RM scope versus wider parent |
| Hazelhurst | site179; app284 NOT/2026/0722; parent566 23/81719/HYBEIA; variation995 PA/2026/0239 | Phases2/3 versus hybrid parent/Phase1 |
| Lacy Street | site249; app290 117039/FUL/25; NMA861 118970/NMA/26 | Subject identified; separate site406/app576 114329/EIASCR/24 must not be collapsed into it |
| Brixham Road | site405; app572 114228/FUL/24 | Scheme; allocation AN9 is policy context, not AH authority |
| World of Pets | site248; app578 114619/RES/24; app289 117022/VLA/25 | RM and separate legal variation; referenced outline105905/OUT/21 not assumed equivalent to current RM AH |
| Focus School | site78; app175 DC/085997; related821 DC/093884 | 72 retirement component versus10 private houses; legacy storage and source-described component kept separate |
| Brotherton House | site236; app328 144656/FO/2025; NMA961 145694/NMC/2026 | C2/C3 specialist/mixed proposal; no automatic general-needs or whole-site AH classification |

R3 binds identities at its retained date only. Current production identity/state remains unknown.

## E–N. Individual case dispositions

### E. Cross Lane — BLOCKED
R2 records the original false-zero defect from AH not mentioned. R3 identifies the application, but no retained source-reviewed AH passage was located establishing an affirmative zero or alternative count. SOURCE_EVIDENCE_INSUFFICIENT for AH count/terms. Expected: missing AH remains UNKNOWN; stored zero is at most REPORTED/unqualified, never a qualified zero. T3 test_application_with_no_ah_evidence_at_all_yields_no_position and T1/T2 support this generic behaviour. They do not independently resolve Cross Lane. Required gap: original source passage/review showing what was absent/affirmatively stated for PA/2023/0556.

### F. Woodford Garden Village Extension — BLOCKED
R2 records wrong scheme scale/status/AH quantum. R3 establishes site102/DC/094533. R4 Aerodrome bridge/phase observations concern other sites and cannot close this case. SOURCE_EVIDENCE_INSUFFICIENT for this Extension's AH count, scope and operative position. Expected: reported data stays qualified as unverified; no borrowed Aerodrome denominator. T2/T3 scope tests support safe behaviour only. Required gap: original Extension source review/passage and the intended scope/version.

### G. Viadux Phase2 — BLOCKED
R2 identifies a denominator error; R3 binds app1293 and mixed-use Plot2a/2b identity. The correct AH numerator and compatible denominator are not established by a retained source passage. Both qualified percentage and any derived percentage stay UNKNOWN. T2 same-scope exact-count checks and T3 percentage safeguards are generic controls, not Viadux ground truth. Required gap: original source passage identifying AH scope, residential denominator and any hotel/non-residential exclusion.

### H. Stretford Mall — BLOCKED for full AH acceptance
R4 source observation at 2026-10-08T11:06:18.539Z supports251 RM residences versus parent up to800. This is useful SOURCE-OBSERVED scope evidence, not evidence of a specific AH quantum or obligation. SOURCE_EVIDENCE_INSUFFICIENT for the original AH claim's placement across those scopes. Expected: no donation of whole-scheme AH to RM251; no 800 denominator attached to RM AH without support. T2 narrow-packet/phase controls and T3 coexistence tests support containment. Required gap: original AH source and whether it applies to parent, RM, or an explicitly linked component.

### I. Hazelhurst — BLOCKED for full AH acceptance
R4 audit records176 RM homes for Phases2/3 and explicitly says35AH not verified; parent/other totals remain separate. Observation dated2026-10-08T11:13:53.334Z. Neither35 nor a scheme percentage is source-qualified by this review. Expected: retain separate consented/active scopes and unresolved AH. T3 test_consent_and_active_proposal_remain_distinguishable and scope-conflict tests support behaviour. Required gap: retained passage resolving or explicitly documenting the competing AH figures/scope; no new source request.

### J. Lacy Street — BLOCKED
R2 identifies loss of grant-dependent intended AH qualification. R3 fixes identity, but no retained funding/viability/AH passage was located. The Plot25 regression is useful residential-scope evidence, not proof of grant qualification. Expected: proposed or grant-dependent delivery cannot become secured planning obligation; current legal terms remain unverified. T1 legal captions/T3 phase-stage tests support generic behaviour. Required gap: original grant/AH passage for app290 or a supported relationship to the reviewed source. Do not substitute site406 screening.

### K. Brixham Road — BLOCKED for source-reviewed closure
T3 explicitly reproduces145 total,54AH and reported40%, with wording37% on-site plus3% financial contribution. It verifies that an unqualified40% cannot be paired with54 as the same-basis percentage. These are SYNTHETIC FIXTURE values, not newly verified source facts. R2 retains the original defect but not its supporting passage. Expected: on-site homes and financial contribution remain distinct; no qualified percentage or legal obligation inferred. Required gap: retained source passage/review proving numerator, denominator and contribution wording. Passing the real-shaped fixture alone is insufficient.

### L. World of Pets — BLOCKED for full AH acceptance
R4 source observation2026-10-08T11:03:33.969Z supports RM76 versus stored116 and leaves the historical cause unresolved. It does not establish current AH quantum, tenure or executed obligation. The separately stored VLA proposal is not proof that revised legal terms took effect. Expected: preserve dated scope/conflict; qualified AH remains UNKNOWN without direct support. T2 current-versus-sibling and T3 scope tests apply. Required gap: retained AH passage and supported current/historical relationship.

### M. Focus School — CLOSED_WITH_EXPLICIT_LIMITATION proposed
R5 retains an explicit account of the October2024 statement supporting72 retirement apartments plus10 private houses, while the observed legacy count72 is unlinked/unqualified. This is a retained source-review account, not a fresh document verification. T1 test_focus_exact_component_retains_minimum_and_source_scope uses DC/093884/document2378349/date2024-10-23 as synthetic acceptance inputs; those identifiers must not be treated as an independent verification just because the test passes. Expected: reported72 stays visible; qualified whole-site count/percentage remains unavailable without accepted scope; retirement component is not82 wholly affordable/general-needs homes; tenure/Condition40/operative terms and availability remain unverified. T1 presentation/tenure and T2 component tests pass. Limitation: original full source and final condition are not re-inspected; no claim is imported. REVIEW must explicitly accept this bounded disposition.

### N. Brotherton House — BLOCKED
R2 records specialist/whole-site100%-AH classification risk; R3 establishes site236/app328 and mixed C2/C3 identity. No retained source-reviewed AH/tenure breakdown was located. SOURCE_EVIDENCE_INSUFFICIENT; qualified count, percentage and tenure remain UNKNOWN. T1/T2 prevent unqualified whole-site classification but do not establish Brotherton's actual mix. Required gap: original source passage separating specialist/older-living/dwellings and AH tenure/scope.

## O–R. Field matrices

| Case | Count / denominator / percentage | Tenure / mix | Scope | Legal / funding / viability |
|---|---|---|---|---|
| Cross Lane | Qualified UNKNOWN; absence is not0 | UNKNOWN | app1177, no condition donation | UNKNOWN/unverified |
| Extension | Qualified UNKNOWN; no borrowed scale | UNKNOWN | app109 only | UNKNOWN/unverified |
| Viadux | Numerator and compatible denominator unverified; no derived% | UNKNOWN | Plot2a/2b not collapsed | UNKNOWN/unverified |
| Stretford | Source scope251 versus up to800; AH UNKNOWN | UNKNOWN | RM/parent separate | AH terms unverified |
| Hazelhurst |35AH explicitly unverified; no blended denominator | UNKNOWN | Phases2/3 versus hybrid | AH terms unverified |
| Lacy | Qualified UNKNOWN | UNKNOWN | app290; site406 separate | Grant-dependent defect retained; exact terms insufficient |
| Brixham |54/145/40 and37+3 are fixture evidence only | UNKNOWN | Same-source same-basis required | On-site/contribution distinct; legal UNKNOWN |
| World of Pets |76/116 residential discrepancy is not AH truth | UNKNOWN | Current RM/history/VLA separate | VLA proposal not executed obligation |
| Focus | Reported72; source-described72 component+10private; no whole-site100% | Specialist component; current approved tenure UNKNOWN | Component not whole scheme | Condition40/current terms uninspected |
| Brotherton | Qualified count/% UNKNOWN | C2/C3 metadata not verified AH tenure | app328; no NMA donation | UNKNOWN/unverified |

All missing fields are SOURCE_EVIDENCE_INSUFFICIENT, not zero. Irrelevant fields need no invented value. No date of snapshot/retrieval is substituted for legal/document effective date.

## S–V. Current consumer, export and packet acceptance

Current code inspection plus T1–T3 supports the following contracts, **not full ten-case source acceptance**:

| Consumer | Existing behaviour / test basis |
|---|---|
| Dashboard/feed | Reported qualification and current-scope matching; T2 test_feed_matching_facts_use_current_scope_and_do_not_mutate_prior |
| Explore/search | Qualified threshold checks; UNKNOWN cannot pass zero/minimum; T1 and T3 test_unknown_ah_stays_unknown_on_explore |
| Site profile | Shared AH captions, reported evidence, no raw legal certainty; T1 classification/tenure |
| Allocation profile | Policy/context is not a scheme AH claim; no new AH panel required. Ten-case allocation-to-scheme claim parity not established |
| Buyer evaluation | Qualified same-scope exact inputs; bounds not converted to points; component cannot prove scheme maximum; T2 |
| Agent packet | Rebuild current assessment; narrow/phase without authority withheld; numeric AH qualified exact whole-site only; percentage UNKNOWN; T2 packet tests |
| Exports/reports | Shared assessment columns retain application/scope/provenance, reported versus qualified count, blanks for unknowns, qualified legal label; T1/T3 |
| Explanations | Existing subject/buyer identity controls preserved; no independent ten-case AH explanation acceptance claimed |

Conflicts remain alternatives; no cherry-picked winner. Qualified count does not qualify legal status, tenure, percentage or availability. Historical evaluations remain historical. No model generation was run. Existing rendered selected-CSV evidence is preserved but was not rerun here; this focused selection is not full UI or report acceptance.

## W. Offline tests

Exact application base d253773; candidate is documentation only.
Command from worktree (PY=/workspace/scratch/bd6a3a220c00/stage2-venv/bin/python):
```sh
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PY" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin verification/test_ah_count_threshold.py verification/test_ah_kpi_selection.py verification/test_ah_classification_presentation.py verification/test_ah_tenure_presentation.py tests/test_ah_scope_consumers.py tests/test_wholly_affordable_state.py tests/test_gate2b2b1_trusted_consumer_alignment.py tests/test_affordable_housing_scope.py
```
137 passed plus10 subtests passed;0 failed,0 errors,0 skipped,0 deselected. Existing syscall-denial runner, disposable SQLite and synthetic authority. No new assertions, weakening or test exclusions. Source insufficiency cannot be cured by more synthetic tests.

## X. Hosted CI
Normal existing PR acceptance must run on the published exact candidate; final handoff reports run identity/status separately. No manual native rehearsal, operational dispatch or workflow edits authorised. Hosted success cannot change this source-evidence NO-GO.

## Y. Security artifact
5f1c41027ee1052c131faaeac83d9e04b3a8cf2d remains BLOCKED for installation. Historical36846625500 failed “AH membership unexpectedly present”. No repair, rerun, migration, role/RLS work, importer/reader/registrar activation. It is not a demonstrated dependency of this read-contract closure.

## Z–AB. Limitations, independent review and decision
Independent read-only review challenged identity substitution, source/fixture confusion, missing ten-case source coverage and infrastructure overreach. It supports NO-GO for full closure, not a demonstrated runtime defect. Retained metadata resolves identity gaps but does not supply missing AH source passages. In particular Extension102 is not Aerodrome62/67; Brixham's meaningful fixture does not become source truth; source-reviewed residential scope at Stretford/World of Pets does not qualify AH.

No runtime semantic contradiction was demonstrated. This does not establish one cannot exist. The present blocker is missing original AH source substantiation and consequently incomplete per-case consumer acceptance. Blanket CLOSED_WITH_EXPLICIT_LIMITATION would hide that original requirement; only Focus has the retained source-review account supporting the narrower proposed disposition.

## AC–AE. Carry-forwards and next decision
Stage4 retains bounded known-reference refresh, new discovery, material ten-council GM coverage and recovery. Stage9 retains recurring activation. No advancement.

Request REVIEW to accept this evidence-gap ledger and choose the narrow next step: recover/provide the original retained AH audit passages/reviews for the nine blocked cases (and the complete Focus statement/condition only if REVIEW requires stronger acceptance). This is recovery of already held evidence, not permission for council requests or an AH infrastructure programme. If those records cannot be recovered, REVIEW must decide a separately bounded evidence-acquisition authority or explicitly amend the gate; DEVELOPMENT must not silently waive it.

PR57 merge remains separately subject to exact-head authority.
Actions not taken: runtime/test/schema changes; production access/repair/import; source requests; model calls; ranking changes; security-artifact work; migration; deployment; merge; monitoring; Stage4 or other later-stage implementation.
