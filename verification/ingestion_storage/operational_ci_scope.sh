#!/usr/bin/env bash
# Disposable kernel validation only; no production credentials.
set -euo pipefail
test "$(id -u)" = 0
target_uid=$1
target_gid=$2
shift 2
case "$target_uid:$target_gid" in *[!0-9:]*|'0:'*) exit 1;; esac
scope_path=$(sed -n 's/^0:://p' /proc/self/cgroup)
test "${scope_path##*/}" = propertyaigent-operational-once.scope
scope=/sys/fs/cgroup$scope_path
test "$(cat "$scope/memory.max")" = 1610612736
test "$(cat "$scope/memory.swap.max")" = 0
test "$(cat "$scope/memory.oom.group")" = 1
chown "$target_uid:$target_gid" "$scope" "$scope/cgroup.procs" "$scope/cgroup.subtree_control"
exec setpriv --reuid="$target_uid" --regid="$target_gid" --init-groups "$@"
