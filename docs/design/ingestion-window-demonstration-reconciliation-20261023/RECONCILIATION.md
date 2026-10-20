# Reconciliation note: Bolton window demonstration (hosted run 39510197559)

Status: **reconciliation of a completed run; it changes no original evidence.** Stage 4 remains OPEN. Scheduling, deployment and Stage advancement remain held. Sparse-day coverage remains an explicit unresolved requirement.

All times are UTC on **2026-10-20** (audit timestamps). Run ids, run times and the 14 October observation date come from the GitHub API and the repository's observation record, not from the archive. Names such as `…_20261021`, `…_20261022` and `…_20261023` are identifiers, not dates. The only earlier date used here is the 14 October 2026 observation (run 38538689624, 08:56Z).

## 0. Originals (preserved, unchanged)
The write-protected archive `~/stage4-owner/archive/bolton-window-demonstration-20261023/` holds the original owner audit and final result, the policy-v5 ceremony, both registrations, the sealed hosted artifact and the published branch files. Its `SHA256SUMS` has sha256 `dd72ecf0c299501b78315ce0ab8d7fa6bc55f1a558888d052fa71988ec55e65b`. This note quotes them and corrects nothing in them. The owner's `final-result.json` (below) is **not** edited; it is reconciled against the evidence in section 3.

| Original | sha256 |
|---|---|
| owner `events.jsonl` (191 events, sequence 0–190, chain intact) | `c84ee8b4edad66d224b978403d73800dba4683ddf5d9684a4afe69264fda83c2` |
| owner `final-result.json` | `8f5ec37f94c78c7e004ebd4a6a1ca1b64aa20aa141750aa6522623f05b72085e` |
| policy-v5 ceremony `events.jsonl` / `final-result.json` | `1464ce01669f…` / `b019c9642e0d…` |
| sealed hosted `events.jsonl` / `final-result.json` | `d1289661416b…` / `ed8afa828f36…` |
| hosted `source/worker-result.json` / `source/supervisor.json` | `b3d765e77df3…` / `6ee4453aa121…` |
| branch `capture/source.json` | `5525be5a6b5fc3fdfac43849bc502cd05c0c9023da1440627b975672fe55013a` |
| branch `completed/final-result.json` (provisional) | `d38db9b67dbc8715e9257d040d7dff19c2b759ca6b25393169388d310437ab9e` |
| branch `capture-retained/retained.json` / `screening-authority/registered.json` | `a47122d0bf38…` / `458c50efd3c5…` |

## 1. Provisional versus final
* Branch `completed/final-result.json`: `closure_stage = PUBLISHED_BEFORE_MEMORY_SCOPE_CLOSURE`, `cleanup = PENDING_MEMORY_SCOPE_CLOSURE`. **Provisional.**
* Sealed hosted artifact 12306091257: `closure_stage = FINAL_AFTER_PUBLICATION`, `cleanup = CLOSED`, `publication = PUBLISHED`. **The authority for the hosted half.**
* The owner's `/owner` publication was never made (section 3).

## 2. Operations mapped to evidence

