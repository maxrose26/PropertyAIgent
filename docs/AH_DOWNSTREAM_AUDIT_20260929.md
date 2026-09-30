# Trusted AH downstream audit — 29 September 2026

## Isolation and scope

Branch `review/ah-downstream-audit`, worktree `ah-downstream-review`, base `e6fcbf7be53a7627aa7c20726163db7c0e0f0904`. Documentation only: no application, migration, P0-A artifact, specification or roadmap edits. No production data changes, paid generation, exports, shortlist additions or source scraping initiated. Read the Product Vision, architecture and AH addendum with targeted roadmap/specification inspection. The acquisition-first objective and roadmap P1 require shared scoped evidence and downstream consistency, not a new agent or ranking feature.

## Fresh live observations (limited)

A separate browser tab opened the production application, which first displayed Render cold-start loading. Dashboard and Explore subsequently rendered. Footer reported v0.4.5, commit `6fd4202`, Production. Explore displayed 414 sites. The following small cohort was directly visible in the rendered table on 29 September around 15:55 UK; these are **displayed values, not independently verified planning facts**:

| Record | Total units | Displayed AH | Audit role |
|---|---:|---|---|
| Land At Southlink Oldham | 147 | 147 (100%) | Wholly-affordable/exclusion-rule candidate |
| Wall Hill Mill, Wall Hill Road, Dobcross | 26 | Not stated | Explicitly uncertain AH |
| Waterloo House, Hopes Carr, Stockport | 28 | 2 | Count without displayed percentage |
| Godley Green Eastern Village | 2350 | Not stated | Large unknown-AH scheme |
| Land South Of Hyde East And West Of Stockport Road Hyde | 440 | 0 (0%) | Zero requiring affirmative-source verification |

The table already distinguishes Not stated from 0 (0%); that is a working safeguard, not a defect. No claim is made that the displayed zero is false, that Southlink is actually excluded for a particular buyer, or that any percentage is legally secured. The dashboard buyer selection was Generic / No buyer. Known historical Focus School/Cross Lane findings remain historical; they were not freshly rechecked.

**Coverage limitation:** this pass did not freshly inspect the same records' detail panels, selected-buyer cards, shortlist, CSV/PDF or authoritative source documents. Their provenance, last source-verification dates and actual buyer exclusions remain unverified. Do not present this as completed live cross-surface acceptance. Further live navigation stopped when the coordinator reported an unrelated Render build incident requiring priority handling.

## Code trace and concrete risks

1. `app/reporting/affordable_housing_scope.py` has a reusable `AffordablePosition`: application ID/reference, scope, units, percentage, tenure, status, notes and decided state stay together. Existing scope/decided-state tests are a foundation to preserve. However `_has_no_independent_affordable_position` admits any non-null/non-unknown extracted status even with zero figures and absence-of-information notes. This is an evidenced code risk, not proof of a particular live false zero. Adding more text phrases would not establish source authority.
2. `app/reporting/opportunity_intelligence_packet.py` lines 182–197 and 292–309 take AH status from the first populated linked application's SchemeIntelligence but units/percentage from `opportunity.matching_facts`. No ordering or scope/authority match binds those sources. Literal `unknown` is truthy and can become a KNOWN FactValue. This can construct semantically incompatible packet fields. It is a concrete source-selection defect in the code path; its occurrence in the live cohort was not measured.
3. `app/reporting/opportunity_universe.py` lines 429–449 deliberately retains representative-application AH facts for fingerprint compatibility. `app/policy/buyer_matching.py` lines 449–500 has an operative-facts route selecting consented whole-site, otherwise a single active proposal. These are different source-selection routes. Changing the universe indiscriminately would alter fingerprints/baselines and exceeds a small display patch. Packet consumers cannot assume every MatchingFacts instance is already operative.
4. Buyer matching labels established percentages as trusted, uses wholly-affordable exclusions for applicable mandates, and keeps unknown AH as uncertainty. The risk is upstream admission/selection, not evidence that all buyer rules are wrong. A resolved percentage alone does not prove secured status or general-needs provision.
5. Explore table and report rows both call `resolve_operative_filter_facts` and `resolve_explore_affordable_percentage_display`, preserving reconciliation flags. Tenure still comes from merged fields and needs a coherence check. The natural-language maximum-AH filter at `app/ui/pages/0_Explore.py` line 461 uses `fillna(0) <= max_affordable_units`: for maximum zero, missing counts pass alongside confirmed zero. The preceding comment explicitly gives “no affordable units” as the intended query. Including unknowns can be commercially useful, but silently satisfying an asserted zero constraint is not equivalent to explicitly including uncertain sites. Minimum-zero default is different: retaining unknowns there reasonably avoids excluding every unknown from the unfiltered universe.
6. `app/ui/pages/3b_Shortlist.py` is **allocation-only**, built from one `AllocationReportContext` shared with CSV/PDF. It is not an existing site acquisition shortlist and has no scheme-AH field to align. Do not create a new shortlist or infer a defect where the field is not applicable.
7. Site Profile selects an operative application for residential mix (`app/reporting/site_profile.py` around 599–605); Explore inline detail retains a different legacy presentation path. This deserves same-record acceptance, not an assumption that every displayed field differs.
8. Existing generated-at labels (`app/ui/shell.py`, AI summaries) and Site.updated_at activity dates (`app/reporting/dashboard.py`) identify generation/entity activity, not necessarily source verification. No fresh AH verification timestamp was established in this audit.

