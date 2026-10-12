# Oldham production persistence registration — candidate, not execution authority

Stage4 remains OPEN. Accepted dependency is PR63 exact head `379185018bf43882abd20e81a493980da3bdd68a`; its genuine history and all acceptance evidence remain ancestors. No application/B2 implementation is changed by this registration. Only the fixed application42 / Oldham / FUL/355686/26 / TA7382MCIP700 summary can be retrieved and persisted.

## Admission and resource boundary

Manual dispatch only; exact reviewed SHA equals workflow revision and clean checkout; master workflow ref; run1/attempt1; acknowledgement `AUTHORISE_STAGE4_OLDHAM42_B2_PERSISTENCE_ONCE`. No caller reference/URL/council/database input. GitHub-hosted Ubuntu, contents:read, credentials not persisted. One supervised worker, 45 seconds,512MiB address-space,30CPU seconds; job3minutes with20seconds reserved for cleanup/upload. Source2attempts/one transient retry/zero redirects,1MB response/2MB total. Existing transport/parser/registration audit qualification is reused. Source retrieval occurs inside accepted B2 loader ordering. Frozen observations cannot be supplied through the CLI.

## Credential prerequisite — NOT YET ESTABLISHED

The candidate references only an existing Actions `DATABASE_URL` secret, delivered solely to the transaction step as OLDHAM_DATABASE_URL. No OpenAI, Render, Supabase-management, council or browser credentials are supplied. No secret value was inspected or copied. Existing repository evidence does not prove this Actions secret exists or identify its production target/connection mode. The GitHub connector excludes secret metadata endpoints. **This unresolved prerequisite blocks a GO claim and execution authority.** Do not create a new database user or assume availability. Registration requires confirmation that this name is the existing accepted application route and its non-secret target metadata, without a production connection. No production credential is needed in CI.

The candidate accepts PostgreSQL+psycopg Supabase direct/pooler endpoints, database postgres, no URL query overrides. TLS is required. Connect5s/statement10s/lock8s/idle-in-transaction40s. A single-slot/no-overflow pool means one connection at a time (below2maximum); readback uses an independent session after the B2 session closes. Actual production pooler compatibility remains a canary admission outcome, not a rehearsed fact. Missing/unsupported credentials fail before source acquisition.

## B2 authority and transaction

B2 is byte-identical to accepted PR63. No wrapper commit/add/update, schema or migration call exists. Engine guards deny text/DDL, bulk statements and writes outside the existing verify_application_status stack; allowed writes are coupled application42 columns and existing lifecycle inserts for42/status_verification. Session guards constrain application/event selects to42 and cap rows; other tables, deletes, other applications and unrelated dirty columns are denied. Before/after audit uses only coupled facts and at most16 lifecycle records; larger or unsafe existing state fails closed.

A per-session before_commit hook flushes B2 changes, verifies expected lifecycle/signal consequences using accepted material-change semantics and validates the closed audit before commit. Any rejection raises inside B2's rollback boundary. Readback compares exact candidate watermark/facts/events/signal. Source facts may differ from the prior live canary; no refusal is forced. Unchanged production evidence remains unchanged apart from accepted successful-verification semantics.

Lost acknowledgement never retries. Readback classifies COMMITTED when it equals the exact precommit state, NOT_COMMITTED when it equals the before state, otherwise UNKNOWN. Missing/interrupted worker output also remains UNKNOWN, including whether a commit occurred. No timeout is misreported as rollback. Outer interruption may prevent readback/artifact upload; stop and return uncertainty, never automatically repeat.

## Audit/privacy

At most16KiB, closed schemas, bounded allowed fact text and error enums. Includes run/SHA, exact identity/destination, fresh source provenance, retrieval interval/accounting, literal/normalized qualified facts/field states/semantics, before/expected/after coupled state, B2 outcome, materiality, transaction classification and cleanup. No raw source body, proposal/contact details, arbitrary errors/headers or credentials. Worker stdout/stderr are discarded and exception strings never exported. Source audit validation precedes B2 reservation; persistence audit/consequence validation precedes commit. Cleanup/readback failure after a commit is reported honestly and cannot retroactively undo it.

## Acceptance plan

Offline admission, scope, privacy, fresh-only/no-direct-writer checks; nativePG material/unchanged/partial/wrong-reference/redirect, precommit rejection rollback, lost acknowledgement/readback, readback unknown, SQL denial, other-app read restriction and actual native path under worker limits. Existing B2/B2.1/direct/Stage1 regressions retained. CI uses synthetic summary transport and disposablePG only. Hosted results and final candidate identities must be recorded before integration. Zero production workflow runs must be checked after registration, without dispatch.

No production/source query, migration, repair, new user/credential, rollout, scheduling, model call or deployment is authorised. Preserve [skip render] on any separately gated integration. Credential-route metadata and independent review remain open at this checkpoint.
