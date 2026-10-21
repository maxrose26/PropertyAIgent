# Recurring kernel memory-scope CI failures: tracking (separate from feature work)

Status: **cause NOT established.** This file records facts, labels hypotheses, and fixes only the *diagnostic output*. No assertion was weakened, no retry added, and no step is skipped. Reruns should wait for the diagnostics below to be merged.

## What the steps do
In the `restricted-provisioning` job of `.github/workflows/stage4-discovery-offline.yml`, three steps start a command inside a `systemd-run --scope` with a hard memory ceiling, let it exceed the ceiling, and then assert three things: the command failed; `systemctl show <unit>.scope -p Result` is `oom-kill`; `ControlGroup` is empty (the scope is gone). Units: `propertyaigent-storage-memory-20261017`, `propertyaigent-operational-cleanup-timing-20261018`, `propertyaigent-operational-once`.

## Observed occurrences (facts)
| When | Where | Failing step | Outcome |
|---|---|---|---|
| 20-21 Oct 2026, PR 162, [run 39517067678](https://github.com/maxrose26/PropertyAIgent/actions/runs/39517067678) attempt 1 | restricted-provisioning | "Cleanup actual-memory excess kills entire owned scope" | exit 1 after the scope command; the log shows nothing about which of the three assertions failed |
| same run, attempt 2 (rerun of the failed job, same commit) | restricted-provisioning | "Operational controller and all descendants killed above256MiB" | exit 1; log line `Killed  timeout --kill-after=2s 30s sudo systemd-run ...` |
| same run, attempt 3 | restricted-provisioning | none | passed |
| earlier in this work (before 20 Oct 2026 evening) | various PRs | kernel-kill steps | four earlier intermittent failures were recorded in the session notes; their run ids are not reproduced here and must be filled in from the Actions history |
The same job passed on the unchanged master commit immediately before (23:21-23:29Z on 20 Oct 2026). The failing code paths touch no code changed by those PRs (the steps run kernel/systemd tests only).

## What the steps never printed (the diagnostic gap)
Neither the observed `Result` nor `ControlGroup`, nor any kernel OOM message, so the first failure above cannot be attributed to a specific assertion.
Note: the `Killed` line in attempt 2 is **expected** behaviour, not itself the failure: GNU `timeout` re-raises the signal that terminated its child, so a scope killed by the kernel makes the shell print `Killed` for `timeout`.

## Hypotheses (unverified, for the diagnostics to separate)
* **H1 teardown race:** `Result` or `ControlGroup` is read before systemd has finished tearing the scope down (intermittent by nature).
* **H2 different kill path:** the scope ends by a path other than the cgroup OOM kill (for example `RuntimeMaxSec`, the 30 s `timeout`, or a runner-wide OOM), so `Result` is not `oom-kill`.
* **H3 runner memory pressure or reuse of a unit name** across steps within one job leaves a previous scope's state visible.

## Diagnostic improvement (this change; observation only)
`verification/ingestion_storage/ci_scope_diagnostics.sh`: `assert_killed_scope` performs **exactly the original three assertions** and then `reset-failed`, but first prints the command exit status and the scope's systemd properties and cgroup counters, and on any failure prints the observed values, kernel OOM messages, `dmesg`, memory pressure, and re-observes the scope at +0 s, +2 s and +5 s (a race shows up as a value that changes between the three). A failure-only step reports all three units. The helper is tested under bash with stubbed `systemctl` (`tests/test_ci_kernel_diagnostics.py`).

## Closing criteria
The next failure's output identifies the failing assertion and the observed values. Only then decide between fixing a race in the harness, correcting the expectation, or reporting a runner problem. Do not add retries or loosen an assertion before that.
