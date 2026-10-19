# Stable-credential pipeline — operational decision package (one grouped production proposal; nothing here is authorised or run)

Stage 4 remains OPEN. Storage and the bounded credential qualification (run 39284253302) remain accepted. Server reconciliation and operational acceptance remain outstanding. The Salford global stop (`CONSUMED_SALFORD_GLOBAL_STOP`) and `STORAGE_TEST_STOP` (hard-stop generation 1) are preserved; this package does **not** release either. No merge, registration, production connection, grant, council call, credential change, workflow activation or scheduling has occurred. All historical authorities, audits and IDs 1504–1508 are untouched.

## 1. Candidate
| Item | Value |
|---|---|
| PR | #153 (draft), branch `stage4/stable-pipeline-20261020`, based on `master` `46b9356d352efcde39df9e1505db582543adecee` |
| Tested code state | `57e1b536520a14f00ab1d5bba381ea830aaa10cd`, tree `f8bcf4bb6b2edebe5c77165d9bd59b05c8db9971` (later commits on the branch are documentation only) |
| Specification | `specifications/032-stage4-stable-credential-pipeline.md` |
| Package | `docs/design/ingestion-stable-pipeline-20261020/` (`PACKAGE.md` with the itemised arithmetic and residuals, `owner-run.sh`, `render_registration.py`, `base_constants.json`, `MANIFEST.json`) |
| Restricted job | `.github/workflows/stage4-stable-pipeline-once.yml` (sha256 pinned in the two environment-exclusivity guards: `8e7ed37afc87…`) |
| Hosted checks at the tested head | all pass: offline contract suite, postgres-admission, restricted-provisioning (disposable PG17, real gh: the eight-scenario lifecycle and the loopback probe test), reusable-batch and Oldham exclusivity guards, hosted actual-memory proof, web |

## 2. What it does (and what it cannot)
Two cooperating controllers, kept apart:
* **Owner controller** (`STABLE_PIPELINE_AUTHORITY`, your visible WSL terminal, administrative credential at the 120-second hidden prompt). It never holds the restricted passwords and never changes a credential, membership, role setting or secret. P0 fixed read-only readback → P1 one capture authority + Bolton exception → waits for the restricted job's retained marker and verifies the database checkpoint → P2 one source-free screening authority → waits for the result → P3 **revocation-only** invalidation of both authorities, a readback, a repeated fixed readback and evidence publication.
* **Restricted job** (GitHub Actions, protected environment, the two restricted secrets only, no administrative credential): bounded connection qualification (the reviewed `stable_qualification`, ≤ 6 attempts, read-only) → capture authority check → one source request and durable retention (evidence branch, fast-forward only) → wait for the owner's marker → source-free queued screening → sealed result. Secrets and the job token arrive on stdin only. Kernel-enforced actual memory.

