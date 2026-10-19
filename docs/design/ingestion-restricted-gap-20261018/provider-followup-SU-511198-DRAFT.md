# DRAFT — sanitised update for existing ticket SU-511198 (NOT SENT)

Not sent. Existing support access in this environment only offers a *new* request form; updating SU-511198 is an email-thread reply and no email capability was available. For the Product Owner to send as a reply on the existing ticket. Contains no secrets, URLs, passwords, tokens or raw logs. Bracketed values must come from owner-held evidence.

Subject: Re: SU-511198 — administrative role connects through the pooler; custom-role authentication still failing

Findings (sanitised):
- Project `zcikcfgpblzuzpanpdqd`, session-mode pooler `aws-0-eu-west-2.pooler.supabase.com:5432`, TLS verify-full, pinned IPv4. The project's `postgres.<ref>` administrative role **connects successfully through the pooler with our startup options** (`-c statement_timeout`, `-c lock_timeout`, `-c idle_in_transaction_session_timeout`) on [date/time UTC].
- Earlier, a custom application role (`<role>.<ref>`) failed on the first connection at [UTC window] with a client-side `OperationalError` that carried no SQLSTATE (recorded connection-active time ≈0.6 s). That same role, and a sibling custom role, had authenticated through this same route on [earlier date] without startup options, when the role names were new.
- Lifecycle of those custom roles at rest: `NOLOGIN`, password NULL, `CONNECTION LIMIT 1`. At use: password set (SCRAM-SHA-256) with `VALID UNTIL`, then `LOGIN`, then connect within a few seconds.
- We have not established the cause and are not asserting one.

Questions (from server-side logs we cannot see):
1. What did the pooler record for the custom-role connection at [UTC window] from [source IP]?
2. Does the pooler cache credential lookups per (tenant, user)? For how long, and does that include the NULL-password/NOLOGIN state, so that a password set and `LOGIN` seconds earlier can still be rejected?
3. Are startup `options` handled differently for custom roles than for the `postgres` role? If filtered or rejected, how is that surfaced to the client?
4. Does `CONNECTION LIMIT 1` on a login role interact with session-mode pooling (for example a pre-opened or second backend connection)?
5. Anything specific you require for custom-role authentication through the pooler beyond `CREATE ROLE … LOGIN PASSWORD …` and the `<role>.<project-ref>` username?

Please do not ask us for a connection string or password.
