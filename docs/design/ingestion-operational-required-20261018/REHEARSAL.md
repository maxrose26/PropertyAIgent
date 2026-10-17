# Exact-candidate disposable rehearsal

Candidate `406db539584625a97adafb939e8e5abde0767df5`; tree `8482c3d62c79bcbdb6ce91b1b8075751bcaf9893`. GitHub discovery run `39079564348`, run number 185, attempt 1. All three discovery jobs passed. No production or council connection was made. PostgreSQL 17 and the real Linux gh executable communicated only with disposable PostgreSQL and a loopback TLS GitHub fixture. The existing non-superuser migration contract and real restricted logins were exercised.

| Measured success path | Actual | Proposed/accepted ceiling |
|---|---:|---:|
| Retained rows / batch tasks | 60 / 12 | 60 / 12 |
| Source callback observations | 1 | 1 |
| Runtime driver commands | 814 | 1,040 |
| Runtime connection attempts | 27 | 40 |
| Runtime returned DB data-value bytes | 1,658,525 | 4,194,304 |
| Runtime supervised seconds | 2.703400017 | 300 |
| Administrative driver commands | 117 | proposed 240 |
| Administrative connection attempts | 6 | proposed 13 |
| Administrative returned DB data-value bytes | 92,626 | proposed 1,048,576 |
| Administrative supervised seconds | 0.791217476 | proposed 240 |
| Complete local journal bytes | 105,598 | 1,048,576 audit / 2,097,152 combined output |
| GitHub CLI invocations | 25 | 40 |
| Effective restricted-login denials | 16 | all required denials must pass |

These are disposable costs, not predictions of live latency. Administrative counters include actual wrapper operational installation, lifecycle and grants; they exclude fixture-only base storage creation, database setup, assertion queries and deliberately injected negative ambient grants. Runtime accounting carries the reopened capture slot and completed screening receipt into a fresh Runner. Between-batch pause/reconstruction used the same immutable receipt and never invoked its replacement source callback. Mixed proposal outcomes and literal citation leads use the accepted sixty-row fixture. Twelve five-row batches fit without consuming provisional 1,560/208 reservations.

The complete four-case wrapper suite ran inside real delegated cgroups: 256 MiB controller, 1 GiB source, 1.5 GiB aggregate. Its PostgreSQL test process peak was not separately exported; enforcement and successful closure were exercised. The separately exported harmless source-placement/startup probe measured aggregate peak 28,254,208 bytes, controller peak 18,890,752 bytes and source peak 5,242,880 bytes, zero max/OOM events and zero survivors, both owned groups removed. These are **startup probe peaks**, not full-wrapper PostgreSQL peaks. A separate 400 MiB controller allocation produced kernel oom-kill and empty scope, rather than an advisory sample-only limit.

Failure outcomes:

- Mapping acknowledgement loss: exactly one mapping invocation, zero source callbacks; actual worker NOLOGIN/password present, effect NOLOGIN/password NULL. No subsequent mutations or automatic teardown. This is reconciliation-required, not CLOSED or successful provisioning.
- Teardown DELETE acknowledgement loss: one source callback and exactly one DELETE request. Actual database roles NOLOGIN/password NULL, no memberships/sessions; fixture observed one remaining effect secret. No second DELETE or retry after uncertainty.
- Final closure failure: roles/secrets disabled/removed but durable report remains CLOSURE_PENDING. No false CLOSED publication.
- Effective permission negatives: inherited TRUNCATE, column UPDATE, direct broker SELECT and extensions schema USAGE each prevented activation before passwords; restricted roles could not read statistics, call/reset statistics, mutate the ledger or assume owner/issuer/releaser roles. Stored query text and verifier material were never retrieved by the controller or readbacks.

Artifact `12118127269`, `ingestion-provisioning-disposable-406db539584625a97adafb939e8e5abde0767df5`, 67,056 bytes. Downloaded ZIP SHA256 verified against GitHub's digest:
`308474c2320a8ddf9dfb5f0de93d308c0597c9d81a509e6f87d38fcf45263343`.
The original ZIP, per-member hashes, measurements and native proof are archived with this package; hosted expiry is not a recovery dependency.

Independent exact-candidate review PASS. It verified all seventeen selected Git blobs against the remote tree, including the Supabase username correction, effective privilege checks, actual native source placement and truthful closure reporting. The limitations above remain explicit. Required exact-head and post-merge checks are recorded separately in execution-identities.json.

The previously accepted shared admission/B2 writer proof remains separate: `7d626d6e9cf463147c52b3c917d0de29cd8fbfbf`. It is not re-run or relabelled as production admission, unit extraction or complete scheme extraction. Production operational acceptance and backlog completion remain outstanding.

## Integrated checkpoint

PR #126 merged as `ad8d5211afcc635c5bc50f4963adde4f31b4ef62` with `[skip render]`; exact reviewed tree unchanged. All nine candidate checks and all seven post-merge checks passed. No deployment command was issued; no Render configuration was changed. Render connector inspection was unavailable without a selected workspace, so it supplies no additional service-state attestation.

Post-merge discovery run `39079807470`, number 186/attempt 1, also passed all three jobs. The wrapper repeated automatically as a required post-merge check: runtime 814 commands/27 connections/1,658,501 returned values/3.636922171 supervised seconds; administration 117/6/92,626/1.231980539 seconds; audit 105,598 bytes. Artifact `12118920258`, 66,978 bytes, ZIP SHA256 `fa413ee0ef421925d9cebe89f71298eb83e96e7d9a32d544a8bab67a134c99b4`, downloaded and verified. Its independent startup/source-placement probe recorded aggregate/controller/source peaks 30,363,648/20,979,712/5,505,024 bytes, zero max/OOM events and zero survivors. These remain startup probe measurements, not full PostgreSQL wrapper peaks.

The required runner is ready for grouped production approval. Held registration, credential-risk scope, new operational permissions, administrative budget and exact expiring exception still require that approval. No production registration was issued and no production execution occurred.
