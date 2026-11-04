#!/usr/bin/env bash
# Disposable hosted validation ONLY. Never takes credentials or runs production.
set -euo pipefail
test "$(id -u)" = 0
target_uid=$1
target_gid=$2
mode=$3
shift 3
case "$target_uid:$target_gid" in *[!0-9:]*|'0:'*) exit 1;; esac
scope_path=$(sed -n 's/^0:://p' /proc/self/cgroup)
test "${scope_path##*/}" = propertyaigent-storage-memory-20261017.scope
scope=/sys/fs/cgroup$scope_path
test "$(cat "$scope/memory.max")" = 268435456
test "$(cat "$scope/memory.swap.max")" = 0
test "$(cat "$scope/memory.oom.group")" = 1
chown "$target_uid:$target_gid" "$scope" "$scope/cgroup.procs" "$scope/cgroup.subtree_control"
if [ "$mode" = suite ]; then
    mkdir "$scope/supervisor"
    echo $$ > "$scope/supervisor/cgroup.procs"
    echo +memory > "$scope/cgroup.subtree_control"
    mkdir "$scope/tests"
    chown "$target_uid:$target_gid" "$scope/tests" "$scope/tests/cgroup.procs" "$scope/tests/cgroup.subtree_control"
    echo +memory > "$scope/tests/cgroup.subtree_control"
    export INGESTION_TEST_CGROUP_ROOT=$scope/tests
elif [ "$mode" != startup ] && [ "$mode" != excess ]; then
    exit 1
fi
exec setpriv --reuid="$target_uid" --regid="$target_gid" --init-groups "$@"
