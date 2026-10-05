# Stage 2 bounded unit/phasing amendment

Authorised continuation base: `090fd06b4573fe82dd09d5460a17a109b07306d3`.
Base tree: `9e9bf9e6b7f3747fa4f30bac8fe698a5b3e8ed4e`.
Branch: `stage2/unit-phasing-amendment`. Original candidate is preserved.
Publication, master merge, deployment and production recomputation remain paused.

## Implemented read contract

`residential_count.CountAssessment` is derived, not persisted. It carries subject,
scope, metric, precision, exact/representative value, supported bounds, resolution,
confidence, application provenance/dates, approved/proposed basis and superseded
positions. Exact source precision is not independent verification. Mixed/all-use
totals retain their metric instead of becoming residential homes.

The explicitly accepted set 100/101/102 yields `~100 homes`, bounds 100–102 and an
uncertainty note only for same-scope, same-role, same-decision-date evidence.
Differently dated unresolved versions remain conflict. No general tolerance is
introduced. Portal estimates retain approximate presentation without invented
hard bounds. A source-supported range requires qualified, subject/metric/scope/
version/date/provenance-matching range evidence; no legacy scalar adapter invents
such evidence. Other conflicting point counts do not become a reassuring range.

Rounded values never enter `exact_value`, legacy strict filter columns or numeric
Buyer Fit inputs. `within_hard_bounds` returns True/False/None, with a straddled
limit returning None. Existing maxima remain soft preferences, not newly invented
hard maximum fields. Existing hard minimum policy remains respected. Approximate
discovery can remain investigatable without becoming verified exact compliance.
Matching policy version is 5; no stored mandate/evaluation was recomputed.

## Six correction boundaries

1. Only granted eligible variations contribute approved counts. Supersession
   requires an explicit same-scope application-reference link and later decision
   date. Older/unlinked variations cannot automatically win. Pending counts can
   remain separately proposed; refused/withdrawn figures cannot replace approval.
2. Site context excludes named child and multi-scope totals. Explicit phase
   context uses its own count and planning state. No containment is inferred.
3. Multiple phase counts are not summed without explicit pairwise non-overlap
   evidence. Duplicate scopes or incomplete counts prevent an aggregate. Current
   persisted data does not supply that proof, so normal production adapters do
   not assert disjointness. Individual figures remain visible.
4. Profile headline/inline detail/residential overview, Explore table/tooltips,
   strict filter value, feed/stack/cards, opportunity universe, PDF/CSV/prompt
   count presentation and linked-site allocation coverage use the shared count
   resolution. Raw application report entries remain attributed application
   evidence, not site totals. Approved uncertainty blocks active fallback.
5. Every eligible phase is generated before existing feed limits. A sole named
   phase is eligible too. This represents planning evidence subjects, not proven
   independent/saleable packages. Whole-site reconciliation is reused per site
   within the opportunity-universe pass.
6. Discovery labels are separate from exact qualification, with bounds, metric,
   scope and source references exported as plain values.

## Tenure and AH boundary

Nesten, National and Strategic templates remain total-unit mandates; the HA
template remains affordable-unit based. The existing qualified AH contract is
unchanged. Named phase matching does not inherit a whole-site AH count.

`aligned_tenure_counts` rejects missing or mismatched subject/metric/document
version provenance. Legacy scalar rows cannot prove that stronger alignment and
do not produce a newly asserted 70-private/30-affordable package breakdown.
Existing separately labelled reported AH/private evidence remains inspectable.
The helper is a derived contract, not an AH integration or a claim that current
data can populate every presentation case. No package availability is inferred.

## Verification and test migration

Synthetic SQLite only, with syscall-level network denial. The spawn-compatible
runner is required for renderer subprocess tests. AppTest permits local
socketpair but denies network connects/datagram sends. No paid/production calls.

Test selections:
- Focused: `test_stage2_commercial_evidence.py` (62 original) and
  `test_stage2_unit_phasing.py` (36 amendment/adversarial cases).
- Business/UI: original 769-case selection recorded in
  `stage2-evidence/regressions.xml`, plus `test_residential_mix.py` and
  `test_allocation_development_coverage.py` (92 additional cases).
- Security: the existing four Stage 1 access/buyer-scope/call-site/command files.
- Lifecycle/journeys: existing 8 lifecycle and 2 AppTest journey cases.

