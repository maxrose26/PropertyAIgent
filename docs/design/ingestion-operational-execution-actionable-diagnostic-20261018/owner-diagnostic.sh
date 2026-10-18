#!/usr/bin/env bash
# Exact owner-approved diagnostic only. Never run a pipeline or retry.
set -euo pipefail
umask 077
[[ $# = 1 && "$1" =~ ^[a-f0-9]{40}$ ]]

cd "$HOME/stage4-owner/pr122-storage-acceptance"
test -z "$(git status --porcelain)"
test ! -e "$HOME/.local/state/propertyaigent/operational-actionable-diagnostic-once-20261018"
test ! -e "$HOME/stage4-owner/actionable-connection-diagnostic-registration-20261018.json"
test -x "$HOME/stage4-owner/storage-controller-venv/bin/python"

test "$(timeout 15s gh api repos/maxrose26/PropertyAIgent/git/ref/heads/master --jq .object.sha)" = 3113e0155ef29b344a44ff0483045f38b666afb0
test "$(timeout 15s gh api repos/maxrose26/PropertyAIgent/git/ref/heads/stage4/narrow-continuation-evidence-20261016 --jq .object.sha)" = "$1"
test "$(timeout 15s gh api "repos/maxrose26/PropertyAIgent/git/commits/$1" --jq '.parents[0].sha')" = 016669e58ecd65faf3163d2ae89b3dc9d615300c

timeout 15s git fetch origin master
test "$(git rev-parse FETCH_HEAD)" = 3113e0155ef29b344a44ff0483045f38b666afb0
git switch --detach 3113e0155ef29b344a44ff0483045f38b666afb0
test "$(git rev-parse HEAD)" = 3113e0155ef29b344a44ff0483045f38b666afb0
test "$(git rev-parse 'HEAD^{tree}')" = 0c51773453e9c88aca2ad25b7cf2c194e0acdade
test -z "$(git status --porcelain)"

timeout 15s gh api repos/maxrose26/PropertyAIgent/git/blobs/84468532c7b720d32767bbfdf0dd326a493cec85 --jq .content |
  base64 --decode > "$HOME/stage4-owner/actionable-connection-diagnostic-registration-20261018.json"
printf '%s  %s\n' \
  76e9a1dced8a6a4aa148e140e2eba719d7b37fad38a93ac1f942b109ddbdfbe2 \
  "$HOME/stage4-owner/actionable-connection-diagnostic-registration-20261018.json" |
  sha256sum --check

# Read-only validation, no authentication setup, database or secret-store calls.
"$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; p=Path.home()/"stage4-owner/actionable-connection-diagnostic-registration-20261018.json"; r=validate_registration(p.read_bytes(),"76e9a1dced8a6a4aa148e140e2eba719d7b37fad38a93ac1f942b109ddbdfbe2"); assert r["mode"]=="CONNECTION_DIAGNOSTIC_ONLY"; from verification.ingestion_storage.operational_runner import DIAGNOSTIC_AUTHORITY,DIAGNOSTIC_STATE; assert r["authority"]==DIAGNOSTIC_AUTHORITY and r["execution"]==dict(kind="OWNER_LOCAL",attempt=1,maximum_attempts=1,retry=False,state_directory=DIAGNOSTIC_STATE); import hashlib,json; assert hashlib.sha256((json.dumps(r["limits"],sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()==r["manifest_sha256"]; assert all(r["limits"][k]==0 for k in ("observations","execution_grants","exceptions","discovery_insertions")) and r["limits"]["runtime"]["batches"]==0 and not r["limits"]["screening"] and not r["limits"]["policy_patch"]; print("Exact diagnostic binding verified. Expiry: 19 October 2026, 16:00 BST (15:00 UTC).")'

printf '%s\n' \
  'One diagnostic only. No pipeline grant, exception, policy patch or council calls.' \
  'Hidden credential input: maximum five minutes, with no database/secret API operations.' \
  'Active operation: maximum 480 seconds, including 25 seconds diagnostic reserve and five seconds reporting. Outer ceiling: 790 seconds.' \
  'Enter the existing migration credential only at the hidden prompt. Do not paste it into chat.'

printf 'owner_preparation_github_cli_invocations=5\n'
# Five preparation gh invocations include the outer wrapper download.
# Runtime accounting begins at the separately supervised credential/input phase.
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
  --registration "$HOME/stage4-owner/actionable-connection-diagnostic-registration-20261018.json" \
  --registration-sha256 76e9a1dced8a6a4aa148e140e2eba719d7b37fad38a93ac1f942b109ddbdfbe2
controller_status=$?
printf 'controller_exit_status=%s\n' "$controller_status"

# Local, read-only evidence. A timeout does not repeat the diagnostic.
timeout 3s systemctl --user show propertyaigent-operational-once.scope \
  -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup
scope_status=$?
printf 'scope_readback_exit_status=%s\n' "$scope_status"
for audit_file in events.jsonl final-result.json; do
  path="$HOME/.local/state/propertyaigent/operational-actionable-diagnostic-once-20261018/$audit_file"
  if test -f "$path"; then sha256sum "$path"; else printf 'evidence_file_absent=%s\n' "$audit_file"; fi
done
exit "$controller_status"
