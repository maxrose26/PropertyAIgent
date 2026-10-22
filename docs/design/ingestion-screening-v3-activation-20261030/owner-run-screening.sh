#!/usr/bin/env bash
# Owner-local SCREENING-V3 RETAINED-WINDOW run, SUCCESSOR ATTEMPT (PR #175 follow-up). ONE Ubuntu terminal (plus the GitHub approval page later), inside the validated PRIVATE GitHub session:
#   bash docs/design/ingestion-screening-v3-activation-20261030/owner-run-screening.sh <commit> <tree> <registration-sha256>
# One run per registration. The credential is entered ONLY at the hidden prompt, validated against the complete route BEFORE the registration is consumed.
# The controller prints seven numbered, secret-free progress messages from its actual stages (credential accepted, retained records verified, READY FOR HOSTED DISPATCH, waiting, authority registered, revocation and cleanup, final result).
# It verifies the 30 retained rows and the absence of the 29 new items, waits for the restricted GitHub job's READY marker, registers the ONE named source-free screening allowance, waits for the result, then ENDS the allowance
# (revocation-only invalidation with readback), publishes inside the enforced envelope, closes and seals. No credential, membership, role setting or secret is changed. Nothing here dispatches the hosted workflow.
# Ctrl-C ENDS THE ATTEMPT (safely: before registration nothing is issued; afterwards the owner revokes the allowance before it exits) and the attempt is then spent.
# ATTENDANCE is bounded by this mode's own deadlines: preparation, then up to 1800 s READY wait (queueing and protected-environment approval, outside the grant), then the 900 s grant (600 s execution + 300 s cleanup), all inside
# the 4200 s job deadline (70 minutes). The 4600 s (about 77 minutes) systemd RuntimeMaxSec below is the INHERITED kernel outer limit, not this mode's deadline. KEEP THIS TERMINAL OPEN until controller_exit_status is printed.
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run-screening.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/operational-bolton-screening-v3-retained-successor-registration-20261030.json"
STATE_DIRECTORY=operational-bolton-screening-v3-retained-successor-once-20261030
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
# The consumed 22 October capture acceptance (generation 3) and its policy-v4 ceremony must be exactly as archived.
printf '%s  %s\n%s  %s\n' \
  751eda655375d19a945a2a1cddc8524979f3fd44ad5b35e9dbd76f212385438e "$STATE_ROOT/operational-bolton-capture-acceptance-once-20261022/events.jsonl" \
  05d87b20a561d24a4cfd145c7f2f2b9332e9e907e680aab2b2cf1ccc387d10b2 "$STATE_ROOT/operational-bolton-capture-acceptance-once-20261022/final-result.json" | sha256sum --check
printf '%s  %s\n%s  %s\n' \
  1daeb6b44e617855a43d4a5fdb2d3af48ba1128769a51f19f0ce3f1baf66c88f "$STATE_ROOT/operational-policy-capture-allowance-once-20261022/events.jsonl" \
  4ca0a7eccfe5bc51cc3b70c2df1f52822160e6f87fb31917be826e80d48dd888 "$STATE_ROOT/operational-policy-capture-allowance-once-20261022/final-result.json" | sha256sum --check
# The consumed 23 October policy-v5 ceremony and the window demonstration (its policy-v5 audit and its owner audit) must be exactly as reconciled.
printf '%s  %s\n%s  %s\n%s  %s\n%s  %s\n' \
  1464ce01669fd8a28725ba0fa86dfb7acff226bbf9473043a1f35fd162400809 "$STATE_ROOT/operational-policy-window-allowance-once-20261023/events.jsonl" \
  b019c9642e0d865181363aff1b0e49238b468de286c758c69eeb637f536c73fe "$STATE_ROOT/operational-policy-window-allowance-once-20261023/final-result.json" \
  c84ee8b4edad66d224b978403d73800dba4683ddf5d9684a4afe69264fda83c2 "$STATE_ROOT/operational-bolton-window-demonstration-once-20261023/events.jsonl" \
  8f5ec37f94c78c7e004ebd4a6a1ca1b64aa20aa141750aa6522623f05b72085e "$STATE_ROOT/operational-bolton-window-demonstration-once-20261023/final-result.json" | sha256sum --check
