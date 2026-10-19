#!/usr/bin/env bash
# Privileged, minimal setup of the dedicated cgroup-v2 memory scope for a HOSTED restricted job, then exec of the unprivileged command INSIDE it.
#
# Run as:  env -i <exact environment> sudo -E bash verification/ingestion_storage/hosted_memory_scope.sh <uid> <gid> <command...>
#
# This gives the hosted pipeline the same kernel enforcement the owner-local controller has (verification/ingestion_storage/operational_memory.py): a scope named exactly
# propertyaigent-operational-once.scope with memory.max 1.5 GiB, memory.swap.max 0 and memory.oom.group 1, owned by the unprivileged runner user so the controller can create its own 256 MiB
# and 1 GiB sub-groups. The caller's secrets reach the command only through the environment (never argv, never a file). Exit status is that of the command. If any step cannot be proven the
# script stops BEFORE the command starts (ACTUAL_MEMORY_ENFORCEMENT_UNAVAILABLE) and nothing connects to a database.
set -euo pipefail
[[ $# -ge 3 && "$1" =~ ^[0-9]+$ && "$2" =~ ^[0-9]+$ ]] || { echo 'USAGE: hosted_memory_scope.sh <uid> <gid> <command...>' >&2; exit 2; }
UID_NUM=$1; GID_NUM=$2; shift 2
[[ "$(id -u)" = 0 && "$UID_NUM" != 0 && "$GID_NUM" != 0 ]] || { echo 'ACTUAL_MEMORY_ENFORCEMENT_UNAVAILABLE: privileged start and an unprivileged target are required' >&2; exit 3; }
ROOT=/sys/fs/cgroup
SCOPE=$ROOT/propertyaigent-operational-once.scope
unavailable() { echo "ACTUAL_MEMORY_ENFORCEMENT_UNAVAILABLE: $1" >&2; exit 3; }
[[ "$(stat -f -c %T "$ROOT")" = cgroup2fs ]] || unavailable 'cgroup v2 is not mounted'
grep -qw memory "$ROOT/cgroup.controllers" || unavailable 'the memory controller is not available'
grep -qw memory "$ROOT/cgroup.subtree_control" || echo +memory > "$ROOT/cgroup.subtree_control" || unavailable 'the memory controller cannot be delegated'
[[ ! -e "$SCOPE" ]] || unavailable 'the scope already exists'
mkdir "$SCOPE" || unavailable 'the scope cannot be created'
echo 1610612736 > "$SCOPE/memory.max"
echo 0 > "$SCOPE/memory.swap.max"
echo 1 > "$SCOPE/memory.oom.group"
[[ "$(cat "$SCOPE/memory.max")" = 1610612736 && "$(cat "$SCOPE/memory.swap.max")" = 0 && "$(cat "$SCOPE/memory.oom.group")" = 1 ]] || unavailable 'the limits were not applied'
chown -R "$UID_NUM:$GID_NUM" "$SCOPE"
echo $$ > "$SCOPE/cgroup.procs"     # this shell becomes the SOLE member; exec keeps the pid, so the command starts alone in the scope
[[ "$(cat "$SCOPE/cgroup.procs")" = "$$" ]] || unavailable 'the scope is not exclusive'
exec setpriv --reuid="$UID_NUM" --regid="$GID_NUM" --clear-groups -- "$@"
