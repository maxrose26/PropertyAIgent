#!/bin/bash
# Dependency download only. No database/service actions.
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/../.." && pwd)
venv=${1:?Supply a NEW dedicated venv path}
[[ ! -e "$venv" ]] || { echo 'Refusing an existing venv' >&2; exit 1; }
setup_home=$(mktemp -d)
trap 'rm -rf -- "$setup_home"' EXIT
/usr/bin/env -i HOME="$setup_home" PATH=/usr/bin:/bin /usr/bin/python3 -m venv "$venv"
/usr/bin/env -i HOME="$setup_home" PATH="$venv/bin:/usr/bin:/bin" "$venv/bin/python" -m pip --isolated install --index-url https://pypi.org/simple -r "$repo/verification/ah_pg/requirements.lock"
/usr/bin/env -i HOME="$setup_home" PATH="$venv/bin:/usr/bin:/bin" "$venv/bin/python" "$repo/verification/ah_pg/preflight.py" "$venv/ah-dependencies.json"
echo "Dependency preflight complete: $venv/ah-dependencies.json"
