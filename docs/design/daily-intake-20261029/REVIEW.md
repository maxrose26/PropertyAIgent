# Minimal daily intake — INACTIVE, corrections required

Stage 4 OPEN. This is partial authorised implementation, not an executable
production release. No production connection, collection, grant, stop release,
Render change, merge, deployment or activation is authorised here.

## Identity and scope

Base: master 210d09c5bf314c16baf0680df71d4ae8b30b71f4,
tree e71939ef6c07d45fb8f234c665e116f8af4e2f28. Draft PR #206, branch
stage4/minimal-daily-intake-20261029. Final commit/tree are recorded in the PR
handoff (a document cannot contain its own commit identity).

No commits from PR #205 are included. In particular its search_path consistency
correction is NOT silently imported. The accepted correction and unresolved full
provider/recovery/access gate remain separate release dependencies; do not import
standing-access changes merely to obtain that correction.

## Implemented, deliberately without a live bootstrap

- app/ingestion/daily_intake.py connects an injected, externally authorised
  supervised collector to the existing ChainCaller, Coordinator.retained_capture,
  verified archive publication, restricted SQLLedger/ControllerLedger, v3
  screening registration, batch_plans/process_batch and bounded backlog reads.
- An explicit generic intake_only caller mode never constructs an Application
  engine, refuses CHAIN/ADMISSION registrations and cannot prepare admission.
  Historical callers and Oldham's existing mode retain their defaults.
- The existing database claim checks stop/authority BEFORE invoking the injected
  collector. This is a retention claim, not a source permit. Source authority and
  its durable intent/accounting must still come from a supported release.
- Capture is validated, archived/read back, checkpointed, completed and read back
  before screening preparation. The supervised source's observed_at is retained;
  it is not inferred from historical filter dates or the later retention time.
- Completed redelivery of the SAME scope/root is read-only and never recollects.
  Changed record content/configuration yields a distinguishable assessment.
- Screening preparation failure retains readable unscreened records and supports
  later unattempted preparation without another collection. Attempted screening
  failure preserves capture and requires existing reconciliation; it is NOT an
  automatic resume with fresh budget/authority.
- Backlog includes council/reference, source ID/URL, literal field states,
  observation time, capture/archive hashes, screening outcome/state, task phase,
  attempt/reason/next_action and derived processing state. It explicitly reports
  no Application admission, no extraction completion and no coverage advance.
  Reads are limited to 73 explicitly bound items (one capture, 60 screens,
  12 batches), 60 records and 2MiB projection. No unbounded queue scan or schema.
- current_windows selects a London-completed-day overlap (default seven days,
  maximum 28), exact council date semantics, no Trafford and at most three slots.
  It does not block current intake on historical catch-up, advance watermarks,
  reconstruct historical public availability or refresh older decisions.
- scripts/run_daily_councils.py now refuses live execution with the fixed reason
  DAILY_INTAKE_AUTHORITY_BOOTSTRAP_NOT_SUPPORTED (exit 2, no source/DB calls).
  Its old behaviour is available only through the separate manual
  python -m scripts.run_daily_councils_legacy command, with the SAME existing
  launch:run_daily_councils permission. This is not authority to run that command.
  No --include-ai-stages flag can activate a legacy fallback in the new main.

The extraction consumer is NOT implemented. Existing Application-based processing
fields (extraction_last_outcome/attempted_at, intelligence evidence timestamps,
SchemeIntelligence absence) remain untouched. Completed screening items form a
retained backlog, not executable extraction tasks. Existing nomination accepts
representative eligible records; detail targets, fresh factual verification,
independent admission/B2 and consumer handoff are still required before existing
AI processing. Unknown/truncated facts and related/low-signal records stay held.

## Concrete material dependencies — stop rule applied

1. Existing production Owner.register issues the fixed Bolton exception via
   ingestion_register_bolton_exception. Chain registration can PREPARE other
   scopes, but the PG harness inserts rows/grants as a disposable owner stand-in.
   There is no supported unattended Render issuer for a rolling scope/period.
   The source-only external permit cannot authorise SQL writes. No new issuer,
   owner/admin credential path, grant or access framework is added.
2. Overlapping COMPLETE captures with unchanged record/configuration reuse the
   same screening task identity but require different capture dependencies.
   The actual v3 worker refuses CONFLICTING_DUPLICATE. A focused PG test retains
   both captures and demonstrates this collision without resetting old rows.
   Same-root redelivery is safe; cross-capture unchanged delivery is NOT solved.
   Smallest remedy is a reviewed compatibility decision for observation-bound
   assessment identity or verified reuse of the existing assessment, including
   SQL checks. Do not alter historical keys or merely change a Python hash.
3. Coordinator.idox_source raises the shared stop on source failure, and an
   abandoned SOURCE_INTENT is reconciliation-required. Existing partial
   observation screening is explicitly Bolton-only. A generic contained-error
   label cannot grant continuation or turn partial source audits into complete
   capture receipts. Council-local continuation and safe partial capture need
   an exact existing worker-policy/contract adaptation before they can be wired.
   None is manufactured in this partial delivery; no sequence silently continues.