| Claim | Evidence (original, by sequence or file) |
|---|---|
| Policy v5 installed over the exact v4 inventory, derived generation-3 state verified before any change | policy ceremony: inventory `GENERATION2_CAPTURE_POLICY_APPLIED` → `GENERATION3_WINDOW_POLICY_APPLIED`; observed stop digest `ff287601…f39f7b`; control digest `fd055d95…` before = after; capability read back absent; 27 commands, 3/3 connections |
| Fixed read-only owner readback before any grant was clean | owner event 10 (`BEFORE_ANY_GRANT`, 9 statements, no findings, v5 inventory recognised) |
| Transient owner capability absent after registration | owner event 41 (flags all false) |
| Capture allowance registered under the verified baseline | owner events 43–44 (capture key `d1ff23c04af746a5219e7c109255db0310d2a006c732bcac4f66f126b0240545`, grant expiry 23:38:18Z) |
| Hosted checkout was exactly the registered one | sealed hosted `checkout_binding`: revision `b851b358…`, tree `65ef0c4e…`, controller `e4391314…`, manifest `8fb79d78…` (the window manifest), `tracked_files_modified = false` |
| Source contact within the unchanged ceilings | sealed hosted `source_resources`: 6 requests (limit 10), 296,803 bytes (3,000,000), 10.87 s (45), 0 redirects, 0 retries, not capped |
| The window satisfied the existing completeness contract | `worker-result.json`: `enumeration_evidence = COUNT_RECONCILED`; pages (1–10, 11–20, 21–24) of 24 with terminal `EXPLICIT_LAST_EQUALS_TOTAL`; applied interval 2026-09-28 to 2026-10-04; 24 unique references. (The raw audit's own `completeness` and `outcome` fields read `UNKNOWN`: the window audit is a *candidate contract* that never self-certifies; the adapter's admission, which requires `COUNT_RECONCILED`, passed - proved by the `LISTING_RECEIPT_V1` checkpoint of event 88.) |
| Durable retention before the ledger checkpoint | branch `capture/source.json` sha `5525be5a…` equals the owner's `archive_sha256` (event 88) and equals `worker-result.json` byte for byte; retained marker names kind `LISTING_RECEIPT_V1`, capture sha `d5fa9e29bdd51afbf36772e9b08880af6811a8cec771a3335bad0095801445ee` |
| The ledger checkpoint is durable and matches | owner event 88 is emitted only after the database read shows state `COMPLETE`, kind `LISTING_RECEIPT_V1`, an archive record whose sha and path match the branch file, and a marker naming this execution; 24 rows, 5 batches |
| Screening authority registered | owner event 120 (5 batches, 24 children prepared) |
| Screening complete | owner event 163 (database read: 5 of 5 batch items `COMPLETE`, none incomplete); sealed hosted `rows = 24`, `batches = 5`, dispositions 1 `SUPPORTED_PROCESSING_PRIORITY`, 3 `RELATED_APPLICATION_FOLLOW_THROUGH`, 20 `INSUFFICIENT_EVIDENCE`, 24 proposal-usable, 3 citation leads |
| Authorities invalidated with a committed readback | owner event 183 (`readback = CONFIRMED`; revoked: window `_CAPTURE` and `_SCREEN`; none refused) |
| Control state unchanged after invalidation | owner event 188 (`AFTER_INVALIDATION`, no findings): generation 3, manual stop IDOX, global stop intact, 0 unexpired grants |
| Standing credentials, memberships and role settings unchanged | event 188 (roles, memberships, role settings read); owner result `credentials = UNCHANGED…`; 0 credential changes; 0 application writes |
| Owner connection closure | owner `closure_components.connections`: 7 opened, 7 closed, 0 failed attempts |
| Hosted runtime and memory closure | sealed hosted: `cleanup = CLOSED`, 6 runtime slot receipts each 2 connections opened and closed; memory scope removed, 0 survivors, 0 OOM/high/max events, peak 139,751,424 bytes |
| Process closure | owner `closure_components.process`: 0 live children, 0 new sockets, memory scope removed with 0 survivors (original owner result) |
| Outer systemd scope removed after exit | **Not in the archive.** A live observation made after the owner exited (22:49Z): `systemctl --user show propertyaigent-operational-once.scope -p LoadState` = `not-found`, no runner process. Stated as a session observation, not archived evidence |
| Hosted accounting | 22 GitHub invocations (limit 140); stable credential qualification 2 attempts, 4.5 s; active 102 s |
| Owner accounting | 66 commands (limit 80), 7 connections (limit 10), 39 GitHub invocations (limit 180), active 347.8 s |

## 3. The owner's own final record, reconciled (not edited)
The original owner `final-result.json` says `STOP_RECONCILE_NO_RETRY`, `cleanup = UNCERTAIN`, `authority_invalidation = UNCERTAIN_RECONCILE`, `access = UNRECONCILED`, stop reason `RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS`, operation phase `PIPELINE_INVALIDATION`.

What the audit shows happened: event 183 (invalidation confirmed), 188 (clean readback), 189 (`pipeline_owner_result`: a completed, `CLOSED` result with `authority_invalidation = ACKNOWLEDGED_READBACK`, `screening = COMPLETE`) and then event 190 (`stopped`). Between 189 and 190 the owner's next step was its final publication to the evidence branch, and its tail had already closed the memory scope. The unchanged closed-envelope guard denies every GitHub call after closure *before* any request event is written, so there is no `github_intent` event for it: that the publication was the denied call is **inferred** from the code order and the stop reason `RESOURCE_ENVELOPE_CLOSED_NO_MORE_OPERATIONS`, not directly observed. The failure path then replaced the result with an UNCERTAIN one (its closure/invalidation fields reflect that the failure path could make no further operation, not an observed fault).

So the original owner result is a **bookkeeping failure of the final publication ordering**, not an operational failure. Everything in section 2 except the two rows marked as not archived is supported by events written before the failure. Not supported by any later observation: no database or GitHub state was read after event 188 and event 190; the reconciliation therefore does not claim a fresh independent observation of the database after that point. A fresh read-only control observation would be a new privileged action and is not taken here because no specific unresolved fact requires it.

## 4. Fact-versus-claim summary
* **Achieved and evidenced:** the first complete-window capture of Bolton RECEIVED 2026-09-28 to 2026-10-04 (24 references) through the real source, durable retention, queue and source-free screening, under the unchanged completeness contract and ceilings.
* **Not proved by this run:** sparse-day coverage; how Bolton presents other windows; that the count is stable (it was 22 on 14 October and is 24 here).
* **Open:** the owner's publication/closure ordering (corrected offline in the accompanying candidate); the original owner final-result stays as written.