Machine-readable results are in `unit-phasing-evidence/`. The completion report
records the exact final identity and independent review; this document alone is
not publication approval.

No failing test was removed. Historical assertions were migrated for the approved
contract: recency-only counts remain conflict; sole child count stays scoped;
unknown wording and policy version change; summary output uses the shared label.
Arrow's real integer/unknown regression now explicitly supplies an extracted
count rather than treating a portal estimate as exact. Allocation-capacity
fixtures explicitly identify substantive residential proposals; a test retains
the representative identity while requiring conflicting capacity to stay unknown.

The optional `unit_phasing_regression_plugin` only enables the existing visual
classification permission in synthetic historical test policy, where tests inject
fake vision clients. It does not modify application security or production policy.
Security tests run separately without that adapter. An initial broad attempt used
the non-spawn wrapper and was interrupted after renderer failures; the retained
final run uses the repository's spawn-compatible offline wrapper.

## Deferred and operational boundary

No schema/migration, persistent subject hierarchy/package model, AH schema or
security change, scraping, production access, Google work, deep-verification
agent, paid call, Render/Supabase/cron mutation, publication, merge or deployment.

Durable package/hierarchy modelling and Level 2 verification require separate
approval. No egress saving is claimed. Unknown relationships and count-level
document provenance remain limitations. Existing numeric search is conservative:
an approximate count remains discoverable unfiltered but does not satisfy an
exact scalar filter by its rounded representative value.

Count and subject-generation changes can change future monitoring fingerprints.
The new assessment fingerprint retains bounds/precision/scope so a change from
approximate to conflict is visible. Historical rows are untouched. A separately
reviewed semantic transition/rebaseline is needed before production recomputation;
do not report these code-driven differences as new real-world planning events.

Independent review of the first descendant found a secondary category renderer
navigation regression. The continuation restores links regardless of count/note
and tests all three cases inside the correct card container. Material plot
identities now use `plot_<code>` to avoid colliding with an identically numbered
phase when all eligible subjects are emitted; ordinary phase IDs are unchanged.
This also requires explicit production identity-transition review before any
future monitoring recomputation. No stored anchors or evaluations are rewritten.


## Hosted CI reconciliation (2026-10-05)

The 1,168 local result was a **selected regression set**, not comprehensive or
hosted-workflow-parity acceptance. Its 98 focused + 861 business/UI + 199 security
+ 10 lifecycle/journey cases omitted `tests/test_affordable_housing_scope.py`
and the complete `verification/web_ah/check.sh` invocation. The selection
included `test_ah_scope_consumers.py`; that is a different file and did not cover
the omitted prompt assertion. No marker excluded the test: explicit path
selection omitted it. The same failure reproduced locally without environment
changes, so the original failure is not attributable to hosted dependencies.

The protected test originated in `ca5df0c` (AH scope-aware summary introduction).
`41e75e8` already migrated its scalar wording for trusted operative facts. Its
purpose is non-AH consumer preservation during AH work, not permanently frozen
prose or a schema/security test. Spec 023 and this amendment intentionally extend
CountAssessment and non-inferential lifecycle semantics to the generic prompt.
Changing that prompt does not change AH qualification. Restoring the old scalar
path globally would discard approximate/unknown semantics; restoring legacy
lifecycle instructions would reintroduce unsupported physical/legal claims.

The hosted first failure is STALE TEST: its `45 total units (consented position)`
assertion is superseded by `45 homes`, with planning status separately retained.
Developer, recommendation, linked application and granted-status assertions stay.
Exact prose is retained where meaningful; optional count-note whitespace is not.

Complete script parity then exposed further unexecuted walkthrough checks:
- Inline historical narrative is intentionally withheld under Spec 023. The
  revised check requires the review notice and absence of the seeded unsupported
  AH claim and obsolete expander, preserving all AH/CSV safeguards.
- `26 (proposed)` is now `26 homes`; the walkthrough separately requires awaiting
  decision and prohibits permission-granted promotion.
