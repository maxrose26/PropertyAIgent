# Independent finite metadata rollout review

Status: PASS for exact committed candidate `f2602d3bfcc86e7e459217d52339992e64f2bb4c`, tree `5b35da2516f1a97490bc044ff504c0d64f6bb7d9`. Reviewer verified both identities and clean working tree. No source or database calls, implementation edits or broad test reruns were performed.

Reviewed: metadata_rollout.py; screening_assessment.py generalisation; instrumented_probe.py fixed-window gate; arcus_ui_config.py finite profiles; shared qualify_segment and supervisors; manifest, workflow/template and focused tests.

## Findings

No blocking live-path defect found. Thirteen unique fixed windows contain 401 historically retained identities; the completed Manchester 1–3 October observation is excluded. Current source counts are contextual, not forced historical totals. Salford qualification is job 00 and Rochdale job 01; every later job requires its immediate predecessor job success and explicit GO. Therefore any non-GO, worker error, uncertain accounting, non-CLOSED cleanup, failed artifact upload or failed job halts every successor; no continue-on-error or rerun path is introduced.

Each job binds master revision, workflow revision/content, frozen manifest hash, job/index, previous GO, run number 1 and attempt 1, followed by clean exact checkout. Single-use history and unused authority must still be independently established before dispatch. No registration binding itself establishes factual source success.

Per-job source/outer time, request/byte, source/owned RSS and file/output limits reuse the accepted supervised path. Thirteen jobs enforce aggregate allocation by construction with no borrowing: 1,040 requests, 272,629,760 accounted source bytes, 585 source-worker seconds, 780 outer active seconds, 3,380 setup seconds, 2,080 allocated cleanup seconds and 6,240 combined allocated seconds. Export ceiling is 27,262,976 bytes. Sequential execution prevents concurrent aggregate RSS multiplication. Setup/network dependencies are not included in source byte accounting and must not be reported as total network egress.

The source path validates HTTPS exact council host, fixed detail URL shape/record ID, displayed reference equality and qualified row dates. Salford row dates remain UNKNOWN under its accepted source shape; criteria and pagination still gate enumeration. Council-specific capture qualification is established by the first two non-empty usable-proposal GO observations, not Arcus brand similarity. Empty, truncated, capped or proposal-missing outputs cannot pass full mechanism GO. Optional absent fields remain UNKNOWN without invalidating valid proposal evidence.

No models, documents, detail fan-out, DB interfaces, parent retrieval, new screening policy, scheduling or production persistence are added. Historical comparison cannot establish disappeared-record absence or full completion of the retained 415; unresolved historical identities require explicit reconciliation.

## Follow-up corrections verified

Both initial nonblocking suggestions are addressed in the committed candidate. metadata_rollout.evaluate reconstructs each exact row card, requalifies against the council-specific config and requires full projected-row equality, including host/reference/ID/date and captured fields. Cross-council and changed-proposal negative fixtures test this boundary. The artifact verifier independently recomputes the GO result from the hashed checkpoint and compares every expected decision field. New rollout tests are included in existing offline CI.

No remaining implementation blockers were identified in final review. No further code edits are requested by this review.

## Acceptance limits

Committed JUnit evidence records 170 tests, zero failures/errors/skips; reviewer inspected that evidence and the focused negative tests without rerunning passing suites. This review supports bounded execution suitability only. Parent must complete exact committed-tree identity, required checks, unused execution history, clean checkout, guarded integration and all original authority controls. Live results, citations, resource accounting, artifact/checkpoint integrity and coverage reconciliation remain required after execution. Stage 4 remains OPEN.

Final delta review: compared successor against 71a592bf13d09f2acdbae1ec359cd009d8a0a9df. Only two stale test assumptions and JUnit changed; no runtime/workflow/manifest changes. Date expectations now compare the exact frozen scope instead of assuming all metadata profiles share Manchester dates; registry assertion adds exactly 13 new case keys. Assertions remain restrictive. No blockers.
