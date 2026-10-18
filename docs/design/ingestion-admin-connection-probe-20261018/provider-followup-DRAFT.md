# DRAFT — sanitised provider follow-up for SU-511198 (NOT SUBMITTED; for Product Owner review only)

Nothing in this file has been sent. Values in `[brackets]` must be filled by the owner from owner-held evidence; they are deliberately not guessed here. No credential, connection URL, password, token or verifier is included or requested.

Subject: Follow-up to SU-511198 — session-mode pooler rejects a custom-role connection; request for server-side rejection reason

Context (facts we can state):
- Project ref `zcikcfgpblzuzpanpdqd`; session-mode pooler host `aws-0-eu-west-2.pooler.supabase.com`, port 5432, database `postgres`, TLS verify-full against the Supabase production CA, IPv4 address pinned.
- Custom (non-`postgres`) application roles are addressed with the project-suffixed username form `<role>.<project-ref>`.
- Our client attempted a connection as a custom restricted role at [UTC timestamp window from owner evidence] and received a driver-level `OperationalError` with no SQLSTATE and no server message we retained.
- We have since added client-side stage attribution so preparation failures and connection failures are told apart. We have **not** yet established whether the failure was client-side, pooler-side or database-side, and we are not asserting a cause.

Questions (please answer from server-side logs, which we cannot see):
1. For the connection attempt(s) from [source IP, owner-supplied] at [timestamp window], what rejection or termination reason did the pooler record for the custom-role username `[role].zcikcfgpblzuzpanpdqd`?
2. Does the session-mode pooler accept startup `options` (specifically `-c statement_timeout`, `-c lock_timeout`, `-c idle_in_transaction_session_timeout`) from custom-role clients? If startup parameters are filtered or rejected, is that logged, and what does the client observe?
3. Is there any difference in how the pooler authenticates the built-in `postgres.<ref>` identity versus custom roles created with `CREATE ROLE ... LOGIN` and a password set by `ALTER ROLE` (for example SCRAM verifier propagation delay or a per-tenant role cache)? If so, what is the expected propagation time?
4. Are there per-role or per-tenant connection limits in session mode that a short burst of two roles could hit?

What we will do next (for transparency): a single administrative-identity connection probe with fixed budgets (one attempt, one read-only statement), without any role or credential changes. We will share its sanitised outcome if it is relevant to your investigation.

Please do not ask us to send a connection string or password; we will not provide one in a ticket.
