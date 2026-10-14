# TO REVIEW — STAGE 4 ADMISSION RUN 38655110927 FAILURE ANALYSIS

Master Stage 4: OPEN. Current gate: committee-discovered application admission. This is a bounded execution checkpoint, not an architecture or discovery NO-GO.

## Consumed execution and artifact

Run: https://github.com/maxrose26/PropertyAIgent/actions/runs/38655110927

Run number 1 / attempt 1. Revision `e1e98704913b572e46822f1fbe2b5a273f47bbd9`. Workflow `.github/workflows/stage4-material-cohort-admission-once.yml`. Admission job `116162911565` failed. Revision guard and dependency installation passed; artifact upload and ordinary job cleanup completed. Execution authority is CONSUMED. No retry, attempt 2, new dispatch or resume occurred.

Artifact `11936366419`, 406-byte ZIP, was downloaded and validated against both the supplied and GitHub-reported SHA-256:
`2ef32797d7990612f045e83fdb9a8c6ac332f76335f0ca0b8285f5f4f421cadc`

Exactly one bounded result.json. JSON SHA-256:
`896a57ae20e7e6dd1933c959d276c797b7b45df60ec6695be788061ab374edc3`

The artifact reconciles run/revision/frozen manifest `91be2de17f9e7fd0f4e62c7e95b611ef91bb1484673191f489f928b9879e5981`, qualification run 38652271830, empty results, no watermark advancement, no site/opportunity creation and zero model calls. Its generic `STOP_UNCERTAIN_OR_FAILED_NO_RETRY` label does not itself establish an uncertain transaction.

## Exact failure and causal proof

The traceback at 2026-10-14 23:37:47 UTC shows:

`material_admission.main`, line 117:
`engine = checked_engine(os.environ['COMMITTEE_DATABASE_URL'])`

`committee_exact.checked_engine`, line 79:
`raise ValueError('existing production route only')`

This is a local parsed-URL allowlist rejection, NOT a database connection, authentication, SQL, source retrieval, B2 or commit failure. URL parsing completed and the compound guard rejected it before the subsequent `create_engine` call. At least one of these requirements did not match:

- driver exactly `postgresql+psycopg`;
- host exactly `aws-0-eu-west-2.pooler.supabase.com`;
- explicit port exactly `5432`;
- database exactly `postgres`;
- username exactly `postgres.zcikcfgpblzuzpanpdqd`;
- no URL query parameters.

The log does not identify which requirement failed. The actual secret value/components were not inspected, copied or exposed. The non-empty-secret shell check passed because execution reached the Python guard; that proves presence, not correctness or authentication.

Exact-revision source files were retrieved from GitHub and matched inspected local SHA-256 values:

`committee_exact.py`: `c6321cc45beff660845fa81c4c6063089c5cf7eacfc50ce7f89fa3f1d6520da3`

`material_admission.py`: `97b346621e57262b4541376f0004077524110682a765fba504b3ed7fb49851ce`

`main` initializes engine=None, calls checked_engine before execute, and writes the audit in finally. The rejected branch raises before create_engine; execute/current_identity/shared admission/source retrieval/B2 are never entered. Relevant imports define model metadata and functions; they do not call a production engine factory. Therefore zero database access follows from exact control flow plus traceback, not from duration, workflow failure or empty results alone.

The Node.js deprecation warnings occur in action infrastructure and are not causal.

## Per-candidate production reconciliation

| Candidate | Admission/identity check | Source/B2 | Transaction/effects |
|---|---|---|---|
| Manchester 143413/FO/2025 | NOT_ATTEMPTED | NOT_ATTEMPTED | No transaction; no application created by this run |
| Manchester 145583/FO/2026 | NOT_ATTEMPTED | NOT_ATTEMPTED | No transaction; no application created by this run |
| Tameside 26/00396/FUL | NOT_ATTEMPTED | NOT_ATTEMPTED | No transaction; no application created by this run |

For this run: zero database engines created, connections, production reads, writes, application/site/opportunity creation, B2 activity, commits or rollbacks. Transaction state is NOT_STARTED, certain. There is no UNKNOWN_COMMIT.

No production readback was required or performed. The failure occurred before any possible production access. Whether another actor has since created one of these references is not assessed; these conclusions concern this run's effects only. Any future admission must perform its automatic exact duplicate/absence checks again.

