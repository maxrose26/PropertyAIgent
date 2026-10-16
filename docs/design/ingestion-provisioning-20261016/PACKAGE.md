# Restricted ledger provisioning and three-item storage acceptance

REVIEW PACKAGE ONLY — preparation/disposable validation authorised; production role creation, credentials and permission changes are NOT authorised. Stage4 OPEN. No master integration or production workflow registration in this package. No consumers, source execution, factual/application writes, scheduling, deployment or stage advancement.

Accepted baseline: runtime eaed72d7d9e377d7e397b28db4e4936435ed85ec/tree697fd47af7c7fd5ced97e055f7aaed00e4fe7896; consumed TLS/catalogue run38907801607,1/1; accepted evidence b48769539effa9e209f79cd392120e7919c5bc07. Do not repeat that preflight. Original run38894230179 stays consumed, original cleanup UNCERTAIN/cause UNDETERMINED.

## Concrete package and changes

`install.sql` is one first-install transaction derived from the accepted f790550778172adbfe1db792d20b4c4fb58298e5829f4033f269c8670dc47033 migration. The two table definitions, fixed seed contents, control row, FORCE RLS and function bodies remain unchanged. It adds an explicit non-superuser ownership-transfer sequence, two disabled logins, CONNECT and exact capability memberships. It narrows the operator by removing its stop-function grant. `activate.sql` fails closed on unexpected effective permissions; `revoke.sql` disables access without deleting data. No coordinator/agent architecture or schema redesign.

The previously accepted three-items.json SHA2567883c1a8f99ce3e498fb73911713c3b531d4c73d20fd2524e3c9901e822e7b04 is unchanged. Items: Salford VALIDATED8–14October2026 SAFETY_BLOCKED; Rochdale PL/2026/0882 UNSUPPORTED_CONTRACT; Oldham NMA/356901/26 contextID1507 UNSUPPORTED_CONTRACT/FACTS_WITHHELD. Exactly3 items + consumed-stop control,0 attempts,grants={},no executable authorities. No pending Application is created.

## Exact principal and membership sequence

Use the existing approved migration credential/endpoint only. Supabase shared session pooler aws-0-eu-west-2.pooler.supabase.com:5432/postgres; original migration username postgres.zcikcfgpblzuzpanpdqd maps to SQL current_user=postgres. Native psycopg3, NullPool or direct psycopg connection closed after each phase, prepare_threshold=None, verify-full with the accepted checked-in CA (PEM700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7; DER807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa). No URL TLS override, environment-file loading, alternate host/port, runtime CA download, or stronger credential fallback. Select one address of the approved hostname and retain hostname verification. Mapping helper does this explicitly; later installation client must use the same reviewed connection recipe.

Run only `install.sql`, not the old migration followed by ad-hoc grants:
1. BEGIN with3s lock/10s statement timeouts. Require PostgreSQL17+, non-superuser CREATEROLE principal, public-schema USAGE/CREATE WITH GRANT OPTION and database CONNECT WITH GRANT OPTION. These grant options were not proven by the consumed catalogue. Failure rolls back and returns that exact blocker; no privilege expansion or substitute principal.
2. Create five fixed NOLOGIN/NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOINHERIT/NOBYPASSRLS roles: owner, storage_operator, worker, authority_issuer, barrier_releaser. Existing names cause failure/reconciliation, never replace/reuse an unverified role.
3. Add a separately attributable self-grant of ingestion_storage_owner to CURRENT_USER with INHERIT TRUE/SET TRUE. Grant owner CREATE on public temporarily. The creator's original bootstrap-issued ADMIN-only grant cannot by itself transfer ownership. No worker/operator/login receives owner membership.
4. Harden default function EXECUTE only for the NEW owner role; leave migration-principal and unrelated defaults unchanged. Create ingestion_worker_login and ingestion_storage_login NOLOGIN/PASSWORD NULL, NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS, NOINHERIT, CONNECTION LIMIT1.
5. Grant CONNECT only on the existing database. Grant worker -> worker_login and storage_operator -> storage_login WITH ADMIN FALSE, INHERIT TRUE, SET FALSE. These are their sole memberships; inherited object access works without SET ROLE. No postgres/service_role/owner/issuer/releaser membership.
6. Create and transfer the two ledger tables and fixed functions to owner; normalize all new-object default ACL grants (including PUBLIC and platform-role grants) before adding the exact allowlist. Enable/FORCE RLS; fixed owner policy and SELECT-only policies. Insert original consumed-stop control.
7. Grant worker only ledger SELECT + bounded raise_stop(text); operator only ledger SELECT + fixed seed(). Issuer/releaser stay dormant placeholders with no login, members, APIs or object grants.
8. Revoke temporary owner schema CREATE and only the migration-principal-issued owner self-grant (`GRANTED BY CURRENT_USER`). Assert no effective owner SET or inherited access remains. COMMIT.

