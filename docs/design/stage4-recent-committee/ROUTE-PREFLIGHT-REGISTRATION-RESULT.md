# TO REVIEW — ROUTE CORRECTION INTEGRATION AND CONNECTION-FREE PREFLIGHT REGISTRATION

Stage 4 OPEN. Current gate: committee-discovered application admission. Actual-secret route compatibility pending; no production admission authorised.

## Integration identities

- Original master: e1e98704913b572e46822f1fbe2b5a273f47bbd9.
- PR #88 approved head: 30ea36b5af266dc770609c58f183c037209f2e35; tree 905b1e3e09d8372edec14da7cf4ca9ed986e0278.
- PR #88 guarded merge: 7da3f32482be30a77bcafb45d82f8625348a4335; approved tree unchanged.
- Registration PR #89: head 9d06ffb03f7cdda0040997331401337d83d0621d; tree 59343f83957e801ca9ab09a4b1d81d0630153fbc.
- Registration merge/current verified master: 6fe91141ff8da09fc51e521ab9f8c8fdcf04ebca; tree 59343f83957e801ca9ab09a4b1d81d0630153fbc.
- Both merge titles preserve [skip render]. No Render deployment was requested.

## Registration diff

Exactly three paths, 67 additions/3 deletions:
- .github/workflows/stage4-route-preflight-once.yml (new).
- verification/discovery/proposals/stage4-route-preflight-once.yml.txt (obsolete comment only).
- tests/test_discovery_route_validation.py (absence assertion replaced by exact registered/template equality plus controls checks).

Approved template blob 3043a10f355990667d04b6d3a384e9fdfc9955e5 differs only in its initial proposal-only comment. Registered workflow and updated template are byte-identical, blob a5385491b6b0c08ac23206709a3d9187ea65fc12, SHA256 e6142ecdbd296130cd70f6143a0a1dddfec2989651474e35e6639bf22e622773.

No validator, destination policy, engine, evidence, transaction, source, admission or B2 implementation changed in registration.

## Validation

41 focused local network-denied tests passed, including actual synthetic seccomp entrypoint. Two initial local invocations failed before tests because of an incorrect wrapper filename and a missing synthetic DATABASE_URL; corrected invocation passed without code changes.

All six exact registration-head hosted checks passed:
- 116324647811 offline (including network-denied route entrypoint tests).
- 116324647855 disposable PostgreSQL admission.
- 116324648710 and 116324642828 web.
- 116324648869 and 116324643344 Stage 2 commercial/Stage 1 security offline.

PR #88 exact-head six checks had also passed before merge. Existing independent review of its unchanged validator and preflight implementation remains applicable. Registration was checked against the explicitly approved template and restricted diff; no new independent agent review is claimed.

## Execution state and owner action

Connector exposes no workflow-dispatch operation. No dispatch attempted. Post-integration complete workflow_dispatch history contained 19 runs and zero for this preflight; latest 100 all-event runs also contained none. Workflow is manual-only. No preflight run, artifact or result exists yet. Authority is not consumed by registration.

Open https://github.com/maxrose26/PropertyAIgent/actions/workflows/stage4-route-preflight-once.yml

Choose Run workflow, branch master, and enter:
reviewed_sha: 6fe91141ff8da09fc51e521ab9f8c8fdcf04ebca
authority: AUTHORISE_CONNECTION_FREE_ROUTE_PREFLIGHT_ONCE

Dispatch once only, then approve stage4-production-canary if prompted. If a run already appears, do not dispatch another; provide that run link. Do not rerun or create attempt 2. If master has moved from the specified revision, stop before dispatch.

The workflow enforces master/revision/workflow SHA equality, run 1/attempt 1, fixed authority, existing protected environment, five-minute deadline, read-only repository permission and shared production concurrency group. Only the validator step receives the existing secret under PREFLIGHT_DATABASE_URL; no value transfer or replacement. Seccomp denies networking before application imports. No engine/source/admission/B2 path runs.

## Result limits

Actual-secret COMPATIBLE/rejection code and normalization/default-port flags remain PENDING. Authentication and connectivity are NOT_TESTED. No database connection/read/write or source retrieval was performed in this slice. A compatible result will prove route compatibility only, not authentication/connectivity or historical cause of run 38655110927. That run and its manifest remain consumed/unchanged. Production admission remains unauthorised. Next action is the already-approved single preflight; after artifact reconciliation REVIEW decides any further authority.
