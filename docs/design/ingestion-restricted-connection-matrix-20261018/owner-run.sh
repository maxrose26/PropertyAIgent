#!/usr/bin/env bash
# Owner-local restricted-connection matrix. Run it in YOUR OWN visible WSL terminal:
#   bash docs/design/ingestion-restricted-connection-matrix-20261018/owner-run.sh <commit> <tree> <registration-sha256>
# One matrix only (four connection entries). Never retry, never run a pipeline. DIAGNOSTIC ALLOWANCE ONLY: it grants no execution authority.
# The credential is entered ONLY at the hidden prompt: never as an argument, file or environment variable.
set -euo pipefail
umask 077
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/restricted-connection-matrix-registration-20261018.json"
STATE_ROOT="$HOME/.local/state/propertyaigent"
STATE_DIRECTORY=operational-restricted-connection-matrix-once-20261018
PY="$HOME/stage4-owner/storage-controller-venv/bin/python"

# The hidden prompt needs a real terminal you can see and type into. Refuse BEFORE anything is consumed if there is not one.
[[ -t 0 && -t 2 ]] || { echo 'VISIBLE_INTERACTIVE_TTY_REQUIRED: run this in your own WSL terminal, not an automation tab'; exit 2; }

cd "$HOME/stage4-owner/probe-checkout"
test -z "$(git status --porcelain)"
test -x "$PY"
# The script runs from the checkout it verifies, so it never switches commits itself: check out the approved commit first (see the command).
test "$(git rev-parse HEAD)" = "$COMMIT"
test "$(git rev-parse 'HEAD^{tree}')" = "$TREE"
test -z "$(git status --porcelain)"
printf '%s  %s\n' "$REGISTRATION_SHA256" "$REGISTRATION" | sha256sum --check
test ! -e "$STATE_ROOT/$STATE_DIRECTORY"
printf 'matrix_namespace_absent=%s\n' "$STATE_DIRECTORY"

# Read-only preconditions: registration bindings, and the existing keyring identity the lifecycle's first call uses (no secret read, no write).
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]=="RESTRICTED_CONNECTION_MATRIX_ONLY"; print("registration_valid",file=sys.stderr)' \
  "$REGISTRATION" "$REGISTRATION_SHA256"
test "$(timeout 15s gh api user --jq .login)" = maxrose26
printf 'owner_preparation_github_cli_invocations=1\n'

printf '%s\n' \
  'Restricted-connection matrix only: four entries (worker without/with startup options, effect without/with startup options), each one connection and one fixed identity statement.' \
  'It uses the accepted credential lifecycle (fresh temporary passwords, temporary secrets, activation, teardown) and grants NO execution authority. No source, queue, grant, exception or application write.' \
  'The 120-second hidden-input timer starts at the prompt below. Enter the existing migration credential only there (typing is not echoed). Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=410s \
  "$PY" -I -B -c \
  'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_module("verification.ingestion_storage.operational_runner",run_name="__main__")' \
  --registration "$REGISTRATION" --registration-sha256 "$REGISTRATION_SHA256"
controller_status=$?
printf 'controller_exit_status=%s\n' "$controller_status"

# Local, read-only evidence. A readback timeout is reported as UNKNOWN and never repeats the run.
timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup
printf 'scope_readback_exit_status=%s\n' "$?"
for audit_file in events.jsonl final-result.json; do
  path="$STATE_ROOT/$STATE_DIRECTORY/$audit_file"
  if test -f "$path"; then sha256sum "$path"; else printf 'evidence_file_absent=%s\n' "$audit_file"; fi
done
exit "$controller_status"
