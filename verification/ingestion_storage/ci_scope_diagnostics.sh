#!/usr/bin/env bash
# CI diagnostics for the kernel memory-scope steps (disposable hosted validation ONLY; no credentials, no production). DIAGNOSTIC ONLY: sourcing this file changes no state, and `assert_killed_scope`
# performs EXACTLY the assertions the steps always made (non-zero exit; systemd Result == oom-kill; ControlGroup empty), then `reset-failed`. What it adds is what the steps never printed: the observed values,
# at the moment of failure and again two and five seconds later (to tell a teardown race from a wrong outcome), the scope's cgroup counters, and kernel OOM messages.
now(){ date -u +%T.%N; }

scope_report(){      # unit [phase]
    local unit=$1 phase=${2:-observed} cg
    echo "== scope report: $unit.scope ($phase) at $(now)"
    sudo systemctl show "$unit.scope" -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup -p MemoryCurrent -p MemoryPeak -p MemoryMax -p MemorySwapMax -p OOMPolicy -p InvocationID 2>&1 || true
    cg=$(sudo systemctl show "$unit.scope" -p ControlGroup --value 2>/dev/null || true)
    if [ -n "$cg" ] && [ -d "/sys/fs/cgroup$cg" ]; then
        for f in memory.events memory.events.local cgroup.events memory.current memory.peak; do echo "-- $cg/$f"; sudo cat "/sys/fs/cgroup$cg/$f" 2>&1 || true; done
    else echo "-- no live cgroup directory for this scope"; fi
}

kernel_report(){
    echo "== kernel messages mentioning oom / killed process / memory cgroup (last 10 minutes) at $(now)"
    sudo journalctl -k --no-pager --since "-10min" 2>&1 | grep -i -E "oom|killed process|memory cgroup" | tail -25 || true
    echo "== dmesg tail"; sudo dmesg 2>&1 | tail -20 || true
    echo "== memory pressure and free memory"; cat /proc/pressure/memory 2>&1 || true; free -m 2>&1 || true
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
}

assert_killed_scope(){      # unit command-exit-status
    local unit=$1 result=$2 observed
    echo "command exit status: $result"
    scope_report "$unit" "after the command"
    if [ "$result" = 0 ]; then echo "ASSERTION FAILED: the command was expected to fail (be killed) but exited 0 at $(now)"; settle_report "$unit"; return 1; fi
    observed=$(sudo systemctl show "$unit.scope" -p Result --value)
    if ! expect_equal "systemd Result" "oom-kill" "$observed"; then settle_report "$unit"; return 1; fi
    observed=$(sudo systemctl show "$unit.scope" -p ControlGroup --value)
    if ! expect_equal "ControlGroup after the kill" "" "$observed"; then settle_report "$unit"; return 1; fi
    sudo systemctl reset-failed "$unit.scope"
}
