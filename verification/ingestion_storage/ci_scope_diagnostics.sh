#!/usr/bin/env bash
# CI diagnostics for the kernel memory-scope steps (disposable hosted validation ONLY; no credentials, no production). DIAGNOSTIC ONLY: sourcing this file changes no state, and `assert_killed_scope`
# performs EXACTLY the assertions the steps always made (non-zero exit; systemd Result == oom-kill; ControlGroup empty), then `reset-failed`. What it adds is what the steps never printed: the observed values,
# at the moment of failure and again two and five seconds later (to tell a teardown race from a wrong outcome), the scope's cgroup counters, and kernel OOM messages.
# Safe under `bash -e`: every diagnostic command is bounded by `timeout` and can neither abort the step nor hang it, and a failing `systemctl show` is reported and then treated exactly as the original
# `test "$(...)" = ...` treated it (the substitution yields what it printed, normally nothing, and the assertion is judged on that). A failed assertion still returns 1, as the failing `test` did.
DIAG_TIMEOUT_SECONDS=${DIAG_TIMEOUT_SECONDS:-10}
now(){ date -u +%T.%N; }

bounded(){ timeout --kill-after=2s "$DIAG_TIMEOUT_SECONDS" "$@"; }

observe(){      # run a diagnostic command bounded; print its output; report (never propagate) a failure or timeout
    local status=0
    bounded "$@" 2>&1 || status=$?
    if [ "$status" != 0 ]; then echo "(diagnostic '$*' ended with status $status; 124 means it exceeded ${DIAG_TIMEOUT_SECONDS}s)"; fi
    return 0
}

scope_report(){      # unit [phase]
    local unit=$1 phase=${2:-observed} cg
    echo "== scope report: $unit.scope ($phase) at $(now)"
    observe sudo systemctl show "$unit.scope" -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup -p MemoryCurrent -p MemoryPeak -p MemoryMax -p MemorySwapMax -p OOMPolicy -p InvocationID
    cg=$(bounded sudo systemctl show "$unit.scope" -p ControlGroup --value 2>/dev/null || true)
    if [ -n "$cg" ] && [ -d "/sys/fs/cgroup$cg" ]; then
        for f in memory.events memory.events.local cgroup.events memory.current memory.peak; do echo "-- $cg/$f"; observe sudo cat "/sys/fs/cgroup$cg/$f"; done
    else echo "-- no live cgroup directory for this scope"; fi
    return 0
}

kernel_report(){
    echo "== kernel messages mentioning oom / killed process / memory cgroup (last 10 minutes) at $(now)"
    local out status=0
    out=$(bounded sudo journalctl -k --no-pager --since "-10min" 2>&1) || status=$?
    printf '%s\n' "$out" | { grep -i -E "oom|killed process|memory cgroup" || true; } | tail -25 || true
    if [ "$status" != 0 ]; then echo "(journalctl ended with status $status; 124 means it exceeded ${DIAG_TIMEOUT_SECONDS}s)"; fi
    status=0; echo "== dmesg tail"
    out=$(bounded sudo dmesg 2>&1) || status=$?
    printf '%s\n' "$out" | tail -20 || true
    if [ "$status" != 0 ]; then echo "(dmesg ended with status $status; 124 means it exceeded ${DIAG_TIMEOUT_SECONDS}s)"; fi
    echo "== memory pressure and free memory"; observe cat /proc/pressure/memory; observe free -m
    return 0
}

expect_equal(){      # label expected observed
    if [ "$2" = "$3" ]; then echo "ok: $1 = '$3'"; return 0; fi
    echo "ASSERTION FAILED: $1 expected='$2' observed='$3' at $(now)"
    return 1
}

settle_report(){      # unit: the same observation again after short waits, to expose a teardown race
    scope_report "$1" "failure+0s"; kernel_report
    sleep 2; scope_report "$1" "failure+2s"
    sleep 3; scope_report "$1" "failure+5s"
    return 0
}

read_scope_property(){      # unit property -> SCOPE_VALUE and SCOPE_STATUS; never fails the caller
    SCOPE_STATUS=0
    SCOPE_VALUE=$(bounded sudo systemctl show "$1.scope" -p "$2" --value 2>/dev/null) || SCOPE_STATUS=$?
    if [ "$SCOPE_STATUS" != 0 ]; then echo "note: systemctl show $1.scope -p $2 ended with status $SCOPE_STATUS (output '$SCOPE_VALUE'); judged on that output, as the original test did"; fi
    return 0
}

assert_killed_scope(){      # unit command-exit-status
    local unit=$1 result=$2
    echo "command exit status: $result"
    scope_report "$unit" "after the command"
    if [ "$result" = 0 ]; then echo "ASSERTION FAILED: the command was expected to fail (be killed) but exited 0 at $(now)"; settle_report "$unit"; return 1; fi
    read_scope_property "$unit" Result
    if ! expect_equal "systemd Result" "oom-kill" "$SCOPE_VALUE"; then settle_report "$unit"; return 1; fi
    read_scope_property "$unit" ControlGroup
    if ! expect_equal "ControlGroup after the kill" "" "$SCOPE_VALUE"; then settle_report "$unit"; return 1; fi
    sudo systemctl reset-failed "$unit.scope"
}
