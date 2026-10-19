# Stable-credential pipeline — final operational decision package (one grouped production proposal; nothing here is authorised or run)

Stage 4 remains OPEN. Storage and the bounded credential qualification (run 39284253302) remain accepted. Server reconciliation and operational acceptance remain outstanding. The Salford global stop (`CONSUMED_SALFORD_GLOBAL_STOP`) and `STORAGE_TEST_STOP` (hard-stop generation 1) are preserved; this package does **not** release either. No merge, registration, production connection, grant, council call, credential change, workflow activation or scheduling has occurred. All historical authorities, audits and IDs 1504–1508 are untouched.

## 1. Candidate (exact state to be approved)
| Item | Value |
|---|---|
| PR | #153 (draft), branch `stage4/stable-pipeline-20261020`, based on `master` `46b9356d352efcde39df9e1505db582543adecee` |
| **Tested head** | commit `d5d855330fb8eeb01836db76647ecfd5f11b46b6`, tree `729e2f3f41fe839df8c25c2a502f5bd58b552bbf` |
| Previous tested head (superseded) | `57e1b536520a14f00ab1d5bba381ea830aaa10cd` / tree `f8bcf4bb6b2edebe5c77165d9bd59b05c8db9971` (eight-scenario rehearsal passed there) |
| This delta (`57e1b536`→`d5d85533`, apart from the documentation commit `f23ed211`) | hosted checkout/executable binding check before any source request; fixed stop reason exported; two new rehearsal scenarios; tests |
| Specification | `specifications/032-stage4-stable-credential-pipeline.md` |
| Restricted job | `.github/workflows/stage4-stable-pipeline-once.yml` (unchanged by this delta; sha256 `8e7ed37afc870ed993bcd6aae8e4b1f59982309ae188926d1d9d25343d577b20`, pinned in the two exclusivity guards) |
| Hosted checks at the tested head | all pass: offline contract suite (203 passed, 1 skipped), restricted-provisioning (disposable PG17, real gh: 12 passed — the **ten**-scenario lifecycle plus the loopback probe tests), reusable-batch and Oldham exclusivity guards, hosted actual-memory proof, web |
| Approval applies only to this exact state; any material change needs fresh approval. This package is documentation committed after the tested head and does not change code. |

## 2. What changed in this delta
1. **Checkout binding before any source request.** Immediately after the worker's capture-authority check, the hosted job reads the capture grant's registered `execution_binding` (revision, controller sha256, manifest sha256) and compares it with what it is *actually running*: the checked-out commit (`git rev-parse HEAD`), the commit the workflow pinned, the hash of the loaded controller module, the hash of the package manifest, and clean tracked files. Any mismatch raises `CHECKOUT_BINDING_MISMATCH` **before** `capture_once`: zero source requests; the owner sees the job end before retention and revokes both authorities. All owner-side checks (marker/result identity, checkpoint digests, invalidation bindings) are unchanged.
2. **Fixed stop reason exported.** Results now carry `stop_reason` (owner and hosted). It is the controller's own fixed code and only when the exception is a controller-owned class whose *entire message* is a code, or one of five listed bound codes. Library exceptions, free text and anything else give `null` and the failure stays `UNKNOWN`; classification and `UNCERTAIN` status are unchanged and no exception text is exported.
3. **Tests.** Unit tests for exact-state acceptance (wrong revision, controller hash, manifest hash, modified tracked file, missing evidence, pinned-commit mismatch, extra binding keys) and for the stop-reason export rules; two rehearsal scenarios, `wrong_revision` and `wrong_executable`, asserting zero source calls, `CHECKOUT_BINDING_MISMATCH`, and authorities ended by readback.

