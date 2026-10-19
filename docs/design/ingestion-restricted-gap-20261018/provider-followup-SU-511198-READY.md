# READY TO SEND — reply on the existing ticket SU-511198 (NOT SENT; the Product Owner sends it from the ticket's email thread)

Status: prepared 2026-10-19 from owner-held audits. This is a reply on the existing ticket, not a new request. It contains no secrets, passwords, verifiers, tokens, connection strings or raw logs, and it asks Supabase for none. It supersedes `provider-followup-SU-511198-DRAFT.md` (kept unchanged beside it).

**Essential information still needed from the owner (nothing secret):** (1) the owner sends the message from the ticket thread; (2) only if Supabase asks to match their logs: the outbound public IPv4 of the test machine (not held in the repository) — do not volunteer anything else. All UTC times below are taken from the file times of the owner-held audit directories and are approximate to the minute; the audits themselves carry sequence numbers and intervals, not wall-clock stamps.

---

**Subject:** Re: SU-511198 — new custom login roles are rejected on their first pooler connection; administrative role works; please advise the supported provisioning/rotation procedure

Hello,

We are still unable to authenticate newly provisioned custom login roles through the session-mode pooler, and we would like your help identifying the supported procedure and the likely cause. Details are sanitised; placeholders are in angle brackets.

**1. Environment**
- Project `<project-ref>`; session-mode pooler `<pooler-host>:5432` (region host from our dashboard), TLS `verify-full` against the Supabase CA, connection pinned to one IPv4 `<pinned-ipv4>`.
- Client: libpq 18 through psycopg 3.3 on Linux, `connect_timeout=3`, no prepared statements.
- Usernames use the pooler routing form `<role>.<project-ref>`; database `postgres`.

**2. What we observed (UTC, approximate)**
| When | What |
|---|---|
| 2026-10-17 (09:04–18:51) | Two custom login roles (`<worker-role>`, `<storage-role>`), newly created, authenticated through this same pooler with no startup options and ran their work. |
| 2026-10-18 (~07:23) | First connection of `<worker-role>` in a later run was rejected: client-side `OperationalError`, no SQLSTATE, ≈0.6 s of connection time. |
| 2026-10-18 (~19:56) | The administrative role (`postgres.<project-ref>`) connected through the pooler **with** our startup options and ran a fixed read-only statement. Administrative connections have worked every time. |
| 2026-10-18 (~22:09) | Four-connection diagnostic: entry 1 (`<worker-role>`, no startup options) rejected at 1.6 s after the password was set; entry 2 (same role, with startup options, 2.2 s after the password was set and 0.6 s after `LOGIN`) **connected** and executed our identity statement, but our check (which merged several comparisons into one result) reported an unexpected identity; because of that merge **we cannot say whether the role identity, its flags or the startup-option timeouts differed**, and we are not claiming the options were ignored. The remaining entries did not run. |
| 2026-10-19 (~09:57) | First connection of `<worker-role>` rejected again (fresh password, startup options, role-level timeouts set). |
| 2026-10-19 (~12:12) | We waited a fixed 30 s after the password and `LOGIN` were committed. The first connection of `<worker-role>`, 30.1 s after `LOGIN`, 31.4 s after the secret was mapped, 32.2 s after the password was set, was rejected again (no SQLSTATE; `<effect-role>` was never attempted). |
We have not established the cause and are not asserting one. A delay of about 30 s, startup options and role-level timeouts did not change the outcome for the first connection.

**3. Our credential lifecycle (placeholders only)**
1. At rest the login roles are `NOLOGIN`, `PASSWORD NULL`, `CONNECTION LIMIT 1`, a member of one capability role (`INHERIT TRUE, SET FALSE`), no sessions.
2. For each use: the client generates a SCRAM-SHA-256 verifier locally with libpq (`PQencryptPasswordConn`) from a fresh random password and runs `ALTER ROLE <role> PASSWORD '<scram-verifier>' VALID UNTIL '<timestamp>'` as the project's administrative role.
3. The same password is stored as a protected secret on our side, then `ALTER ROLE <role> LOGIN`.
4. (Latest runs only) role-level `ALTER ROLE <role> SET statement_timeout / lock_timeout / idle_in_transaction_session_timeout`.
5. The restricted client connects once with user `<role>.<project-ref>` and the generated password.
6. Teardown: `ALTER ROLE <role> NOLOGIN PASSWORD NULL`, capability membership revoked.
Startup options we send: `-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=20000`.

**4. Questions**
1. What is the supported procedure to create, or rotate the credentials of, a custom login role so that it can authenticate through the session-mode pooler, and how soon after `ALTER ROLE … PASSWORD` / `LOGIN` is the first connection expected to succeed?
2. Does the pooler cache role or credential lookups (per tenant and user)? For how long, and does that include a previous `NOLOGIN` / `PASSWORD NULL` state, so that a login enabled earlier can still be rejected? Is there a supported way to invalidate or refresh it?
3. Are client-generated SCRAM-SHA-256 verifiers set with `ALTER ROLE … PASSWORD '<verifier>'` supported for pooler authentication, and are startup `options` (`-c …`) honoured, filtered or rejected for custom roles? How is a filtered or rejected option surfaced to the client?
4. Does `CONNECTION LIMIT 1` on a login role interact with session-mode pooling (for example a pre-opened or second backend connection)?
5. What minimal, sanitised diagnostic evidence from you would distinguish the remaining causes? For example, for a given UTC minute and source IP, the pooler's authentication decision and reason for `<worker-role>.<project-ref>` (user not found, cache hit/miss, SCRAM failure, role not permitted to log in, option rejected), or the upstream backend log line for that attempt. If you want a specific attempt, we can run one at a time you name.

Please do not ask for a connection string, password or verifier; none will be sent. We can provide further sanitised timing on request.

Thank you,
`<owner>`

---

*Preparation notes (not part of the message):* the lifecycle and settings above are those of the reviewed controller; role-level timeouts were added in the last two live runs only. Production access remains disabled, no registration is open and no diagnostic is authorised while this is pending.