## Smallest defensible next correction

First implement a narrow shared consumption contract using existing `AffordablePosition` and operative reconciliation, not a new schema or verification agent. An AH consumer must select one eligible position for the requested development scope and carry its source reference/status/notes alongside units and percentage. No suitable or ambiguous position returns explicit unknown/unresolved; do not combine a first-linked status with unrelated counts. Preserve absent/unknown/not-applicable/confirmed-zero distinctions. Initially target packet construction and its focused regression tests, then prove the same selection against detail and buyer fit before changing fingerprints. A whole-site answer must not silently apply to a phase opportunity.

Separately, a minimal Explore filter correction can require known AH count for an explicit maximum/no-AH constraint, while leaving the default unfiltered unknowns visible. Document the treatment of unknowns so this does not silently remove otherwise investigable opportunities. It does not correct source data.

No implementation was made: the full shared-consumer correction needs its narrow scope/provenance contract fixed and actual affected tests available. Local Python cannot import pytest or SQLAlchemy. Adding an AST-only check would not establish ORM or UI correctness. No installation was retried, and no test pass is claimed.

## Focused acceptance before any release

- Linked applications with different scope/status: AH packet count, percentage and legal/status label come from the same eligible position, independent of input order.
- Withdrawn/technical evidence cannot supply current status; literal unknown remains UNKNOWN.
- No resolved whole-site position, conflicting same-scope evidence and phase-only evidence retain explicit unknown/unresolved for a whole-site consumer.
- Confirmed zero stays zero; missing evidence remains unknown; maximum-zero filtering handles each distinctly.
- Grant/viability/minimum/up-to qualifications survive; denominator conflicts remain visible rather than converted into an invented on-site percentage.
- Compare actual displayed cohort detail, buyer interpretation and exported values from the same loaded state, with provenance and source dates. Include a known specialist exclusion (Focus School) and uncertain Cross Lane after current authoritative evidence is checked.
- Preserve allocation shortlist's existing not-applicable scope and test shared CSV/PDF context without adding site functionality.
- If changing fingerprint inputs is ultimately required, review explicit invalidation/baseline migration separately; no bulk recalculation in this task.

## Outcome

Useful live values and concrete code hazards established; live cross-surface/source verification incomplete. Documentation-only local branch remains isolated from P0-A. No production AH correction or release recommendation. P0-A remains the immediate operational priority; this proposal advances P1 design without requiring reliability testing to finish first.

## Authorised local correction follow-up

The subsequent user instruction authorised implementation of the two narrow defects. Local changes now:

- Existing AH scope module selects a single consented position or a single eligible active position for the requested scope. Same-scope conflict returns unknown. Named phase/parcel positions never inherit whole-site values; indistinguishable Phase/Plot codes remain unknown. No extraction phrase patch.
- Packet status and affordable count now come together from that selected position. Blank/literal unknown status remains UNKNOWN. Percentage is withheld unless operative quantum source application identity, stored denominator and packet quantum agree and arithmetic reconciles; otherwise retain the count/status and explicit unknown percentage. Universe fingerprints and persisted matching facts are unchanged, but packet contents (future agent inputs) change. This is not full downstream invalidation or a repair to previously stored evaluations.
- Explicit maximum-AH filtering now requires a known count. Default minimum-zero browsing still includes unknowns. Helper lives beside existing AH presentation helpers in `app/ui/housing_type.py`; no new framework/module.
- No schema, production correction, source reprocessing, P0-A artifact or roadmap change.

### Additional fresh record inspection