## 3. Evidence
The full lifecycle was **repeated** (the change affects the hosted half of it). At `d5d85533` all ten scenarios pass on a disposable PG17 with real gh and a separately spawned hosted process:
| Scenario | Disposition | Fixed reason | Owner commands / connections |
|---|---|---|---|
| success | capture retained, 60 rows screened, both authorities ended, readback confirmed, credentials unchanged | — | 73 / 7 |
| idle pooled session | same; idle backend reported, not a leak | — | 73 / 7 |
| active session | nothing issued | `PIPELINE_READBACK_ROLE_SESSION_NOT_IDLE` | 15 / 2 |
| unexpired earlier grant | nothing issued | `PIPELINE_READBACK_UNEXPIRED_GRANT_PRESENT` | 15 / 2 |
| expiry mismatch | nothing issued | `PIPELINE_READBACK_VALID_UNTIL_MISMATCH` | 15 / 2 |
| source request fails | one call, no replay, authority ended, newer stop preserved | `HOSTED_ENDED_BEFORE_RETENTION` (owner) | 38 / 4 |
| screening stops | capture preserved, reported incomplete, authorities ended | — | 73 / 7 |
| owner wait expires | authority ended | `HOSTED_PUBLICATION_WAIT_EXPIRED` | 38 / 4 |
| **wrong revision** | **zero source calls**; hosted `CHECKOUT_BINDING_MISMATCH`; authorities ended | `CHECKOUT_BINDING_MISMATCH` | 38 / 4 |
| **wrong executable** | **zero source calls**; same | `CHECKOUT_BINDING_MISMATCH` | 38 / 4 |
Honest history of this delta: the first CI run on the delta failed all success-path scenarios because of a defect **in my rehearsal probe** (string quoting lost by my own edit → `NameError` in the checkout check, reported as `UNKNOWN`/`NOT_A_FIXED_CODE`); it was a test-code bug, not a production defect, and was fixed in `d5d85533` (test file only). Independent review (read-only) found that same wiring defect (HIGH, fixed), and disclosed the residuals in §6.
Hosted actual-memory proof, earlier evidence and defects found/fixed in the previous rounds are unchanged (see `PACKAGE.md`). The reason codes in the table beyond `CHECKOUT_BINDING_MISMATCH` are surfaced by the rehearsal wrapper as before; production now exports `stop_reason` for them too.

## 4. Final numerical limits and request arithmetic (proposed production limits; none is released authority)
| Boundary | Limit |
|---|---|
| Owner administration | **56 / 80 / 96 commands** (normal / through end / failure; measured 52 / 73 / 90), **8 / 10 connections** (measured 5 / 7 / 9) |
| Readback | 9 statements (≤ 12), 1 connection, read-only, no query text, password presence boolean only |
| Owner session | hidden input 120 s; active ≤ 4,380 s; outer ≤ 4,500 s; backstop 4,600 s; registration ≤ 110 min (default 100) |
| Authorities | capture ≤ 55 min (`source_calls=1`), screening ≤ 30 min (`source_calls=0`); ended at P3 |
| Source | one observation; ≤ 10 requests, ≤ 3,000,000 received bytes, ≤ 6 pages, ≤ 60 rows (owner caps rows itself) |
| Restricted runtime | ≤ 1,040 driver statements, ≤ 40 connections, ≤ 300 s aggregate + qualification (≤ 6 attempts, ≤ 330 s); the capture-authority/binding check is one extra worker connection with 2 statements inside its own 24-statement budget |
| Hosted job | 40-minute limit, hard kill 2,100 s; memory 1.5 GiB / 256 MiB controller / 1 GiB source, no swap |
| Waits | capture 2,700 s at 30 s; screening 600 s at 30 s (owner); hosted marker wait 480 s at 15 s |

**Owner commands** (52 normal): readback 9 + capture registration 11 + ledger read 5 + screening registration (12 batches of 5 rows) 22 + ledger read 5 = 52 on 5 connections; + revocation-only invalidation with readback 12 + final readback 9 = 73 on 7; failure after the normal path adds invalidation 12 + diagnostics 7 and the connections already used = 90 on 9. Allowances add 4 / 7 / 6.
**Owner GitHub requests — worst case 166 of 180**: account check 1; freshness check 5; capture wait 91 ref reads + 18 file examinations = 109; archive probe and marker re-read 2; screening marker publication 8; result wait 21 ref reads + 9 = 30; owner evidence publication 10; failure-path secret-name read 1 → 166. This delta adds **no** GitHub requests.
**Hosted GitHub requests — bound 140, modelled about 71 (not measured on the real job)**: evidence anchor 1; owner-marker wait 480 s / 15 s = 32 + 1 boundary ref reads and up to 9 file examinations = 42; three publications (archive, retained marker, result) ≈ 8 each = 24; a few readbacks ≈ 4. This delta adds no GitHub requests.

