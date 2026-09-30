# AH provenance — bounded local implementation

30 September 2026. Branch `review/ah-downstream-audit`. Local implementation only; no production or release approval.

## Delivered behaviour

Separate AH metadata declares immutable `ah_source_claims` and append-only `ah_claim_events`; the explicit migration creates only these tables and required constraints, indexes and guards. They are deliberately absent from Base.metadata, so the platform's startup/broad migration cannot create incomplete AH storage. Disposable SQLite tests execute the real migration and verify unchanged legacy fields, exact extra table inventory, retained-history rollback and rejection of UPDATE, DELETE and INSERT OR REPLACE.

`scripts.ah_claims_local` provides explicit-target local migration, one-claim validated import, preview and one-event human review. Default import/review is dry-run. It never loads DATABASE_URL or bootstraps the application. Same key/same payload replays the stored ID; changed content fails. Identical different-key evidence is rejected with the original key/ID; distinct source documents remain distinct. Human review asserts the source supports the typed claim; this code does not infer truth by parsing prose or call a model. The reviewer identity is supplied by the trusted local operator, not independently authenticated by a new identity service.

Review history uses expected context tokens and sequence heads with transactional locking. Tests execute competing imports/reviews in real independent SQLite connections. Corrections preserve original claims and relationships; same-source scope correction cannot erase unrelated documents/components. Stage labels do not split away count conflicts. A checked later stage alone does not win: an explicit supported relationship is required. Broken replacement chains require review and do not resurrect stale evidence.

The default-disabled source reader feeds the existing AHAssessment contract through both matching paths and operative scope selection. Search, detail, feed, packet and CSV expose the same quantities, qualifiers, source/scope evidence and alternatives. Tests execute the real Explore `build_report_rows` function without UI/bootstrap side effects, then its CSV serialization. Detail rendering already displays the shared assessment's label and columns. The tests do not constitute a live browser acceptance exercise.

Whole-scheme zero requires accepted, explicitly scoped source evidence. No claim rows/unknown/raw zero remain unqualified. Component evidence cannot establish a whole-scheme total or upper bound. Existing minimum leads and supported above-maximum exclusions remain unchanged. Retirement/specialist exclusions remain independent. Tenure counts remain separate, conflicting tenure quantities are visible, and no tenure summation or inferred OPSO is introduced.

Readers do not flush pending ORM work, write review events, refresh evaluations or invoke model services. Reaccepting unchanged evidence preserves the effective fingerprint. Relationship reasons are retained for explanation and excluded from the fingerprint's audit-only prose. The matching-policy constant remains5.

## Validation and evidence

Focused tests are in `tests/test_ah_source_claims.py`. Exact-commit comparison uses `verification/ah-local-compare.py`, archives the exact candidate and baseline Git trees into temporary checkouts, runs with a clean environment and temporary HOME, and installs seccomp network denial before test imports. Fixtures use only SQLite memory/temporary files. No packages are installed by the runner.

The final archive records `candidate.txt`, `baseline.txt`, runtime/dependencies, each suite's JUnit XML/log/exit code, summary and working-tree evidence. Refer to that archive for the exact tested SHA and final measured counts; a commit cannot embed its own SHA in this document. Baseline remains `c5b17a0ddb5a088502288bc58935ecc07ba05535`. Updated WSL scripts include the provenance suite, but a local Linux run is not described as WSL execution.

## Explicit remaining gates

1. PostgreSQL: no server, initdb or container runtime is installed here. DDL compilation is tested, but PostgreSQL migration, server-normalised constraint/trigger verification and real locking are NOT validated. PostgreSQL AH execution deliberately fails closed until that work is completed against a disposable PostgreSQL instance. SQLite results must not be used as PostgreSQL release evidence.
2. Real-source acceptance: Focus School is exercised as a synthetic component/percentage-dispute fixture. Its actual passages, component linkage and current planning/legal position still need review. Unknown and zero acceptance fixtures are synthetic; no genuinely source-supported production whole-scheme zero is claimed found.
3. Live rendering: automated shared-consumer/actual CSV assembly coverage is complete for the tested cases; actual-site browser/export acceptance remains separate.
4. Production impact: previously identified Render artifacts use matching4. Stored mandate/evaluation combinations remain unmeasured. Neither version5 refresh nor paid evaluation is authorised; no new production inspection was performed during implementation.

Rollback: disable `PROPERTYAIGENT_AH_SOURCE_CLAIMS`, return to the previous approved executable, and retain claim/event tables/history. Do not drop records or rewrite fingerprints to label old evaluations current. Production rollout, source import, and any refresh remain separate decisions.

No production migration/import/write, data correction, evaluation refresh, paid call, push, merge, deployment, discovery resumption or P0-A change is part of this work.
