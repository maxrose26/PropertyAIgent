#!/usr/bin/env bash
# Owner-local BOLTON CAPTURE ACCEPTANCE ceremony. Run it in YOUR OWN visible WSL terminal, inside the validated PRIVATE GitHub session:
#   bash docs/design/ingestion-capture-acceptance-20261022/owner-run-capture.sh <commit> <tree> <registration-sha256>
# One ceremony per registration. The credential is entered ONLY at the hidden prompt, validated against the complete route BEFORE the registration is consumed.
# It issues the named single-use Bolton capture allowance (source_calls=1) under the observed generation-2 stop and the installed policy v4, waits for the restricted GitHub job's durable retention, verifies it in the database,
# issues the source-free screening allowance, waits for the screening result, then ENDS every allowance (revocation-only invalidation with readback).
# No credential, membership, role setting or secret is changed. KEEP THIS TERMINAL OPEN until it prints controller_exit_status (up to about 77 minutes).
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run-capture.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/operational-bolton-capture-acceptance-registration-20261022.json"
STATE_DIRECTORY=operational-bolton-capture-acceptance-once-20261022
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
# The reconciled form-probe ceremony (20 October) and its policy-v3 ceremony must be exactly as archived.
printf '%s  %s\n%s  %s\n' \
  41c113b4190d17afda199e201c1da1a1787a6cadff8e5eef7de753a5fee7bab5 "$STATE_ROOT/operational-bolton-form-probe-once-20261021/events.jsonl" \
  0c4d3ad83fa9c374953beaa164c83ea2a0b9603ef255d2f2a51cbee3292bff44 "$STATE_ROOT/operational-bolton-form-probe-once-20261021/final-result.json" | sha256sum --check
printf '%s  %s\n%s  %s\n' \
  e961467e5d62bfe7cdbba780ba5b9b4e4c55b630179068aabb09faa9e75edd17 "$STATE_ROOT/operational-policy-generation2-once-20261021/events.jsonl" \
  508c8ffb9325b24aa7de79888799dfdb79c3afff852c26f375e79922d5e7a2ea "$STATE_ROOT/operational-policy-generation2-once-20261021/final-result.json" | sha256sum --check
scope_state="$(timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState --value)" || { echo 'SCOPE_STATE_UNKNOWN: refusing to launch'; exit 3; }
[[ "$scope_state" = not-found ]] || { echo "SCOPE_PRESENT_OR_UNKNOWN ($scope_state): refusing to launch"; exit 3; }
# The policy-v4 ceremony this capture depends on must be exactly as bound in the registration.
read -r POLICY_EVENTS POLICY_FINAL < <("$PY" -I -B -c 'import json,sys; a=json.load(open(sys.argv[1]))["policy_ceremony_audit"]; print(a["events_sha256"],a["final_result_sha256"])' "$REGISTRATION")
printf '%s  %s\n%s  %s\n' "$POLICY_EVENTS" "$STATE_ROOT/operational-policy-capture-allowance-once-20261022/events.jsonl" "$POLICY_FINAL" "$STATE_ROOT/operational-policy-capture-allowance-once-20261022/final-result.json" | sha256sum --check
EVIDENCE_HEAD_FILE="${TMPDIR:-/tmp}/.probe-evidence-head-$$"
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]==sys.argv[3]; open(sys.argv[4],"w").write(r["evidence_head"])' \
  "$REGISTRATION" "$REGISTRATION_SHA256" BOLTON_CAPTURE_ACCEPTANCE "$EVIDENCE_HEAD_FILE"
test "$(timeout 15s gh api user --jq .login)" = maxrose26
# The restricted job and this controller publish alternately to the evidence branch; its head must still be the registered one, or the run stops BEFORE any authority exists.
test "$(timeout 15s gh api repos/maxrose26/PropertyAIgent/git/ref/heads/stage4/narrow-continuation-evidence-20261016 --jq .object.sha)" = "$(cat "$EVIDENCE_HEAD_FILE")"
rm -f "$EVIDENCE_HEAD_FILE"
printf 'owner_preparation_github_cli_invocations=2\n'

printf '%s\n' \
  'BOLTON CAPTURE ACCEPTANCE. Effects:' \
  '  0. ONE bounded hidden prompt (120 seconds), validated against the complete exact route BEFORE the registration is consumed.' \
  '  1. a FIXED READ-ONLY readback bound to the reviewed policy-v4 inventory, the OBSERVED generation-2 baseline and the exact control record the policy ceremony left. Any mismatch ends the run with nothing issued.' \
  '  2. ONE named single-use Bolton CAPTURE allowance + exception (source_calls=1, at most 55 minutes). The restricted job makes ONE form request; only a valid form leads on to the listing collection (at most 10 requests in all).' \
  '  3. the restricted GitHub job is dispatched by Claude and approved by you; the raw source is retained durably BEFORE the ledger checkpoint; this controller verifies the retention in the database.' \
  '  4. ONE named source-free SCREENING allowance + exception (source_calls=0, at most 30 minutes); the restricted job screens; every allowance is then ENDED with a committed readback and the final readback repeated.' \
  '  5. NO stop, credential, membership, role setting or secret is changed. Any stop or failure ends the allowances and retains the permitted diagnostics; nothing is retried or replaced automatically.' \
  'Keep this terminal open. Claude will dispatch the restricted job once the capture allowance is recorded; you approve the protected environment in GitHub.'
printf '%s\n' 'The 120-second hidden-input timer starts at the prompt below (you are asked once).'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=4600s \
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
