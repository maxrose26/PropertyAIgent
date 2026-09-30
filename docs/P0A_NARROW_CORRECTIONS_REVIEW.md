# P0-A narrow corrections and partial-progress review — 29 September 2026

## Status and decision

Original offline Gate A acceptance remains attached to ff0baa237f809265be50b72247633a7b7a193c1d (351 passed, four matched-baseline failures, no skips, one deselection). This new candidate is **not integration-verified**. No release, migration, activation, live scrape, suspension or production configuration change occurred. No push/PR/merge. The original specification remains byte-identical. The feature branch is preserved; the accompanying response identifies the exact new local commit.

The safe recommendation is a **separately approved, temporary suspension of the old daily cron**, reviewed after the next verification result rather than left indefinite. It still saves useful evidence for early councils, so suspension is not cost-free. However five consecutive recent invocations stop in Manchester, seven later councils get no attempt, and repeated document work ends in OOM. Continuing unchanged is not sustained discovery. The cron has NOT been suspended and old deployed code does not understand P0-A activation switches.

## Local changes and self-review

- `app/db/session.py`: opt-in engine transaction-begin listener applies SET LOCAL statement_timeout=15s, lock_timeout=5s, idle_in_transaction_session_timeout=30s, then verifies all three. Works by intended Core/ORM autobegin lifecycle, including rollback/retry and replacement connections. Failure invalidates the connection and raises; client connect/pool wait 10s, TCP keepalives and independent watchdog remain. No role/global/persistent setting or preparation change. Actual behaviour needs new disposable PostgreSQL execution; static review is not proof.
- `app/pipeline/discovery_owner.py`: rejects known shell identities and all identities outside a reviewed scheduled-instance contract. Both cross-instance owners must carry that contract and match it. Existing PID/start-time and inherited flock checks remain; no age lease/advisory fallback; legacy rows remain visible. Conditional result writes unchanged and their PostgreSQL regression retained.
- **Material unresolved identity assumption:** SCHEDULED_INSTANCE_PATTERN is deliberately None. Production cannot activate this candidate even with ACTIVATED=1. Offline tests substitute a synthetic contract solely to exercise positive admission/recovery. The exact scheduler-generated instance identity format, its distinction from shell/one-off execution, uniqueness/change across real cron runs and termination guarantee must be verified through an independently approved, non-scraping diagnostic in the real cron execution context. Render's shell cannot establish this. No guessed prefix or environment self-attestation is used. Committing the eventual reviewed contract is another candidate change requiring checks. This is a fail-closed implementation, not a completed production admission proof.
- `scripts/migrate_p0a.py`: default read-only preflight; --apply remains unapproved. One PostgreSQL transaction creates only parent_lookup_work (its PK, three FKs, unique reference key and due index) and nullable TEXT scrape_runs.progress. No generic create_all, historical backfill or application UPDATE. Verifies managed column names/types/nullability plus exact P0-A defaults/constraints/index; rejects drift; repeats verify rather than silently trusting IF NOT EXISTS. Existing unrelated column nullability/type drift can cause a deliberate stop; it is not auto-repaired. Non-P0-A historical constraints/defaults are not an exhaustive schema audit. Any such drift discovered must be reviewed before proceeding.
- New `tests/test_p0a_release_corrections.py`: seven disposable PostgreSQL cases covering bounds, ORM/Core rollback/replacement, real 15-second timeout and subsequent query, verification failure, exact migration first/repeat/no UPDATE, rollback after DDL, and drift rejection; seven parameterised/other ownership cases. Existing stale-owner PostgreSQL checks updated to require an explicit synthetic scheduler contract.
- Updated integration runner includes these cases; CI assessor requires the new non-parameterised acceptance cases. WSL launcher now requires the full reviewed candidate SHA as its argument and checks the revised runner blob. Dependency snapshot unchanged. Standard-library scheduler contract checks are additional logic tests, not lifecycle evidence.

Self-review preserved the absolute watchdog/130s parent envelope, typed outcomes, deduplication, continuation and page-lifetime correction; no Stockport retry, AH, egress or broad SQL work. SQLAlchemy transaction-hook semantics, reflected PostgreSQL migration definitions and real cleanup are intentionally left for actual execution rather than asserted from code inspection.

