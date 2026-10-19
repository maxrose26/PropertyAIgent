#!/usr/bin/env bash
# Owner-local STABLE-PIPELINE authority ceremony. Run it in YOUR OWN visible WSL terminal:
#   bash docs/design/ingestion-stable-pipeline-20261020/owner-run.sh <commit> <tree> <registration-sha256>
# One ceremony per registration. Never retry. The credential is entered ONLY at the hidden prompt: never as an argument, file or environment variable.
# This ceremony changes NO credential, membership, role setting or secret. It issues one bounded Bolton capture authority, then (after the restricted GitHub job has durably retained the
# capture) one source-free screening authority, then ENDS both. KEEP THIS TERMINAL OPEN until it prints controller_exit_status (up to about 75 minutes while the restricted job runs).
set -euo pipefail
umask 077
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/operational-stable-pipeline-registration-20261020.json"
STATE_ROOT="$HOME/.local/state/propertyaigent"
STATE_DIRECTORY=operational-stable-pipeline-once-20261020
RUNNER_MODE=STABLE_PIPELINE_AUTHORITY
RUN1_DIRECTORY=operational-capture-queue-successor-once-20261018
RUN2_DIRECTORY=operational-capture-queue-settled-once-20261019
RUN3_DIRECTORY=operational-capture-queue-settled-r2-once-20261019
PROVISIONING_DIRECTORY=operational-stable-provisioning-once-20261020
QUALIFICATION_ARCHIVE="$HOME/stage4-owner/archive/stable-qualification-run1-20261019"
PY="$HOME/stage4-owner/storage-controller-venv/bin/python"

[[ -t 0 && -t 2 ]] || { echo 'VISIBLE_INTERACTIVE_TTY_REQUIRED: run this in your own WSL terminal, not an automation tab'; exit 2; }

cd "$HOME/stage4-owner/probe-checkout"
test -z "$(git status --porcelain)"
test -x "$PY"
test "$(git rev-parse HEAD)" = "$COMMIT"
test "$(git rev-parse 'HEAD^{tree}')" = "$TREE"
test -z "$(git status --porcelain)"
printf '%s  %s\n' "$REGISTRATION_SHA256" "$REGISTRATION" | sha256sum --check
test ! -e "$STATE_ROOT/$STATE_DIRECTORY"
printf 'pipeline_namespace_absent=%s\n' "$STATE_DIRECTORY"
# Every consumed predecessor must be exactly as archived: the three capture/screening runs, the stable provisioning audit and registration, and the accepted qualification artifact.
printf '%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n' \
  2af82ca9247366d5ada8e0873ea97abaab84cdeb8dfb81c3f3efb146708059b0 "$STATE_ROOT/$RUN1_DIRECTORY/events.jsonl" \
  ffedfe33c342f6e808376a1617ac14a1895b863f87e4958d4edbdeaa346c5609 "$STATE_ROOT/$RUN1_DIRECTORY/final-result.json" \
  c4dc12776784ca678f5a1a0558f421ba405d0a243df52f5e78008a9ef66fb6cc "$STATE_ROOT/$RUN2_DIRECTORY/events.jsonl" \
  8116e06698669fb03a9550860ced87685fa4e483a9f93921989a40f295f528c3 "$STATE_ROOT/$RUN2_DIRECTORY/final-result.json" \
  945b1b500676ab0a43e6982e0a65fb849e75637e89e915d790182e91c284e159 "$STATE_ROOT/$RUN3_DIRECTORY/events.jsonl" \
  389d4623f0b86be450123b9255ac84c2d1184882c2797e6834b3ab47410bd40f "$STATE_ROOT/$RUN3_DIRECTORY/final-result.json" \
  a26f9d1f51d8e908431cfdebf2bf20f6362b7bcbcecb35717a13935017155a19 "$STATE_ROOT/$PROVISIONING_DIRECTORY/events.jsonl" \
  51aea5d5ce0a3515b369b0d098a5c3da73a210ff86034f1f9e368d654274d3e6 "$STATE_ROOT/$PROVISIONING_DIRECTORY/final-result.json" \
  b7e00b48d659b4fa83cd72d14efe734846c2d9d2e699f6998e509e3c3f280264 "$HOME/stage4-owner/operational-stable-provisioning-registration-20261020.json" \
  43d87e525c7b035b5799131f3a565fc62efdb3857e3d0258dd06a0a2bccfe02f "$QUALIFICATION_ARCHIVE/events.jsonl" \
  c7a3e6c15f80c9dc0b682420c35be99ca8503be7295fc92fbabfca67f587399d "$QUALIFICATION_ARCHIVE/final-result.json" \
  b02da6fcf1658f627f4935db0a998fb3764498b3e15b6d57ad2ab135ba15db58 "$QUALIFICATION_ARCHIVE/artifact-12212818855.zip" | sha256sum --check
