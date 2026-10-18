# Restricted-connection diagnostic: NO-GO; temporary access disabled

## Exact execution binding
Integrated revision b9e6bd639ad1f1a472c35f339b70f8f524c08ac4; tree a9d28fcf3994d2105c79b15e8f717f752d591e3c.
Registration SHA256 396f48d328891b872ee715f2f9cf6a33076620ba852a2fc7a436ec7b5af7cc1c.
Authority AUTHORISE_INGESTION_RESTRICTED_ROUTE_DIAGNOSTIC_ONCE_20261018 is consumed. No rerun, replacement, source execution or pipeline authority is released.
Owner-reported systemd invocation 429041fd4bf449d0a927f2c3ac4df133.
Controller exit 1; scope readback exit 124. These two exit statuses are owner terminal evidence, not fields in the uploaded audit.

## Full uploaded evidence verification
events.jsonl: 32032 bytes; SHA256 621a47a6b0b251faeb77db532d23bc4a61100b2586e82bcf4a6603a3195778c4.
final-result.json: 2755 bytes; SHA256 6fb30bfbd0fcbf73e652ea24f74a31faff5b4ae6852068c0aa1a297886e6aff7.
All 108 sequence numbers, previous hashes and canonical SHA256 event hashes verified.
Chain head 7908b2e594be68a918573734536f4f4d6d945da733da494db678651613a7ee1c.
Final result matches terminal audit payload, with the expected added phase_timing object.
Full audit and original final-result bytes preserved alongside this report; no excerpts substituted.

## Observed outcome
One ingestion_worker_login connection attempt failed in DRIVER_CONNECT, OperationalError, SQLSTATE null, no arbitrary message exported, underlying cause UNDETERMINED.
Zero restricted connections opened; zero restricted driver statements. ingestion_effect_login was not attempted after the failure, as required.
No restricted identity or transaction-mode qualification succeeded. Do not infer TLS, routing, password or permission cause from this exception alone.
No source observation, source request, retained capture, screening or application/factual write.
No new execution grant, exception or generation-policy patch. Control readback: generation 1, unexpired grants 0, original CONSUMED_SALFORD_GLOBAL_STOP/run 38884069913 and STORAGE_TEST_STOP unchanged.
Initial grant_count 1 describes the retained historical grant collection, not an executable grant; final readback explicitly reports unexpired_grants 0.

## Access teardown established
SQL teardown readback and separate diagnostic reconnection both show:
- ingestion_worker_login and ingestion_effect_login NOLOGIN, password-null booleans true.
- Memberships empty; associated sessions empty.
Both exact temporary secret DELETE intents and acknowledgements recorded.
Two subsequent names-only readbacks show INGESTION_WORKER_DATABASE_URL and INGESTION_EFFECT_DATABASE_URL absent, DATABASE_URL present.
Access DISABLED_VERIFIED; no uncertain administrative effect recorded. No additional access mutation is presently indicated by these readbacks.

## Cleanup boundaries
Runtime database slot cleanup CLOSED; all five administrative connections opened and closed.
Owned memory groups removed, owned_survivors 0, no memory max/OOM events.
Overall recorded cleanup remains UNCERTAIN and is not reclassified.
Offline code inspection establishes that operational_runner.Runtime.failed assigns cleanup UNCERTAIN unconditionally and does not execute the final owned process/socket baseline comparison used in the success path. Positive final socket closure is therefore not established by this failure receipt.
The later systemd scope readback separately timed out (124); post-exit scope removal remains UNVERIFIED. That later timeout did not cause the already-recorded controller classification.
Historical UNCERTAIN outcomes and earlier accounting gaps remain unchanged.

## Actual accounting
Administration: 52 driver commands; 5 connection attempts/opened/closed; 30370 returned DB data-value bytes; 1.282625216026645 DB active seconds.
Runtime: 1 failed connection attempt; 0 opened; 0 statements; 0 returned DB data-value bytes; 0.6158585599987418 supervised seconds.
Total DB connection attempts: 6 (5 administrative, 1 restricted).
GitHub CLI invocations: 8.
Active accounting: 5.367925684000511 seconds; before-reporting elapsed 5.371390081003483 seconds.
Hidden input: 10.17832041300062 seconds.
Aggregate memory peak 77848576 bytes; controller group peak 18792448 bytes; source group 0.
Evidence persisted 34787 bytes; reported exported total 38218 bytes (including terminal output).
Returned data-value bytes and source received-body bytes are not total network traffic. Source bytes/requests are zero.
All reported usage within this diagnostic's published ceilings. This does not reconstruct historical missing usage.

## Decision and smallest next review
NO-GO for capture. Storage remains accepted, Stage 4 OPEN.
The diagnosis established phase/type only, not root cause. The next review should cover a minimal offline improvement to classify credential-free connection failure reasons and complete failure-path closure evidence. Another provisioning loop or live replay is not authorised by this reconciliation.
Preserve current disabled access, all ledger data/functions, IDs 1504–1508, stops and consumed authorities. Capture, B2, scheduling, deployment and stage advancement remain held.