PostgreSQL17 automatically leaves bootstrap-issued ADMIN TRUE/INHERIT FALSE/SET FALSE creator memberships on new roles. A non-superuser creator cannot remove those bootstrap grants. This residual migration-administrator power is explicit; it is not worker access and is not a promise of permanent separation from the existing administrator. Removing it would require separately authorised provider-level intervention; this package does not request a stronger-role fallback. Recheck actual grantors/options after commit. A missing temporary-grant revocation is an installation failure and cannot be called least privilege.

## Permission matrix

| Principal | Ledger read | Fixed seed | Raise stop | Direct ledger DML/claims/checkpoints | Issue/release | Application writes | Owner/CREATE |
|---|---|---|---|---|---|---|---|
| migration principal | Installation/admin boundary | Admin may retain role-administration power | Admin boundary | Installation only under explicit mandate | No operational issuance | No application operation in this scope | Temporary owner SET/INHERIT and schema CREATE revoked; bootstrap ADMIN-only residual documented |
| ingestion_worker_login -> ingestion_worker | Both tables | DENY | Allow bounded reason, preserving consumed stop | DENY | DENY | DENY effective privileges | DENY |
| ingestion_storage_login -> ingestion_storage_operator | Both tables | Fixed3 only | DENY | DENY | DENY | DENY effective privileges | DENY |
| ingestion_storage_owner | FORCE RLS owner policy | Definer only | Definer only | Definer implementation only | No API | No grants | NOLOGIN, no runtime members, no schema CREATE after install |
| ingestion_authority_issuer / ingestion_barrier_releaser | None | None | None | None | No API | None | NOLOGIN, no members |

`activate.sql` checks login flags, exactly one intended membership with the exact options, no owner/issuer/releaser membership, no persistent schema CREATE, no effective non-ledger table/column access and no unreviewed callable non-system SECURITY DEFINER functions. PUBLIC grants are additive: there is no per-login DENY override. Existing ambient access causes a stop. Do not revoke unrelated PUBLIC/application permissions to make the gate pass. System catalog visibility, built-in functions and baseline PUBLIC database TEMP privileges are not claimed removed; no temporary/session-state mechanism is used. This is storage-stage SQL isolation, not a general SQL sandbox for untrusted agents.

## Secure owner-local credential mapping

After production approval and successful installation, owner performs ONE supervised local handoff using `verification.ingestion_storage.credential_mapping`. No browser session is used. Trusted owner Linux/WSL workstation (the helper refuses other platforms), existing authenticated GitHub CLI identity with environment-secret write permission, existing migration URL from the owner's trusted credential store, no shell tracing/transcript/debugger/crash dumps/terminal recording. Do not obtain passwords/tokens through chat, command-line arguments, clipboard history, files, repository, CI artifacts or logs. If existing access is unavailable, stop; no new broad token/credential fallback.

First confirm provider-side password/SCRAM statement and parameter redaction across server logs, audit extensions and external platform capture. The helper requires `--provider-password-redaction-attested`; it does NOT disable logging or silently assume that password-bearing SQL is redacted. Provider-supported psql \password protects cleartext by client-side SCRAM encryption; SCRAM verifier privacy still requires the provider audit assessment. If that cannot be attested, credential installation remains blocked and the exact provider-supported secure password operation must be resolved before running this helper. No unsupported management endpoint is invented.

Following approval, exact owner command from the reviewed clean checkout:

```sh
python -m verification.ingestion_storage.credential_mapping --authority AUTHORISE_RESTRICTED_INGESTION_CREDENTIAL_MAPPING_ONCE_20261016 --provider-password-redaction-attested
```

That future authority is a proposed execution binding, not granted by this preparation instruction. The existing migration URL is read once through a hidden local prompt. After that prompt, a90-second POSIX deadline includes DNS/DB/secret operations; memory is256MiB, core dumps and file creation disabled, each CLI call20s with GitHub hostname fixed and interactive/debug fallback disabled. Successful exit requires a closed direct connection and no new socket descriptors/live children; failed/aborted execution has no CLOSED claim and requires reconciliation. A later approved execution supervisor must enforce a2-second kill/owned-process cleanup grace if signal cleanup itself stalls. The helper verifies the approved route and CA, generates independent48-byte CSPRNG passwords in memory, sets client-generated SCRAM verifiers in separate bounded transactions while logins remain NOLOGIN, and uses official `gh secret set` with plaintext URL only on stdin, stdout/stderr suppressed. CLI repository includes github.com explicitly. GitHub CLI encrypts environment secrets before upload. It never replaces DATABASE_URL.

