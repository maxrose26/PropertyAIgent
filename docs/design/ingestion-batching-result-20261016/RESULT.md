# Stage 4 bounded batching: offline implementation result

Candidate **6f1b81b2851ecdc9f9902c3a0111b7d305827ff4**.
Tree **20a48f9e864f1eaab34686bc23957fa7db85f4ab**.
Draft PR120: https://github.com/maxrose26/PropertyAIgent/pull/120
Local counterpart72f518d830ce13a1eccf5d8b0e318dbbeff59cfc has the same tree.
Accepted predecessor5f36a886e685fb4e705ee7c58fbbb81bbd41736f and design evidence
0d7627505b5070bdf2c9c0ecfda0d2ab6ecbf822 remain ancestors/preserved.
Master remains a3a698beb0542579042bbcc48e8cf7a66f13514f. No integration occurred.

Executable ordered decision package is at this candidate:
docs/design/ingestion-batching-20261016/PACKAGE.md; the exact final package and
runtime digests are recorded in IMPLEMENTATION-SHA256SUMS.
No production action is registered or approved by this result.

## Delivered and demonstrated

- One immutable capture, then at most12 five-row tasks using the existing SQL
  ledger, broker, Idox source components and screening. Dates are workload scope,
  not another pipeline. No full legacy ingestion wrapper or new service/schema.
- Per-row atomic create/reuse plus progress; live claims/fences/dependencies;
  source-free interruption recovery; completed-task reuse; duplicate delivery
  creates neither another attempt nor application. Full capture read once per
  batch, not per row. Row effects remain visible, not hidden in bulk SQL.
- Complete512KiB-bounded original audit archive/readback before receipt. Oversized
  inline receipt retains the entire original and becomes explicitly blocked;
  no truncation, false screening completion or automatic refetch.
- Hash-sealed cumulative slot/allocation accounting, CLOSED prior receipt and
  separate restricted supervised recovery; no budget reset by new process.
- Owner-only exact Bolton exception, expiry<=24h, immutable grant/execution
  snapshot, no worker extension, wrong-scope denials, atomic invalidation of every
  exception on the next hard stop. Original Salford stop/run/checkpoint unchanged.
  Uncertain persistence, security, identity, accounting and cleanup stay global.

Independent exact-tree review PASS: REVIEW.md. Corrected nullable SQL checks,
both recovery seals, confounded policy negatives and unsupervised recovery cost.
Final focused local validation25PASS/6.38s; compilation and diff checks PASS.
Final hosted discovery run38942073107, run147/attempt1; restricted job117111927297,
PostgreSQL17. Real non-superuser migration and real restricted logins.
All4 provisioning/operational/native tests PASS,0skips/0failures,21.736s.
No test retry/rerun or production execution was used.
All9 exact-head hosted checks PASS; CHECKS.json and RUNS.json retain their exact
identities. Independent review's hosted-check condition is now satisfied.

## Final 60-row measurement

One synthetic observation,6pages/60rows,9 fake Requests calls,26,638 received-body
bytes, one reader callback. No live council traffic. Exact capture checkpoint:
dfa825c681e9f70e9d3e9f04906c02812ab623447e2e0cc8db1b74762bfd4e5c.
Complete canonical source audit39,775bytes, SHA256
39d02499fcf12d3295ba18bdf081b1a5390f05201731ce8dce312a5dfee22dd6.
Both independently reconciled against original ZIP members and archive receipt.

| Operational metric, including interruption/recovery and duplicate | Actual |
|---|---:|
| Driver commands, including initialization/transaction commands |845|
| Physical connection attempts |30|
| Returned PostgreSQL data-value bytes |1,646,404|
| Cumulative DB-controller active seconds |3.261|
| Owned supervised seconds, including separate recovery |12.377|
| Peak sampled owned RSS, sequential/non-stacked |87,044,096bytes|
| Combined worker/supervisor/source exported files |133,853bytes|
| Worker audit bytes, summed across executions |89,749|

All supervised executions have positive CLOSED, certain accounting and zero live
owned survivors; all database receipts report CLOSED and connections_closed=true.
Capture26commands/2connections; ordinary five-row slot65/2; interrupted+recovery+
resumed logical slot96/5; first slot plus completed duplicate73/3. Completed
source checkpoint hash remained identical throughout.60 screening tasks COMPLETE;
20SUPPORTED_PROCESSING_PRIORITY,20RELATED_APPLICATION_FOLLOW_THROUGH,
20INSUFFICIENT_EVIDENCE. No proposed policy threshold was added.20 citations retain
literal02000/26, full wording, offsets and field provenance. No inferred council,
relationship/site/phase/progress or verified residential count was created.

