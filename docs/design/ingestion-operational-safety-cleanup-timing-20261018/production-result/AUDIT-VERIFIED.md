# Complete production cleanup audit verified

This verification supersedes the audit-collection-pending statement in the preceding production report. Original uploaded bytes are preserved as events.jsonl and final-result.json.

## Identity and integrity
Integrated revision: acd3f5690b439d7d91b7a7efb9ace79c9098d303.
Consumed registration SHA256: 3a1f7e58506d507deb9bf5c1b60c08af8c7a4ea2202785d27344e53d404f696f.
Complete audit: 39,887 bytes; 70 contiguous events (0–69).
Audit SHA256: a28b06aadc13ee0eb7bd2362c40ec7111804777febf230e44041fae2de116ec7.
All canonical event hashes, predecessor links and sequence numbers independently verified.
Chain head: ca6922b1c24394b1f3da77ccbbcc0ff97dda9ae3051aa1ba98ef939ddbe895ee.
Final result: 1,475 bytes; SHA256 da098789bde167157b09d85ae8379e095f77b45bf2cd930c7a52a54cf34f3c0d.
Both hashes match the original owner terminal receipt.

## Reconciled outcomes
SAFETY_CLEANUP_ACCESS_DISABLED; database commit ACKNOWLEDGED; controller cleanup CLOSED.
All 20 database intents have matching acknowledgements, including commit and readback rollback.
Both exact worker/effect logins are NOLOGIN with password-removal booleans true, no reviewed memberships and no associated sessions on reconnection.
Temporary migration ownership USAGE/SET capabilities both false.
Consumed capture grant and exception expiry both zero; hard-stop generation 0 -> 1.
Salford stop (run 38884069913) and STORAGE_TEST_STOP preserved.
Four non-control ledger records and zero attempts unchanged across reconnection:
ledger SHA256 2e1e6e88536b78b641648877921e19d0453ba8107fc1d512de623832f900e502.
Two exact secret DELETE intents acknowledged. Final complete names-only read contains DATABASE_URL only; existing DATABASE_URL preserved.

## Actual accounting and closure
20/32 commands; 2/2 connection attempts, both opened and closed.
17,236/1,048,576 returned database data-value bytes (not wire traffic).
2 DELETEs and 2 complete names-only GETs.
2.167912 active seconds through audit flush; 7.522072 credential-input seconds; 10.272191 total seconds through audit flush.
64,049,152-byte cgroup memory peak; all memory-limit/OOM counters zero.
41,362 persisted evidence bytes plus 2,174 terminal JSON bytes = 43,536 exported bytes.
No new sockets or live children; controller was sole process in its scope and exited 0.
Separate post-exit systemd readback exited 124; post-exit unit/cgroup removal is not established. This does not invalidate the acknowledged database/access readbacks or controller connection/socket cleanup.

## Preserved holds
All predecessor UNCERTAIN cleanup classifications and original operational accounting gaps remain unchanged.
Storage milestone remains accepted. Operational acceptance failed; pipeline retry HELD.
No source calls, provisioning replay, new execution authority, application/factual writes or scheduling were performed in this reconciliation.
Stage 4 remains OPEN.
