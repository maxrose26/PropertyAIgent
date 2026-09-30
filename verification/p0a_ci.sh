#!/usr/bin/env bash
# Review draft: no production inputs; no application code before isolation.
set -euo pipefail
repo=$(git rev-parse --show-toplevel)
: "${RUNNER_TEMP:?GitHub disposable runner required}"
[ "$(id -u)" != 0 ]
while IFS= read -r key; do
 case "$key" in DATABASE_URL|RENDER*|OPENAI*|ANTHROPIC*|SUPABASE*|PG*|PROPERTYAIGENT_*|P0A_TEST_POSTGRES_URL)
  echo "Rejected inherited $key"; exit 2;; esac
done < <(compgen -e)
check="$repo"
while :; do
 [ ! -e "$check/.env" ] || { echo 'Rejected repository/ancestor .env'; exit 2; }
 [ "$check" = / ] && break
 check=$(dirname "$check")
done
candidate=$(git rev-parse HEAD)
[ -z "$(git status --porcelain)" ]
git cat-file -e 301a56b3cde781f37e5f5bb0ffaded6537d5ca14^{commit}
output="$RUNNER_TEMP/p0a-results"
mkdir "$output"
printf '%s\n' 'Python 3.12.3; pinned dependency snapshot; matched baseline; no production secrets.' > "$output/environment-decision.txt"
git hash-object verification/p0a_ci.sh > "$output/ci-launcher-blob.txt"
git hash-object .github/workflows/p0a-offline.yml > "$output/workflow-blob.txt"
uname -a > "$output/kernel.txt"
/usr/lib/postgresql/16/bin/postgres --version > "$output/postgres-version.txt"
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
  PATH="$3/p0a-venv/bin:/usr/lib/postgresql/16/bin:/usr/bin:/bin" \
  PLAYWRIGHT_BROWSERS_PATH="$3/p0a-browsers" PYTHONDONTWRITEBYTECODE=1 \
  P0A_EXPECTED_COMMIT="$5" P0A_OUTPUT_DIR="$4" \
  /bin/bash -c '\''cd "$1"; exec bash verification/p0a_gate_a.sh'\'' bash "$6"
 ' bash "$(id -un)" "$HOME" "$RUNNER_TEMP" "$output" "$candidate" "$repo" 2>&1 | tee "$output/operator-console.log"
result=${PIPESTATUS[0]}
set -e
printf '%s\n' "$result" > "$output/runner-exit-code.txt"
# Assessment checks actual XML/errors/skips and known failure messages, not just exit 1.
[ "$result" = 0 ] || [ "$result" = 1 ]
