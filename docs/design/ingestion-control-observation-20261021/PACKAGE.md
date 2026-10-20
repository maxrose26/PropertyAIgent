# Control observation (offline preparation; nothing here is authorised or run)

Purpose: establish the actual state of the control record after the consumed stable-pipeline run (stop generation, manual stop, `last_hard_stop`, the digest of the stop state, and the identity and expiry
state of every grant and Bolton exception) so that the next decision rests on observed state. It is a **diagnostic observation**, not an acceptance of anything.

## What it does
One database connection and 6 statements (limit 12): the migration identity check; `BEGIN`; the transaction-local owner capability (`GRANT ingestion_storage_owner TO CURRENT_USER`); one `SELECT` of the
control record with the server clock; `ROLLBACK`; the capability readback (both false). The projection (names, expiry numbers and states, stop fields, counts and two digests - never bindings or key lists) is persisted
to the audit journal before anything else can happen.

## The concrete limitation
No existing function exposes the fields needed (`ingestion_acceptance_control()` returns only the global stop, manual stop, stop generation and the count of unexpired grants). The administrative identity has no
table privilege, so the full record can only be read through the transaction-local owner capability that the accepted preflight and the accepted invalidation readback already use. **That `GRANT` is a statement that would
write the role catalog if it were committed; it is rolled back and its absence is read back, but this is not a strictly read-only (`BEGIN READ ONLY`) transaction.** If a strictly read-only observation is required, only
the four fields of the existing function are available.

## Limits
1 connection; 12 statements (6 measured); 20 database-active seconds; 30 supervised-active seconds after the 120-second hidden input; registration expiry at most 30 minutes; zero GitHub requests, source requests,
grants or exceptions; local audit only.

## Not authorised by this package
Installing any policy, clearing or replacing a stop, a source request, a probe registration, a dispatch, any credential change.
