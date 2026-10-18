#!/usr/bin/env bash
# Owner-local administrative connection probe. Run it in YOUR OWN visible WSL terminal:
#   bash docs/design/ingestion-admin-connection-probe-20261018/owner-run.sh <commit> <tree> <registration-sha256> <attempt>
# One probe only. Never retry, never run a pipeline. The credential is entered ONLY at the hidden prompt: never as an argument, file or environment variable.
set -euo pipefail
umask 077
[[ $# = 4 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ && "$4" =~ ^[0-9]+$ ]] || { echo 'USAGE: owner-run.sh <commit40> <tree40> <registration-sha256> <attempt>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3; ATTEMPT=$4
REGISTRATION="$HOME/stage4-owner/admin-connection-probe-registration-attempt-${ATTEMPT}.json"
STATE_ROOT="$HOME/.local/state/propertyaigent"
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

# Read-only validation: no hidden input, no database, no network, no GitHub. Verifies the registration bindings, the predecessor evidence and that this
# attempt's audit namespace does not exist yet.
STATE_DIRECTORY=$("$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage import admin_connection_probe as p; q=Path(sys.argv[1]); r=p.validate_probe_registration(q.read_bytes(),sys.argv[2]); assert str(r["attempt"])==sys.argv[4]; v=p.verify_predecessor(r,sys.argv[3]); print("registration_valid",file=sys.stderr); print("predecessor_verified=%s"%v,file=sys.stderr); print(r["state_directory"])' \
  "$REGISTRATION" "$REGISTRATION_SHA256" "$STATE_ROOT" "$ATTEMPT")
test ! -e "$STATE_ROOT/$STATE_DIRECTORY"
printf 'successor_namespace_absent=%s\n' "$STATE_DIRECTORY"

printf '%s\n' \
  'One administrative connection probe only: preparation, at most one connection attempt, one fixed read-only statement.' \
  'No credential generation, secret mapping, role change, grant, queue mutation, GitHub access or council request is possible in this program.' \
  'The 120-second hidden-input timer starts at the prompt below. Enter the existing migration credential only there (typing is not echoed). Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=200s \
  "$PY" -I -B -c \
  'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_module("verification.ingestion_storage.admin_connection_probe",run_name="__main__")' \
  --registration "$REGISTRATION" --registration-sha256 "$REGISTRATION_SHA256"
controller_status=$?
printf 'controller_exit_status=%s\n' "$controller_status"

# Local, read-only evidence. A readback timeout is reported as UNKNOWN and never repeats the probe.
timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup
printf 'scope_readback_exit_status=%s\n' "$?"
for audit_file in events.jsonl final-result.json; do
  path="$STATE_ROOT/$STATE_DIRECTORY/$audit_file"
  if test -f "$path"; then sha256sum "$path"; else printf 'evidence_file_absent=%s\n' "$audit_file"; fi
done
exit "$controller_status"
