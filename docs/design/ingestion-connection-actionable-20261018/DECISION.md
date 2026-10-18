# Stage 4: actionable connection diagnostics and evidence-based failure closure

## Decision
Offline correction complete; draft PR #129. NO-GO for capture or live retry.
Final candidate: 4f4ef89edc83a549fc16e0c43986b9ca30539ecd
Tree: 724adb7104fb9ce4a77f6118b35c75b32ca08525
Base remains integrated b9e6bd639ad1f1a472c35f339b70f8f524c08ac4.
No merge, production access, credential/permission operation, new registration, grant, exception, source call or scheduling was performed.
Accepted evidence 3d5d852748af9129a24d273eb14bdf1fb72192d2 and consumed authority remain unchanged.

## What the offline trace establishes
The accepted storage controller production_transport passes the custom password directly to Psycopg.
The operational Owner.map_and_activate generates an independent secrets.token_urlsafe(48) value per exact role, uses it to create the SCRAM verifier, passes it through the exact restricted_url factory to protected mapping, and keeps the same URL for runtime_principal/DatabaseBudget. No protected secret is fetched back for runtime use.
Synthetic tests compare generated password, verifier input, mapped URL and native kwargs. Both exact roles pass; reserved punctuation, whitespace, Unicode and literal percent sequences survive exactly once through encoding/parsing.
Native kwargs agree with the accepted storage transport for host, selected hostaddr, port, database, routing username, password, verify-full/root CA, connect timeout, prepare threshold and initial autocommit.
Operational-only differences remain deliberate: accounted Connection/Cursor subclasses, strict restricted-role/server-setting check, three startup timeout settings, SQLAlchemy one-connection pools and worker AUTOCOMMIT/effect READ COMMITTED.
The same startup options are also used by the successful migration connection. This is not proof that the managed pooler accepts every custom-role startup/authentication combination.
No password-encoding, routing-suffix or TLS-parameter defect was established. No accepted production record was refetched or changed.

## Defects established and corrected offline
1. The old failure handler assigned UNCERTAIN unconditionally and omitted the success-path final socket/process check. A shared closure method now separately reports access teardown, administrative/runtime connection closure, native memory/process closure and derived overall cleanup. Historical results are not reclassified.
2. A real Psycopg timeout through the actual DatabaseBudget SQLAlchemy factory retained a native socket while its exception traceback held the suspended connection generator. Discard the retained native traceback/context after recording fixed observations; still require positive FinishedPGconn or no-new-owned-socket evidence. This fixture finding does not identify the historical production failure.
3. On a kernel omitting task/TID/children, the old resource inspector silently treated a missing file as zero children. It now reuses the existing supervisor PPID-graph helper with root start-identity validation. A live child and socketpair both prevent closure; inspection failure remains uncertain.
4. A diagnostic reserve could return before checking native memory. The guard now checks kernel memory before the diagnostic branch and rejects checked operations after native group closure. A reporting failure cannot open another DB/gh operation under only the outer aggregate ceiling.
5. A cleanly closed failed execution still exits nonzero and reports STOP_RECONCILE_NO_RETRY. Physical closure is not successful route qualification.
Outer systemd scope disappearance remains explicitly separate and cannot be proved by a controller before it exits.

## Fixed-code diagnostic contract
Use native structured SQLSTATE first. Where unavailable, inspect only bounded native Psycopg message text locally against narrow fixed patterns; export no matched text, username/password, URL, arbitrary message or traceback.
Known codes cover authentication rejection, authorization rejection, routing identity rejection, permission denial, connection capacity, server-not-ready, missing database, cancellation, connection failure, TLS hostname mismatch, TLS chain rejection, missing/unreadable CA, connection timeout/refusal and DNS lookup failure.
Reported provider/libpq wording is an observation, not an independently established root cause.
Unrecognised, conflicting-pattern, excessive-length and non-native text stays UNKNOWN. underlying_cause remains UNDETERMINED.
Message export remains false.

