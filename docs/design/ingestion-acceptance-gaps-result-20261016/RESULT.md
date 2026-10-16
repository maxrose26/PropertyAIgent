# Stage4 — two acceptance gaps

Candidate: 5f36a886e685fb4e705ee7c58fbbb81bbd41736f / tree: 39f1dc85628223d62767507f3a4e0ad148f0be18, draft PR #120. Accepted predecessor2de9b2c/evidence48d57bb9 remains preserved. No production access, credential change, migration, source calls, application changes, scheduling or stop release. Stage4 OPEN.

## Qualifier correction

The existing extraction/reconciliation path now withholds qualified final scalar totals and derived final splits/percentages instead of persisting an exact point claim. Existing literal documents and proposal wording remain untouched. The same conservative eligibility predicate prevents legacy proposal-qualified scalars from becoming an EXACT residential or all-use total. Existing CountAssessment/schema are unchanged; no fabricated lower bound or parallel extractor.

Actual stage_extraction + fake provider + committed readback proves proposal-level up-to200 and document-only up-to200 both persist finaltotalNULL. An intentionally retained legacy scalar200 remains stored unchanged while its count assessment isUNKNOWN/valueNULL. Exact mixed-use60+70 remains130; qualified up-to60+70 isUNKNOWN. Proposed120/consented100 remain separate; phase30 remains scoped, not additive; conflict100/180 unresolved; unknownNULL, not0; additional20 remains unsupported as a new total/delta without baseline. All quantities remain evidence-local, not whole-site or commercial qualification.

This is qualifier-safe withholding, not affirmative unit-fact acceptance. Selected-document-wide suppression is deliberately conservative: historical/parent quotations may withhold a current figure; no automatic resolver is added. Legacy document-only qualifiers not present in the proposal were not retrospectively inspected or repaired. Production accuracy/provenance, additional-unit baseline, phase non-overlap and unit persistence remain unproved. Status-only canary remains separate, unitsUNKNOWN.

## Measured multi-row retention and screening

Synthetic three-row one-page ordinary Bolton RECEIVED listing reuses the actual listing request boundary, parser, source-specific projection, coordinator, SQL broker and restricted logins. It exercises count/date/identity/row-bound proposals, terminal proof and sparse optional fields; all three fixture proposals are affirmative20-dwelling signals. It does not test mixed relevance decisions, six-page pagination, live latency/recall or60rows. Fixture date span28September–4October is historical-shaped; production proposal remains only16October. Historical/current date scopes use the same components.

Deliberate owned-process interruption occurs after the first committed screening child. Full3-row checkpoint remains in PostgreSQL. Positive CLOSED cleanup permits separate restricted expired-fence recovery under finite fixture authority; the old claim is fenced. Source-free continuation re-seals the identical checkpoint under the new fence, idempotently revisits the first child, creates the other two through the actual coordinator and completes all3screening tasks. Duplicate delivery creates no new children or work attempts; completed screening is skipped. Only first capture invokes the synthetic listing callback; both later phases invoke neither listing nor detail. No application is created or changed by this multi-row path. Expiry alone never grants source/write replay permission.

| Phase | Cumulative connections | Cumulative driver commands | Cumulative DBactive seconds |
|---|---:|---:|---:|
| Interrupted capture |2|28|0.081|
| Restricted recovery |3|40|0.090|
| Materialisation+3screening complete |5|92|0.197|
| Duplicate delivery |6|103|0.258|

The aggregate remains below16connections/120driver commands/165active seconds, including restricted recovery. Eight-command closure reserve unchanged. All connection/process phases CLOSED; zero survivors. Sequential owned RSS85,708,800/85,782,528/85,602,304bytes, worker elapsed0.534785/0.531583/0.512165seconds. Recovery's DBcall is included; fixture bootstrap, synthetic lease expiry, authority construction and assertion readbacks are test preparation/verification outside controller accounting, not a claim that a full production installation fits103commands. No runtime login receives those fixture capabilities. Original job's finite setup/test/cleanup ceilings remain unchanged.

Exact hosted retained checkpoint digest5f75e9a3e9dba788103cc98b7f58930ed4de41426b9a0c4142f3c5c13def97d8. Original JUnit ZIP retains this digest and measured phase properties; test code asserts full checkpoint equality across recovery. The locally generated synthetic-listing-input.json and offline-fixture-checkpoint-example.json are inspectable examples from a separate offline invocation, NOT the original CI checkpoint; their digests are distinct. No live observation is substituted.

## Explain the108-command baseline

The unchanged one-candidate path repeats at108commands/5connections in the final rehearsal. Capture30; later single-candidate continuation adds78. Measured steady child materialisation is4driver commands per row. Screening body is4, plus caller read/claim2, so6per screened row. In this topology, the one-row capture contains26fixed/scope/connection commands+4row materialisation; the108baseline contains98remaining commands+4materialisation+6screening. The98 includes connection/dialect/profile setup, scope/authority/checkpoint operations, exact candidate checks and shared admission/B2/committed readbacks; it is not a per-row cost or universal constant.

A fresh broker connection explains the resumed first enqueue's13commands:9setup+4steady work. Remaining resumed enqueues cost4each. Three screening bodies cost4each; their surrounding reads/claims are separately counted. Recovery adds12commands. Duplicate completed delivery adds11read/setup commands, no work attempts or child insertions.

The budget measures driver submissions/internal protocol commands, including initialization/BEGIN/COMMIT/ROLLBACK; PL/pgSQL statements inside one restricted function invocation are not separately counted. Fixed statements/timeouts, locks, storage bounds and finite invocation counts bound that server work. Do not call this total backend query-count or wire-byte accounting.

Recommend first a metadata-only acceptance batch of at most3returned rows in one complete one-page listing, with retained-checkpoint recovery and all3durable screenings; no model/detail/application effects. This is useful proof beyond one row. Do not extend it to60rows or assume3screenedrows+admission/B2 fits120commands. The single-candidate status-only path is separately proved at108. A source returning more than the agreed test row bound must stop honestly with retained evidence, not truncate, select a replacement window or reset budgets. A combined multi-row+writer production canary needs its own measured fit within existing ceilings before registration; no increase requested here.

## Decision

Accept the offline qualifier-withholding correction and measured3-row retention/recovery/screening capability. ACCEPTANCE-CHECKLIST.md is the single current gate list and timezone/Salford disposition. Production storage/access remainsNOTRUN; operational permissions/controllerPROPOSED; provider answerOUTSTANDING; SalfordUNRESOLVED. No unit-fact or operational production acceptance is claimed. IDs1504–1508,PR119,seals and consumed authorities preserved.

## Final hosted validation and evidence

All9exact-head hosted checksPASS. Discovery workflow38935264680, number144/attempt1, explicit clean checkout5f36a886e685fb4e705ee7c58fbbb81bbd41736f:780offline discovery regressions,7unit-acceptance checks,25PostgreSQL admission checks,4restricted-provisioning/native checks PASS. AH security run38935257682 is the direct candidate push, distinct from PR synthetic-merge run38935264736; both checks passed. Direct-candidate originalZIPs12061305712 and12060487381 are archived alongside the discovery artifacts, with GitHub digests independently verified. No retry/rerun was dispatched. Existing CI ran automatically for relevant corrections.

SOURCE-SHA256SUMS pins changed candidate files; SHA256SUMS pins this evidence publication. Prior accepted package manifests remain historical, unchanged. The initial failureZIP and its exact retained digest are preserved, never relabelled success.
