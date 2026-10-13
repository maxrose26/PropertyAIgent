# Stage 4 reusable batch acceptance

Status: candidate, OFFLINE/DISPOSABLE ONLY. No production workflow registration.

## Reviewed data, not caller input

`batch-manifest.json` SHA256:
`33882abdafca290400e43a18359d1654fa8a9b80f985ea1aabe54c10003fc1c1`.
It freezes the exact census selection (A8/E8/F4), seed, ordered identity and
selection strata. Embedded retained engineering metadata is historical, not
current evidence and is never used as factual B2 input. IDs:
72,468,197,18,381,41,409,37,126,187,45,53,54,56,305,783,289,220,209,499.
Seven councils: Bolton3/Bury2/Oldham3/Stockport3/Tameside3/Trafford3/Wigan3.
All must independently match the existing admitted identity data.
Future reviewed manifests replace data and its digest, not scraper code. The
historical 202 cohort remains an admission/regression source, not the production
refresh denominator. No extension of the 116 admitted routes is made here.

## Architecture and transaction ownership

`batch.run` consumes only frozen data, sequentially, and invokes a supplied
record-worker capability. `batch_supervisor.isolated` supervises a separate
process per record, with 45-second maximum deadline and no inherited environment.
`resource_limits` caps that worker at512MiB/30CPU seconds. The only new CLI is
explicitly disposable PostgreSQL, localhost, synthetic-only. No production CLI.

`batch_transaction.run_transaction` uses scoped sessions and guards. Existing
`refresh` calls existing `verify_application_status`; that B2 is the sole writer.
No factual write, lifecycle insertion or commit exists in the batch adapter.
Fresh retrieval occurs after B2 captures the prior state, never from the frozen
manifest. Exact displayed reference, literal fields, semantic qualification and
NOT_PRESENT/blank distinction reuse accepted checks. Scoped before/expected/after
snapshots reconcile coupled facts, watermark, lifecycle and refresh consequence.
The transaction hook validates consequences before B2 commits. Each application
has an independent transaction; earlier commits survive a later failure.

## Failures and resume

Record-local unavailable/ordinary timeout/rate limit/parser/withholding outcomes
continue only with independently confirmed no-change readback, no expected
commit and closed cleanup. Exhausted budgets, wrong identity, destination escape,
privacy/audit failure, DB failure or uncertain readback STOP. Neither redirects
nor arbitrary alternative sources are followed. Lost acknowledgement can be
classified COMMITTED only when bounded independent readback equals the expected
snapshot; the original B2 PERSISTENCE_FAILED outcome remains visible.

Every manifest row has COMPLETED, SAFELY_REJECTED, NOT_ATTEMPTED, UNCERTAIN or
SAFETY_STOP disposition. A missing worker audit cannot imply no-write. Accounting
is UNKNOWN when an uncertain worker did not produce trustworthy source counters.
No diagnostic exception text/HTML/headers/credential enters an audit.

Resume is explicit: validated prior audit plus its SHA256, same candidate and
manifest, new invocation identity. Completed and safely rejected records are
carried unchanged with parent digest, not rewritten or silently called current.
Only NOT_ATTEMPTED records execute. Any UNCERTAIN or SAFETY_STOP record blocks
resume for REVIEW; no automatic reconciliation or replay. A later refresh of a
safely rejected record requires a new reviewed invocation. No scheduler/retry
controller exists. Existing B2 idempotence prevents duplicate lifecycle events
when a separately authorised refresh sees unchanged evidence.

## Budgets and accounting

20records; sequential; <=40 GET attempts; <=one eligible transient retry/ref;
zero followed redirects;1MB/response;20MB aggregate;150s source;45s/reference;
512MiB/30CPU per worker;300s batch; proposed10min outer production job.
The batch passes remaining request/byte/source-time allowances into each record.
The supervisor passes the remaining batch deadline into each worker. Reaching
the batch deadline before launching a worker leaves it NOT_ATTEMPTED.
No raised limits are used to pass fixtures. Single concurrent DB connection;
connect5s/statement10s/lock8s/idle40s; existing session-pooler production route is
only a future registration requirement, not accessed during acceptance.

Audit16KiB/record,384KiB/batch. Closed schemas reject extra fields. Actual driver
statement events distinguish SELECT/SHOW reads, INSERT/UPDATE/DELETE writes and
other statements; commit/rollback and checkout counts are separate. Counts omit
disposable schema/seed setup. Checkout count is connection reuse, not number of
new physical sockets. Peak concurrent checkout must be1.

## Proposed production registration (NOT created)

Manual workflow_dispatch only, master-bound, exact reviewed SHA/manifest hash,
contents:read, checkout credentials not persisted, exclusive production
concurrency,10min timeout. Only the live step/job may bind
stage4-production-canary and DATABASE_URL. The existing route and sslmode=require
must remain pinned. A new admission wrapper must bind run/attempt/SHA/authority,
fresh requests_session and FRESH_OFFICIAL_SUMMARY provenance to this mechanism;
synthetic disposable CLI must never be used as a production loader. Any resume
needs separate REVIEW-authorised invocation and exact prior artifact digest.
No current workflow exposes the production secret to the batch candidate.

Live success means truthful outcomes, every row accounted, only B2-qualified
writes, prior state preserved on ordinary rejection, reconciled consequences,
valid bounded audit and cleanup, no safety violation. No requirement that all20
write or that a material change occurs. Withholding is not factual coverage.

## Coverage and limitations

1453apps/555sites remain the denominator. The39 admitted policy-due records are
the immediate catch-up target after reliability, not all814 worklist records.
Subtract only successfully verified policy-due members of a future live batch;
do not subtract E/F review cases or safely rejected records as refreshed. No
39catch-up,116rollout or619admission extension is authorised here. Those619
offline-compatible unsupported routes remain the next likely high-leverage
coverage assessment. No new source-by-source investigation is begun.

Refresh cannot discover absent applications. Committee agendas/minutes remain
a later Stage4 discovery/change-signal candidate. Cadence7/60days is provisional;
no scheduling or Stage9 orchestration. Stage4 remains OPEN.

Accepted security limitations remain: postgres-role credential; privileges
uninspected; no proved DB least privilege; environment approval not exact workflow
allowlist; earlier private tool-record exposure accepted/unremediated; TLS and
hostname/certificate verification not independently proved. No remediation,
credential inspection, production connection or council request in this slice.
