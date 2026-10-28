#!/usr/bin/env bash
# REVIEW ONLY. Separate attended approval and registration.json are required.
set -euo pipefail
[[ $# = 1 && "$1" =~ ^[a-f0-9]{64}$ ]] || { echo 'APPROVED_REGISTRATION_SHA256_REQUIRED'; exit 2; }
registration_sha256=$1
umask 077
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir="$HOME/stage4-owner/pr122-storage-acceptance"
owner_python="$HOME/stage4-owner/storage-controller-venv/bin/python"
registration="$bundle_dir/registration.json"
[[ -t 0 && -t 2 ]] || { echo 'VISIBLE_OWNER_TTY_REQUIRED'; exit 2; }
cd "$bundle_dir"
sha256sum --check SHA256SUMS
cd "$repo_dir"
test "$(git rev-parse HEAD)" = fa0064aa111c55bf4f8be1e4d4216aa2fe2b529e
test "$(git rev-parse 'HEAD^{tree}')" = 03751b14fa23d260baad2d39de2ad7bf604e563a
test -z "$(git status --porcelain)"
test -x "$owner_python"
test -f "$registration"
test ! -e "$HOME/.local/state/propertyaigent/oldham-activation-reconciliation-once-20261028"
printf '%s  %s\n' "$registration_sha256" "$registration" | sha256sum --check
# No hidden input, DNS or connection: pure local approval/binding validation.
"$owner_python" -I -B -c 'import importlib.util,os,sys;sys.path.insert(0,os.getcwd());s=importlib.util.spec_from_file_location("fixed_reconciliation",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.configure();m.validate(m.Path(sys.argv[2]).read_bytes(),sys.argv[3]);print("READONLY_REGISTRATION_VALID")' "$bundle_dir/diagnostic.py" "$registration" "$registration_sha256"
printf '%s\n' 'One READ ONLY diagnostic. No GRANT, SET ROLE, activation, revocation, policy rollback or secret API.' 'Existing administrative migration URL: hidden prompt only. Never paste it into chat. No retries.'
set +e
systemd-run --user --scope --unit=propertyaigent-operational-once \
 -p Delegate=memory -p MemoryMax=1610612736 -p MemorySwapMax=0 -p OOMPolicy=kill -p RuntimeMaxSec=180s \
 "$owner_python" -I -B -c 'import os,runpy,sys;sys.path.insert(0,os.getcwd());runpy.run_path(sys.argv.pop(1),run_name="__main__")' \
 "$bundle_dir/diagnostic.py" --registration "$registration" --registration-sha256 "$registration_sha256"
controller_status=$?
printf 'controller_exit_status=%s\n' "$controller_status"
timeout 5s systemctl --user show propertyaigent-operational-once.scope --no-pager -p LoadState -p ActiveState -p SubState -p Result -p ControlGroup
printf 'outer_scope_readback_exit_status=%s\n' "$?"
for file in events.jsonl final-result.json; do
 sha256sum "$HOME/.local/state/propertyaigent/oldham-activation-reconciliation-once-20261028/$file"
done
exit "$controller_status"