Ledger scope:74items = capture1 + batch12 + screening60 + unexecuted policy
sentinel1.74attempts = capture1 + batch13(including interrupted second attempt) +
screening60. Sentinel positive claim is rolled back and denials retain0attempts;
completed duplicate adds0. Serialized scope item bytes213,867; attempts170,450.
Whole disposable ledger+attempt physical relations712,704bytes includes earlier
fixtures and indexes, not a marginal production-storage forecast.

Separate fixture setup/owner-registration/assertion harness:94connections,
334cursor calls(excludes internal driver commands),13.163s elapsed including
the contained runtime. These are NOT added to or hidden inside845/30 operational
figures. PostgreSQL test-service setup/teardown and runner dependency installation
are separate CI costs, not fully metered production controller work.

The old one-candidate path remains108cumulative commands/5connections: capture30
includes4child-materialisation commands; subsequent selection/detail/writer path
adds78, with4screening-body commands plus live read/claim overhead. It was not a
108-per-row listing cost. New batches amortise fixed setup while preserving one
typed broker transaction per row and actual screening work.

Original final artifacts are archived, not merely linked until hosted expiry:

| Artifact ID | Original ZIP SHA256 |
|---|---|
|12062853676 restricted PG/receipts|befafd45d5ad7bdd4e7f8ed4bf7022354dd004e4b9c4c0bcdb45e674c2630b92|
|12063043953 offline|f1542bde73969580718a8d18a540c2c5944bdbb7139ef409b297317e1cc08c5c|
|12063467605 admission PG|18fafd59e9ef8e683a326ff52931d732c518e160c06cccba74c63a604bb15bf2|

ARTIFACTS.json binds IDs/run/head; ARCHIVE-MEMBERS.json hashes all67 original PG
ZIP members; MEASUREMENTS.json preserves exact JUnit properties including slot
receipts, every supervisor and citations. Intermediate first/second PG artifacts
are also retained truthfully, not substituted for final evidence.

## Proposed finite production decision, not activated authority

Accept/reject1,040aggregate driver commands,40connections,4MiB returned data-value
bytes and300active supervised seconds for one capture + at most12batches + any
separately approved recovery/duplicate handling. Headroom23%commands/33%connections
above this measured rehearsal. Keep existing120commands/16connections/165seconds
per logical slot, source10requests/3,000,000received-body bytes/45seconds/6pages/
60rows, memory/output and480second job ceilings. No borrowing. Exact finite
five-job combined allocation and separate provisioning/candidate envelopes are
in PACKAGE.md. A cap ends BLOCKED with preserved evidence, never a new observation.

Returned data-value bytes exclude PostgreSQL protocol/column metadata/TLS/wire
traffic. Source received-body accounting is not total wire traffic either. Remote
latency, larger legal proposal payloads and compressed/header/framing overhead
are not certified from these synthetic local measurements.

Ordered future gates: targeted provider response/concrete secure method; exact
access prerequisites; reviewed base storage3blocked+control test; operational SQL/
restricted mappings; explicit exact scoped disposition and capture authority;
archive/readback; source-free batches with sealed allocation; separately nominated
at-most-one candidate; non-destructive revoke/secret removal and positive closure.
No worker may issue its own grant, release the original barrier or expand scope.

Optional nomination uses a completed batch without rewriting the source receipt.
It is covered with actual SQLite writers and negative tests. Prior separate PG
shared admission/B2/readback remains passing. Combined batched nominee factual
stage PostgreSQL command-budget proof is NOT established. Its proposed separate
one detail observation/2requests/2,000,000received-body bytes/45worker seconds/
120commands/16connections/165controller seconds/two write slots remains subject
to bounded acceptance. No eligible/new/supported nominee means no replacement,
pending identity or admission/B2 success. Status-only proof is not unit extraction.

Production prerequisites remain: targeted Supabase answer and accepted secure
method; base storage/access NOT RUN; operational permissions NOT INSTALLED;
protected durable archive publisher binding/readback required; scoped exception
NOT REGISTERED; no source or write authority granted. The disposable archiver's
fixture commit is not claimed as a real Git commit. No production queue population.

Salford remains consumed/blocked; no replay or inferred TargetClosedError cause.
Bolton future proposed civil day16OctBST corresponds15Oct23Z–16Oct23Z;
conservative eligibility17Oct00Z =01BST, with late-publication gap explicit.
IDs1504–1508, PR119, historical seals and consumed authorities are untouched.
Qualifier-safe withholding remains accepted but is not verified unit delivery.
All415 retained identities and discovery gaps retain their historical dispositions;
synthetic rows do not complete backlog, database catch-up or commercial relevance.

Pipeline offline/disposable readiness: demonstrated bounded scope.
Production storage acceptance: NOT RUN.
Operational acceptance/activation: NOT RUN.
Backlog completion: INCOMPLETE. Stage4 OPEN. No integration/deployment/scheduling.
