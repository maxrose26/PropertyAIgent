#!/usr/bin/env bash
# Owner-local matrix cleanup. Run it in YOUR OWN visible WSL terminal, inside the private-keyring GitHub session (see PACKAGE.md):
#   bash docs/design/ingestion-matrix-cleanup-20261018/owner-run.sh <commit> <tree> <registration-sha256>
# Revoke-only: re-reads the two logins, ends at most ONE exactly-bound worker session, deletes exactly the two temporary secrets. One run; never retry.
# The credential is entered ONLY at the hidden prompt: never as an argument, file or environment variable.
set -euo pipefail
umask 077
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/matrix-cleanup-registration-20261018.json"
STATE_ROOT="$HOME/.local/state/propertyaigent"
STATE_DIRECTORY=operational-restricted-matrix-cleanup-once-20261018
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
printf 'cleanup_namespace_absent=%s\n' "$STATE_DIRECTORY"

# Read-only preconditions: registration bindings, the retained matrix audit it answers, and the keyring-backed GitHub identity (no secret read, no write).
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage import matrix_cleanup as m; r=m.validate_cleanup_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); print("predecessor_verified=%s"%m.verify_predecessor(r,Path(sys.argv[3])),file=sys.stderr); print("registration_valid target_pid=%s role=%s"%(r["target"]["pid"],r["target"]["role"]),file=sys.stderr)' \
  "$REGISTRATION" "$REGISTRATION_SHA256" "$STATE_ROOT"
test "$(timeout 15s gh api user --jq .login)" = maxrose26
printf 'owner_preparation_github_cli_invocations=1\n'

printf '%s\n' \
  'Revoke-only cleanup: re-read both restricted logins, end at most the one named worker session after re-confirming its pid, role and start time, delete exactly the two temporary secrets, verify.' \
  'No role/password/membership/grant/ledger change, no new credential, no restricted-login connection, no matrix. Ceilings: 2 database connections, 20 commands, 30 database seconds, 1 termination, 3 GitHub requests.' \
  'The 120-second hidden-input timer starts at the prompt below. Enter the existing migration credential only there (typing is not echoed). Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=240s \
  "$PY" -I -B -c \
  'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_module("verification.ingestion_storage.matrix_cleanup",run_name="__main__")' \
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