## Actual validation and blocker

Executed here: 14 standard-library tests passed (seven evidence-assessment tests plus seven admission/contract logic tests), zero failures/skips. Python AST syntax checks, shell syntax, YAML parsing and git diff whitespace checks passed. These counts are NOT the affected application suite.

This runtime currently has neither pytest, SQLAlchemy, Psycopg, Playwright nor psutil installed; initdb/pg_ctl are absent. Candidate and matched-baseline collection probes both exit before collection with “No module named pytest”; command outputs are recorded in `docs/reports/p0a-narrow-local-evidence.json`. No blocked installation method was retried. The affected candidate suite, matched-baseline rerun, PostgreSQL, Chromium and real ownership subprocess tests therefore **did not execute**. Their new pass/fail/skip counts are unavailable, not zero and not baseline-equivalent. Original WSL results cannot be assigned to changed code.

Required next operator action: use the already authorised non-production WSL Ubuntu runtime and existing venv/browser/PostgreSQL setup, import the new Git bundle, checkout its exact candidate and run `bash verification/p0a-wsl-run.sh FULL_CANDIDATE_SHA`. The script rejects production variables and .env files, checks clean SHA/runner/dependencies, uses disposable UTF8 PostgreSQL and loopback-only namespace, and runs candidate plus fixed baseline 301a56b3cde781f37e5f5bb0ffaded6537d5ca14. Return the generated results archive. No new installation or production credential is requested. Full candidate details and copyable commands accompany the bundle.

The four historical missing-OPENAI_API_KEY failures and explicitly deselected renderer-RSS test remain visible expectations; new failures/skips must be assessed. Browser/process cleanup and interrupted result recovery remain in the runner, not replaced by mocks. A 15-second timeout test adds runtime; it asserts SQLSTATE57014 and termination under 19 seconds (4-second scheduling margin), then rollback and useful work under re-established bounds.

## Read-only old-cron cohort: 24–29 September

Source: at most 80 ScrapeRun records in this six-day interval (25 actually represented), aggregate application/document timestamps, bounded terminal log windows. Queries were SELECT/metadata reads inside explicit read-only transactions with transient SET LOCAL timeouts, rolled back/closed. No document corpora were exported; no row was corrected. The daily cron is still scheduled 05:00 UTC on deployed 6fd4202f2cc8cbc9cd5a664c3f0a71019933eb5a. Latest run displayed failed, with no active run displayed at the preceding inspection; this is not process visibility into a running scheduler container.

| Day | Completed council records | Interrupted / failed / unattempted |
|---|---|---|
| 24 Sep | Bolton, Bury, Manchester, Oldham, Rochdale, Salford, Tameside, Wigan: success | Stockport failed after3600s with HTTP429 after four attempts; Trafford failed primary coverage with portal-unavailable circuit. Later councils DID run despite these council failures. |
| 25 Sep | Bolton, Bury: success | Manchester left running in DB; Render OOM >2Gi during document extraction. No later seven council records. |
| 26 Sep | Bolton, Bury: success | Same interruption pattern; OOM confirmed in Render logs. |
| 27 Sep | Bolton, Bury: success | Same interruption pattern; OOM confirmed in Render logs. |
| 28 Sep | Bolton, Bury: success | Manchester incomplete; retained parent-stage-before marker and previously observed OOM termination. No later seven council records. |
| 29 Sep | Bolton, Bury: success | Manchester incomplete; Render OOM at06:28:20BST during document extraction. No later seven council records. |

“Running” legacy rows are incomplete records, not proof a process remains alive; no age-based mutation occurred. No overall invocation row exists that fully records deferred councils. The absent later rows plus termination/order evidence support unattempted coverage, not a portal failure attributed to those councils.

### What was actually saved

Committed application rows first seen during the cohort: Bolton3 (two on26Sep, one on29Sep), Bury1 (29Sep), Manchester7 (one each24/25/26Sep, four29Sep). These are all application records, not seven qualified buyer opportunities. Dates align with discovery windows and observed log activity; timestamps alone are not exclusive attribution to one writer.

Committed document rows downloaded during cohort: Bolton8 on26Sep and2 on28Sep, all ten marked text_extracted. No other council had a document row with downloaded_at in this interval. This does not mean no pre-existing document evidence exists or every council had eligible new documents.