## Resources and cleanup

No planning-source worker/browser/context/process was started. Source requests and source response bytes are zero by call-path evidence. Per-source worker timing/memory/accounting and cleanup are NOT_STARTED, not invented WITHIN_LIMITS/CLOSED results. No database engine existed to dispose; the parent Python process exited with code 1 and GitHub completed ordinary post-job/orphan cleanup. Dependency-installation network/process activity is separate from planning-source acquisition; no claim of zero job-wide network activity is made.

## Code compatibility gap versus configuration blocker

A concrete compatibility gap is independently reproducible: checked_engine calls make_url on the raw URL without the existing pure `_normalize_database_url` helper and requires an explicit port. The previously accepted `oldham_production.production_engine` uses that helper and interprets an omitted port as 5432 while preserving its exact route allowlist.

A synthetic offline check with create_engine replaced by a sentinel demonstrated:

| Synthetic URL form | Current guard | Engine-factory calls |
|---|---|---:|
| Explicit postgresql+psycopg, exact route and port | Reaches mocked factory | 1 |
| Plain postgresql, same destination | Rejected | 0 |
| Legacy postgres, same destination | Rejected | 0 |
| Native driver, omitted default port | Rejected | 0 |

All inputs used a synthetic password. No real credential, database connection or source request was used. The existing normalizer maps the two plain/legacy schemes to the native driver without changing their destinations.

This confirms an implementation/test-coverage gap, but does NOT prove that it caused this execution. A different host, username, database, explicit port or query parameter could also explain the observed rejection. Classification: PRECONNECTION_ROUTE_MISMATCH; exact mismatch category UNKNOWN. No secret replacement is justified.

The earlier offline/native PostgreSQL passes tested shared transactions and caller behavior with supplied disposable engines; they did not establish compatibility of the actual production secret with this new raw-URL guard. That prerequisite was overstated in the preparation handoff.

## Smallest corrective proposal — not implemented

1. Reuse the existing pure URL normalizer, rather than requiring owner edits to a valid dashboard-format secret.
2. Apply the previously accepted default-port interpretation if REVIEW confirms this is the same authorised route.
3. Preserve exact host/project username/database/port/query restrictions, native driver, TLS, transaction limits and B2 semantics. Do not admit an alternative destination or relax evidence rules.
4. Before engine creation, retain a bounded phase/result and mismatch-category code such as DRIVER_MISMATCH, HOST_MISMATCH, PORT_MISMATCH, DATABASE_MISMATCH, USERNAME_MISMATCH or QUERY_FORBIDDEN. Never export values, a URL, password, query text or raw parser exception.
5. Record REJECTED_BEFORE_ENGINE_CREATION explicitly so a generic failure cannot suggest an uncertain transaction.

Focused regression protection should prove accepted equivalent URL forms project to the same exact route; wrong destinations/users/databases/ports/query forms still fail before the factory; rejection audit contains only whitelisted codes and no credential values; execute/source/admission/B2 remain uncalled on preconnection rejection. Reuse the existing tests and native PostgreSQL acceptance; no new generic safety or diagnostic programme.

No production code, workflow, secret, persistence or evidence semantics were changed in this inspection. Only minimized failure evidence and this analysis were added.

## Independent review and precise decision

Independent review confirmed the no-effects reasoning, the known normalization/default-port incompatibilities and the unresolved actual mismatch category. It supports reuse of the existing pure normalizer with unchanged destination guards and privacy-safe category-only auditing.

Recommendation: approve only the bounded offline adapter/audit correction and focused validation next. Do not approve production re-execution on the assumption that the scheme/port gap caused this run. First qualify the actual route-mismatch category through an explicitly reviewed, secret-safe preconnection path; this must not connect to the database or expose/replace the secret.

Any new production execution requires exact REVIEW approval of the corrected revision, frozen cohort, workflow identity, single-use authority and pre-dispatch evidence. The consumed workflow/run must not be rerun or resumed. No new dispatch is prepared or authorised by this report.

The three-record cohort and its successful source qualification remain preserved. Bolton and Salford 1664 remain withheld; Salford 1506 remains withheld; Stockport's accepted supplementary limitation and Trafford deferral are unchanged. No new source investigation, broader SQL, compensating write, AI/model execution, scheduling or prospective acceptance occurred. Master Stage 4 remains OPEN.