## 3. Evidence
**Complete-lifecycle rehearsal** (disposable PG17, real gh, hosted-job half as a separate process; all eight scenarios pass at the tested head):
| Scenario | Disposition | Fixed reason code | Owner commands / connections |
|---|---|---|---|
| success | capture retained, 60 rows screened (12 batches), both authorities ended, confirmed by readback (`ACKNOWLEDGED_READBACK`), credentials unchanged | — | 73 / 7 |
| idle pooled session | same; the idle backend is reported accurately and is not a leak | — | 73 / 7 |
| active session | nothing issued | `PIPELINE_READBACK_ROLE_SESSION_NOT_IDLE` | 15 / 2 |
| unexpired earlier grant | nothing issued | `PIPELINE_READBACK_UNEXPIRED_GRANT_PRESENT` | 15 / 2 |
| expiry mismatch | nothing issued | `PIPELINE_READBACK_VALID_UNTIL_MISMATCH` | 15 / 2 |
| source request fails | one source call, **no replay**; the capture authority ended; the newer fail-safe stop and generation 2 preserved; unrelated grants untouched | `HOSTED_ENDED_BEFORE_RETENTION` | 38 / 4 |
| screening stops | capture preserved; ended incomplete and reported incomplete; authorities ended | — | 73 / 7 |
| owner wait expires | authority ended | `HOSTED_PUBLICATION_WAIT_EXPIRED` | 38 / 4 |
The reason codes in the table are surfaced by the rehearsal's test wrapper; production exports an uncertain stop as `UNKNOWN` (a recommended follow-up, needs approval).
**Hosted actual-memory proof** (real GitHub-hosted runner, the same `OperationalMemory` class the owner-local runs use): the cgroup-v2 scope is established, exclusive and within limits; a real allocation above the 256 MiB controller limit is killed by the kernel with `oom_kill` ≥ 1; the helper refuses to start the command when it cannot prove the scope. The memory limit files are root-owned and the process runs with `no_new_privs`. **The hosted limit is an actual-memory cgroup ceiling (1.5 GiB aggregate / 256 MiB controller / 1 GiB source, no swap) — not the 3 GiB address-space limit of the earlier qualification, and not the owner-local systemd scope.**
**Defects found by the rehearsals and independent reviews, fixed with regression tests:** the first invalidation was refused after a newer stop (now revocation-only and independent of every stop-state); the placeholder administrative allowance (48) was exhausted by the normal path (52); a change-based publication wait missed a file when a poll saw only a later head (now presence-based, reproduced and fixed); markers were bound only by existence (now bound to the execution and the database checkpoint); revocation was skipped after an uncertain GitHub publication; a second write was possible after an uncertain commit; the scope helper delegated the limit files; secrets were in the process environment. Details in `PACKAGE.md`.
**Independent reviews** (read-only, separate agents): the wait logic and fixture; the whole candidate. Both sets of findings are fixed or disclosed as residuals below.

## 4. Budgets (rehearsal allocations and PROPOSED production limits; none is released authority)
| Boundary | Bound |
|---|---|
| Owner administration | measured 52 commands / 5 connections normal, 73 / 7 through the end, 90 / 9 worst failure; allowances **56 / 80 / 96 commands, 8 / 10 connections** |
| Readback | 9 statements (≤ 12), 1 connection, read-only, no query text, password presence boolean only |
| Owner session | hidden input 120 s; active ≤ 4,380 s; outer ≤ 4,500 s; backstop 4,600 s; registration ≤ 110 min (default 100) |
| Authorities | capture ≤ 55 min (`source_calls=1`), screening ≤ 30 min (`source_calls=0`); both ended at P3 |
| Source | one observation; ≤ 10 requests, ≤ 3,000,000 received bytes, ≤ 6 pages, ≤ 60 rows (owner caps rows itself); screening 0 source requests |
| Restricted runtime | ≤ 1,040 driver statements, ≤ 40 connections, ≤ 300 s aggregate + the qualification allowance (≤ 6 attempts, ≤ 330 s) |
| Hosted job | 40-minute limit, hard kill 2,100 s |
| GitHub requests | owner worst case **166 of 180** (itemised in `PACKAGE.md`), hosted ≤ 140 |
| Evidence | combined output closure reserve as accepted; sealed chain published |

## 5. The exception requested
Two authorities, both executed by the restricted worker login only (`ingestion_worker_login` / `ingestion_effect_login`), both under the **unchanged** stops (global Salford stop, `STORAGE_TEST_STOP`, generation 1), each ended by the owner:
1. `AUTHORISE_INGESTION_STABLE_PIPELINE_AUTHORITY_ONCE_20261020_CAPTURE`: Bolton, `RECEIVED`, 16 October 2026, transport `REQUESTS_IDOX`, `source_calls = 1`, `writes = 0`, ≤ 55 minutes, worker `required_once`, bound to the single capture root item. A Bolton exception is registered for it (the existing owner step).
2. `AUTHORISE_INGESTION_STABLE_PIPELINE_AUTHORITY_ONCE_20261020_SCREEN`: `source_calls = 0`, `writes = 0`, ≤ 30 minutes, bound to the batch items, the capture root and the prepared screening children (≤ 60) of that one capture. A Bolton exception is registered for it as the existing owner step requires; enforcement is the grant's `source_calls = 0`.
Nothing clears or alters either stop. A failed source request makes the accepted fail-safe raise a newer stop (replacing the manual stop, generation 2); the invalidation preserves it and the owner reconciles it.

