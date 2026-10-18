# Matrix cleanup — revoke-only package

Status: PREPARED FOR REVIEW. Nothing here runs by itself; one execution needs an exact single-use registration, a clean checkout and a visible-terminal hidden-input handoff. Storage remains accepted; ingestion activation and Stage 4 advancement remain held; original stops and consumed authorities are preserved.

## State this answers (from the retained matrix audit, hashes in the registration)
The restricted-connection matrix stopped after two entries. Its teardown disabled both logins (`NOLOGIN`, NULL password, capability memberships revoked) but its session readback found one idle `ingestion_worker_login` backend (pid 3175259), so it did not delete the temporary secrets. Both `INGESTION_WORKER_DATABASE_URL` and `INGESTION_EFFECT_DATABASE_URL` remain in the GitHub environment beside the preserved `DATABASE_URL`.

Disabling a login stops **new** logins. It does not end a session that already exists, which is why password removal alone was not sufficient cleanup and why the secrets are described as *disabled for new login*, never as simply "dead".

## What the cleanup does (and nothing else)
| Step | Rule |
|---|---|
| 1. Re-read | `ingestion_effect_login` and `ingestion_worker_login`: `NOLOGIN`, NULL password, no superuser/createrole/createdb/bypassrls/replication, **no capability membership**, and their sessions (pid, role, state, backend start only — no query text, no credentials). Any role not exactly disabled is a stop with no change. |
| 2. Terminate | At most **one** session, only if the fresh read shows it is the **only** session of those logins and its pid and role match the registered target. The backend start time observed in that read is bound; the state is re-read immediately before the signal; the single terminating statement repeats pid, role **and** backend start in its predicate, so a reused pid cannot match. Any other session, a different pid, or a change between the reads is reported as a discrepancy and nothing is terminated. |
| 3. Verify | Poll (up to 3 reads, 0.5 s apart) until none of the two logins has a session; the final state is read again on a second connection after the secret step. |
| 4. Secrets | `DELETE` exactly the two temporary secrets (each must answer 204), then one names-only read: both absent, `DATABASE_URL` present. Done whenever the logins were verified disabled, independently of the session outcome; a non-204 answer is a stop with no retry. |

It issues exactly three SQL statements (identity, state read, the single terminate) from a hashed allow-list. No `ALTER`, `GRANT`, `REVOKE`, `CREATE`, `DROP`, write, commit or role/membership/control/ledger change exists in it; it creates no credential or secret, connects as no restricted login and calls no council.

## Finite ceilings (bound in the registration; enforced in code)
| Quantity | Ceiling |
|---|---|
| Database connections | 2 |
| Driver commands | 20 (this path uses at most 9) |
| Database active seconds | 30 |
| Session terminations | 1 |
| GitHub API requests | 3 (2 deletions + 1 names read) |
| Hidden input / active window / outer | 120 s / 60 s / 210 s (systemd backstop 240 s) |
| Returned data bytes | 8 192; evidence 64 KiB |
| Memory | 256 MiB controller, 1.5 GiB aggregate, no swap (existing `OperationalMemory`) |

## Truthful outcome and closure
Access is reported `DISABLED_VERIFIED` only if the final read shows roles disabled, no membership, no session, both temporary secrets absent and `DATABASE_URL` present. Each part carries its own disposition (`VERIFIED`, `NOT_DISABLED`, `PRESENT`, `DISCREPANCY_NOT_TERMINATED`, `SIGNALLED_NOT_VERIFIED_ABSENT`, `UNVERIFIED`, …). Connection closure (opened = closed, no new socket) and process closure (no child, kernel groups removed) are separate components. Anything not read back stays UNCERTAIN and the result is `RESTRICTED_MATRIX_CLEANUP_INCOMPLETE_RECONCILE` or `STOP_RECONCILE_NO_RETRY`; there is no retry and no replacement run.

Privilege note: `pg_terminate_backend` on another role's session needs a privilege the migration identity may not hold in the managed database. The cleanup never grants itself one; a privilege failure is reported and the session stays `UNCERTAIN`.

## Validation (disposable PostgreSQL logging every statement; real Linux `gh` against the loopback GitHub fixture)
27 focused tests: the named session ended and absent; already-absent session recorded; a different pid or an extra session ends nothing, leaves sessions alive and reports `UNRECONCILED`; a lying backend-start (pid-reuse simulation) is refused by the predicate and stops with secrets untouched; roles not disabled stop without any change or GitHub request; non-204 delete is a stop; the statement allow-list and every ceiling; the real session controller end to end with preparation; registration bindings and rejections; predecessor binding to the actual retained matrix audit; owner script refusals; no role/ledger/credential capability in the module.

## Release procedure (not authorised by this package)
`render_registration.py` (offline; reads the target pid and the predecessor hashes from the retained matrix audit) from the approved clean checkout; expiry ≤ 2 h; the owner runs the private-keyring GitHub sign-in helper and then `owner-run.sh <commit> <tree> <registration-sha256>` in the same visible WSL shell.
