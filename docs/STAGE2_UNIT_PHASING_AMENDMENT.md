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
