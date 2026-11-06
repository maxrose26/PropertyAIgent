# Bolton canary — offline validation and inactive live proposal

MASTER STAGE 4: OPEN. Current gate: one reusable Bolton scope through collection, retention, screening and backlog. Next gate: REVIEW authorises or refuses one bounded live canary. This is not Greater Manchester readiness or permission to restart scheduling.

## Scope and clocks

Proposed single-use identity: `b-bolton-20261103-1105-01`. Bolton only, RECEIVED, 3–5 November 2026 inclusive. No details, documents, AI extraction, Manchester/Tameside recollection or GitHub publication.

- Source: 10 physical requests, zero retries, 3,000,000 received-body bytes, 500,000 bytes per response, six pages, 60 records, 45 seconds; 1 GiB source-process-group ceiling; existing 512 KiB per-file and retained-output bounds. The nested Idox reader also retains its stricter 512,000-byte output check. Other collectors' limits are unchanged.
- Owner access: 2,100 seconds from binding; runtime deadline at 1,915 seconds leaves the existing 185-second closure reserve. Opening/startup requires strictly more than 1,500 seconds remaining. This is an access envelope, not a claim that build/preparation/restoration together finish within 960 seconds.
- Intake job: 960 seconds, normal work stops at 780, 180 reserved for cleanup. Existing request, database, memory and export accounting remains enforced independently.

## Implementation

`intake_scope_policy.py` is the immutable council/window/limit policy. `owner_intake_scope.py` selects the existing Pilot lifecycle; `intake_successor.py` adds successful-predecessor admission rather than manufacturing a failure settlement. Worker, issuer, capture, screening, backlog and cleanup implementations are reused. No new recovery framework, credentials or persistent privilege is introduced.

The existing atomic namespace migration updates three existing function bodies, preserving owners, security-definer settings and ACLs:

1. `ingestion_intake_owner_state`: adds only the Bolton owner journal namespace.
2. `ingestion_register_bolton_exception`: admits the exact one-council policy/window. Registration copies the original period-10 marker to `intake_periods[period10].verified_run` atomically with admission. It leaves the original active marker until the first new capture registration replaces it. Finalisation's council identity check accepts the exact Bolton audit; every other completion/evidence guard remains unchanged.
3. `ingestion_intake_evidence_write`: accepts Bolton only for this period and fixed window, with matching RECEIVED subject/audit identity. Existing run, authority, expiry, hash, conflict, size and quota checks remain.

Temporary SET-only owner membership and schema CREATE permission are removed before commit; original schema/member/function ACL state is checked. Failed migration rolls back all three functions. Lost commit acknowledgement is reconciled by fresh read-only inventory; it is not grounds to repeat a write.

Generation 13, null global/manual stops, last_hard_stop and unrelated history are preserved. There is no stop-disposition operation in this successor. Changed stops refuse.

Two integration defects were demonstrated and corrected: the evidence writer and final evidence guard previously accepted only Tameside/Manchester source identities. A final limits review also found the shared outer supervisor's 1.5 GiB group default; the new scope explicitly selects 1 GiB without changing other collectors.

## Validation and evidence

Final owner: `426919cdf297d440f7b1433fc0bc15469e467911`.
Final scraper: `ee9dbb7b9dccca161aad46526248f14a9661ce9c`.
Tree: `9eaf248641ae2d09defc9f1703c5814cb4278a7a`.
Workflow SHA-256: `946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9`.
Manifest SHA-256: `570b020ca03ad47a2d00c265f1a752cd39c0eb70d91c1071f70ffed17de07eba`.
Source branch: `prep/b-timing-pg17-current-20261103`.
Scope-policy SHA-256: `d5b25334ef4c75cfbe801e2e3c797c70d2db427fc7e48e6849d962b19925e909`.

