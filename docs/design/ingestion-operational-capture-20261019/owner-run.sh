#!/usr/bin/env bash
# Owner-local operational acceptance run (one Bolton listing capture, durable retention, queued screening). Run it in YOUR OWN visible WSL terminal:
#   bash docs/design/ingestion-operational-capture-20261019/owner-run.sh <commit> <tree> <registration-sha256>
# One run only. Never retry. The credential is entered ONLY at the hidden prompt: never as an argument, file or environment variable.
set -euo pipefail
umask 077
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/operational-acceptance-registration-20261019.json"
STATE_ROOT="$HOME/.local/state/propertyaigent"
STATE_DIRECTORY=operational-capture-queue-successor-once-20261018
EVIDENCE_REF=repos/maxrose26/PropertyAIgent/git/ref/heads/stage4/narrow-continuation-evidence-20261016
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
printf 'capture_namespace_absent=%s\n' "$STATE_DIRECTORY"

# Read-only preconditions: registration bindings, GitHub identity, and that the evidence branch head is still the one the registration binds (a moved head would only be
# discovered AFTER the single source observation, so it is checked now, before anything is consumed).
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]=="REQUIRED_CAPTURE_SCREENING"; open(sys.argv[3],"w").write(r["evidence_head"]); print("registration_valid",file=sys.stderr)' \
  "$REGISTRATION" "$REGISTRATION_SHA256" "${TMPDIR:-/tmp}/.evidence-head-$$"
test "$(timeout 15s gh api user --jq .login)" = maxrose26
test "$(timeout 15s gh api "$EVIDENCE_REF" --jq .object.sha)" = "$(cat "${TMPDIR:-/tmp}/.evidence-head-$$")"
rm -f "${TMPDIR:-/tmp}/.evidence-head-$$"
printf 'owner_preparation_github_cli_invocations=2\n'

printf '%s\n' \
  'Operational acceptance run: one credential lifecycle, role-level timeouts on the two restricted logins (captured, applied, restored), qualification of both identities,' \
  'then ONE Bolton RECEIVED 2026-10-16 observation (at most 10 transport requests, 3 MB, 6 pages, 60 rows), durable retention, queued screening (no further source requests), teardown.' \
  'It stops and tears down on any failed qualification. No matrix replay, no application/B2 write, no unit facts, no scheduling.' \
  'The 300-second hidden-input timer starts at the prompt below. Enter the existing migration credential only there (typing is not echoed). Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=810s \
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
