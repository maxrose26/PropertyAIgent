# Production storage successor — storage verified, teardown incomplete

Stage4 OPEN. Status STOP_RECONCILE_NO_RETRY / TEARDOWN_READBACK / cleanup UNCERTAIN.

Exact controller revision7cf8d32547b63d485de872afc2f717c3dce55322, tree68bf766cda023b1f15a19a63978903995391ec46. Registration43bb06a2ee93cc77428e056eb8a19b2efe8f98e880ed42d0a0e0b2b69e33d5f3 is consumed; no replacement/retry. Owner systemd invocation6ee93a9ad895419a8f84dc8484de3258.

## Evidence and verification limit

Owner-local inspector verified original audit SHA256788351d1bf68d282640a88f0c5627631a57b447bd4028db2ee781290ce73b560,104114bytes,182entries, chain headb741c4b08b8ef067087e2510ec24963fa601cbbd87e3beda4617e87b663af691. Original full events.jsonl remains on the owner's machine; it has NOT been supplied here or archived by this publication. This publication preserves the supplied console excerpt, its original bytes and selected events. Independently verified all10supplied event hashes and the contiguous174–181tail chain. Do not claim independent full-audit reconstruction from this excerpt.

Original excerpt SHA256a5b87857068aa6e937826fd8f5ccc233157a32b1c3d7b8df6bf39a6d191cee3a,12665bytes. Preserve all previous checkpoints/audits and their historical UNCERTAIN classifications.

## Verified recorded outcomes

Migration postgres/current_session identity, NOSUPERUSER/CREATEROLE/CREATEDB/BYPASSRLS and all grouped PostgreSQL/grant-option/unused-role/absent-object predicates passed. Owner checkpoint report records installation COMMITTED, installation_readback VERIFIED, mapping MAPPED_NOLOGIN, activation COMMITTED, first_seed COMMITTED, duplicate_seed COMMITTED, storage VERIFIED.

The independently hashed storage_readback event163 contains exact3blocked items plus control:
- Rochdale PL/2026/0882: UNSUPPORTED_CONTRACT, LISTING_METADATA.
- Oldham NMA/356901/26: UNSUPPORTED_CONTRACT, FACTUAL_REFRESH; existing pending ID1507 context only, FACTS_WITHHELD.
- Salford VALIDATED8–14October2026: SAFETY_BLOCKED, LISTING_METADATA.
- Control preserves CONSUMED_SALFORD_GLOBAL_STOP/run38884069913; manual STORAGE_TEST_STOP added as reviewed, grants empty.

Zero work attempts, zero executable grants,8permission denials, duplicate seed NO_OP.4595serialized readback bytes and49152physical ledger bytes. Exact retained rows/provenance are in SELECTED-EVENTS.json. These are storage results, not live ingestion or factual delivery. No Application/factual writer/source route exists in this fixed controller; accepted IDs1504–1508 were not modified.

## Teardown and uncertainty

Fixed revocation script returned through COMMIT, then its readback expected (disabled_logins=2,memberships=0,sessions=0). Reason TEARDOWN_READBACK means the result did not equal that tuple. The actual tuple was not logged. Do not infer which condition failed from7serialized result bytes or assume a pooler cause.

Effective NOLOGIN/membership/session state is therefore NOT_VERIFIED. Controller secret deletion and absent-name verification occur after this gate and were not reached. Do not claim temporary secrets removed; their present existence has not been independently checked. No automatic credential/reset/DDL/seed replay or compensation is authorised.

Native migration connection_closed event178 reports open_connections0. Worker cgroup empty/removed,0reported owned survivors,0OOM/max events; no forced cleanup. These narrower positive facts do not establish global CLOSED or absence of provider-side sessions. Overall cleanup remains UNCERTAIN.

## Resource accounting and exact blocker

Successor5.1800128019986005supervised seconds; cumulative6.463323766999565including both earlier attempts.8cumulative connections and139commands, including prior1connection/4commands. DBactive2.9165738029942077s; storage40commands/4connections/.7638419260038063active seconds; teardown10commands/.17419392399642675active seconds.9429returned database data-value bytes, not total wire traffic. Outer kernel peak128180224bytes; worker kernel peak19546112bytes; sampled owned RSS103444480bytes;256MiB kernel limit not breached. Audit104114bytes.

Aggregate headroom is233.53667623300043supervised seconds and5connections, BUT teardown's10-command allowance is exhausted. This is not authority to borrow phase budget, start another controller or rerun consumed registration.

## Smallest REVIEW decision

Approve only one separate read-only teardown reconciliation within carried cumulative accounting: at most1connection,6driver statements including BEGIN READ ONLY,3localtimeouts, one grouped exact-role query and ROLLBACK;10supervised seconds; existing verified endpoint/CA/verify-full/migration credential through hidden input and256MiB containment. Query only exact2role flags/memberships and associated session PID/backend_start/state/database, never query text, passwords or verifiers. Separately read names-only existence of the exact2protected temporary secrets through existing keyring gh access.

No mutation in this observation. Return exact failed condition and readback before further effects. If all DB teardown predicates are now true, complete the already-reviewed exact2secret removals only after certain reconciliation and reviewed recovery accounting; do not reinstall or seed again. If sessions remain, request only finite termination of their identified PIDs. Failed login/membership state requires a specific reviewed correction, not automatic replay.

This finite read-only phase is proposed, not executed; it needs an explicit phase allowance because the original teardown10commands are spent. Preserve original expiry18October2026 09:54:58BST; do not silently renew.

Production storage acceptance remains INCOMPLETE. Operational activation/source calls/consumers/scheduling/stage advancement remain held.
