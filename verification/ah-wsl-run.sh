#!/usr/bin/env bash
# Isolated AH consumer verification; no PostgreSQL, browser or production inputs.
set -euo pipefail
: "${1:?Pass the exact reviewed candidate SHA}"
candidate="$1"
[[ "$candidate" =~ ^[0-9a-f]{40}$ ]] || { echo 'STOP: require full SHA'; exit 2; }
[ "$(id -u)" != 0 ] || { echo 'STOP: run as your normal Ubuntu user'; exit 2; }
repo=$(git rev-parse --show-toplevel)
venv="$HOME/p0a-work/venv"
for key in $(compgen -e); do
 case "$key" in DATABASE_URL|RENDER*|OPENAI*|ANTHROPIC*|SUPABASE*|PG*|PROPERTYAIGENT_*|P0A_*|PYTHONPATH|PYTHONHOME)
 echo "STOP: inherited $key present; use a clean terminal."; exit 2;; esac
done
path_check="$repo"
while :; do
 [ ! -e "$path_check/.env" ] || { echo 'STOP: ancestor .env present; use a separate clean checkout'; exit 2; }
 [ "$path_check" = / ] && break
 path_check=$(dirname "$path_check")
done
[ -z "$(find "$repo" -name .env -print -quit)" ] || { echo 'STOP: checkout contains .env'; exit 2; }
[ "$(git -C "$repo" rev-parse HEAD)" = "$candidate" ] || { echo 'STOP: wrong commit'; exit 2; }
[ -z "$(git -C "$repo" status --porcelain)" ] || { echo 'STOP: dirty checkout'; exit 2; }
[ -x "$venv/bin/python" ] || { echo 'STOP: existing p0a-work/venv missing; no installation attempted'; exit 2; }
for tool in sudo unshare mount runuser timeout git; do command -v "$tool" >/dev/null; done
baseline=c5b17a0ddb5a088502288bc58935ecc07ba05535
git -C "$repo" cat-file -e "$baseline^{commit}"
output="$HOME/p0a-work/ah-results-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$output"
mkdir "$output/home"
git -C "$repo" worktree add --detach "$output/baseline" "$baseline"
cleanup() { git -C "$repo" worktree remove --force "$output/baseline" >/dev/null 2>&1 || true; }
trap cleanup EXIT
printf '%s\n' "$candidate" > "$output/candidate.txt"
printf '%s\n' "$baseline" > "$output/baseline.txt"
git -C "$repo" status --porcelain > "$output/working-tree-before.txt"
sha256sum "$repo/verification/ah-wsl-run.sh" > "$output/runner.sha256"
set +e
sudo /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
 /usr/bin/timeout --signal=TERM --kill-after=10s 1900s /usr/bin/unshare --mount --net --propagation private -- /bin/bash -c '
 set -euo pipefail
 mount -t sysfs -o nosuid,nodev,noexec sysfs /sys
 exec /usr/sbin/runuser -u "$1" -- /usr/bin/env -i \
 HOME="$3/home" PATH="$4/bin:/usr/bin:/bin" \
 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 DATABASE_URL=sqlite:///:memory: \
 /bin/bash "$2/verification/ah-isolated-checks.sh" "$2" "$3" "$4"
 ' bash "$(id -un)" "$repo" "$output" "$venv" 2>&1 | tee "$output/operator-console.log"
result=${PIPESTATUS[0]}
set -e
printf '%s\n' "$result" > "$output/runner-exit.txt"
git -C "$repo" status --porcelain > "$output/working-tree-after.txt"
cleanup
trap - EXIT
tar -czf "$output.tar.gz" -C "$(dirname "$output")" "$(basename "$output")"
echo "Return this archive: $output.tar.gz"
echo "Runner exit $result; logs require assessment, not release approval."
exit "$result"
