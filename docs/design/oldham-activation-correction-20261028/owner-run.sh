#!/usr/bin/env bash
# Inactive until exact owner approval and registration release. No credentials in args.
set -euo pipefail
umask 077
if [[ $# != 4 && $# != 5 ]]; then echo 'STOP: expected checkout, python, package, SHA256'; exit 2; fi
checkout=$1
owner_python=$2
package=$3
expected=$4
test -d "$checkout"
test -x "$owner_python"
test -f "$package"
[[ $expected =~ ^[a-f0-9]{64}$ ]]
fixture=false
if [[ $# == 5 ]]; then [[ $5 == --disposable-test ]]; fixture=true; fi
cd "$checkout"
printf '%s  %s\n' "$expected" "$package" | sha256sum --check
"$owner_python" -I -B -c 'import json,sys,subprocess; p=json.load(open(sys.argv[1])); assert p["version"]=="OLDHAM_CAPTURE_SCREENING_INSTALLED_V1"; assert p["mode"]==("DISPOSABLE_TEST" if sys.argv[2]=="true" else "LIVE"); assert p["expires_at"] is not None,"STOP: INACTIVE_PACKAGE"; assert subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()==p["revision"]; assert subprocess.check_output(["git","rev-parse","HEAD^{tree}"],text=True).strip()==p["tree"]; assert not subprocess.check_output(["git","status","--porcelain"],text=True)' "$package" "$fixture"
runner='import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module("verification.ingestion_storage.oldham_owner_once",run_name="__main__")'
if $fixture; then
  # Explicit fixture only: backend refuses any destination except isolated loopback PG.
  exec env -i HOME="$HOME" PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite:///:memory: INGESTION_PROVISIONING_TEST_URL="${INGESTION_PROVISIONING_TEST_URL-}" OLDHAM_WRAPPER_SCENARIO="${OLDHAM_WRAPPER_SCENARIO-reuse_zero}" OLDHAM_WRAPPER_NATIVE="${OLDHAM_WRAPPER_NATIVE-0}" "$owner_python" -I -B -c "$runner" "$checkout" --package "$package" --package-sha256 "$expected" --disposable-test
fi
[[ -t 0 && -t 2 ]]
set +e
systemd-run --user --scope --unit=propertyaigent-operational-once -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=790s env -i HOME="$HOME" PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$owner_python" -I -B -c "$runner" "$checkout" --package "$package" --package-sha256 "$expected"
controller_status=$?
printf 'OWNER_CONTROLLER_EXIT_STATUS=%s\n' "$controller_status"
timeout 5s systemctl --user show propertyaigent-operational-once.scope --no-pager -p LoadState -p ActiveState -p SubState -p Result -p InvocationID -p ControlGroup
printf 'OUTER_SCOPE_READBACK_EXIT_STATUS=%s\n' "$?"
exit "$controller_status"