| SQL login/current_user | Shared-pooler connection username | Protected environment secret |
|---|---|---|
| ingestion_worker_login | ingestion_worker_login.zcikcfgpblzuzpanpdqd | stage4-production-canary / INGESTION_WORKER_DATABASE_URL |
| ingestion_storage_login | ingestion_storage_login.zcikcfgpblzuzpanpdqd | stage4-production-canary / INGESTION_STORAGE_DATABASE_URL |

Same hostname/port/database and CA, no TLS parameters in the stored URL. Password expiry24h, connection limit1 per login; no automatic rotation. The helper emits only role/secret names, expiry and mapped/NOLOGIN receipts. Python strings cannot be guaranteed erased from process memory; exit promptly and keep core/crash dumps disabled. Expiry/NOLOGIN does not terminate an already-authenticated session. No automatic consumer receives these credentials. Preserve current protected reviewer and master restrictions; no environment bypass or wider sharing.

The helper and GitHub mapping are not an atomic distributed transaction. Do not retry a timeout automatically. A lost DB commit acknowledgement stops before upload/activation/further DB mutations. A failed or ambiguous secret upload stops before the next role. Logins stay NOLOGIN. Owner inspects only secret metadata, exact role flags and known transaction state, preserves evidence and returns for bounded recovery. Do not export secret values, print verifier hashes, blindly reset passwords, compensate with deletion or activate from an incomplete receipt. Both mappings and a sole-controller/no-active-consumer check are required before `activate.sql`.

## Proposed finite production procedure and ceilings

No production execution is approved by this document. No new live workflow is registered. A later approved storage controller must map only the two named environment secrets, bind exact revision/SQL/manifest/CA hashes, use the existing global production concurrency control, respect protected approval and preserve durable output. Do not reuse either consumed catalogue workflow/run or activate the legacy ingestion command.

Proposed separate provisioning/credential allowance: one installation transaction, one mapping invocation (at most2 credential transactions and2 secret PUTs), one activation transaction; <=4 database connections in this phase, <=90 supervised seconds after owner secure input, each connect3s, each SQL10s/lock3s, each secret CLI20s,256MiB worker RSS,32KiB credential-free receipt. No retries/budget borrowing. Owner time obtaining existing access/attesting redaction is outside execution and must finish before the controller timer starts. Install alone retains30s outer cap. Any ownership, logging, effective-privilege, accounting or cleanup failure stops before activation. These are finite NEW permission-operation ceilings requiring concrete approval, not reuse of the consumed preflight allowance.

Finite combined proposal across provisioning, storage and revocation: <=240 supervised seconds, <=13 connection attempts, one owned DB connection/process at a time, <=256MiB worker RSS and <=2MiB TOTAL exported evidence including all receipts. No parallel phases or allowance borrowing. No owner interactive wait inside an execution timer.

Storage acceptance retains its reviewed ceilings: exactly3 items +1 control,0 attempts/grants,<=32KiB serialized rows,<=1MiB combined physical relations,<=2MiB exported evidence,<=8 connection attempts after install,<=40 total SQL commands/driver statements,<=30 active DB seconds,<=120 supervised seconds,<=256MiB RSS. Use sequential connections, no retries and no pool/resource stacking. No production Application SELECT/DML; inspect permissions through catalogues only. Installation/setup and storage are separately checkpointed; report their combined actual totals and do not label a provisioning failure as a storage PASS.

Fixed storage command budget (40, no hidden SQLAlchemy initialization: direct psycopg/autocommit):
- Two fixed seed transactions: BEGIN +3 SET LOCAL + seed() + COMMIT =12 commands. Confirm both return3; second insert is a no-op.
- One worker stop transaction: BEGIN +3 SET LOCAL + raise_stop('STORAGE_TEST_STOP') + COMMIT =6 commands. Original global stop must survive.
- Two new-connection readbacks using `storage-readback.sql`:6 commands each =12. Compare exact3 manifest rows, control stop/grants/manual_stop, attempts0 and both size caps. JSON field structural equality, no identity creation or evidence completion inference.
- Eight denied commands, autocommit implicit rollback: worker seed, control UPDATE, attempt INSERT, SET ROLE owner/issuer/releaser; operator stop and direct ledger UPDATE =8. SQLSTATE42501 required. No actual application DML attempted.
- One identity/role/membership/effective-permission catalogue SELECT per real login =2. Require SQL current_user=session_user be the exact intended login; no SET ROLE substitute. All other role flags and object grants must match the matrix.

Total40. Do not run old11-command readback twice in addition. Connect budgets include failed attempts; disposal/close/end-of-process and socket/child census require positive evidence. No source/B2 writer connections. On any denied test unexpectedly succeeding, stop and preserve state; do not try more commands or seed further. The larger offline denial matrix tests DELETE/TRUNCATE/CREATE/RLS changes and application UPDATE in disposable data only.

