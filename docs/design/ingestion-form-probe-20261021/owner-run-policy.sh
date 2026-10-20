#!/usr/bin/env bash
# Owner-local POLICY-V3 ceremony (Bolton form probe, specification 032 section 12). Run it in YOUR OWN visible WSL terminal (no GitHub sign-in is needed):
#   bash docs/design/ingestion-form-probe-20261021/owner-run-policy.sh <commit> <tree> <registration-sha256>
# One ceremony per registration. The credential is entered ONLY at the hidden prompt, which is validated against the complete route BEFORE the registration is consumed (a rejected value consumes nothing).
# It installs EXACTLY two reviewed function definitions (ingestion_bolton_allowed, ingestion_register_bolton_exception), verifies the installed inventory equals the reviewed one, verifies the control
# record is byte-for-byte unchanged and reads the transient owner capability back absent. It issues no authority, makes no source request and no GitHub request, and changes no stop, grant, exception,
# credential, membership, role setting or secret. KEEP THIS TERMINAL OPEN until it prints controller_exit_status.
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run-policy.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/operational-bolton-policy-generation2-registration-20261021.json"
STATE_DIRECTORY=operational-policy-generation2-once-20261021
set -euo pipefail
umask 077
STATE_ROOT="$HOME/.local/state/propertyaigent"
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
printf 'namespace_absent=%s\n' "$STATE_DIRECTORY"
# The consumed predecessors must be exactly as reconciled: the stable-pipeline run, the first observation attempt, the successor control observation.
printf '%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n%s  %s\n' \
  35dedf6a87c3b10d4e23af54590c49bb5af4393358dd79ee9f95675be5035449 "$STATE_ROOT/operational-stable-pipeline-once-20261020/events.jsonl" \
  8c26067b366efc208fec0bbb7affdaed80ab355b0e50c867a6d538dad7a26381 "$STATE_ROOT/operational-stable-pipeline-once-20261020/final-result.json" \
  842139208adb04e180e2776790f8111216510277d9c433cbea7a1ebf3c0107a4 "$STATE_ROOT/operational-control-observation-once-20261021/events.jsonl" \
  7505156e6c459d6fc3903e4d8a80960c6ee2282f3aa467f12603b65c0924fb27 "$STATE_ROOT/operational-control-observation-once-20261021/final-result.json" \
  bc2187fb125667090f536be4031f285c2887be52af184313abeccd72c0ad8f41 "$STATE_ROOT/operational-control-observation-successor-2-once-20261021/events.jsonl" \
  ac00382c21e59e259b61e5dfd94beee2272495de6d2ce9a8d8c06b8f4bde46be "$STATE_ROOT/operational-control-observation-successor-2-once-20261021/final-result.json" | sha256sum --check
scope_state="$(timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState --value)" || { echo 'SCOPE_STATE_UNKNOWN: refusing to launch'; exit 3; }
[[ "$scope_state" = not-found ]] || { echo "SCOPE_PRESENT_OR_UNKNOWN ($scope_state): refusing to launch"; exit 3; }
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]==sys.argv[3]' \
  "$REGISTRATION" "$REGISTRATION_SHA256" BOLTON_POLICY_GENERATION2

printf '%s\n' \
  'POLICY V3. Effects:' \
  '  0. ONE bounded hidden prompt (120 seconds), validated against the complete exact route BEFORE the registration is consumed.' \
  '  1. a fixed control observation (6 statements; the transaction-local owner capability is rolled back and read back absent) that must equal the OBSERVED generation-2 record exactly.' \
  '  2. the reviewed installed inventory is verified; the reviewed policy-v3 script then replaces exactly two function definitions; the new inventory is verified; the capability is read back absent;' \
  '     the control record is observed again and must be byte-for-byte unchanged.' \
  '  3. no stop, grant, exception, credential, membership, role setting or secret is touched; no GitHub or source request is made.' \
  'Keep this terminal open until controller_exit_status is printed.'
printf '%s\n' 'The 120-second hidden-input timer starts at the prompt below (you are asked once).'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=300s \
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
