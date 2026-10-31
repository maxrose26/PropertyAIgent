#!/usr/bin/env bash
# INACTIVE: run only after separate approval of this mutating recovery transaction.
(
set +x
set -eu
umask 077
repo="$HOME/stage4-owner/b-inspection-405f77f"
read -r -p 'Absolute extracted Bolton intake-install package directory: ' package
case "$package" in /*) ;; *) printf 'STOP: absolute path required\n'; exit 1;; esac
cd "$repo"
test "$(git rev-parse HEAD)" = 405f77f078a64175e037bd2e735de30658c1437f
test "$(git rev-parse 'HEAD^{tree}')" = 7a315b6a3388737d88498e69dc43d7282f74a95f
test -z "$(git status --porcelain)"
"$HOME/stage4-owner/storage-controller-venv/bin/python" -I -S - "$repo" "$package" <<'PY'
from pathlib import Path
import ast,hashlib,sys
r,p=map(Path,sys.argv[1:])
check=lambda path,h:hashlib.sha256(path.read_bytes()).hexdigest()==h
assert check(p/'bolton-intake-install.sql','674b4905ebf3b55edb541fe971a04b654d92d093d33e7afa5d7823992a37a86d')
assert check(p/'bolton-intake-install-client.py','c351b750e04fd5925a51919627a93b57d34e1db9211f8ca52e28a225384ecc55')
assert check(r/'verification/ingestion_storage/trust/supabase-prod-ca-2021.crt','700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7')
assert check(r/'docs/design/daily-intake-20261029/b-readonly.sql','131e519e8d69f2b48b951b2dcc45e43dd2967cba66ec3e894b028752506e4997')
assert check(r/'verification/ingestion_storage/intake_policy.py','ea5a27817d49b74c27e148e2478ae2327cfb294d4226470f1103cd090bae5487')      # the generators that produced this SQL (identical at 62fad2f)
assert check(r/'verification/ingestion_storage/screening_v3_worker_sql.py','937f9ad181e3492063d86c31e33851044fe630237370a0456ce39a6107161d1b')
pick=lambda s:next(x for x in ast.parse(s).body if isinstance(x,ast.FunctionDef) and x.name=='capture')
assert ast.dump(pick((r/'docs/design/daily-intake-20261029/b-readonly-client.py').read_text()))==ast.dump(pick((p/'bolton-intake-install-client.py').read_text()))
print('INSTALL_BINDINGS_VERIFIED; NO_DATABASE_CONNECTION_YET')
PY
"$HOME/stage4-owner/storage-controller-venv/bin/python" -I -S "$package/bolton-intake-install-client.py"
)
