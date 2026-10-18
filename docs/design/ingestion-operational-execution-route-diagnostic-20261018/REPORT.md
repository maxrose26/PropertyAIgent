# Released restricted-connection diagnostic — Stage 4 OPEN

PR #128 integrated with [skip render], deployment suppressed.
Candidate: 07f4dc05d8fbd16d537d3ba2b1e9767407a4ae8d
Integrated revision: b9e6bd639ad1f1a472c35f339b70f8f524c08ac4
Exact reviewed tree: a9d28fcf3994d2105c79b15e8f717f752d591e3c
Nine candidate hosted checks and all seven post-merge checks passed.
Predecessor review evidence: eab100b369fc90c8ff5400d473bc06476536f65b

## Release
One owner-local attempt, diagnostic only. Newly released, no owner invocation reported at publication.
Authority: AUTHORISE_INGESTION_RESTRICTED_ROUTE_DIAGNOSTIC_ONCE_20261018
Registration blob: 80eb344ca8589f85cb05e440790fa004222030ee
Registration SHA256: 396f48d328891b872ee715f2f9cf6a33076620ba852a2fc7a436ec7b5af7cc1c
Manifest blob: 21f27a818fb6beb8b682a4c6210b14aeac5e1956
Manifest SHA256: 37cb050e7d56c19a5b62a669a779ddff006fea504ca3b312f7fef91a0757b15f
Owner wrapper blob: f269bc0118ae49baf7367d0f9971a3a13fe307bd
Owner wrapper SHA256: d783cf4a640b2fbd12b42b1ab9f2f791819b4548a6bf3586b1c90a04b8d33cbf
Released timestamp: 2026-10-18T13:58:27.797570+00:00
Expiry: 2026-10-19T12:00:00+00:00 (19 October, 13:00 BST), less than 24 hours after release.
No renewal, replacement, rerun or reuse of consumed registrations.

## Exact scope and safeguards
Existing worker/effect restricted logins only, exact capability memberships and permission gates; independent passwords generated from 48 random bytes in memory, direct protected-secret mapping, accepted finite provider-side verifier-retention risk, existing endpoint and verify-full/provider CA.
One handshake per restricted login; abort further handshakes after first failure.
Verify restricted identities and transaction modes. No grant, exception, generation-policy update, discovery insertion, source observation, screening, application or factual write.
Preserve generation 1 and exact baseline control hash 0d829597f1422fef0af13920d5749c5751adf6d896588f379c400db7b3fa27cf.
Preserve original Salford stop and STORAGE_TEST_STOP.
Teardown disables logins, removes passwords and two reviewed memberships; read back exact sessions/access state; remove worker/effect temporary secrets and verify absence while preserving DATABASE_URL.
Uncertain mutation or secret-store result stops subsequent mutations. No compensation/retry.
Expected success: RESTRICTED_ROUTE_QUALIFIED_ACCESS_DISABLED with CLOSED controller cleanup and complete accounting.
Diagnostic is pending owner execution; no production effects performed by publishing this release.

## Ceilings, not targets
Runtime: 1040 driver commands, 40 connections, 4 MiB returned DB data-value bytes, 300 supervised seconds.
Administration: 240 commands, 13 connections, 1 MiB returned DB data-value bytes, 240 supervised seconds.
Phase maxima are not additive entitlements.
Hidden input: 300 seconds, zero DB/secret API calls.
Active maximum: 480 seconds; work deadline 450 seconds; 25-second diagnostic reserve and 5-second reporting reserve.
Finite outer maximum: 790 seconds.
Controller and owned controller subprocesses: 256 MiB kernel-enforced; aggregate outer 1.5 GiB, swap zero. Source group unused.
Combined exported output: 2 MiB. Returned DB-value bytes are not total wire traffic.
Fresh allowance only. Historical missing accounting remains unknown.

## Validation and independent release review
Existing accepted exact-head native proof preserved, not repeated: workflow 39115906670, run 200/attempt 1; 45 focused wrapper tests, zero failures/errors/skips. Artifact 12132182744, SHA256 e87fe64a7404a9b4cc9c1a1cbc7c737670da6c07ddd246b2c79c75d9f77a49e0.
Post-merge checks archived alongside this report. Wrapper bash syntax and manifest/registration dependency hashes validated.
Independent operational reviewer: PASS, no substantive release-package finding. Confirmed exact registration/manifest/wrapper hashes, integrated bindings, fresh one-use state, hidden input, enforced deadlines/memory, generation-1 stops, zero grants/exceptions/work/source scope. No live review action.

## Preserved history and decision
Prior cleanup controller CLOSED, post-exit systemd scope removal unverified. Older UNCERTAIN classifications and original missing accounting unchanged. IDs 1504–1508, storage acceptance and consumed authorities preserved.
Original restricted connection cause remains UNDETERMINED; this diagnostic reports safe phase/kind/SQLSTATE rather than arbitrary exception text.
Capture/screening, admission/B2, scheduling, deployment and Stage 4 advancement remain held.
NO-GO for later capture until the diagnostic's actual result, teardown, accounting and closure are reconciled.