- A REAL provenance regression was also found: a newer portal-only 82-home
  proposal selected the extraction reference while the exact count was 440 from
  the older extracted record. The profile now chooses an actual supporting
  exact extracted source (including multiple agreeing extractions) for residential extraction, independently of the current
  AH/navigation identity. Existing old-source/current-AH assertions are retained;
  explicit 440-not-82 rendered checks were added. This correction does not change
  count resolution or AH qualification policy, schema or security.

Corrected acceptance now requires BOTH the selected suites AND the entire
`bash verification/web_ah/check.sh INTERPRETER OUTPUT_DIRECTORY`, including the
actual rendered CSV walkthrough after its 11-module pytest selection. This is
still not the entire repository suite or production/real-world verification.
The workflow uses env-i, SQLite, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and its existing
Stage 1 synthetic admission adapter; none of these controls were relaxed.

### Reproducible selected-suite invocations and results

The original literal shell session was not committed; its exact module selections
are recoverable from retained JUnit classnames. The following corrective reruns
use those same module selections (not a claim of a recovered shell transcript).
`PY` denotes the isolated test interpreter; `OUT` is an output directory outside
the checkout. Prefix each command with
`DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

focused: 100 passed, zero failures/errors/skips.

```sh
"$PY" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin tests/test_stage2_commercial_evidence.py tests/test_stage2_unit_phasing.py --junitxml="$OUT"/focused.xml
```

security: 199 passed, zero failures/errors/skips.

```sh
"$PY" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider verification/test_stage1_access.py verification/test_stage1_buyer_scope.py verification/test_stage1_call_sites.py verification/test_stage1_commands.py --junitxml="$OUT"/security.xml
```

regressions: 861 passed, zero failures/errors/skips.

```sh
"$PY" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin -p verification.unit_phasing_regression_plugin tests/test_ah_scope_consumers.py tests/test_allocation_development_coverage.py tests/test_allocation_discovery.py tests/test_allocation_report.py tests/test_allocation_report_pdf.py tests/test_arrow_safety.py tests/test_buyer_mandate_v2_phase_b2.py tests/test_buyer_matching.py tests/test_dashboard.py tests/test_entity_search_allocation_refinement.py tests/test_explore_presentation.py tests/test_gate2b2b1_trusted_consumer_alignment.py tests/test_gate2b2b2_acquisition_scope_alignment.py tests/test_gate2b2c_planning_signal_consumer_alignment.py tests/test_opportunity_change_detection.py tests/test_opportunity_feed.py tests/test_opportunity_time_transitions.py tests/test_opportunity_transaction_signals.py tests/test_opportunity_universe.py tests/test_ownership_control_reporting.py tests/test_recent_permission_opportunities.py tests/test_residential_mix.py tests/test_scheme_reconciliation.py tests/test_site_headline.py tests/test_site_profile.py tests/test_visual_evidence.py --junitxml="$OUT"/regressions.xml
```

lifecycle-journey: 10 passed, zero failures/errors/skips.

```sh
"$PY" verification/stage2_ui_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin tests/test_stage2_profile_journey.py verification/test_ui_session_lifecycle.py --junitxml="$OUT"/lifecycle-journey.xml
```

Additional gates (overlap the selections above; do not sum as unique tests):
- Original failing node: 1 passed; previously reproduced as 1 failed.
- Complete affordable-housing-scope file: 20 passed.
- Exact workflow `bash verification/web_ah/check.sh "$PY" "$OUT/hosted-parity"`:
  257 passed + 10 subtests passed, followed by successful actual rendered CSV
  walkthrough. No workflow, adapter, schema, AH policy or security changes.

Hosted historical runs on 146f8a3: push 37315986512 and PR 37317769220 failed.
The PR run's checkout was GitHub's synthetic merge 17dc1fda1ea4b5e255950629aaa17d159a699e99,
with candidate head 146f8a3 and unchanged master 28c2c16. Its log confirms
256 passed, 1 failed, 10 subtests passed. No corrected hosted result is claimed
by this local acceptance record.

Independent review extended the provenance regression to two agreeing extracted
440 sources plus a newer portal-only 82 proposal. Two parametrized tests now
verify both single-source and agreeing-source attribution while retaining the
newer current AH identity with unknown AH count. Exact agreement permits a
supporting representative extraction; the full CountAssessment source set remains
unchanged. Approximate/conflicting count resolution is not altered.
The corrected selected-suite total is 1,170 (100 + 861 + 199 + 10), not 1,168.
