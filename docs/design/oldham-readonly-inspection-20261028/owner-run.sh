#!/usr/bin/env bash
# NOT AUTHORISED FOR EXECUTION. This file is a proposal; it must not be run until the Product Owner gives the separate production approval named in PACKAGE.md.
#
# Owner-local READ ONLY inspection of the installed ingestion state. Run it in YOUR OWN visible WSL terminal:
#   bash docs/design/oldham-readonly-inspection-20261028/owner-run.sh <commit> <tree> <registration-sha256>
# One inspection only. Never retry, never run a pipeline. The credential is entered ONLY at the hidden prompt: never as an argument, file or environment variable.
set -euo pipefail
umask 077
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/oldham-readonly-inspection-registration.json"
STATE_ROOT="$HOME/.local/state/propertyaigent"
STATE_DIRECTORY=oldham-readonly-inspection-once-20261028
PY="$HOME/stage4-owner/storage-controller-venv/bin/python"

[[ -t 0 && -t 2 ]] || { echo 'VISIBLE_INTERACTIVE_TTY_REQUIRED: run this in your own WSL terminal, not an automation tab'; exit 2; }

cd "$HOME/stage4-owner/inspection-checkout"
test -z "$(git status --porcelain)"
test -x "$PY"
test "$(git rev-parse HEAD)" = "$COMMIT"
test "$(git rev-parse 'HEAD^{tree}')" = "$TREE"
test -z "$(git status --porcelain)"
printf '%s  %s\n' "$REGISTRATION_SHA256" "$REGISTRATION" | sha256sum --check
test ! -e "$STATE_ROOT/$STATE_DIRECTORY"      # single use: this audit namespace must not exist yet
# Read-only validation: no hidden input, no database, no network, no GitHub.
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage import oldham_inspection as i; q=Path(sys.argv[1]); i.validate_registration(q.read_bytes(),sys.argv[2]); print("registration_valid")' \
  "$REGISTRATION" "$REGISTRATION_SHA256"

printf '%s\n' \
  'One READ ONLY inspection: preparation, one connection, at most 12 fixed statements (11 planned: BEGIN READ ONLY, nine SELECT, ROLLBACK). No GRANT, SET ROLE, installation, credential change, GitHub access or council request is possible in this program.' \
  'The account is the existing ADMINISTRATIVE migration identity. READ ONLY is a guard on this transaction; it does not make the account restricted.' \
  'The 120-second hidden-input timer starts at the prompt below. Enter the existing migration credential only there (typing is not echoed). Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=200s \
  "$PY" -I -B -c \
  'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_module("verification.ingestion_storage.oldham_inspection",run_name="__main__")' \
  --registration "$REGISTRATION" --registration-sha256 "$REGISTRATION_SHA256"
controller_status=$?
printf 'controller_exit_status=%s\n' "$controller_status"

timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup
printf 'scope_readback_exit_status=%s\n' "$?"
for audit_file in events.jsonl final-result.json; do
  path="$STATE_ROOT/$STATE_DIRECTORY/$audit_file"
  if test -f "$path"; then sha256sum "$path"; else printf 'evidence_file_absent=%s\n' "$audit_file"; fi
done
exit "$controller_status"
