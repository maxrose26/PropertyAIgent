# Bolton canary preparation — 6 November 2026

MASTER STAGE 4 OPEN. Current gate: a reusable, bounded Bolton intake proposal. Next gate: REVIEW resolves the timing-policy constraint before a live proposal is issued. NO-GO for live execution; this is boundary evidence, not an executable Bolton release.

## Baseline and authorised scope

Accepted period10 handoff d03f39ae73694ad9f4700b3c127a99180e806c3e; owner c8b3950ea74c462843791f041349a4bd655110f7; scraper 5af5f42ca8e299a83017851fc8c61a03880ced2e. Scraper tree 87125a88c1e4b1879a1d06fcf68099340d983562, workflow SHA256 946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9, manifest SHA256 044819280bfd7ac0850a79c9ddf8a409716175865a7494e19f0502be13e43a2c. These remain baseline bindings, NOT a Bolton release.

Proposed identity b-bolton-20261103-1105-01; Bolton RECEIVED 2026-11-03 through 2026-11-05 inclusive. Limits: 10 physical requests including redirects, zero retries, 3,000,000 received-body bytes, 500,000 bytes/response, six pages, 60 records, 45 source seconds, existing 1 GiB group, 512 KiB retained output and stricter file/process limits. No detail/documents, AI extraction, other-council recollection or runtime GitHub publication.

## Demonstrated constraint requiring REVIEW

The earlier proposal confused the intake-job ceiling with the owner lifecycle. The current code does not provide a 960-second whole-owner lifecycle:

- owner_pilot.fixed_binding fixes an access envelope of 2,100 seconds, runtime_deadline at bound_at + 1,915, leaving 185 seconds for owner closure.
- intake_owner.validate_binding requires that exact policy (FINITE_FIXED_DEADLINE), and opening requires more than 1,500 seconds remaining (SETUP_TEN_MINUTE_BOUND).
- daily_intake_runtime.execute independently requires more than 1,500 seconds of access remaining (DATABASE_PILOT_STARTUP_RESERVE).
- IntakeRun alone has a 960-second wall ceiling, with 180 seconds protected inside it: normal work stops at 780 seconds. Owner preparation/provider restoration are not bounded by that job clock.

An actual-validator regression proves that substituting 960 seconds is refused. No guard was weakened. A true whole-lifecycle 960-second contract requires a measured timing-policy change across setup, activation, worker admission and restoration, not another council allowlist entry. The 2,100-second value is itself an access envelope, not proof of a 2,100-second end-to-end owner-operation deadline.

Smallest decision: retain the established 960-second job ceiling and existing owner timing/cleanup policy for this canary, or require a new end-to-end 960-second timing contract. Recommend retaining the existing policy for the canary, explicitly, rather than silently exceeding the instruction or inventing another owner workflow. This decision authorises no live execution by itself.

## Fresh read-only evidence

Queries used READ ONLY transactions, ending in ROLLBACK and closed connections. No registration, grants, configuration changes, deployments, council requests or submissions occurred.

- Period10 marker remains VERIFIED / RETAINED_AND_SCREENED, run 6e0cb337843748f08bbfcec71d5e87fc.
- Generation13; global_stop and manual_stop null; last_hard_stop ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP. No stop disposition is indicated by this state. Any future drift must refuse.
- Proposed Bolton identity absent from period control, matching work revisions and run/owner evidence namespaces. This is absence at read time, not a reservation.
- Historical Bolton capture d1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545 remains COMPLETE / FINISHED, fence1, 24 records. Historical window RECEIVED 28 September–4 October 2026, not this canary's window.
- Capture checkpoint SHA256 d5fa9e29bdd51afbf36772e9b08880af6811a8cec771a3335bad0095801445ee.
- Independently fetched archive at commit 3587e2778720f56a9510b33c7bbce7584f6be59d, docs/design/ingestion-operational-execution-bolton-window-demonstration-20261023/capture/source.json: 20,733 bytes; SHA256 5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a, matching the checkpoint.
- Historical screening dependencies contain 48 COMPLETE assessments: 24 with current configuration SHA256 58e2a1a1dae30a21b8fa150a27d223793d4601e8d400a686c4f8e17d999e1b7e and 24 with no config_sha256 field; ten COMPLETE metadata batches. These are retained versions, not 48 distinct applications.
- The actual backlog_page reader, positioned at that capture, refuses BACKLOG_MULTIPLE_ASSESSMENTS. Historical capture/screening is verified; present reader discoverability is NOT verified. No historical version was deleted, selected arbitrarily or rewritten.