scope_state="$(timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState --value)" || { echo 'SCOPE_STATE_UNKNOWN: refusing to launch'; exit 3; }
[[ "$scope_state" = not-found ]] || { echo "SCOPE_PRESENT_OR_UNKNOWN ($scope_state): refusing to launch"; exit 3; }

EVIDENCE_HEAD_FILE="${TMPDIR:-/tmp}/.pipeline-evidence-head-$$"
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]==sys.argv[3]; open(sys.argv[4],"w").write(r["evidence_head"]); print("registration_valid",file=sys.stderr)' \
  "$REGISTRATION" "$REGISTRATION_SHA256" "$RUNNER_MODE" "$EVIDENCE_HEAD_FILE"
test "$(timeout 15s gh api user --jq .login)" = maxrose26
# The restricted job and this controller publish alternately to the evidence branch; its head must still be the registered one, or the run stops BEFORE any authority exists.
test "$(timeout 15s gh api repos/maxrose26/PropertyAIgent/git/ref/heads/stage4/narrow-continuation-evidence-20261016 --jq .object.sha)" = "$(cat "$EVIDENCE_HEAD_FILE")"
rm -f "$EVIDENCE_HEAD_FILE"
printf 'owner_preparation_github_cli_invocations=2\n'

printf '%s\n' \
  'STABLE-PIPELINE AUTHORITY. Effects:' \
  '  1. a FIXED READ-ONLY readback (one connection, at most 12 statements): logins, password PRESENCE, exact expiry, memberships, role settings, sessions (no query text), grants, stops. Any mismatch ends the run with nothing issued.' \
  '  2. ONE bounded Bolton RECEIVED 16 October 2026 capture authority + exception (source_calls=1, at most 55 minutes) under the UNCHANGED Salford stop and STORAGE_TEST_STOP.' \
  '  3. after the restricted GitHub job has durably retained the capture: ONE source-free screening authority (source_calls=0).' \
  '  4. both authorities are INVALIDATED and the readback repeated. NO password, membership, role setting or secret is changed; the standing logins stay as provisioned until you revoke them.' \
  'Keep this terminal open. Claude will dispatch the restricted job once the capture authority is recorded; you approve the protected environment in GitHub.'
printf '%s\n' 'The 120-second hidden-input timer starts at the prompt below. Enter the existing migration credential only there (typing is not echoed). Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=4900s \
  "$PY" -I -B -c \
  'import os,runpy,sys; sys.path.insert(0,os.getcwd()); runpy.run_module("verification.ingestion_storage.operational_runner",run_name="__main__")' \
  --registration "$REGISTRATION" --registration-sha256 "$REGISTRATION_SHA256"
controller_status=$?
printf 'controller_exit_status=%s\n' "$controller_status"

# Local, read-only evidence. A readback timeout is reported as UNKNOWN and never repeats the ceremony.
timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup
printf 'scope_readback_exit_status=%s\n' "$?"
for audit_file in events.jsonl final-result.json; do
  path="$STATE_ROOT/$STATE_DIRECTORY/$audit_file"
  if test -f "$path"; then sha256sum "$path"; else printf 'evidence_file_absent=%s\n' "$audit_file"; fi
done
exit "$controller_status"
