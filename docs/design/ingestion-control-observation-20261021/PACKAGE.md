# Control observation (offline preparation; nothing here is authorised or run)

Purpose: establish the actual state of the control record after the consumed stable-pipeline run (stop generation, manual stop, `last_hard_stop`, the digest of the stop state, and the identity and expiry
state of every grant and Bolton exception) so that the next decision rests on observed state. It is a **diagnostic observation**, not an acceptance of anything.

## What it does
One database connection and 6 statements (limit 12): the migration identity check; `BEGIN`; the transaction-local owner capability (`GRANT ingestion_storage_owner TO CURRENT_USER`); one `SELECT` of the
control record with the server clock; `ROLLBACK`; the capability readback (both false). It has **no committed mutation** (it is not a strictly read-only observation; see below). The projection (names, expiry numbers and states, stop fields, counts and two digests - never bindings or key lists) is persisted
to the audit journal before anything else can happen.

## The one operation that is NOT strictly read-only (explicitly listed for approval)
The observation has **no committed mutation**. It is **not** a strictly read-only observation, and it must not be described as one. It executes exactly this one statement beyond reads, inside an explicit transaction that is rolled back:

```sql
GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE;   -- transaction-local owner capability; the migration identity already holds ADMIN-only membership
```

* **Why it is needed.** The administrative identity has no table privilege on the ledger, and no installed function returns the fields requested (`ingestion_acceptance_control()` returns only the global stop, manual stop, generation and the count of unexpired grants). The same technique is already used by the accepted preflight and the accepted invalidation readback.
* **Sequence (6 statements).** identity check; `BEGIN`; the `GRANT` above; one `SELECT` of the control record with the server clock; `ROLLBACK`; capability readback (`pg_has_role(..., 'USAGE')`, `pg_has_role(..., 'SET')`, both must be false).
* **What the GRANT would change if it were ever committed:** the migration identity's membership row in `ingestion_storage_owner` would gain inherit and set options, giving it the owner's table privileges. Nothing commits it: there is no `COMMIT` on this path.
* **If the process, connection or server fails between the `GRANT` and the `ROLLBACK`:** PostgreSQL aborts the open transaction when the session ends, so the grant is never committed. In that case the observer **cannot read the absence back** (a second connection is not permitted) and the result says `UNVERIFIED_..._NOT_READ_BACK`; it never claims verification it did not perform. If the route is a transaction pooler, the owner should confirm that it rolls back an open transaction on client disconnect.
* **Disposable evidence (real PostgreSQL 17, the real installed ledger, observed from outside the observer as the bootstrap superuser):** `tests/test_discovery_ingestion_control_observation_pg.py` snapshots every membership row (with its admin/inherit/set options and grantor), every role's login, password hash, validity and settings, the control-record digest and the session count before and after: a normal run, a failure after the grant, a server-side disconnect after the grant, a failed capability readback and a failure before the grant. Every snapshot after equals the snapshot before.
* **Not done to avoid this:** no database function is installed, no privilege is broadened, no role is created or altered.

## Limits
1 connection; 12 statements (6 measured); 20 database-active seconds; 30 supervised-active seconds after the 120-second hidden input; registration expiry at most 30 minutes; zero GitHub requests, source requests,
grants or exceptions; local audit only.

## Not authorised by this package
Installing any policy, clearing or replacing a stop, a source request, a probe registration, a dispatch, any credential change.
