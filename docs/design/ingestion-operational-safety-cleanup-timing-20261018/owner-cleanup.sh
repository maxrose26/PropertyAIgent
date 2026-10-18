#!/usr/bin/env bash
set -euo pipefail
umask 077

cd "$HOME/stage4-owner/pr122-storage-acceptance"
test -z "$(git status --porcelain)"
timeout 15s git fetch origin master
test "$(git rev-parse FETCH_HEAD)" = acd3f5690b439d7d91b7a7efb9ace79c9098d303
git switch --detach acd3f5690b439d7d91b7a7efb9ace79c9098d303
test "$(git rev-parse HEAD)" = acd3f5690b439d7d91b7a7efb9ace79c9098d303
test "$(git rev-parse 'HEAD^{tree}')" = 3f07eeb8442ef6fe5bf93907a03c357faf602a72
test -z "$(git status --porcelain)"
test -x "$HOME/stage4-owner/storage-controller-venv/bin/python"
test ! -e "$HOME/.local/state/propertyaigent/operational-safety-cleanup-timing-successor-20261018"
test ! -e "$HOME/stage4-owner/operational-cleanup-timing-registration.json"

timeout 15s gh api \
  repos/maxrose26/PropertyAIgent/git/blobs/f123d34b2f1557ebadf089b3c7be5a063803d388 \
  --jq .content |
  base64 --decode > "$HOME/stage4-owner/operational-cleanup-timing-registration.json"

printf '%s  %s\n' \
  3a1f7e58506d507deb9bf5c1b60c08af8c7a4ea2202785d27344e53d404f696f \
  "$HOME/stage4-owner/operational-cleanup-timing-registration.json" \
  66467e6396fffe6ae4e8a8860f1b22b50a102dbad3814e5d8e4058ca2d72be7b \
  verification/ingestion_storage/operational_cleanup.py |
  sha256sum --check

printf '%s\n' 'Secure input: up to five minutes, no database or secret API calls during input.' \
  'Active cleanup: 45 seconds including finalisation. Pipeline retry remains held.'

set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-cleanup-timing-20261018 \
  -p MemoryMax=268435456 \
  -p MemorySwapMax=0 \
  -p OOMPolicy=kill \
  -p RuntimeMaxSec=355s \
  "$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B -c \
  'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_module("verification.ingestion_storage.operational_cleanup",run_name="__main__")' \
  --registration "$HOME/stage4-owner/operational-cleanup-timing-registration.json" \
  --registration-sha256 3a1f7e58506d507deb9bf5c1b60c08af8c7a4ea2202785d27344e53d404f696f
controller_status=$?
printf 'controller_exit_status=%s\n' "$controller_status"

# Local read-only post-exit evidence only; no DB/secret calls or retry.
timeout 3s systemctl --user show propertyaigent-operational-cleanup-timing-20261018.scope \
  -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup
scope_status=$?
printf 'scope_readback_exit_status=%s\n' "$scope_status"
exit "$controller_status"
