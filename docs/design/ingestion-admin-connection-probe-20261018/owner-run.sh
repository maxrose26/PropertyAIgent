#!/usr/bin/env bash
# TEMPLATE for the owner-local administrative connection probe. NOT released: it refuses to run until the placeholders below are replaced by values the
# Product Owner has approved for an exact commit. One probe only. Never retry, never run a pipeline.
set -euo pipefail
umask 077
COMMIT="@@APPROVED_COMMIT_40_HEX@@"
TREE="@@APPROVED_TREE_40_HEX@@"
REGISTRATION_SHA256="@@APPROVED_REGISTRATION_SHA256@@"
REGISTRATION="$HOME/stage4-owner/admin-connection-probe-registration-20261018.json"
STATE="$HOME/.local/state/propertyaigent/operational-admin-connection-probe-once-20261018"
[[ "$COMMIT" =~ ^[a-f0-9]{40}$ && "$TREE" =~ ^[a-f0-9]{40}$ && "$REGISTRATION_SHA256" =~ ^[a-f0-9]{64}$ ]] || { echo 'PLACEHOLDERS_NOT_APPROVED'; exit 2; }

cd "$HOME/stage4-owner/pr122-storage-acceptance"
test -z "$(git status --porcelain)"
test ! -e "$STATE"
test -x "$HOME/stage4-owner/storage-controller-venv/bin/python"
git switch --detach "$COMMIT"
test "$(git rev-parse HEAD)" = "$COMMIT"
test "$(git rev-parse 'HEAD^{tree}')" = "$TREE"
test -z "$(git status --porcelain)"
printf '%s  %s\n' "$REGISTRATION_SHA256" "$REGISTRATION" | sha256sum --check

# Read-only validation: no hidden input, no database, no network, no GitHub.
"$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.admin_connection_probe import validate_probe_registration; p=Path(sys.argv[1]); validate_probe_registration(p.read_bytes(),sys.argv[2]); print("registration_valid")' \
  "$REGISTRATION" "$REGISTRATION_SHA256"

printf '%s\n' \
  'One administrative connection probe only: preparation, at most one connection attempt, one fixed read-only statement.' \
  'No credential generation, secret mapping, role change, grant, queue mutation, GitHub access or council request is possible in this program.' \
  'Hidden input maximum 120 s; active window 45 s; outer 180 s. Enter the existing migration credential only at the hidden prompt. Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=200s \
  "$HOME/stage4-owner/storage-controller-venv/bin/python" -I -B -c \
  'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_module("verification.ingestion_storage.admin_connection_probe",run_name="__main__")' \
  --registration "$REGISTRATION" --registration-sha256 "$REGISTRATION_SHA256"
controller_status=$?
printf 'controller_exit_status=%s\n' "$controller_status"

# Local, read-only evidence. A readback timeout is reported as UNKNOWN and never repeats the probe.
timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup
printf 'scope_readback_exit_status=%s\n' "$?"
for audit_file in events.jsonl final-result.json; do
  path="$STATE/$audit_file"
  if test -f "$path"; then sha256sum "$path"; else printf 'evidence_file_absent=%s\n' "$audit_file"; fi
done
exit "$controller_status"
