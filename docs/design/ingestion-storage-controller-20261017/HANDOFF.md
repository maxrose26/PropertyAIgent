# Finite owner-local storage acceptance

Stage4 OPEN. Storage acceptance only. No source/admission/B2/consumer/scheduling
capability is called. PR122 and all historical records/authorities remain intact.
This controller completes the already-authorised package; it does not activate
operational ingestion. The original Salford stop stays present and unchanged.

## Owner preparation already completed

Owner WSL Ubuntu24.04/WSL2, secure TTY, Linux gh2.45.0 authenticated as maxrose26
using GNOME Keyring, and clean PR122 checkout are verified by owner readbacks.
Do not repeat authentication or copy token files. Keep the same D-Bus/keyring
session open. Generated database credentials stay in worker memory and go to the
exact two protected environment secrets through gh stdin. No credential is read
back from GitHub. Possible provider SCRAM-verifier retention is accepted only
for these two logins; this is not provider-confirmed redaction.

Use the integrated revision and credential-free successor registration recorded
in RESULT.md on the existing evidence branch. The predecessor registration SHA
`e685c79086758f5b52bf5ceff5a8ad34fb2d9e2598e8670485b3ce3a07d7252d`
is retired UNUSED, not consumed or replayed. Its expiry and original content
remain in history. A successor is not a second allowance. Do not use the old
mapping CLI, its old provider-redaction flag, or an expired registration.

Prepare a NEW external virtual environment with the minimal owner-requirements
file (versions reuse the accepted stage1 lock). Keep all environment/evidence
files outside the exact clean repository checkout. Dependency installation and
human credential input are preparation, with no database access. The exact
reviewed command is published only after integration/checks/registration.

## Ordered execution and accounting

One owner command accepts the existing migration URL through the reviewed
getpass mechanism (secure TTY, no echo fallback). It validates the exact route,
checkout, registration, CA and expiry before effects. The timer begins before
fork, machine owner-access checks and DNS. All production connections retain
verify-full/checked-in CA/hostname verification, the same selected IPv4 address,
3s connection timeout and prepare_threshold=None. No route or credential fallback.

1. Bounded owner account and fully paginated protected-secret-name checks.
   Existing test secrets cause a stop before database changes. Metadata read
   access is not misreported as proof of write access; the authorised first PUT
   is the actual write. Token/debug environment overrides are rejected.
2. Exact reviewed install.sql, non-superuser migration identity and privilege
   gates; committed installation closed, then fresh migration connection checks
   owner-transfer revocation, disabled runtime logins and ADMIN-only residual.
3. Exact read-only activation gate before generating password material. Reuse
   credential_mapping.install_mapping: two independent 48-random-byte passwords,
   client-generated SCRAM, initial NOLOGIN, role-bound password commit intent/ack,
   secret PUT intent/ack. Expiry is the earlier of registration expiry and 24h.
4. Exact activate.sql. No issuer/releaser membership, new baseline permission
   exception or new credential route. Close migration connection before testing.
5. Four sequential restricted-login connections, exactly40 storage commands:
   - operator first seed plus identity/session timeouts7; second seed6; denials2;
   - worker fixed stop plus identity/session timeouts7; denials6;
   - fresh worker and operator six-command readbacks12.
   First connection timeouts are session-scoped so expected-denial statements
   remain bounded after COMMIT; readbacks retain reviewed read-only transactions.
   Each role authenticates directly; no SET ROLE substitute. Full three manifest
   rows, original control stop, no grants, zero attempts, size caps, exact
   reconnection equality; the immutable seed function supplies no-op duplicate
   semantics. No Application row SELECT or DML is executed.
6. Fresh migration connection: session statement timeout1 + exact revoke.sql8
   + read-only membership/login/session readback1 =10 teardown commands. Acknowledged
   exact SQL/COMMIT proves PASSWORD NULL was requested and committed; production
   does not read pg_authid, hashes or verifiers. Independent catalogue readback
   proves two NOLOGIN roles, zero memberships and zero remaining role sessions.
   Disposable bootstrap independently verifies NULL passwords; do not mislabel
   that as a production verifier readback. Any remaining pooled/backend session
   stops here; no mass termination or stronger-role fallback.
7. Two exact protected-secret deletions and bounded name-only absence check.
   Preserve ledger/roles/objects/audit; no destructive rollback.
8. Worker socket/child census, supervisor process/RSS/time closure. Only the final
   supervisor result can report STORAGE_ACCEPTED_ACCESS_DISABLED.

Successful normal path: seven connection attempts total (two provisioning,
four restricted storage, one teardown). Hard ceilings remain13 combined,
4 provisioning/8 storage/1 teardown,240 supervised seconds including closure,
256MiB sampled aggregate worker+owned-child RSS,2MiB combined exported audit.
Provisioning90s; storage120s and30 active DB seconds; teardown30s and10 active DB
seconds. Two seconds of total/teardown time are held for owned-process closure;
work stops at238s/teardown28s. A30s teardown reserve cannot be spent on earlier
phases. No process/artifact restart resets counters. Each driver statement is
counted separately, including SQL script top-level statements and helper-issued
BEGIN/COMMIT; reviewed server-side function/DO internal statements are not
claimed as additional driver calls. All fetched database values are counted as
serialized data-value bytes, not protocol/network traffic. Secret HTTP traffic
is not labelled DB traffic. PG rehearsal excludes real GitHub/TLS/DNS latency;
production supervisor includes it. Source calls remain zero.

## Durable progress and stops

Fixed single-use directory:
`~/.local/state/propertyaigent/storage-acceptance-once-20261016/`

Creation is exclusive. Existing directory blocks invocation; do not delete,
rename or select another path to retry. The parent fsyncs the hash-chain journal
before acknowledging the worker's next effect. It records stage intent/ack,
role-bound credential transaction intent/ack, secret operations, counted driver
calls, exact safe readbacks and closure. It never records SQL/params/credentials.
A missing ack is uncertain even if the operation may have succeeded. Journal
checksums detect alterations; they are not an external signature or independent
proof of an uncertain database commit. Copy the credential-free audit to durable
project evidence after the run; do not depend on CI artifact retention.

To stop from a second WSL shell, create the empty file:
`touch ~/.local/state/propertyaigent/storage-acceptance-once-20261016/STOP`

Ctrl+C also requests stop. Supervisor terminates only owned worker/group/children.
No finally-block database changes or secret-store compensation. On any failure,
keep terminal, binding and audit; return final sanitised status and phase. Do
not invoke again. NOLOGIN/expiry does not terminate an existing session. Partial
activation, unmapped roles, failed secret PUT/deletion, uncertain revoke or
remaining sessions require read-only reconciliation and a specific bounded
recovery disposition before further mutation. Teardown incomplete is reported
explicitly, never relabelled CLOSED. No automatic fallback, repair or scheduling.

## Acceptance distinction

Storage PASS proves only the fixed blocked ledger rows, permissions and access
teardown within measured bounds. Pipeline activation, new-candidate admission/B2,
unit facts, backlog completion and scoped Bolton exception activation remain
outside this operation. IDs1504–1508 are not queried or changed in production.
