# Salford15 separately reviewed continuation — 14 October 2026

Product Owner chose quarantine-and-continue after run 38475718624. Application
266 / PA/2025/1295 remains quarantined, not retried or diagnosed. Trafford is
explicitly deferred. This is a new closed invocation, not a resume of the old run.

Exactly the 15 previously NOT_ATTEMPTED Salford identities are frozen in
`salford15-manifest.json`, including the unchanged admitted source destinations.
The first six correspond to the untouched suffix of catchup_e; the final nine
to catchup_f. Two sequential batches retain the existing 300-second batch bound.
Batch b requires an ACCOUNTED, validated batch-a audit from this same SHA/run.
Any safety stop or uncertainty stops the run; identity rejection semantics are
unchanged. No automatic retry, resume, reference input or source substitution.

The accepted prior family validation and production evidence are retained in
artifact 11854451629 (run 38475718624), original ZIP SHA256
`a950708d419d247dc45e73d0732325bdefd911fb8fd9e88eb57a1508582edb3b`.
The Product Owner authorises reliance on that accepted family validation; no
repeat validation or schema migration is included. B2's existing field-level
projection, CAS, transactions, bounded readback and supervised worker are reused
unchanged. The existing source and transaction worker resource budgets remain.

The distinct manual workflow requires exact integrated master SHA, run number 1,
attempt 1, the existing production environment and a dedicated authority literal.
Production credentials are confined to the execution step and isolated workers.
No deployment, scheduler, source research, AI or discovery is included.

Before dispatch: independently review exact identities and controls; reconcile
final-head hosted checks; verify master/workflow blob, manifest hash, zero prior
runs and environment/secret-name presence. Dispatch once, observe and validate
bounded audits. Reconcile the retained118 cohort without calling it a new census.
Known-reference acceptance and Master Stage4 closure are separate: Stage4 stays
OPEN even if the sub-gate is GO.