## Validation and scope limits
72 focused tests: zero failures/errors/skips, 5.89 seconds locally; three existing JUnit-format warnings only.
JUnit SHA256: 8dde193fcb3caf83c957866ae222a8274d436dfb2579e416297429d528824888.
Tests include actual Psycopg/libpq and SQLAlchemy factory calls against bounded loopback PostgreSQL-wire fixtures:
- Authentication rejection, routing rejection, permission rejection, timeout, unknown text.
- verify-full rejects wrong hostname and untrusted certificate.
- Each failure consumes exactly one attempt, executes zero restricted statements, closes factory resources, and exports fixed codes only.
Other focused checks: exact two-role synthetic credential/mapping/native-argument comparisons; actual failure handler closed/uncertain-secret cases; live socket and owned-child negatives; missing inspection/native enforcement negatives; real Linux gh fixture against local fake service only.
These wire fixtures are not a PostgreSQL authentication/permission acceptance or Supabase acceptance test. Existing accepted disposable storage/permissions evidence is reused.
Independent reviewer PASS for exact candidate/tree with no remaining substantive finding. Review examined 25 relevant files and final native test receipts; no live review action.
All nine exact-head hosted checks passed. Discovery run 39136152949, run number203/attempt1, is SUCCESS at the final candidate. Hosted focused connection XML:58 tests, zero failures/errors/skips. Complete required wrapper/restricted PostgreSQL17/real-gh XML:45 tests, zero failures/errors/skips. These counts overlap the local72 and must not be summed as unique cases.
Complete hosted artifacts durably archived with verified GitHub-reported ZIP hashes: provisioning artifact12139802417,74774 bytes,SHA2563b798f5a5f062828ccaf13c61b801ea2320ac23eca90e71883a1a3234dc94cfe; offline artifact12139683280,17974 bytes,SHA2565e36b340b93bf457bab8c77b27cf29de6035070484508be8f0aa7e0ec21d9b3b. ZIP member hashes, raw archives, local JUnit and check metadata are preserved alongside this package.

## Remaining uncertainty and whether another diagnostic helps
The production error's original text/structured native state was not retained, so its cause cannot be reconstructed from the accepted audit. Provider-side role routing, cached authentication, startup policy and transport rejection remain possible, not established causes.
A new diagnostic would materially improve information: it would export a fixed native reason code and independently measured closure instead of only OperationalError/DRIVER_CONNECT. It cannot guarantee a non-UNKNOWN result.
No such diagnostic is released by this package, and there is no owner command to run now.

## Smallest next action
Recommend review/integration of this exact offline correction, followed by a separately approved single improved connection-only diagnostic. Unlike the consumed attempt, it can return narrowly classified native reason codes and independently derived closure. Do not release or execute it from this preparation instruction. No installation, queue seeding, policy, grants or pipeline replay is needed.
The prepared sanitised SU-511198 follow-up is a fallback if the improved result is UNKNOWN or identifies provider-side routing/authentication requiring provider evidence. It is not a new mandatory wait for a response. It asks one specific pooler/custom-role/startup-options question; no new ticket or general platform investigation. Support text is prepared only, not submitted.
A support-only action needs no credential generation or teardown: leave disabled access and DATABASE_URL unchanged.

The proposed diagnostic requires a new explicit diagnostic-only allowance and registration.
The diagnostic must use the existing endpoint, same selected-address policy, reviewed CA/verify-full, independent in-memory 48-byte passwords only for exact existing worker/effect roles, reviewed finite memberships and protected mapping, early NOLOGIN/PASSWORD NULL/revoke/readback and exact secret removal. Abort after first failed handshake; no automatic retry; no stronger credentials.
Reuse the prior published ceilings as maxima (admin 240 commands/13 connections/1 MiB/240s; runtime 1040/40/4 MiB/300s; 256 MiB controller, 1.5 GiB aggregate, 2 MiB output; separate 300s hidden input/450s work/25s diagnostics/5s reporting/480s active/790s outer). Actual prior diagnostic was 52 admin commands, 5 admin connections +1 failed runtime attempt and 5.37 active seconds. A smaller production allowance must be reviewed against exact complete preflight/teardown accounting, not guessed. No new allowance is issued here.
Uncertain SQL or secret acknowledgement stops mutations. Complete credential-free audit and explicit post-exit scope readback remain required.

## Preserved position
Production access disabled and verified at the accepted audit; both historical stops, generation 1, retained ledger records/functions and IDs1504–1508 preserved.
All historical UNCERTAIN classifications and missing accounting remain as recorded.
Storage accepted; operational acceptance failed/pending; backlog incomplete; Stage4 OPEN. Capture, B2, source execution, scheduling and stage advancement remain held.

## Primary reference material checked
- Psycopg errors/SQLSTATE diagnostics: https://www.psycopg.org/psycopg3/docs/api/errors.html
- PostgreSQL17 libpq connection controls: https://www.postgresql.org/docs/17/libpq-connect.html
- PostgreSQL libpq verify-full chain/hostname semantics: https://www.postgresql.org/docs/18/libpq-ssl.html
These documents do not establish the cause of the consumed production failure.
