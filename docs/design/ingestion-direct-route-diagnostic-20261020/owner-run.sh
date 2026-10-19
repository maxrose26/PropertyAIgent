#!/usr/bin/env bash
# Owner-local DIRECT-ROUTE restricted-connection diagnostic. Run it in YOUR OWN visible WSL terminal:
#   bash docs/design/ingestion-direct-route-diagnostic-20261020/owner-run.sh <commit> <tree> <registration-sha256>
# One diagnostic only. Never retry. No ingestion grant, source request or application write exists on this path.
# The credential is entered ONLY at the hidden prompt: never as an argument, file or environment variable.
set -euo pipefail
umask 077
[[ $# = 3 && "$1" =~ ^[a-f0-9]{40}$ && "$2" =~ ^[a-f0-9]{40}$ && "$3" =~ ^[a-f0-9]{64}$ ]] || { echo 'USAGE: owner-run.sh <commit40> <tree40> <registration-sha256>'; exit 2; }
COMMIT=$1; TREE=$2; REGISTRATION_SHA256=$3
REGISTRATION="$HOME/stage4-owner/operational-direct-route-registration-20261020.json"
STATE_ROOT="$HOME/.local/state/propertyaigent"
STATE_DIRECTORY=operational-direct-route-diagnostic-once-20261020
RUN1_DIRECTORY=operational-capture-queue-successor-once-20261018
RUN2_DIRECTORY=operational-capture-queue-settled-once-20261019
RUN3_DIRECTORY=operational-capture-queue-settled-r2-once-20261019
DIRECT_HOST=db.zcikcfgpblzuzpanpdqd.supabase.co
PY="$HOME/stage4-owner/storage-controller-venv/bin/python"
trap 'rm -f "${TMPDIR:-/tmp}/.direct-route-check-$$"' EXIT

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
printf 'direct_route_namespace_absent=%s\n' "$STATE_DIRECTORY"
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
# The direct host must have an IPv4 address (the project's IPv4 add-on). Every reviewed runtime is IPv4-only; without one the run would stop in preparation, so refuse BEFORE the credential prompt.
"$PY" -I -B -c 'import socket,sys; a=sorted({x[4][0] for x in socket.getaddrinfo(sys.argv[1],5432,family=socket.AF_INET,type=socket.SOCK_STREAM)}); print("direct_host_ipv4_addresses=%d"%len(a)); sys.exit(0 if 0<len(a)<=32 else 1)' "$DIRECT_HOST" || { echo 'DIRECT_HOST_HAS_NO_IPV4_ADDRESS: the IPv4 add-on is not active; refusing to launch'; exit 3; }

"$PY" -I -B -c \
  'import os,sys; from pathlib import Path; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; r=validate_registration(Path(sys.argv[1]).read_bytes(),sys.argv[2]); assert r["mode"]=="DIRECT_ROUTE_DIAGNOSTIC_ONLY" and r["restricted_route"]=="DIRECT"; print("registration_valid",file=sys.stderr)' \
  "$REGISTRATION" "$REGISTRATION_SHA256"
test "$(timeout 15s gh api user --jq .login)" = maxrose26
printf 'owner_preparation_github_cli_invocations=1\n'

printf '%s\n' \
  'Direct-route restricted-connection diagnostic. Effects, all finite and reversed in the same run:' \
  '  setup: restore the two reviewed capability memberships; set the three role-level timeouts (captured, restored later); set a FRESH password and VALID UNTIL on each restricted login;' \
  '         store two temporary protected secrets; ALTER ROLE ... LOGIN for both logins.' \
  '  diagnostic: ONE connection attempt for the worker login and, only if it succeeds, ONE for the effect login, to the DIRECT host with verify-full and a pinned IPv4 address; no query beyond the identity/settings check.' \
  '  teardown: NOLOGIN, NULL password, memberships revoked, role settings restored, both secrets deleted, closure verified.' \
  'No grant, exception, source request, queue row or application write. No retry and no fallback to another route.' \
  'The 120-second hidden-input timer starts at the prompt below. Enter the existing migration credential only there (typing is not echoed). Never paste it into chat.'
set +e
systemd-run --user --scope \
  --unit=propertyaigent-operational-once \
  -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=450s \
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