These are specific compatibility/authority gaps, not a request for another
historical diagnosis or a replacement architecture. Oldham successor and
standing-access expansion stay deferred. A production grant alone would not fix
(2) or (3). The default Render command remains held.

## Bounds and accounting

Each intake caller shares the existing finite DB envelope across all stages,
reads and same-root redelivery: 1040 driver statements, 40 connections, 4MiB
returned data, 300 seconds including a 30-second closure reserve. Before each
stage leave 16 statements/two connections for closure; refuse when the minimum
next operation cannot fit. Existing DatabaseBudget enforces each lowered stage
limit, hard driver waits, connection cleanup and cumulative cancellation allowance
(8 requests). Source supervision/publication is external and not counted as DB
traffic. These are per-scope engineering ceilings, NOT a nine-council run budget.

The demonstrated daily selector is max three slots. It does not establish that
three arbitrary profiles, or nine councils, fit a package. An existing V2 source
package supports at most one Arcus plus two Idox under 100 requests, 26,971,520
mixed-accounting bytes, 225 source worker seconds/270 supervision seconds,
2MiB export and 320 GitHub calls (80 publication). Do not multiply these into new
production authority or reset them between slots. Final release needs a shared
aggregate reservation covering source, archive, DB and closure BEFORE collection.
That production aggregate is not implemented while the bootstrap is blocked.

## Validation and limitations

Local focused unit/legacy/security regression uses the pinned existing test
requirements, no production access. Initial local collection failed because the
scratch venv lacked Playwright; installing the existing lock resolved it (no repo
requirements change). Initial CI 40919759973 failed YAML parsing because an
unquoted disposable sqlite URL ended in a colon. Fixed quoting; failure preserved.
Hosted run40919971866/job123610226069 at 5c35c473c8fcc64800cfb4175438f8a095ca963e
passed 14 tests, including connected Idox/Arcus PG17 capture/screening/projection.
That result precedes later cumulative-limit and negative-control additions and
must not be represented as final-head validation. Final results are in the PR.

Connected tests use actual source-reader/parser fixtures and real supervisor
processes with synthetic source data, an isolated archive publisher, real PG17,
installed worker SQL, ControllerLedger and restricted runtime principals. Only
owner registration INSERTs/fixture control setup are stand-ins. They prove no
Application-schema table changed and no Application URL is present. Synthetic
fixtures do not qualify current council markup, Render containment or live access.

## Inactive actual-Render acceptance proposal — NOT executable yet

Reuse service crn-d9sv93vavr4c73f98rb0 (propertyaigent-daily-scrape) in the confirmed
Render workspace. It remains suspended, auto-deploy off, start command /bin/true.
The proposed eventual service command is python -u -m scripts.run_daily_councils.
At this candidate it exits BLOCKED; it is NOT a supported collection invocation.
No alternate module, ad hoc Python or legacy command is an acceptance workaround.

After (1)-(3), exact candidate/CI acceptance and separately authorised deployment:
one UNSCHEDULED package, one reviewed Idox/Tameside scope and one reviewed
Arcus/Manchester scope, both screening metadata. Dates/qualification hashes and
code/tree/dependency/archive bindings must be frozen at release, not copied from
synthetic November fixtures. No recurring schedule or historical replay.

Proposed source ceiling: 90 requests (10 Idox +80 Arcus), 23,971,520 mixed-accounting
bytes (3,000,000 +20MiB), 120 worker seconds (45+75), 150 source supervision seconds,
60 rows/six pages each, 1.5GiB source/2GiB aggregate/256MiB controller. Proposed
package ceiling 960 elapsed seconds, 2MiB export, 320 GitHub calls/80 publication;
DB maximum two per-scope envelopes above (2080 commands/80 connections/8MiB data,
600 seconds) must fit the ONE 960-second package including source/publication and
closure, never add another 600-second entitlement. All figures are proposed
reservations, not measured live usage or approved allowances. A supported Render
containment/deadline route and aggregate enforcement must be demonstrated first.

Access: existing approved machine launch policy, restricted worker/effect inputs
through an inspected secure Render route, finite scope-bound issuer and full gate;
no Application/admin credential. Do not print or request secrets in chat.
Archive and ledger readbacks precede success. Retain original results, hashes,
source/DB/API usage and closure evidence. Shared uncertainty, mismatch, capacity,
publication or cleanup failure stops; no automatic replacement/retry. A later
recurring proposal should bind an owner-approved expiry (suggest seven calendar
days), council allowlist and seven-day rolling source-date filter, capacity and
run count. Derive dates mechanically within that period; no daily owner permit.
This is an authority proposal only, not an implemented recurring mechanism.

## Next decision

Corrections required / production blocked. Review the partial code and decide
whether to authorise the narrow existing worker/registration compatibility changes
in (1)-(3), without a new access framework, before further Render wiring. No
merge, deployment, production acceptance or activation is authorised by this PR.