Hosted PostgreSQL 17 run [42193736282](https://github.com/maxrose26/PropertyAIgent/actions/runs/42193736282), job 127811715005: SUCCESS; 36 contract/PG checks passed in 150.96 seconds; two actual nested-worker tests passed in 8.18 seconds. Earlier full sequence run 42192561016 passed 31 + 2 tests; the 60-record extension at 6735c614 passed 32 + 2 (run 42193250348). Those are supporting iterations, not separate live runs.

Final owner hosted run [42194338694](https://github.com/maxrose26/PropertyAIgent/actions/runs/42194338694), job 127813718231, at exact owner 426919cdf297d440f7b1433fc0bc15469e467911: SUCCESS; 36 contract/PG checks passed in 159.96 seconds and two nested-worker tests passed in 8.28 seconds.

Final owner-pin focused checks: 76 passed in 1.22 seconds. Independent comparison proves every BOUND_FILES byte, workflow/manifest, and all three migration function bodies match the sealed scraper; only the owner pin differs. Final clean scraper startup through scripts.owner_pilot_job returned CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION, clean exact tree/binding, authentication_attempts=0 and source_requests=0. This was local isolated startup validation, not a Render artifact verification. No Render deployment/job ID exists for this canary.

Function body SHA-256 values for independent migration readback:
- Registrar: `b1cb4b54493ce2b1ed2a90acb996a70e96cce9545171f57f7c9efd03ae4b382a`.
- Evidence writer: `8ffd8fdda0692a49a776137ea6342c1378d1f513cd418b8f983a92f0fe910290`.
- Owner namespace: `adadf1970a5156c5b02b3b0db193376bf71767b04cf29c1557c94d58c185aacb`.

The disposable PostgreSQL sequence uses actual namespace migration, PeriodIssuer, activation, Runtime entry point, intake_slot, retention, screening, backlog and closure. Provider state is simulated and council transport is synthetic. The nested source test executes the real supervisor, source_worker, finite Idox worker, request boundary, parser and capture validator with sockets blocked. It produces 24 records/6 physical requests and 60 records/9 physical requests, zero retries, terminal count reconciliation and verified process cleanup.

Cases cover successful 24- and 60-record retention/screening/backlog, independent archive bytes/hash readback, duplicate refusal before recollection, incomplete enumeration refusing VERIFIED, changed council/window/stop/predecessor/used identity refusal, rollback before commit, fresh readback after lost acknowledgement, absent temporary permissions, exact 1,500-second startup refusal, and the owner/job timing boundaries. Predecessor fixture reproduces Manchester 35 and Tameside 24; all prior work snapshots and original evidence hashes remain unchanged.

Retained-capture recovery is specifically the existing intake_slot path after capture commits but before screening preparation. A fresh read resumes screening with a source callback that fails if called. This does not claim automatic owner restart for attempted/uncertain downstream work; those states still require reconciliation.

The local broader focused suite returned 85 passed/1 failed: the old mocked owner test lacks startup_preflight. That exact failure reproduces at accepted owner c8b3950. The frozen direct-reference request-boundary hash assertion and frozen-v6 import-oracle assertion also reproduce unchanged at c8b3950. No historical hashes or guards were rewritten to make these suites green. The accepted period-10 handoff documents additional old discovery/continuation expectations. Repository-wide green status is not claimed.

## Historical Bolton assessments and accepted records

Reused handoff f91dae73 evidence: historical capture `d1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545`, RECEIVED 28 September–4 October 2026, 24 records. Archive SHA-256 `5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a` was independently verified; 48 COMPLETE assessments are two sets of 24, not 48 applications. Both sets remain retained. Historical reader still refuses `BACKLOG_MULTIPLE_ASSESSMENTS`.

The new explicit contract `bolton-received-intake-v1` scopes fresh canary readback. PostgreSQL tests retain two ambiguous historical assessment sets, demonstrate historical refusal, and separately return all fresh canary results with their own archive period. No implicit latest-version selection, deletion or rewriting occurs. A combined historical assessment UI remains deferred; a fresh capture does not repair the historical ambiguity.

Fresh READ ONLY/ROLLBACK inspection on 6 November 2026 found the proposed identity absent from control, work revisions and both evidence namespaces; period 10 VERIFIED/RETAINED_AND_SCREENED; generation 13 with null global/manual stops; last_hard_stop ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP; disabled runtime logins, zero memberships and sessions. Manchester's 35 and Tameside's 24 capture records retained their original period-10/period-08 run provenance and checkpoint hashes. Accepted full backlog/cleanup evidence is reused. Absence at read time is not a reservation and must be rechecked before live admission.

No production registration, function update, grant, configuration change, deployment, council request or submission occurred. Only review-branch code/tests and disposable database state were written. The source branch was read back at accepted scraper 5af5f42ca8e299a83017851fc8c61a03880ced2e; no branch advancement occurred. Scheduling remains held.

## Inactive executable proposal

After REVIEW authorises one canary, DEVELOPMENT uses the existing protected owner environment and the exact owner checkout below. Configure only PROPERTYAIGENT_INTAKE_SOURCE_RELEASE to the five pinned release fields below, securely retaining the prior setting and verifying unrelated configuration unchanged. Recheck unused identity, exact successful predecessor, original evidence, all 59 accepted records/provenance, generation/stops, dormant access, capabilities and absence of competing operations. Any drift refuses.

Exact proposed protected source-release value (review only; not applied):

```json
{"execution_binding":{"revision":"ee9dbb7b9dccca161aad46526248f14a9661ce9c","workflow_sha256":"946258265cf2e7f346ef57b18c7a7bb5056600581cf51ba4b595459c12c367b9","manifest_sha256":"570b020ca03ad47a2d00c265f1a752cd39c0eb70d91c1071f70ffed17de07eba"},"tree":"9eaf248641ae2d09defc9f1703c5814cb4278a7a","branch":"prep/b-timing-pg17-current-20261103"}
```

Securely retain the exact previous value; read back all five fields and hash. If any pre-submission configuration acknowledgement is uncertain, read back before repetition. Restore the retained exact previous setting if abandoning preparation, without overwriting journals or evidence.

In the existing owner Web Shell, prepare a clean checkout at owner 426919cdf297d440f7b1433fc0bc15469e467911 (proposed path `/tmp/propertyaigent-bolton-owner-426919c`). Verify `git rev-parse HEAD` before the command. Command prefix in that checkout:

```bash
PROPERTYAIGENT_OWNER_PILOT_AUTHORITY=b-bolton-20261103-1105-01 \
python -B -m scripts.owner_intake_scope --action inspect
```

Expected: UNUSED_SUCCESSOR_VERIFIED, exact stop tuple, ROLLED_BACK. After inspecting ancestry and unrelated changes, DEVELOPMENT fast-forwards only `prep/b-timing-pg17-current-20261103` from its independently verified head to the pinned scraper, with an expected-head lease and independent readback. No force/reset is permitted. Then use the same prefix with `--action prepare-successor`: the supported atomic migration, journal link, build, zero-source startup and artifact verification. Independently verify the migrated functions/ACLs, journal preservation and exact artifact commit/tree/binding. `--action verify-successor` must pass. Preparation uncertainty requires journal/provider readback, not another build submission.

Immediately before intake, independently verify baseline suspension/configuration/environment, cleanup capacity and Dashboard isolation (no inherited environment groups/credentials, secret files or competing jobs/deploys/owner operations). Record the timestamp only after that observation. Inactive start command, at most once after approval:

```bash
PROPERTYAIGENT_OWNER_PILOT_AUTHORITY=b-bolton-20261103-1105-01 \
python -B -m scripts.owner_intake_scope --action run-successor \
  --owner-checked-at "$BOLTON_OWNER_CHECKED_AT"
```

The observation must be within 300 seconds. DEVELOPMENT can make it through the existing signed-in Dashboard; only an inaccessible owner-only session would require one owner action. Do not invent the timestamp or populate it before observing. The supported lifecycle performs registration, activation, one submission, monitoring and cleanup. On uncertainty use `--action status` plus independent provider/database readback; never repeat run-successor. Use supported `--action close-successor` when cleanup is required.

Success: live terminal traversal/count reconciliation for the exact window; complete physical accounting within caps; independently hash-verified capture; every captured record screened and discoverable with original provenance; original 59 records unchanged; closed authorities, disabled runtime roles, zero memberships/sessions, temporary permissions absent, exact scraper configuration/environment restored and suspension independently verified. Publication NOT_REQUESTED. Failure/unknown coverage remains visible and cannot be labelled success. No replacement run is included.

## Recommendation and remaining requirements

GO for REVIEW of one bounded Bolton live approval. Offline validation is complete; live execution is still held. Live council behaviour, actual Render artifact/startup and fresh runtime qualification remain unverified for this release. Explicit-zero Bolton pages without the existing required evidence still refuse; no empty-result semantics were invented.

The smallest approval covers the pinned owner configuration/code, exact three-function migration, source-branch fast-forward/build/startup, one fixed Bolton registration/activation/submission and independent cleanup. It does not require stop clearance on the observed baseline. It excludes scheduling, details/documents/AI, wider collection and recollection of accepted windows.

Before scheduled restart: recurring single-use issuance and concurrency exclusion; explicit rolling completed-day rule/timezone/overlap; late-arrival and freshness accounting; visible incomplete coverage; owner-level recovery of attempted/uncertain interruptions without source replay; independently reliable closure. Other Greater Manchester councils still need their own reconciled capability/coverage evidence. Stage 4 remains OPEN for REVIEW.