# The interrupted FIRST screening attempt (stopped in the READY wait, no authority issued, nothing dispatched) must be exactly as archived. It is preserved and never touched.
printf '%s  %s\n%s  %s\n' \
  f3eb84a4c469e26af2d5bd173653c95f8213e74bd0f6860a43c241a489279f84 "$STATE_ROOT/operational-bolton-screening-v3-retained-once-20261030/events.jsonl" \
  8c784e81b98c520f3306552b97908febbc36d1c58b8995aeb1c40f7947df77cd "$STATE_ROOT/operational-bolton-screening-v3-retained-once-20261030/final-result.json" | sha256sum --check
scope_state="$(timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState --value)" || { echo 'SCOPE_STATE_UNKNOWN: refusing to launch'; exit 3; }
[[ "$scope_state" = not-found ]] || { echo "SCOPE_PRESENT_OR_UNKNOWN ($scope_state): refusing to launch"; exit 3; }
# The screening-v3 installation ceremony this run depends on must be exactly as bound in the registration.
read -r POLICY_EVENTS POLICY_FINAL < <("$PY" -I -B -c 'import json,sys; a=json.load(open(sys.argv[1]))["policy_ceremony_audit"]; print(a["events_sha256"],a["final_result_sha256"])' "$REGISTRATION")
printf '%s  %s\n%s  %s\n' "$POLICY_EVENTS" "$STATE_ROOT/operational-policy-screening-v3-once-20261030/events.jsonl" "$POLICY_FINAL" "$STATE_ROOT/operational-policy-screening-v3-once-20261030/final-result.json" | sha256sum --check
EVIDENCE_HEAD_FILE="${TMPDIR:-/tmp}/.probe-evidence-head-$$"
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]==sys.argv[3]; open(sys.argv[4],"w").write(r["evidence_head"])' \
  "$REGISTRATION" "$REGISTRATION_SHA256" BOLTON_SCREENING_V3_RETAINED "$EVIDENCE_HEAD_FILE"
test "$(timeout 15s gh api user --jq .login)" = maxrose26
# The restricted job and this controller publish alternately to the evidence branch; its head must still be the registered one, or the run stops BEFORE any authority exists.
test "$(timeout 15s gh api repos/maxrose26/PropertyAIgent/git/ref/heads/stage4/narrow-continuation-evidence-20261016 --jq .object.sha)" = "$(cat "$EVIDENCE_HEAD_FILE")"
rm -f "$EVIDENCE_HEAD_FILE"
printf 'owner_preparation_github_cli_invocations=2\n'

printf '%s\n' \
  'SCREENING-V3 RETAINED-WINDOW ASSESSMENT, SUCCESSOR ATTEMPT (the 24 retained Bolton RECEIVED applications, 28 September to 4 October 2026).' \
  'ONE terminal: this window prints seven numbered progress messages. The only other thing you need is the GitHub approval page, later.' \
  '  [1/7] hidden prompt (120 seconds), validated against the complete exact route BEFORE the registration is consumed.' \
  '  [2/7] the 30 retained rows are verified against the pinned evidence and the 29 new items must be absent (read-only; nothing issued).' \
  '  [3/7] READY FOR HOSTED DISPATCH: paste that message into the Claude chat. Claude dispatches the hosted workflow ONCE; you approve the run in GitHub (Review deployments).' \
  '  [4/7] waiting for the hosted job to publish its READY marker (expected to take minutes; at most 30 minutes; outside the grant lifetime).' \
  '  [5/7] the owner registers the ONE named source-free allowance (900-second grant, 600-second execution deadline, 300-second cleanup reserve, source_calls=0, writes=0) and the hosted job screens the 24 records.' \
  '  [6/7] the owner ENDS the allowance with committed readbacks, publishes inside the enforced envelope, closes and seals.' \
  '  [7/7] final result. NO stop, credential, membership, role setting or secret is changed.' \
  'Ctrl-C ENDS THIS ATTEMPT. Until [5/7] appears nothing has been issued, except that the allowance may be in the middle of being registered, and the owner revokes it before exiting.' \
  'If Ctrl-C lands at the very instant of registration the result can be marked uncertain: then do nothing further, report it, and the allowance expires by itself within 900 seconds. Either way the attempt is spent and nothing is retried or replaced.' \
  'Keep this terminal open until controller_exit_status is printed (at most about 70 minutes by this mode deadlines).'
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