## 6. Retained-access disposition
The two standing restricted logins (qualified; valid until `2027-01-17T16:14:12+00:00`; memberships, role settings and secrets as provisioned) are **unchanged by every path** of this pipeline. A pipeline failure ends only the execution authority; ending the standing credentials is the separately registered `STABLE_CREDENTIAL_REVOCATION` (its earlier registration is bound to the pre-merge revision and expired unused; a fresh one is rendered for the integrated revision when needed). Expiry is not automatic renewal; there is no rotation.

## 7. Remaining limitations and implementation gaps
* Terminal loss: no revocation runs; authorities lapse at their own expiry (≤ 55 / 30 minutes). Failure window 60 s: a slow database can abort the 12-statement invalidation before COMMIT (reported `UNCERTAIN_RECONCILE`).
* A hosted run on the wrong revision is caught only after the single source call is spent (the workflow pins revision, ref and run number; the owner then ends the authority).
* The job token has `contents: write` on the repository; confinement is by code (branch constant, path allow-list, fast-forward only, size bounds), disclosed in specification §6.
* The restricted job reaches the council from a GitHub-hosted address; the earlier council runs were owner-local. **Not tested** (no source call is authorised): whether the council serves the hosted address.
* Whether the migration identity holds `pg_read_all_stats` on the managed server is unproven (the evidence is that earlier teardown reads saw the sessions). The fixed readback requires it and stops, issuing nothing, if the sessions are not observable.
* Production exports an uncertain stop as `UNKNOWN`; surfacing the fixed code is a recommended follow-up.
* The worker's first connection after a long idle period was rejected once and succeeded 20 s later (cause not established); the pipeline repeats the reviewed bounded qualification before any work.
* Server-side closure of the hosted job's sessions is confirmed by the owner's final readback; client closure is the job's own receipts. Expiry never terminates a session.
* Offline-only: the package has run only against the disposable server and loopback fixtures.

## 8. One grouped production proposal (for decision; nothing starts without it)
**Decisions requested:** (a) accept the residuals above, in particular the repository-wide job token, the hosted-to-council uncertainty and terminal loss; (b) accept the Bolton exceptions in §5 under the unchanged stops; (c) accept the possible provider-side SCRAM-verifier retention for the existing credential pair for this run (already accepted for the standing pair; re-bind to this run); (d) approve the proposed limits in §4 as the production limits; (e) approve integration of PR #153 as a guarded `[skip render]` merge.
**If approved, in order:** (1) merge PR #153; verify `master` HEAD, tree and executable hashes; post-merge checks. (2) Render **one** pipeline registration (≤ 110 minutes, default 100) and **one** fresh revocation registration, both bound to the integrated revision and tree and the evidence head; validate both offline. (3) You run, in your own visible WSL terminal (keyring sign-in, then the owner script; the migration credential only at the hidden prompt):
```bash
source ~/stage4-owner/linux-gh-keyring-login.sh
bash ~/stage4-owner/probe-checkout/docs/design/ingestion-stable-pipeline-20261020/owner-run.sh <integrated-commit> <integrated-tree> <pipeline-registration-sha256>
```
and keep the terminal open until it prints `controller_exit_status`. (4) After the owner audit records the capture authority, I dispatch the restricted workflow **once** (run 1 / attempt 1, inputs: the integrated commit, the registered evidence head, the hosted authority) and you approve the protected environment. (5) I verify the artifact, the evidence-branch publications and the owner audit; the owner's final readback is the server-side check of sessions, grants, stops and standing credentials. (6) Standing credentials: revoke or keep, your decision (the separately registered revocation is ready).
**Not authorised by any of this:** rotation, scheduling, further councils, application writes, unit facts, stop release, Stage advancement.
