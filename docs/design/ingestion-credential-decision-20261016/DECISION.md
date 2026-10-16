# One bounded credential-provisioning decision

Stage4 OPEN. REVIEW ONLY. Production master remains PR118 integration a3a698beb0542579042bbcc48e8cf7a66f13514f/tree66844ee85ca97d74f13b5b17aec034d67a040a3c. Accepted evidence fc89a21646d64bd89f47e1e8f60513078e88e1a8 and all historical authorities remain unchanged. No production connection, SQL, credential generation, protected-secret operation, provisioning or storage test in this work. The 240-second/13-connection authority is unused.

## Recommendation

Prefer the existing minimal owner-local client-generated SCRAM plus in-memory protected GitHub-secret mapping, conditional on a narrow provider confirmation of the actual capture path. It preserves the fixed roles, NOLOGIN-before-activation, 24-hour expiry, existing migration principal and verify-full route. It is currently NO-GO: the CLI is now explicitly disabled before prompting, network access or mutation, even with the approved authority/acknowledgement flag. Do not execute the old integrated entrypoint while this candidate is under review. A new accepted method/controller binding must restore a bounded entrypoint; this change itself does not activate anything.

No documented alternative was established that both provisions the two fixed custom logins and avoids the identified verifier-in-SQL path. Changing interfaces without that evidence adds work without resolving the risk. No new authentication system, role permissions or password-reset experiment is proposed.

## Supported alternatives compared

| Method | Evidence and scope | Decision |
|---|---|---|
| Existing helper | Generates SCRAM locally; sends ALTER ROLE containing verifier, then URI only on GitHub CLI stdin. Already rehearsed with real logins; provider SQL capture remains unresolved. | Smallest conditional recommendation; blocked pending operation-specific evidence. |
| Native psql `\password role` | PostgreSQL17 explicitly says it encrypts locally and sends ALTER ROLE. Protects cleartext and command history, but retains verifier-bearing SQL. Requires a separate secure handoff of the same password to the protected secret. | Supported custom-role mechanism; no demonstrated verifier-capture improvement over existing helper. |
| Supabase Database Settings / documented project password API | Role guidance identifies dashboard password reset as the postgres password. API PATCH /v1/projects/{ref}/database/password accepts a password with no target-role field. | Wrong scope; would rotate existing administrative access. Rejected. |
| Supabase experimental CLI login-role API | POST /v1/projects/{ref}/cli/login-role takes read_only and returns generated role/password/TTL, with no fixed custom-role name or exact capability configuration. | Does not provide reviewed custom-login contract. Rejected; no call made. |
| A custom-role dashboard/metadata form | A form may hide SQL but documentation inspected does not establish a custom-role password path that redacts/verifiably avoids captured SQL. | Unqualified, not assumed safe or substituted. No internal/undocumented endpoint used. |

## What is known; precisely what is unknown

Accepted production capture38907801607/1/1 proves PostgreSQL17.6, the approved session-pooler route5432, verify-full TLS/CA, SQL identity postgres (NOSUPERUSER/CREATEROLE/CREATEDB/BYPASSRLS), old object/default grants, rollback, reconnection and CLOSED cleanup. It did not record effective logging settings, audit-extension versions or query-statistics configuration. Do not repeat it or infer defaults as project observations.

The earlier concern about all audit capture was too broad. Upstream pgAudit source has password-token redaction for CREATE/ALTER ROLE audit command text. That narrows the issue; it does not prove the installed version or redact PostgreSQL's separate ordinary statement/error messages. The installed audit version/active ROLE/statement settings remain unknown. No claim that an actual secret has leaked.

Relevant unknowns are finite:
1. Effective postgres-session log_statement, log_min_error_statement, log_min_duration_statement, log_min_duration_sample, log_statement_sample_rate and log_transaction_sample_rate. These select ordinary success/error/sample query-text capture. log_duration alone reports duration, not query text.
2. If pgAudit is loaded: installed extension version, pgaudit.log and pgaudit.log_statement, and provider behaviour of its password redaction versus core error/statement output. log_parameter settings alone do not protect an embedded SQL literal. No parameters contain the verifier in the reviewed command.
3. If pg_stat_statements tracks utility commands: its installed version and track/track_utility configuration, and treatment of ALTER ROLE verifier text. Existing role documentation identifies this query-statistics surface, so it is relevant rather than a hypothetical new system.
4. Provider-side redaction, if any, before this project's ordinary PostgreSQL output is retained. Include Supavisor only if its deployed configuration captures SQL payloads; connection-only metadata does not contain this SQL literal. Include a log drain only if actually configured to receive the relevant stream; copying already-redacted output does not create a separate redaction requirement.

