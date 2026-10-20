#!/usr/bin/env bash
# Owner-local CONTROL OBSERVATION. Run it in YOUR OWN visible WSL terminal (the private GitHub session is NOT needed: this path makes no GitHub request):
#   bash docs/design/ingestion-control-observation-20261021/owner-run.sh <commit> <tree> <registration-sha256>
# One ceremony per registration. Never retry. The credential is entered ONLY at the hidden prompt: never as an argument, file or environment variable.
# It opens ONE database connection and reads the control record (stop state, grant and exception identities and expiry states). It commits NOTHING: the temporary owner capability needed to read the
# record exists only inside a transaction that is ROLLED BACK, and its absence is read back. No authority, no source request, no credential/membership/role-setting/secret change, no GitHub request.
set -euo pipefail
umask 077
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/operational-control-observation-successor-2-registration-20261021.json"
STATE_ROOT="$HOME/.local/state/propertyaigent"
STATE_DIRECTORY=operational-control-observation-successor-2-once-20261021
CONSUMED_DIRECTORY=operational-control-observation-once-20261021
PIPELINE_DIRECTORY=operational-stable-pipeline-once-20261020
PY="$HOME/stage4-owner/storage-controller-venv/bin/python"

[[ -t 0 && -t 2 ]] || { echo 'VISIBLE_INTERACTIVE_TTY_REQUIRED: run this in your own WSL terminal, not an automation tab'; exit 2; }

cd "$HOME/stage4-owner/probe-checkout"
test -z "$(git status --porcelain)"
test -x "$PY"
test "$(git rev-parse HEAD)" = "$COMMIT"
test "$(git rev-parse 'HEAD^{tree}')" = "$TREE"
printf '%s  %s\n' "$REGISTRATION_SHA256" "$REGISTRATION" | sha256sum --check
test ! -e "$STATE_ROOT/$STATE_DIRECTORY"
printf 'observation_namespace_absent=%s\n' "$STATE_DIRECTORY"
# The consumed stable-pipeline run must be exactly as reconciled.
printf '%s  %s\n%s  %s\n' \
  35dedf6a87c3b10d4e23af54590c49bb5af4393358dd79ee9f95675be5035449 "$STATE_ROOT/$PIPELINE_DIRECTORY/events.jsonl" \
  8c26067b366efc208fec0bbb7affdaed80ab355b0e50c867a6d538dad7a26381 "$STATE_ROOT/$PIPELINE_DIRECTORY/final-result.json" | sha256sum --check
# The first (consumed) observation attempt must be exactly as reconciled; it is preserved and never reused.
printf '%s  %s\n%s  %s\n' \
  842139208adb04e180e2776790f8111216510277d9c433cbea7a1ebf3c0107a4 "$STATE_ROOT/$CONSUMED_DIRECTORY/events.jsonl" \
  7505156e6c459d6fc3903e4d8a80960c6ee2282f3aa467f12603b65c0924fb27 "$STATE_ROOT/$CONSUMED_DIRECTORY/final-result.json" | sha256sum --check
scope_state="$(timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState --value)" || { echo 'SCOPE_STATE_UNKNOWN: refusing to launch'; exit 3; }
[[ "$scope_state" = not-found ]] || { echo "SCOPE_PRESENT_OR_UNKNOWN ($scope_state): refusing to launch"; exit 3; }
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]==sys.argv[3]' \
  "$REGISTRATION" "$REGISTRATION_SHA256" CONTROL_OBSERVATION

printf '%s\n' \
  'CONTROL OBSERVATION. Effects:' \
  '  0. ONE bounded hidden prompt (120 seconds). The value is validated against the COMPLETE exact route BEFORE anything is consumed: an invalid value exits with a fixed code and consumes nothing, so you may then start again with the same registration (until it expires). It is never written anywhere.' \
  '  1. ONE database connection, at most 12 statements (6 used), at most 20 database-active seconds and 30 supervised-active seconds after the hidden input.' \
  '  2. Reads the stop state and the identities and expiry states of grants and Bolton exceptions. COMMITS NOTHING (a rolled-back transaction-local owner capability is the only way the record is readable; its absence is read back).' \
  '  3. Issues no authority, makes no source request, changes no credential, membership, role setting or secret, and makes no GitHub request.' \
  'Keep this terminal open until controller_exit_status is printed.'
printf '%s\n' 'The 120-second hidden-input timer starts at the prompt below (you are asked once). Enter the existing migration credential only there (typing is not echoed). Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=240s \
  "$PY" -I -B -c \
  'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_module("verification.ingestion_storage.operational_runner",run_name="__main__")' \
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