Application-level latest successful direct status verification: Bolton28Sep, Bury28Sep, Manchester29Sep, Salford24Sep. Counts of distinct rows whose current status_verified_at lies in cohort:12/4/13/1 respectively; these are not numbers of verification attempts. Others: Oldham18Sep, Rochdale17Sep, Stockport14Sep, Tameside14Sep, Wigan16Sep; Trafford null.

Latest successful document-pass timestamps: Bolton28Sep; Bury14Sep; Manchester19Sep; Salford21Sep. Zero Manchester document-completion or evidence-refresh-completion timestamps in cohort. Related-search timestamps did advance for Bolton/Bury/Manchester on29Sep. Neither last_seen_at nor summary generation was treated as source verification. Old completion timestamps alone do not establish a due backlog or prove all evidence stale; eligibility and coverage still matter.

For Bolton/Bury29Sep, saved tails include final health success with primary_scrape_completed=1, zero parent attempts and zero document applications attempted. Documents/evidence-refresh/allocation/geocode/build-status stages returned; return does NOT imply work occurred in an empty stage. These councils made meaningful primary progress before overall failure.

### Repeated/interrupted work

Render logs for25/26/27/29Sep show the same Manchester application PLA-2026-001341 and documents (Heritage Assessment, Financial Viability Assessment, Wind Microclimate Assessment) downloaded/processed again. Each inspected run subsequently OOM-terminated; no cohort Manchester document rows or completed document-pass timestamp were found. This establishes repeated work without corresponding recorded completion, not which subprocess caused the memory peak. Last sampled RSS below2Gi does not contradict a later unsampled container OOM.

29Sep Manchester had reached related-applications.after, confirm-units.after and documents.before; document-stage completion and later stages are unverified/not reached before termination. 28Sep stopped earlier around missing-parent work. Stage counters are not durably complete in the old implementation, so exact every-stage/per-item totals remain unknown.

Portal failure, timeout and OOM are different: Stockport24Sep exhausted rate-limit retries then council wall timeout; Trafford24Sep reported failed primary coverage/portal circuit while process returned; Manchester25–29Sep prevented overall process completion. A red overall run does not erase earlier commits, and early commits do not mean all ten councils are current.

## Trade-off and review gate

Pausing old discovery loses its current flow of Bolton/Bury and partial Manchester updates; existing evidence and independent downstream jobs remain. Continuing unchanged repeats OOM-prone document work and has not reached seven later councils for five consecutive days. Recommend a temporary suspension under separate explicit approval, with a review after the next WSL result; do not change the schedule automatically or promise P0-A fixes the OOM root cause. This recommendation is driven by both useful-progress and repeated-failure evidence, not the red run label alone.

Next gate: actual WSL results and resolution of the positive scheduler identity contract. Then review exact candidate/migration, externally suspend old discovery and confirm termination, migrate only after approval, deploy inactive, verify runtime/configuration, stop for separate activation review. No smoke test is performed or authorised here. Rollback must retain committed evidence/additive schema and keep old discovery externally suspended.


Read-only log sources (no runs triggered):
- 25 September: https://dashboard.render.com/cron/crn-d9sv93vavr4c73f98rb0/logs?r=2026-09-25%4004%3A59%3A31%7E2026-09-25%4005%3A21%3A28
- 26 September: https://dashboard.render.com/cron/crn-d9sv93vavr4c73f98rb0/logs?r=2026-09-26%4005%3A00%3A01%7E2026-09-26%4005%3A24%3A08
- 27 September: https://dashboard.render.com/cron/crn-d9sv93vavr4c73f98rb0/logs?r=2026-09-27%4004%3A59%3A45%7E2026-09-27%4005%3A22%3A10
- 29 September: https://dashboard.render.com/cron/crn-d9sv93vavr4c73f98rb0/logs?r=2026-09-29%4004%3A59%3A57%7E2026-09-29%4005%3A29%3A20

Implementation reference: PostgreSQL SET LOCAL is transaction-scoped (https://www.postgresql.org/docs/current/sql-set.html); SQLAlchemy exposes a per-connection begin event (https://docs.sqlalchemy.org/en/20/core/events.html). These API references do not replace execution against the pinned environment.