No blanket guarantee about hypothetical extensions, unknown third-party tools or every platform subsystem is requested. Provider can resolve the applicable paths from this project's configuration. Missing schema/CONNECT grant options, ambient permissions and owner secret-write capability remain separate later gates, not reasons to broaden this credential decision.

## Single unavoidable owner dependency

Send SUPPORT-QUESTION.txt once through the owner's existing Supabase support channel. It identifies the exact two roles, SQL operation and unresolved capture mechanism. Do not send passwords, hashes/verifiers, tokens, connection URLs or raw log exports. No acknowledgement flag is accepted as proof, and no support message has been sent automatically.

After the reply, review the concrete documented method against the preserved role restrictions. If the existing client-SCRAM method is confirmed, the smallest owner procedure is: (1) obtain acceptance of the evidenced method and exact revised helper/controller; (2) use the trusted Linux/WSL terminal, existing migration credential and existing GitHub owner access, no new token or stronger role; (3) execute one supervised helper with both roles still NOLOGIN, generate independent48-byte values in memory, set verifiers through the confirmed method and transfer each URI directly to its existing protected environment secret; (4) require credential-free receipts for both mappings before separate reviewed activation/storage phases; (5) after the fixed test, apply reviewed NOLOGIN/password-null/membership revocation, close owned sessions and remove only the exact two environment secrets. Preserve all failure/uncertain-commit stops and the original finite ceilings. These are conditional steps, not a runnable approved command today.

Residual risks even after confirmation: migration-principal administrative trust; transient trusted-process memory; two non-atomic systems (DB and GitHub secrets); ambiguous commit/upload outcomes; session survival after NOLOGIN. Existing finite deadlines, no retry, reconciliation and non-destructive teardown remain required. No claim that a new provider interface is safe simply because it is opaque.

## Independent operational-interface progress

app/ingestion/worker_interface.py adds a finite controller-bound claim/checkpoint interface over the existing Ledger, with immutable key/task/contract/revision/subject binding, fixed worker identity/authority, trusted contract validation, bounded receipt and durable item+attempt checkpoint. It delegates atomic eligibility/dependencies/claims/fencing/global stops to existing code. No duplicate queue implementation or source/extraction path.

Workers get no public enqueue/grant/release/recover/intent/effect/finish API. Source/write-intent resolution stays with existing coordinator acceptance contracts. The constructor rejects live authority strings and any backend other than the existing disposable-only Ledger. Private Python attributes are not a security boundary: this is trusted-process API separation, NOT production restricted-login enforcement. Production SQL claim/checkpoint capabilities, atomic binding checks within their database transaction and shared writer effects remain outstanding. No production permissions, schema, consumers or controllers changed.

Focused network-denied validation:47passed, including10 worker-interface cases,6 mapping cases and31 existing ledger cases. Demonstrates one attempt under concurrent duplicate delivery, scoped keys, no authority from binding, durable dual checkpoint, expiry/recovery fencing, task/global blocks, unresolved-write barrier and refusal to resolve effect intents. New valid-TTY/valid-authority test proves the blocked credential CLI cannot prompt or mutate. JUnit retained here. SQLite demonstrates the API path; it does not newly qualify PostgreSQL ACL enforcement or provider behaviour. No previous disposable provisioning suite was manually rerun.

## Primary evidence checked16October2026

- https://supabase.com/docs/guides/database/postgres/roles
- https://www.postgresql.org/docs/17/app-psql.html (password command)
- https://supabase.com/docs/reference/api/v1-update-database-password
- https://supabase.com/docs/reference/api/v1-create-login-role
- https://github.com/pgaudit/pgaudit/blob/main/pgaudit.c (log_audit_event role-password redaction; upstream source, not deployed-version evidence)
- https://www.postgresql.org/docs/17/runtime-config-logging.html
- https://supabase.com/docs/guides/database/postgres/postgres-log-config

No council calls, application/factual operations, production writes, scheduling, deployment or stage advancement. IDs1504–1508, consumed Salford stop and accepted three-item manifest preserved. Preparation candidate requires review; no integration of these changes in this task.
