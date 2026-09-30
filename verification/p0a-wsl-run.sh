#!/usr/bin/env bash
# WSL operator wrapper. Does not modify the frozen candidate runner.
set -euo pipefail
task_root="$HOME/p0a-work"
repo="$task_root/PropertyAIgent"
venv="$task_root/venv"
: "${1:?Pass the exact reviewed candidate SHA}"
candidate="$1"
[[ "$candidate" =~ ^[0-9a-f]{40}$ ]] || { echo "STOP: require full candidate SHA"; exit 2; }
if [ "$(id -u)" = 0 ]; then echo 'Run as your normal Ubuntu user, without sudo.'; exit 2; fi
# Reject, never print values or silently discard production inputs.
while IFS= read -r key; do
 case "$key" in DATABASE_URL|RENDER*|OPENAI*|ANTHROPIC*|SUPABASE*|PG*|PROPERTYAIGENT_*|P0A_TEST_POSTGRES_URL)
  echo "STOP: inherited $key is present; use a clean test terminal."; exit 2;; esac
done < <(compgen -e)
path_check="$repo"
while :; do
 [ ! -e "$path_check/.env" ] || { echo "STOP: .env present at $path_check; do not delete it or use this checkout."; exit 2; }
 [ "$path_check" = / ] && break
 path_check=$(dirname "$path_check")
done
[ "$(git -C "$repo" rev-parse HEAD)" = "$candidate" ] || { echo 'STOP: wrong candidate'; exit 2; }
[ -z "$(git -C "$repo" status --porcelain)" ] || { echo 'STOP: dirty checkout'; exit 2; }
[ "$(git -C "$repo" hash-object verification/p0a_gate_a.sh)" = aa27ee294e57ff87c7aafa58a71b56df1e6336d7 ] || exit 2
[ -x "$venv/bin/python" ] || { echo 'STOP: create the isolated venv first'; exit 2; }
[ -x /usr/lib/postgresql/16/bin/initdb ] || { echo 'STOP: PostgreSQL 16 tools missing'; exit 2; }
for tool in sudo unshare mount ip tini runuser; do command -v "$tool" >/dev/null; done
task_user=$(id -un)
task_home="$HOME"
output="$task_root/results-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$output"
printf '%s\n' 'Python 3.12.3 is accepted for integration verification subject to pinned dependencies and matched baseline; prior evidence used 3.12.14.' > "$output/environment-decision.txt"
# sudo is only for temporary Linux namespaces. PostgreSQL/tests run as task_user.
# Private mounts leave the WSL host mount table and network untouched.
set +e
sudo /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
 /usr/bin/unshare --mount --net --pid --fork --mount-proc --propagation private --kill-child \
 /bin/bash -c '
 set -euo pipefail
 mount -t sysfs -o nosuid,nodev,noexec sysfs /sys
 ip link set lo up
 [ "$(ls /sys/class/net)" = lo ]
 exec /usr/bin/tini -- /usr/sbin/runuser -u "$1" -- /usr/bin/env -i \
  HOME="$2" USER="$1" LOGNAME="$1" \
  PATH="$3/venv/bin:/usr/lib/postgresql/16/bin:/usr/bin:/bin" \
  PLAYWRIGHT_BROWSERS_PATH="$3/browsers" PYTHONDONTWRITEBYTECODE=1 \
  P0A_EXPECTED_COMMIT="$5" P0A_OUTPUT_DIR="$4" \
  /bin/bash -c '\''cd "$1/PropertyAIgent"; exec bash verification/p0a_gate_a.sh'\'' bash "$3"
 ' bash "$task_user" "$task_home" "$task_root" "$output" "$candidate" 2>&1 | tee "$output/operator-console.log"
result=${PIPESTATUS[0]}
set -e
printf '%s\n' "$result" > "$output/runner-exit-code.txt"
tar -czf "$output.tar.gz" -C "$task_root" "$(basename "$output")"
echo "Return this file: $output.tar.gz"
echo "Runner exit $result. Failures/skips require assessment; this script does not approve Gate A."
exit "$result"
