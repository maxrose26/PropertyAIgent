#!/usr/bin/env bash
# Owner is the sole dispatcher. No automated dispatch or database credential input.
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
printf '%s\n' 'One launch; four scopes maximum. Bury UNKNOWN stops all later scopes.' \
 'No database input. Ctrl+C cancels; never rerun after an uncertain result.'
exec systemd-run --user --scope --unit=propertyaigent-operational-once \
 -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill \
 -p RuntimeMaxSec=1920s \
 env PYTHONDONTWRITEBYTECODE=1 \
 "$HOME/stage4-owner/storage-controller-venv/bin/python" \
 -m verification.discovery.four_council_release run \
 --registration "$registration" --registration-sha256 "$registration_hash" \
 --enable-reviewed-source-only-stop-treatment
