# Release candidate implementation checkpoint — NOT an operational proposal

17 November 2026. Stage 4 OPEN. This is incomplete engineering work, not a new
owner approval dependency. Production recovery, installation, stop clearance,
deployment and collection remain on hold. v1.4 is consumed; v1.3 remains fenced.

## Implemented and exercised

- `bolton_recovery_guard.recover` wraps the unchanged #213 module at
  `f027ba28af69ae70208eab5ed047e4a8a81c6337`, checking its source SHA256
  `5bd306a86bc8b273d3bd0d778e7fc7803e737d7a589828f9f0405bc844a18d4a`.
  It strengthens only the existing OTHER_WORK query to include every unrelated
  CLAIMED state, under the original table/controller locks. Actual pinned
  recovery refused an unrelated CLAIMED/IDLE row, then recovered under STOP14.
  Deliberately lost COMMIT acknowledgement was resolved by a fresh inspect at
  STOP15 without repeating the mutation. Original evidence and permissions
  remained intact.
- Pure conditional release compiler retains the existing release SQL's locked
  seven-effect/controller/ACL comparisons, requires exact manifest fingerprints,
  and adds a manifest-bound finite expiry. PostgreSQL proved expiry refusal,
  transaction rollback, STOP15→16, independent readback and duplicate refusal.
- Conditional campaign compiler binds the entire policy and release-manifest
  hash in SQL. Only Tameside RECEIVED 15–21 September 2026, max_runs=1, is admitted.
  Direct SQL tests refused altered dates, council, expiry, build binding and a
  well-formed but incorrect source-plan hash. Table-before-controller locks
  protect the claim census, including the owner preflight path.
- Stopped campaign installation was exercised as a real non-superuser postgres
  login in the disposable database. CREATE on the schema is temporary, restored
  before commit; owner membership is also restored. Worker EXECUTE remains absent.
- Proposed six-item historical disposition SQL validates compound original
  work/attempt fingerprints while stopped. It saves original rows and attempts
  verbatim in checkpoints, changes no attempts or source evidence, preserves
  UNKNOWN and permanent no-replay, and refuses changed preimages/repetition.

## Validation and precise limits

Local disposable PostgreSQL **17.11**, loopback only, no production credentials or
council requests. Six focused tests passed in 15.46 seconds, including the actual pinned
#213 guard/recovery entry point; no skips. Forty-three existing pure issuer checks were
also reused in the earlier 46-check run (three new PG checks at that point).

Release component fixtures substitute local database/principal identity and
synthetic historical hashes. The restricted installation test keeps the actual
postgres session identity and permission lifecycle. These are component proofs,
NOT one joined production-candidate recovery→collection acceptance. The old
unchanged recovery/retention/backlog proof remains evidence for its earlier
synthetic assumptions; it does not close the new integration gap.

`release-proposal.json` records the seven original fingerprints and exact
historical decision references, the single batch, all-ten follow-on inventory
and a **proposed** expiry of 18 November 2026 20:00 UTC. It is not an accepted
operational manifest. Its digest binds its content, not owner authentication.
Post-recovery controller/work/attempt hashes are intentionally not fabricated.

## Single remaining deliverable

Complete the connected executable integration in this PR. Owner and runtime
still calculate the inactive issuer fingerprint and both default live flags
remain false. The new compilers are not yet selected by those entry points.
The guarded recovery adapter also needs the final bounded command integration.

Wire the reviewed compiler into those existing entry points, produce the exact
enabled build and complete policy/configuration, and define the mechanically
verified post-recovery/disposition receipt-to-release-manifest binding. Do not
fill required hashes with fixture values or obtain them by assuming an unchanged
controller. Reuse the v1.4 observation; do not rerun an inspection. Validate the
actual guarded #213 recovery, fresh STOP15 readback, stopped installation,
six dispositions, conditional STOP16 release, exact historical campaign issuer,
synthetic capture/retention/screening/backlog and cleanup on the same disposable
database, without manufacturing intermediate production states.

Then return exact executable/configuration/manifest pins and ordered commands
for distinct REVIEW and one owner operational decision. Current recommendation:
**NO-GO for that decision; no additional owner scope approval needed for finishing
this offline integration.** Manchester, Bolton and Tameside remain explicit with
Bury, Oldham, Rochdale, Salford, Stockport, Trafford and Wigan in follow-on scope.
Trafford remains unqualified for execution; no dummy source qualification added.

No new production population, qualification, saved facts or backlog is evidenced.
