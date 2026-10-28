# READY TO SEND — reply on the existing ticket SU-511198 (NOT SENT; the Product Owner sends it from the ticket's email thread)

Status: finalised 2026-10-19 from owner-held, reviewed evidence. This is a reply on the existing ticket, not a new request. It contains no secrets, passwords, verifiers, tokens, connection strings or raw logs, and it asks Supabase for none. It supersedes `provider-followup-SU-511198-DRAFT.md` (kept unchanged beside it). The outbound public IPv4 of the test machine is deliberately not included; provide it only if Supabase asks. UTC times are taken from the file times of the owner-held audit directories and are approximate to the minute; the audits themselves carry sequence numbers and intervals, not wall-clock stamps.

---

**Subject:** Re: SU-511198 — rotated custom login roles are rejected on their first pooler connection; administrative role works; please advise the supported provisioning/rotation procedure

Hello,

We are still unable to authenticate our custom login roles through the session-mode pooler after rotating their passwords, and we would like your help identifying the supported procedure and the likely cause.

**1. Environment**
- Project `zcikcfgpblzuzpanpdqd`; session-mode pooler `aws-0-eu-west-2.pooler.supabase.com:5432`, database `postgres`, TLS `verify-full` against the Supabase CA; each run resolves the pooler host once and pins the connection to that single IPv4 address.
- Client: libpq 18 through psycopg 3.3 on Linux, `connect_timeout=3`, no prepared statements.
- Usernames use the pooler routing form `<role>.zcikcfgpblzuzpanpdqd`. The roles involved: `ingestion_worker_login` (worker), `ingestion_effect_login` (effect) and, earlier, `ingestion_storage_login` (storage).

**2. What we observed (UTC, approximate)**
| When | What |
|---|---|
| 2026-10-17 (09:04–18:51) | Two **newly created** login roles, `ingestion_worker_login` and `ingestion_storage_login`, authenticated through this same pooler with no startup options and ran their work. |
| 2026-10-18 (~07:23) | A later run used the **existing** `ingestion_worker_login` with a **freshly rotated password**. Its first connection was rejected: client-side `OperationalError`, no SQLSTATE, about 0.6 s of connection time. |
| 2026-10-18 (~19:56) | The administrative role (`postgres.zcikcfgpblzuzpanpdqd`) connected through the pooler with our startup options and ran a fixed read-only statement. Administrative authentication has succeeded in the observed runs. |
| 2026-10-18 (~22:09) | Four-connection diagnostic using the existing worker role with a freshly rotated password. Entry 1 (no startup options) was rejected 1.6 s after the password was set. Entry 2 (with startup options; 2.2 s after the password was set and 0.6 s after `LOGIN`) **connected** and executed our identity statement, but our check, which merged several comparisons into one result, reported an unexpected identity. Because of that merge **we cannot say whether the role identity, its flags or the startup-option timeouts differed**, and we are not claiming the options were ignored. The remaining entries (`ingestion_effect_login`) did not run. |
| 2026-10-19 (~09:57) | First connection of the existing `ingestion_worker_login`, freshly rotated password, startup options and role-level timeouts: rejected again. |
| 2026-10-19 (~12:12) | After setting the password and enabling `LOGIN` we waited a fixed 30 s. The first connection of the existing `ingestion_worker_login`, 30.1 s after `LOGIN`, 31.4 s after our secret was stored and 32.2 s after the password was set, was rejected again (no SQLSTATE). `ingestion_effect_login` (created on 2026-10-18) was not attempted in that run, and has not connected in any run. |
We have not established the cause and are not asserting one. A delay of about 30 s, startup options and role-level timeouts did not change the outcome for the worker's first connection.

**3. Our credential lifecycle**
1. At rest both restricted logins are `NOLOGIN`, `PASSWORD NULL`, `CONNECTION LIMIT 1`, with **no** capability-role memberships and no sessions.
2. Setup, as the project's administrative role: the reviewed capability-role membership of each login is restored (`INHERIT TRUE, SET FALSE`); then for each login the client generates a SCRAM-SHA-256 verifier locally with libpq (`PQencryptPasswordConn`) from a fresh random password and runs `ALTER ROLE <role> PASSWORD '<scram-verifier>' VALID UNTIL '<timestamp>'`; the same password is stored as a protected secret on our side; then `ALTER ROLE <role> LOGIN`. (In the two most recent runs only: role-level `ALTER ROLE <role> SET statement_timeout / lock_timeout / idle_in_transaction_session_timeout`.)
3. The restricted client connects once with user `<role>.zcikcfgpblzuzpanpdqd` and the generated password.
4. Teardown: `ALTER ROLE <role> NOLOGIN PASSWORD NULL`, capability membership revoked, secrets deleted.
Startup options we send: `-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000`.

**4. Questions**
1. What is the supported procedure to create, or rotate the credentials of, a custom login role so that it can authenticate through the session-mode pooler, and how soon after `ALTER ROLE … PASSWORD` / `LOGIN` is the first connection expected to succeed?
2. Does the pooler cache role or credential lookups (per tenant and user)? For how long, and does that include a previous `NOLOGIN` / `PASSWORD NULL` state, so that a login enabled earlier can still be rejected? Is there a supported way to invalidate or refresh it?
3. Are client-generated SCRAM-SHA-256 verifiers set with `ALTER ROLE … PASSWORD '<verifier>'` supported for pooler authentication, and are startup `options` (`-c …`) honoured, filtered or rejected for custom roles? How is a filtered or rejected option surfaced to the client?
4. Does `CONNECTION LIMIT 1` on a login role interact with session-mode pooling (for example a pre-opened or second backend connection)?
5. What minimal, sanitised diagnostic evidence from you would distinguish the remaining causes? For example, for a given UTC minute, the pooler's authentication decision and reason for `ingestion_worker_login.zcikcfgpblzuzpanpdqd` (user not found, cache hit or miss, SCRAM failure, role not permitted to log in, option rejected), or the upstream backend log line for that attempt. Any additional live diagnostic would require separate approval.

Please do not ask for a connection string, password or verifier; none will be sent. We can provide further sanitised timing on request.

Thank you,
Max Rose
