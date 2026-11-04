#!/bin/bash
# Complete final-candidate local gate. Any nonzero exit is a user stop condition.
set -euo pipefail
interpreter=${1:?isolated Python}; output=$(realpath -m "${2:?external evidence}"); chromium=${3:?Chromium}; office=${4:?LibreOffice}
mkdir -p "$output"
git rev-parse HEAD HEAD^{tree} HEAD^ > "$output/exact-identity.txt"
test -z "$(git status --porcelain)"
bash verification/stage1-bounded-check.sh "$interpreter" "$output/baseline" "$chromium" "$office" > "$output/baseline.log" 2>&1
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$interpreter" verification/ah-offline-pytest.py -q -p no:cacheprovider verification/test_stage1_document_process.py --junitxml="$output/process-unit.xml" > "$output/process-unit.log" 2>&1
env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" verification/stage1_document_bootstrap_check.py "$output/bootstrap" > "$output/bootstrap.log" 2>&1
env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" verification/stage1_document_abi_check.py "$output/abi" > "$output/abi.log" 2>&1
for suite in cleanup native_matrix native_extra rtc; do
 env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" "verification/stage1_document_${suite}_check.py" "$output/$suite" "$chromium" > "$output/$suite.log" 2>&1
done
git diff --check
test -z "$(git status --porcelain)"
git status --porcelain > "$output/ending-status.txt"
printf 'RENDERER VERIFICATION PACK PASS; writer-attribution and acceptance decisions remain separate\n'
