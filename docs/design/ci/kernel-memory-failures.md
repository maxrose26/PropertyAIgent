# Recurring kernel memory-scope CI failures: tracking (separate from feature work)

Status: **cause NOT established.** This file records facts, labels hypotheses, and fixes only the *diagnostic output*. No assertion was weakened, no retry added, and no step is skipped. Reruns should wait for the diagnostics below to be merged.

## What the steps do
In the `restricted-provisioning` job of `.github/workflows/stage4-discovery-offline.yml`, three steps start a command inside a `systemd-run --scope` with a hard memory ceiling, let it exceed the ceiling, and then assert three things: the command failed; `systemctl show <unit>.scope -p Result` is `oom-kill`; `ControlGroup` is empty (the scope is gone). Units: `propertyaigent-storage-memory-20261017`, `propertyaigent-operational-cleanup-timing-20261018`, `propertyaigent-operational-once`.

## Observed occurrences (facts, from the Actions history of `stage4-discovery-offline.yml`)
Seven failures of a kernel-kill step have been found. Each of the 37 failed runs of this workflow created since 19 Oct 2026 (plus the earlier attempts of the PR 162 run) was checked for the failing step, matching step names containing kill / excess / terminat / memory; the other failures were in other steps (stable pipeline lifecycle, wrapper, connection matrix, driver diagnostics) and are not part of this note.
| When (UTC) | Run | Commit | Failing step | Outcome |
|---|---|---|---|---|
| 19 Oct 19:34 | [39312077249](https://github.com/maxrose26/PropertyAIgent/actions/runs/39312077249) (`stage4/stable-pipeline-20261020`) | `ba7a3ede` | "Operational controller and all descendants killed above256MiB" | failed; the commit was followed by further commits, so no same-commit rerun exists |
| 19 Oct 21:15 | [39326097707](https://github.com/maxrose26/PropertyAIgent/actions/runs/39326097707) (`stage4/stable-pipeline-20261020`) | `0db52d35` | "Whole-scope excessive memory terminates and cleans up" | failed (attempt 2 of that run) |
| 20 Oct 08:01 | [39390449075](https://github.com/maxrose26/PropertyAIgent/actions/runs/39390449075) (`stage4/pipeline-publication-correction-20261020`) | `9c96da81` | "Cleanup actual-memory excess kills entire owned scope" | failed |
| 20 Oct 08:37 | [39394772967](https://github.com/maxrose26/PropertyAIgent/actions/runs/39394772967) (`stage4/control-observer-and-probe-20261021`) | `e786e51c` | "Operational controller and all descendants killed above256MiB" | failed |
| 20 Oct 23:45 | [39517067678](https://github.com/maxrose26/PropertyAIgent/actions/runs/39517067678) attempt 1 (PR 162) | `895976c6` | "Cleanup actual-memory excess kills entire owned scope" | failed |
| 20 Oct 23:54 | same run, attempt 2 (rerun of the failed job, same commit) | `895976c6` | "Operational controller and all descendants killed above256MiB" | failed; log line `Killed  timeout --kill-after=2s 30s sudo systemd-run ...` |
| 21 Oct 00:03 | same run, attempt 3 | `895976c6` | none | passed |
| 21 Oct 13:09 | [39604379295](https://github.com/maxrose26/PropertyAIgent/actions/runs/39604379295) attempt 1 (post-merge CI of PR 169 on master `431c0471`; first attempt, never rerun) | `431c0471` | "Operational controller and all descendants killed above256MiB" | **failed; preserved as evidence.** The merge commit's tree (`c709968b`) is byte-identical to the PR head `de4115ca` whose run passed all seven checks minutes earlier. Log: `Killed` for the `timeout ... sudo systemd-run` line, then exit 1 on the first assertion block. The assertions that failed are not identified (this change adds the printing). **Cause: not established.** |
Correction: an earlier session note said four earlier failures; that was right. Four step failures precede PR 162 (the first four rows above) and two more occurred on PR 162's own run. An earlier draft of this table listed only three before PR 162 and said four was wrong; that draft missed run 39326097707. The same job passed on other commits between these failures, and on the unchanged master commit immediately before PR 162 (23:21-23:29Z on 20 Oct). The failing code paths touch no code changed by those PRs (the steps run kernel/systemd tests only). Four different steps have failed, none consistently.

## What the steps never printed (the diagnostic gap)
Neither the observed `Result` nor `ControlGroup`, nor any kernel OOM message, so the first failure above cannot be attributed to a specific assertion.
Note: the `Killed` line in attempt 2 is **expected** behaviour, not itself the failure: GNU `timeout` re-raises the signal that terminated its child, so a scope killed by the kernel makes the shell print `Killed` for `timeout`.

## Hypotheses (unverified, for the diagnostics to separate)
The 30 s `timeout --kill-after=2s` around the scope command is itself a candidate: if the command did not die from the memory limit within 30 s, `timeout` would terminate it, the shell would print `Killed` or a non-zero status exactly as for an OOM kill, and `Result` would not be `oom-kill`. The `Killed timeout ...` line therefore **fits** an OOM kill but does **not prove** one, and it does not rule out the timeout firing.
* **H1 teardown race:** `Result` or `ControlGroup` is read before systemd has finished tearing the scope down (intermittent by nature).
* **H2 different kill path:** the scope ends by a path other than the cgroup OOM kill (for example `RuntimeMaxSec`, the 30 s `timeout` expiring, or a runner-wide OOM), so `Result` is not `oom-kill`.
* **H3 runner memory pressure or reuse of a unit name** across steps within one job leaves a previous scope's state visible.

## Diagnostic improvement (this change; observation only)
`verification/ingestion_storage/ci_scope_diagnostics.sh`: `assert_killed_scope` performs **exactly the original three assertions** and then `reset-failed`, but first prints the command exit status and the scope's systemd properties and cgroup counters, and on any failure prints the observed values, kernel OOM messages, `dmesg`, memory pressure, and re-observes the scope at +0 s, +2 s and +5 s (a race shows up as a value that changes between the three). A failure-only step reports all three units.
* **Survives errors:** every diagnostic command is run through `observe`, which reports a non-zero status instead of propagating it, so nothing can abort the step under `bash -e` / `pipefail` before the report is complete. A failing `systemctl show` in the assertion path is reported and then judged on its output exactly as the original `test "$(...)" = ...` was (an empty `Result` fails; an empty `ControlGroup` passes). A failed assertion still returns **1**, the status the failing `test` produced.
* **Bounded:** every diagnostic command, and the assertion's two `systemctl show` reads, run under `timeout --kill-after=2s ${DIAG_TIMEOUT_SECONDS:-10}`; a timeout is reported as status 124. The only unbounded commands are the original ones (`reset-failed`, the scope command itself, which keeps its 30 s `timeout`).
* **Tested under CI's shell options:** `tests/test_ci_kernel_diagnostics.py` runs the helper with `bash --noprofile --norc -eo pipefail` against fake `sudo`/`systemctl`/`journalctl`/`dmesg`/`free` executables on `PATH` (so the real `timeout` is used), covering a failing and a hanging `systemctl show`, failing and hanging kernel commands, and unchanged assertion outcomes.

## Closing criteria
The next failure's output identifies the failing assertion and the observed values. Only then decide between fixing a race in the harness, correcting the expectation, or reporting a runner problem. Do not add retries or loosen an assertion before that.

## Record rule
A later passing revision does not erase or explain an earlier failure. Run 39604379295 stays recorded as a failure of the unchanged code; no rerun was made before these diagnostics existed. The next failure's output, not this note, is what can identify the cause.
