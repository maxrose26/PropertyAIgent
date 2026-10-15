# Two bounded R0 registrations — execution REVIEW only

Stage 4 remains OPEN. Registration grants no execution authority. No live source,
database, admission or browser observation was performed for this change.

PR #97 was integrated with [skip render] at cc9e2df3b8cf4fe6da5da144eb64a546689df87a,
reviewed tree 0d79597c9c8d811d10fbca75e3d817c0de4b11bb. Its six post-merge checks passed.
The successor registration adds only the two frozen scopes, their shared
credential-free controller, supervision/checkpoint changes and focused tests/CI.
Historical workflows, manifest files, authorities and original seals are unchanged.

## Closed scopes

| Scope | Manifest SHA256 | Calls / requests / received bytes | Execution / audit |
|---|---|---|---|
| fixed80 | 1c4cb696cfd352532a0c19fe9e919e86059908cc3cf21ed37f8be2ec8ab23b12 | 80 / 160 / 160000000 | 4400s / 8000000 bytes |
| untouched27 | f99d86a5deb251f45c0787af295836aa948d8250d9f7b180062db229c6dc0e3d | 27 / 1040 / 278686720 | 1900s / 20000000 bytes |

Both parent-owned process trees have a 1610612736-byte aggregate RSS ceiling.
Existing per-record/source controls are unchanged. Fixed80 contains exactly 54
Bolton and 26 Bury identities, including the five UNKNOWN-window candidates.
Untouched27 contains Manchester3 and Oldham/Rochdale/Salford/Stockport/Tameside/Wigan4
each, preserving original order, dates and cut. It excludes both Bolton/Bury and
the consumed Manchester 17–23 September capped window.

Workflows are manual/master/exact-revision/exact-workflow-SHA/exact-manifest,
run1/attempt1 only. Before any subsequently authorised first dispatch, REVIEW must
bind the final integrated master SHA and confirm complete zero-run history.
Their only inputs are reviewed_sha, manifest_sha and authority. Proposed authorities:

- AUTHORISE_R0_FIXED80_EXACT_RECORD_QUALIFICATION_ONCE
- AUTHORISE_R0_27_UNTOUCHED_PRIMARY_WINDOWS_ONCE

No protected environment, secrets, database input, admission path or arbitrary
reference/destination input exists. Worker environments contain seven runtime/cache
keys only and no execution authority. Parent binding rechecks actual workflow bytes
and clean checkout immediately before source execution.

## Supervision and checkpoint controls

The actual parent invokes the existing owned-process supervisor with the new exact
controller module and fixed profile. The child validates the exact plan and invokes
existing qualification/readers. The parent independently polls owned descendants,
RSS, deadline and aggregate checkpoint/output bytes. Accounting/cleanup uncertainty
stops success; owned groups and tracked descendants are killed, waited and checked.
Disposable hosted-VM teardown is final containment, not hostile-process isolation.

Every completed observation is create-only checkpointed, fsynced, reread/hashed and
the directory fsynced before another source call. A failed checkpoint or unknown
resource accounting prevents the next source call. Diagnostic checkpoints remain
on hard stop where bounded export is possible. Checkpoint bytes reserve a second
copy for the final result plus 131072 bytes of envelope headroom. Final export is
path-, run-, revision-, scope-, manifest- and aggregate-byte checked before upload.
An audit bound/identity failure blocks upload rather than silently exporting excess.

Setup elapsed time is checked again by the real entrypoint: <=280s fixed80 or <=260s
untouched27. Job ceilings are 4800s/2280s; execution deadlines are 4400s/1900s, leaving
at least120s for bounded cleanup/export. Shell timeouts4500s/1930s with10s kill are
secondary backstops. Artifact upload is within the job ceiling; upload completion is
not guaranteed if the hosted service fails. Parent process accounting includes child
supervisor overhead; checkpoints and final audit have independent byte accounting.

Ordinary PAGE_CAP/missing-count gaps continue only when the existing destination,
criteria, identity, resource and cleanup checks all pass. They retain candidates and
INCOMPLETE/UNKNOWN coverage. Exceptions, identity/destination/criteria/security,
resource-accounting and cleanup failures hard-stop. No fatal flags are cleared.

## Independent evidence and remaining limitations

retained-independent-map.json is a mapping of original sealed evidence only, not a
new denominator. Twelve of27 windows retain usable complete independent enumeration:
Oldham4, Rochdale3, Salford4, Stockport1. Fifteen remain UNKNOWN: Manchester3,
Rochdale1, Stockport3, Tameside4, Wigan4. New primary observation has not occurred;
no window is newly reconciled. Later source changes remain a comparison limitation.

Original ledger SHA256:715da66d96a643800c7a30df9ae88481e7fc2576d89fc55a4ec93484a2049f17.
Append ledger SHA256:7a46aa77843e85b226f1f1a0982feff79a2d111a4a93596a37ad953a0c7ceb23.
The original seals and283 independent-only references remain unchanged. No lost set
is reconstructed. Manchester cap-stopping deviation and browser-reset retention/
accounting limitations remain explicit. No new independent observation is authorised.

Bury UNKNOWN and the capped Manchester overlap window require separate later REVIEW.
Publication recall, unsupported latency, residual council coverage and15 October
onward bridge remain unresolved. No database catch-up, admission or stage advancement
is implied. Unknown materiality/site relationship/role remains unknown; no sites,
links or opportunities are automatically created.

## Validation

Network-denied affected/registration suites:186 passed (before final docs only).
Independent executable and registration reviewers each ran31 registration tests and
reported PASS/no blocker. Hosted exact-head and post-merge checks are required before
execution readiness; their exact identities/results are recorded in the final handoff.
Tests intercept processes/sources. No live qualification or new source-shape proof
is claimed. Registration itself does not resolve any remaining discovery acceptance.