Finish with the separately approved non-destructive `revoke.sql` under migration principal and revoke both protected secrets using `gh secret delete <exact-name> --repo github.com/maxrose26/PropertyAIgent --env stage4-production-canary` (owner action, no values). This teardown has its own proposed cap:1 transaction,<=1 DB connection,<=10 SQL commands,<=10 DB-active seconds/30 supervised seconds,2 secret deletions, no data deletion. Include these totals in combined resource reporting. No automatic deletion of queue/audit rows. If continued read access is desired instead, that is a different operational decision; default is disabled after this storage test.

## Failure recovery and non-destructive rollback

First-install SQL is transactional and refuses existing names. A known pre-COMMIT failure rolls back roles, temporary grants, tables/functions/control together. A disconnect around COMMIT is UNCERTAIN: stop all mutations, reconnect read-only only under a finite reconciliation authority, compare exact names/definitions/owners/ACLs/RLS/membership grantors/control, then decide. Never blindly rerun install.sql or drop/create names. This is a fresh installation reconciliation, not permission to repeat historical source observations.

Known committed installation can remain parked with both NOLOGIN roles and password NULL before mapping. A partially mapped state stays NOLOGIN; preserve phase receipts without secrets. Unknown activation leaves login state uncertain and blocks seeding until read-only flag/membership reconciliation. Unknown seed commit stops writes; reconcile exact four rows/attempts/grants through the reviewed readback before deciding any next action. No automatic reseed beyond the reviewed second duplicate check, password replacement or deletion.

`revoke.sql` preserves all populated ledger rows, provenance, control stop and attempts. Run only after known state/authority; NOLOGIN/password NULL plus exact capability membership revocation. First close owned clients. If remaining backend sessions exist, NOLOGIN alone is insufficient: inspect exact two login identities and recorded PIDs. Do not assume migration principal can terminate them; return a specific provider access blocker if it cannot. Never mass-terminate unrelated sessions or drop roles/tables. Record uncertain revocation/secret deletion outcomes for reconciliation.

All accepted IDs1504–1508, historical observations, seals, consumed authorities, parent holds and Salford stop remain unchanged. Pipeline readiness, storage acceptance, backlog completion and operational activation are separate. Idox integration and operational claim/checkpoint effects remain outstanding and are not implemented here.

## Validation and primary references

Initial hosted PostgreSQL17 rehearsal at candidate6893f8fabc8abea0df178a168479e4511dc49465, run38911317012/job117007583139 PASS. It reproduced old migration failure under non-superuser CREATEROLE, rolled back an injected mid-install crash, installed under NOSUPERUSER/NOCREATEDB/NOBYPASSRLS migration privileges, authenticated real restricted logins, verified exact rows/no-op reseed/stop preservation, denied unsafe commands, removed temporary owner SET/INHERIT/CREATE, retained explicit ADMIN-only creator limitation, revoked access without deleting four rows and preserved disposable protected-record fixtures. Follow-up SQL candidate fd7e040b25bfb0fe23e15c5b58085ad51b868615: run38911973571/job117009805301 PASS with the final install/activate/revoke SQL. 30 real restricted-login denials SQLSTATE42501; two real logins;4 retained rows,0 attempts;4595 serialized bytes/49152 physical bytes; effective PUBLIC DML and unreviewed SECURITY DEFINER activation failures tested. Original artifact12050164462 SHA2561931a992e530a628531ebebc0cedfb322e4b521e1f867e894b26d972d96f68d6 and extracted JUnit are retained under validation/. Four credential-helper tests pass locally; final hosted validation additionally exercises the real SCRAM helper with the GitHub CLI boundary mocked (no external secret transmission). Final execution receipt is reconciled separately before approval.

Primary guidance checked16October2026:
- https://www.postgresql.org/docs/17/role-attributes.html — creator ADMIN-only grant and non-superuser limitations.
- https://www.postgresql.org/docs/17/sql-altertable.html — new owner SET ROLE and schema CREATE requirements.
- https://www.postgresql.org/docs/17/sql-revoke.html — grantor-specific revocation and additive PUBLIC privileges.
- https://supabase.com/docs/guides/database/connecting-to-postgres — custom-role shared-pooler username [ROLE].[PROJECT_REF], same approved session endpoint.
- https://supabase.com/docs/guides/database/postgres/roles — provider-supported SQL custom roles.
- https://www.postgresql.org/docs/17/app-psql.html — client-encrypted password setting, cleartext handling.
- https://cli.github.com/manual/gh_secret_set and GitHub REST environment-secrets guidance — stdin and local encryption.

Decisions for one grouped REVIEW: exact SQL/role matrix and narrowed operator; acceptance of existing migration-administrator ADMIN-only residual; provider audit/redaction attestation or concrete secure-provider blocker; owner-local protected mapping; finite permission-operation/storage/revocation ceilings and later exact controller binding. No production role/credential/permission action before approval of this final package.
