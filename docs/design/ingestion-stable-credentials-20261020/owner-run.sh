#!/usr/bin/env bash
# Owner-local STABLE-CREDENTIAL ceremony (provisioning or revocation). Run it in YOUR OWN visible WSL terminal:
#   bash docs/design/ingestion-stable-credentials-20261020/owner-run.sh <provisioning|revocation> <commit> <tree> <registration-sha256>
# One ceremony per registration. Never retry. No ingestion grant, source request or application write exists on either path.
# The credential is entered ONLY at the hidden prompt: never as an argument, file or environment variable.
set -euo pipefail
umask 077
[[ $# = 4 && "$1" =~ ^(provisioning|revocation)$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{40}$ && "$4" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run.sh <provisioning|revocation> <commit40> <tree40> <registration-sha256>'; exit 2; }
MODE=$1; COMMIT=$2; TREE=$3; REGISTRATION_SHA256=$4
REGISTRATION="$HOME/stage4-owner/operational-stable-$MODE-registration-20261020.json"
STATE_ROOT="$HOME/.local/state/propertyaigent"
if [[ "$MODE" = provisioning ]]; then STATE_DIRECTORY=operational-stable-provisioning-once-20261020; RUNNER_MODE=STABLE_CREDENTIAL_PROVISIONING
else STATE_DIRECTORY=operational-stable-revocation-once-20261020; RUNNER_MODE=STABLE_CREDENTIAL_REVOCATION; fi
RUN1_DIRECTORY=operational-capture-queue-successor-once-20261018
RUN2_DIRECTORY=operational-capture-queue-settled-once-20261019
RUN3_DIRECTORY=operational-capture-queue-settled-r2-once-20261019
PY="$HOME/stage4-owner/storage-controller-venv/bin/python"

# The hidden prompt needs a real terminal you can see and type into. Refuse BEFORE anything is consumed if there is not one.
[[ -t 0 && -t 2 ]] || { echo 'VISIBLE_INTERACTIVE_TTY_REQUIRED: run this in your own WSL terminal, not an automation tab'; exit 2; }

cd "$HOME/stage4-owner/probe-checkout"
test -z "$(git status --porcelain)"
test -x "$PY"
test "$(git rev-parse HEAD)" = "$COMMIT"
test "$(git rev-parse 'HEAD^{tree}')" = "$TREE"
test -z "$(git status --porcelain)"
printf '%s  %s\n' "$REGISTRATION_SHA256" "$REGISTRATION" | sha256sum --check
test ! -e "$STATE_ROOT/$STATE_DIRECTORY"
printf 'stable_namespace_absent=%s\n' "$STATE_DIRECTORY"
# The consumed predecessors must be exactly as archived (PRs #142, #145, #148): preserved, never reused.
printf '%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n' \
  2af82ca9247366d5ada8e0873ea97abaab84cdeb8dfb81c3f3efb146708059b0 "$STATE_ROOT/$RUN1_DIRECTORY/events.jsonl" \
  ffedfe33c342f6e808376a1617ac14a1895b863f87e4958d4edbdeaa346c5609 "$STATE_ROOT/$RUN1_DIRECTORY/final-result.json" \
  c4dc12776784ca678f5a1a0558f421ba405d0a243df52f5e78008a9ef66fb6cc "$STATE_ROOT/$RUN2_DIRECTORY/events.jsonl" \
  8116e06698669fb03a9550860ced87685fa4e483a9f93921989a40f295f528c3 "$STATE_ROOT/$RUN2_DIRECTORY/final-result.json" \
  945b1b500676ab0a43e6982e0a65fb849e75637e89e915d790182e91c284e159 "$STATE_ROOT/$RUN3_DIRECTORY/events.jsonl" \
  389d4623f0b86be450123b9255ac84c2d1184882c2797e6834b3ab47410bd40f "$STATE_ROOT/$RUN3_DIRECTORY/final-result.json" | sha256sum --check
# No earlier scope of the unit may be present: an unreadable or timed-out answer is UNKNOWN and blocks the launch.
scope_state="$(timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState --value)" || { echo 'SCOPE_STATE_UNKNOWN: refusing to launch'; exit 3; }
[[ "$scope_state" = not-found ]] || { echo "SCOPE_PRESENT_OR_UNKNOWN ($scope_state): refusing to launch"; exit 3; }

"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]==sys.argv[3]; print("registration_valid",file=sys.stderr)' \
  "$REGISTRATION" "$REGISTRATION_SHA256" "$RUNNER_MODE"
test "$(timeout 15s gh api user --jq .login)" = maxrose26
printf 'owner_preparation_github_cli_invocations=1\n'

if [[ "$MODE" = provisioning ]]; then
printf '%s\n' \
  'STABLE-CREDENTIAL PROVISIONING. Effects (all deliberate and standing until revoked):' \
  '  restore the two reviewed capability memberships and KEEP them; set the three role-level timeouts and KEEP them;' \
  '  set a fresh password on each restricted login with VALID UNTIL = now + 90 days (never printed, never written to a file);' \
  '  store two protected environment secrets; enable LOGIN on both logins and LEAVE IT ENABLED.' \
  'No grant, exception, source request, queue row or application write: a valid login does not authorise ingestion. A failure after the credentials exist disables and removes them.'
else
printf '%s\n' \
  'STABLE-CREDENTIAL REVOCATION (privileged path). Effects: NOLOGIN, NULL password, capability memberships revoked, bounded session policy (at most two exactly identified terminations, only with proven privileges),' \
  'both protected secrets deleted, closure checks. Role-level timeouts are left in place. Sessions that cannot be resolved are REPORTED, never called closed.'
fi
printf '%s\n' 'The 120-second hidden-input timer starts at the prompt below. Enter the existing migration credential only there (typing is not echoed). Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=450s \
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
