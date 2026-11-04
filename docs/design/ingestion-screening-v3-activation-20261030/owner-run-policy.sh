#!/usr/bin/env bash
# Owner-local SCREENING-V3 INSTALLATION ceremony (PR #175). Run it in YOUR OWN visible WSL terminal (no GitHub sign-in is needed):
#   bash docs/design/ingestion-screening-v3-activation-20261030/owner-run-policy.sh <commit> <tree> <registration-sha256>
# One ceremony per registration. The credential is entered ONLY at the hidden prompt, which is validated against the complete route BEFORE the registration is consumed (a rejected value consumes nothing).
# It installs policy v6 (two reviewed function definitions: ingestion_bolton_allowed, ingestion_register_bolton_exception) and then the derived v3 worker function (one definition: ingestion_worker_step), verifying the reviewed
# inventory before, between and after, observes the control record before and after (it must be byte-for-byte unchanged) and reads the transient owner capability back absent. It issues no authority, makes no source request
# and no GitHub request, and changes no stop, grant, exception, credential, membership, role setting or secret. KEEP THIS TERMINAL OPEN until it prints controller_exit_status (the scope allows at most 300 seconds).
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run-policy.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/operational-bolton-policy-screening-v3-registration-20261030.json"
STATE_DIRECTORY=operational-policy-screening-v3-once-20261030
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
scope_state="$(timeout 10s systemctl --user show propertyaigent-operational-once.scope -p LoadState --value)" || { echo 'SCOPE_STATE_UNKNOWN: refusing to launch'; exit 3; }
[[ "$scope_state" = not-found ]] || { echo "SCOPE_PRESENT_OR_UNKNOWN ($scope_state): refusing to launch"; exit 3; }
"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]==sys.argv[3]' \
  "$REGISTRATION" "$REGISTRATION_SHA256" BOLTON_POLICY_SCREENING_V3

printf '%s\n' \
  'SCREENING-V3 INSTALLATION (policy v6 + derived v3 worker function). Effects:' \
  '  0. ONE bounded hidden prompt (120 seconds), validated against the complete exact route BEFORE the registration is consumed.' \
  '  1. a fixed control observation that must be the DERIVED generation-3 stop state, with every consumed name REVOKED, nothing unexpired and the new allowance name never registered.' \
  '  2. the installed policy-v5 inventory is verified; policy v6 (two function definitions) is installed and its inventory verified; the derived v3 worker function (one definition) is installed and the final inventory verified;' \
  '     the capability is read back absent; the control record is observed again and must be byte-for-byte unchanged.' \
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
