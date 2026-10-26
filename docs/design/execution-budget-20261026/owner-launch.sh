#!/usr/bin/env bash
# THREE_COUNCIL_SOURCE_RELEASE_V2 only. Owner is the sole dispatcher. No automated dispatch or
# database credential input. The scope ceiling comes from the validated V2 manifest (2GiB);
# limits are ceilings, not reserved RAM. V1 registrations use the unchanged V1 launcher.
set -euo pipefail
umask 077
if [ "$#" -ne 3 ]; then
    echo 'Usage: bash owner-launch.sh REGISTRATION.json REGISTRATION_SHA256 REVIEWED_REVISION' >&2
    exit 2
fi
registration=$(realpath "$1")
registration_hash=$2
reviewed_revision=$3
cd "$HOME/stage4-owner/pr122-storage-acceptance"
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$reviewed_revision"
test -x "$HOME/stage4-owner/storage-controller-venv/bin/python"
printf '%s  %s\n' "$registration_hash" "$registration" | sha256sum --check
read -r package_seconds aggregate_bytes < <(PYTHONDONTWRITEBYTECODE=1 "$HOME/stage4-owner/storage-controller-venv/bin/python" - "$registration" <<'PY'
import json,sys
from verification.discovery.four_council_release import validate, SUCCESSOR_V2_VERSION
r=validate(json.load(open(sys.argv[1])))
if r['version']!=SUCCESSOR_V2_VERSION or r['manifest']['limits']['aggregate_memory_bytes']!=2147483648:
    raise SystemExit('V2_REGISTRATION_ONLY')
print(r['manifest']['limits']['package_seconds'], r['manifest']['limits']['aggregate_memory_bytes'])
PY
)
test "$aggregate_bytes" = 2147483648
printf '%s\n' 'One launch; only the exact registered scopes and continuation policy apply.' \
 'No database input. Ctrl+C cancels; never rerun after an uncertain result.'
exec systemd-run --user --scope --unit=propertyaigent-operational-once \
 -p Delegate=memory -p "MemoryMax=${aggregate_bytes}" -p MemorySwapMax=0 -p OOMPolicy=kill \
 -p "RuntimeMaxSec=${package_seconds}s" \
 env PYTHONDONTWRITEBYTECODE=1 \
 "$HOME/stage4-owner/storage-controller-venv/bin/python" \
 -m verification.discovery.four_council_release run \
 --registration "$registration" --registration-sha256 "$registration_hash" \
 --enable-reviewed-source-only-stop-treatment