Focus School, site 78, DC/085997 was opened via deterministic Explore search and its Residential Mix tab. Both Overview and Residential Mix display 82 homes, 72 affordable homes and “Recorded percentage requires review.” Mix shows `mixed_retirement_and_market_housing`, “confidence: high · status: all_units_affordable,” and “reconciliation status: OK.” The expanded stored evidence says 72 retirement apartments affordable plus 10 semi-detached homes for open market sale. Thus the high/all-units/OK classifications coexist with an explicit mismatch warning and contrary stored excerpt. The UI warning works; do not claim the whole detail screen asserts unqualified 100%. Underlying evidence date was displayed “Evidence last updated 02 Sep 2026”; this is not proof of current source verification. Source PDF and legal position were not independently checked.

No actual buyer exclusion/feed result, shortlist export or CSV/PDF was generated in this follow-up. Allocation-only shortlist remains out of scheme-AH scope. The same-record all-surface comparison remains a release acceptance requirement, not a claimed completed check.

### Focused verification

- `python -m unittest verification.test_ah_filter -v`: **1 passed**, 0 failures, actual pandas float64 and nullable Float64 masks, four assertions across two dtype subtests. Coordinator independently reran it with the same outcome.
- Python compileall of four changed application files plus new pytest file: passed. `git diff --check`: passed. These are syntax/whitespace checks, not ORM validation.
- `python -m pytest -q tests/test_ah_downstream_consumption.py tests/test_agent_ready_fact_foundation.py tests/test_affordable_housing_scope.py`: **could not start** (`No module named pytest`). SQLAlchemy is also absent. No tests collected, no pass/skip counts invented. No repeated installs attempted.
- Eight new pytest cases are prepared (four status/count parameter cases plus four other cases): original historical row precedes current row, stale caller facts, confirmed zero, literal/blank unknown status, denominator disagreement, missing evidence, phase/parcel identity/conflict, explicit maximum filtering. They require execution in the authorised isolated WSL environment with existing project dependencies, alongside affected existing suites. No production database/keys needed.

This is a local candidate for review, not ready to merge/release until actual ORM checks run. Existing tests may need expectation changes where they relied on representative AH packet values; none were silently weakened. No broad suite was run.

### Verification handoff and classification limitation

Prepared `verification/ah-wsl-run.sh`, isolated checks/summary helpers and `docs/AH_WSL_HANDOFF.md` for the user's existing authorised WSL environment. Uses a separate clone, disposable SQLite and blocked external network; candidate eight new tests are reported separately from matched existing suites. No WSL execution claimed from Astra.

Additional code review: `app/extraction/reconcile.py` has an `all_units_affordable` branch that can force AH units/percentage from the total. That is a supported propagation risk, not proof that this function produced the current Focus School row. The narrow packet/filter correction does not repair that stored classification or establish authoritative legal AH truth. No source-data change or bulk reprocessing is proposed.

## Uploaded WSL evidence independently inspected — 29 September 2026

Exact tested candidate `c91890ae027fb98cd68472e0d8848d954beb1909`; matched baseline `c8580831590e75936f787fcd2ae08b292fa7908e`. Archive `ah-results-20260929T160754Z.tar.gz`, SHA-256 `003d8f8f04eff7587fde16dfd37e023c55fa99eab01a13b102bcf321f917ec14`. Inspected underlying JUnit XML, pytest logs, filter log, exit files, identities, runtime and clean-tree records rather than accepting only summary JSON.

Candidate affected suites: 43 passed, zero failures/errors/skips (6.633s). Matched baseline: same 43 case identities passed, zero failures/errors/skips (3.400s). New consumer cases: eight passed, zero failures/errors/skips (1.895s). Standalone filter unittest: one passed (0.006s). All exit files report zero. No candidate-specific or baseline failures in this targeted AH run. Python 3.12.3. Both working-tree records empty. Runner hash `75be0ba9b925a0a3931510651d162ce4c9081efdae1951366e3a902f181a0260` matches the local reviewed runner. Isolation checks are fail-closed prerequisites in that runner; this is synthetic SQLite verification, not production or UI acceptance. No application correction is warranted by these results.

Continued source-path review: Explore table and `build_report_rows` both use operative facts, the operative filter resolver and the same percentage display resolver. Export tenure/private units still originate from aggregated scheme fields; coherence of those fields is not established by these tests. Dashboard calls `build_opportunity_feed`; its buyer assessments use `evaluate_buyer_fit`, not the corrected intelligence packet directly. Thus this packet fix cannot be represented as a repair to every feed decision or stored evaluation. Allocation Shortlist shares one allocation report context across page/CSV/PDF and is not a scheme-AH shortlist. These are source-code observations, not a newly observed live same-record export comparison.

Focus School classification/source contradiction remains open. No source evidence or production records corrected. Live same-record detail/feed/export acceptance remains outstanding; no broad retest or production release follows automatically from these passes. P0-A branch and evidence, including its additional timing failure, remain separate and unchanged.