## 5. Standing credentials, execution grants and Bolton exceptions — three separate things
| | Standing restricted credentials | Execution grants (authorities) | Bolton exceptions |
|---|---|---|---|
| What | `ingestion_worker_login`, `ingestion_effect_login` (provisioned, qualified) | `…STABLE_PIPELINE_AUTHORITY_ONCE_20261020_CAPTURE` and `…_SCREEN` | one per grant, transport `REQUESTS_IDOX`, bound to the grant's binding |
| Purpose | the identities that may connect | what the run is permitted to do: capture `source_calls=1`, ≤ 55 min; screening `source_calls=0`, ≤ 30 min | the existing owner step that permits the single Bolton source observation under the unchanged stops |
| Created by | earlier provisioning (credential change — not part of this run) | owner registration at P1/P2 | owner registration at P1/P2 |
| Lifetime | valid until `2027-01-17T16:14:12+00:00` | ended by the owner at P3 (expiry values set to 0, revocation-only); otherwise lapse at 55 / 30 min | ended with its grant |
| Changed by this pipeline? | **never** (memberships, role settings, secrets, expiry all unchanged on every path; checked by the fixed readbacks) | yes — this is the only thing the pipeline creates and ends | yes — same |
| Ending them | separately registered `STABLE_CREDENTIAL_REVOCATION` (fresh registration for the integrated revision when wanted) | automatic at P3 | automatic at P3 |
Stops are never altered: Salford global stop and `STORAGE_TEST_STOP` (generation 1) remain; a failed source request makes the accepted fail-safe raise a newer stop, which invalidation preserves for owner reconciliation.

## 6. Residuals and their practical consequence
| Residual | Practical consequence |
|---|---|
| Terminal loss (no signal handler; backstop 4,600 s) | If the owner terminal closes, no revocation runs; the authorities simply lapse at their own expiry (≤ 55 / 30 min). Keep the terminal open until `controller_exit_status`. |
| Failure window 60 s | A very slow database during the 12-statement invalidation could roll back; reported `UNCERTAIN_RECONCILE`; authority then ends at expiry. |
| **Checkout check scope** (new, from review) | The check runs after modules are loaded and hashes the controller and manifest only; other modules rely on clean-tracked-files. An *untracked* file shadowing an import, or skip-worktree/assume-unchanged files, would not be caught. Acceptable because the hosted job uses a fresh pinned clone and the workflow pins the commit; not a substitute for the owner's marker/head checks. |
| **Binding mismatch earlier detected** | The old residual (mismatch seen only after the source call) is **closed for the hosted checkout**; an evidence head that moved is still caught by the head guards. |
| Job token `contents: write` | A bug or compromise in the hosted job could write to the repository; confinement is by code (branch constant, path allow-list, fast-forward only). |
| Hosted-to-council reachability | The council may refuse the GitHub-hosted address; the one authorised call would be spent and the run would stop (no replay). Untested because no source call is authorised. |
| `pg_read_all_stats` unproven | If the migration identity cannot see sessions, the fixed readback stops and **nothing is issued**. |
| Retention SCRAM verifier (provider side) | Possible retention of the verifier for the existing pair; already accepted for the standing pair; re-bind to this run. |
| First worker connection after idle was rejected once | The pipeline repeats the reviewed bounded qualification (≤ 6 attempts) before any work. |
| Stop-reason module allowlist | Any class under the controller packages whose whole message is an all-caps code would be exported; no secrets are placed in such messages. |
| Local verification gap | The local WSL environment has no PostgreSQL; the lifecycle runs only in CI on a disposable server. 10 known environment-only local failures exist in older tests. |

## 7. Recommendation and one grouped production decision
**Recommendation: approve, with the checkout-scope residual accepted.** The exact tested state `d5d85533` has passed every check; the corrections close the main remaining residual (an unapproved checkout can no longer spend the one source request) and make stops explainable.
**Decisions requested:** (a) accept the residuals in §6; (b) accept the two Bolton exceptions (§5) under the unchanged stops; (c) accept the provider-side SCRAM-verifier retention for this run; (d) approve the §4 limits as production limits; (e) approve integration of PR #153 as a guarded `[skip render]` merge.
**If approved, in order:** (1) merge PR #153; verify `master` HEAD, tree, deployed SHA and production-reported SHA agree; post-merge checks. (2) Render **one** pipeline registration (≤ 110 minutes, default 100) and **one** fresh revocation registration bound to the integrated revision, tree and evidence head; validate offline. (3) You run, in your own visible WSL terminal (keyring sign-in, then the owner script; the migration credential only at the hidden prompt):
```bash
source ~/stage4-owner/linux-gh-keyring-login.sh
bash ~/stage4-owner/probe-checkout/docs/design/ingestion-stable-pipeline-20261020/owner-run.sh <integrated-commit> <integrated-tree> <pipeline-registration-sha256>
```
and keep the terminal open until it prints `controller_exit_status`. (4) After the owner audit records the capture authority, I dispatch the restricted workflow **once** (run 1 / attempt 1) and you approve the protected environment. (5) I verify the artifact, evidence publications and the owner audit. (6) Standing credentials: revoke or keep — your decision.
**Not authorised by any of this:** rotation, scheduling, further councils, application writes, unit facts, stop release, Stage advancement.
