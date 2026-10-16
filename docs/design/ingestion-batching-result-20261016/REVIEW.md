# Independent review: PASS

Exact candidate: 6f1b81b2851ecdc9f9902c3a0111b7d305827ff4

Exact tree: 20a48f9e864f1eaab34686bc23957fa7db85f4ab

Reviewer: separate read-only operational_independent_review agent. No production
or publication authority was delegated. Final review found no unresolved
substantive issue, conditional on final exact-head hosted checks.

Findings resolved before final candidate:

1. Nullable required SQL values could bypass comparisons. Exception and batch
   types now fail closed; real restricted owner tests reject JSON-null members.
2. Batch recovery needed an exact accounting digest, not just matching slot and
   capture labels. Sealed prior accounting is required before another claim.
3. Completed-task policy negatives were confounded. Eligible queued sentinel is
   positively claimable in a rolled-back transaction; grant mutation, expiry,
   unrelated council and new stop deny GLOBAL_STOP with zero retained attempts.
4. Capture-recovery needed the same prior seal and exact slot requirement. Added
   checks and focused negative tests prove denial before claim.
5. Parent-process recovery time was outside supervision totals. Recovery now uses
   its own owned restricted-login supervised invocation and is charged to the
   same logical slot, including counters/time/RSS/output and positive closure.

Final optional nomination seam review: completed protected batch must bind root,
scope, full capture hash and plan revision. Nominee must occur in its child list
and exact already-COMPLETE screening task with original root dependency and row
digest. Trusted controller recomputes screening before expensive work. Capture
is immutable; there is no source replay or authority issuance.

Validation limit: this new nomination seam has SQLite actual-writer coverage.
The 60-row restricted PostgreSQL rehearsal and earlier one-candidate PostgreSQL
writer rehearsal are separate evidence. A combined batched nominee factual-stage
PostgreSQL command-budget proof is not claimed. The optional120-command allowance
is a proposal requiring its own bounded acceptance, not established production
delivery. Production credentials, permissions, exception and source remain held.