The accepted 59 Manchester/Tameside records and separate provenance are reused from the accepted period10 handoff. This preparation did not repeat their full fingerprint readback and did not mutate them.

## Focused checks actually run

Added tests/test_bolton_canary_preparation.py on the accepted owner code. Command:

    python -m pytest tests/test_bolton_canary_preparation.py -q --disable-warnings

Result: 10 passed (0.43 seconds). Real Idox reader and capture validator with synthetic transport responses: 1, 24 and 60 records; reconciled enumeration and bounded accounting; missing terminal proof, changed dates, exhausted accounting and unknown cleanup refuse. Real owner validator rejects unsupported Bolton identity and altered timing; actual IntakeRun enforces 780/960-second work/closure boundaries.

These are offline component/boundary tests, NOT the nested worker transport, a newly admitted Bolton owner lifecycle, or disposable PostgreSQL end-to-end acceptance. No new hosted PostgreSQL result is claimed. Accepted period10 hosted results remain valid for their unchanged scope; they are not relabelled Bolton validation.

## Smallest reusable implementation after the timing decision

1. Add one immutable reviewed scope policy containing identity, predecessor evidence binding, council/date field/window, limits and release binding. Pass it through the existing issuer, owner lifecycle and worker. Council/window admission must stay outside recovery and transport algorithms.
2. Extend existing registration/activation validation to consume that exact policy. Preserve strict release, stop, duplicate and incomplete-coverage checks. Existing registration has a VERIFIED-predecessor branch, but the owner continuation currently selects period-specific failed-predecessor machinery; do not route successful period10 through settlement.
3. Preserve period10's successful marker and evidence in retained history before replacing the active marker, atomically with admission. Preserve generation13 and last_hard_stop; no synthetic failure receipt or stop clearance.
4. Use the same capture, evidence, screening and close operations. Keep retained-capture recovery source-free; distinguish supported unattempted-screen preparation retry from attempted/uncertain work requiring reconciliation. Never rerun source to repair downstream work.
5. Resolve historical multi-version backlog reading with explicit provenance/configuration selection while preserving all versions, or report that historical limitation separately. Do not weaken ambiguity checks or treat a new capture as repair of the old one.
6. Prove the actual entry points in disposable PostgreSQL: successful admission through independently read-back capture, screening and backlog; duplicate refusal; incomplete coverage; atomic rollback; permissions removed; fresh readback after lost acknowledgement; downstream recovery with source invocation count unchanged; all 59 accepted records preserved.

No new owner/scraper candidate or inactive live command is supplied: the unchanged entry point refuses this scope. Publishing a runnable command now would misrepresent readiness. The command above is an offline check only. After implementation and connected disposable validation, pin both executable revisions and all release fields, then request one bounded live canary approval covering preparation, activation, one submission and independent closure/restoration. Recheck identity absence and current control state immediately before that future sequence.

## What a passing canary would and would not establish

A live pass would establish Bolton's new fixed RECEIVED window through terminal enumeration, truthful accounting, durable capture/hash readback, screening, discoverable backlog and independent closure/restoration on the reusable path. It would not establish all-Greater-Manchester coverage or justify scheduled restart.

Before bounded scheduling: deterministic recurring issuance and duplicate/concurrency exclusion; explicit timezone/completed-day rolling rule and overlap; late-arrival/freshness tracking; retained-capture interruption recovery through the actual owner entry point; visible incomplete/unknown coverage and recovery escalation; safe automatic closure. Preserve existing evidence and avoid recollecting the accepted Manchester/Tameside window merely to demonstrate another entry point. Stage4 remains OPEN.
