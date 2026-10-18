#!/usr/bin/env bash
# Exact owner-approved diagnostic only. Never run a pipeline or retry.
set -euo pipefail
umask 077
[[ $# = 1 && "$1" =~ ^[a-f0-9]{40}$ ]]

cd "$HOME/stage4-owner/pr122-storage-acceptance"
test -z "$(git status --porcelain)"
test ! -e "$HOME/.local/state/propertyaigent/operational-route-diagnostic-once-20261018"
test ! -e "$HOME/stage4-owner/restricted-connection-diagnostic-registration-20261018.json"
test -x "$HOME/stage4-owner/storage-controller-venv/bin/python"

test "$(timeout 15s gh api repos/maxrose26/PropertyAIgent/git/ref/heads/master --jq .object.sha)" = b9e6bd639ad1f1a472c35f339b70f8f524c08ac4
test "$(timeout 15s gh api repos/maxrose26/PropertyAIgent/git/ref/heads/stage4/narrow-continuation-evidence-20261016 --jq .object.sha)" = "$1"
test "$(timeout 15s gh api "repos/maxrose26/PropertyAIgent/git/commits/$1" --jq '.parents[0].sha')" = eab100b369fc90c8ff5400d473bc06476536f65b

timeout 15s git fetch origin master
test "$(git rev-parse FETCH_HEAD)" = b9e6bd639ad1f1a472c35f339b70f8f524c08ac4
git switch --detach b9e6bd639ad1f1a472c35f339b70f8f524c08ac4
test "$(git rev-parse HEAD)" = b9e6bd639ad1f1a472c35f339b70f8f524c08ac4
test "$(git rev-parse 'HEAD^{tree}')" = a9d28fcf3994d2105c79b15e8f717f752d591e3c
test -z "$(git status --porcelain)"

timeout 15s gh api repos/maxrose26/PropertyAIgent/git/blobs/80eb344ca8589f85cb05e440790fa004222030ee --jq .content |
  base64 --decode > "$HOME/stage4-owner/restricted-connection-diagnostic-registration-20261018.json"
printf '%s  %s\n' \
  396f48d328891b872ee715f2f9cf6a33076620ba852a2fc7a436ec7b5af7cc1c \
  "$HOME/stage4-owner/restricted-connection-diagnostic-registration-20261018.json" |
  sha256sum --check

# Read-only validation, no authentication setup, database or secret-store calls.
"$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; p=Path.home()/"stage4-owner/restricted-connection-diagnostic-registration-20261018.json"; r=validate_registration(p.read_bytes(),"396f48d328891b872ee715f2f9cf6a33076620ba852a2fc7a436ec7b5af7cc1c"); assert r["mode"]=="CONNECTION_DIAGNOSTIC_ONLY"; print("Exact diagnostic binding verified. Expiry: 19 October 2026, 13:00 BST (12:00 UTC).")'

printf '%s\n' \
  'One diagnostic only. No pipeline grant, exception, policy patch or council calls.' \
  'Hidden credential input: maximum five minutes, with no database/secret API operations.' \
  'Active operation: maximum 480 seconds, including 25 seconds diagnostic reserve and five seconds reporting. Outer ceiling: 790 seconds.' \
  'Enter the existing migration credential only at the hidden prompt. Do not paste it into chat.'

set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory \
  -p MemoryMax=1610612736 \
  -p MemorySwapMax=0 \
  -p OOMPolicy=kill \
  -p RuntimeMaxSec=790s \
  "$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B -c \
  'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_module("verification.ingestion_storage.operational_runner",run_name="__main__")' \
  --registration "$HOME/stage4-owner/restricted-connection-diagnostic-registration-20261018.json" \
  --registration-sha256 396f48d328891b872ee715f2f9cf6a33076620ba852a2fc7a436ec7b5af7cc1c
controller_status=$?
printf 'controller_exit_status=%s\n' "$controller_status"

# Local, read-only evidence. A timeout does not repeat the diagnostic.
timeout 3s systemctl --user show propertyaigent-operational-once.scope \
  -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup
scope_status=$?
printf 'scope_readback_exit_status=%s\n' "$scope_status"
for audit_file in events.jsonl final-result.json; do
  path="$HOME/.local/state/propertyaigent/operational-route-diagnostic-once-20261018/$audit_file"
  if test -f "$path"; then sha256sum "$path"; else printf 'evidence_file_absent=%s\n' "$audit_file"; fi
done
exit "$controller_status"
