#!/bin/bash
# Local synthetic/disposable verification only. No hosted or production access.
set -euo pipefail
interpreter=${1:?isolated interpreter}; output=${2:?external evidence directory}; chromium=${3:?local Chromium executable}
mkdir -p "$output"
output=$(realpath "$output")
git rev-parse HEAD HEAD^{tree} > "$output/candidate-identity.txt"
git status --porcelain > "$output/starting-status.txt"
run_pytest() {
 local group=$1; shift
 env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$interpreter" verification/ah-offline-pytest.py -q -p no:cacheprovider "$@" --junitxml="$output/$group.xml" > "$output/$group.log" 2>&1
}
run_pytest security verification/test_stage1_access.py verification/test_stage1_commands.py verification/test_stage1_buyer_scope.py verification/test_stage1_cli.py verification/test_stage1_csv.py verification/test_stage1_outbound.py verification/test_stage1_call_sites.py verification/test_stage1_aia.py verification/test_stage1_pdf_compatibility.py
run_pytest delivery_regressions verification/test_stage1_delivery_identity.py verification/test_stage1_lifecycle_evidence.py
run_pytest registry verification/test_stage1_registry_capacity.py
run_pytest original -p verification.stage1_preservation_plugin verification/test_ah_kpi_selection.py verification/test_ah_classification_presentation.py verification/test_ah_count_threshold.py verification/test_ah_tenure_presentation.py tests/test_ah_scope_consumers.py tests/test_gate2b2b1_trusted_consumer_alignment.py tests/test_opportunity_feed.py tests/test_affordable_housing_scope.py tests/test_residential_mix.py tests/test_site_profile.py tests/test_ownership_control_reporting.py
run_pytest lifecycle -p verification.stage1_preservation_plugin verification/test_ui_session_lifecycle.py
run_pytest workflow verification/production_readiness/test_workflow_context.py
for mode in walkthrough lifecycle; do
 env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" verification/stage1_apptest_adapter.py "$mode" "$output/connection-accounting.json" > "$output/apptest-$mode.log" 2>&1
done
env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" verification/stage1_lifecycle_evidence.py "$output/connection-accounting.json" "$output/apptest-lifecycle.log" > "$output/lifecycle-evidence.json"
"$interpreter" - "$output" <<'PY'
from pathlib import Path
import sys,shutil
out=Path(sys.argv[1]);lines=(out/'apptest-walkthrough.log').read_text().splitlines();source=Path(next(line[5:] for line in reversed(lines) if line.startswith('DONE ')))
for path in source.iterdir():
 if path.suffix in ('.json','.csv'):shutil.copyfile(path,out/path.name)
PY
env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" verification/stage1_transport_check.py "$output/transport" > "$output/transport.log" 2>&1
env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" verification/stage1_document_browser_check.py "$output/document-browser" "$chromium" > "$output/document-browser.log" 2>&1
env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" verification/stage1_browser_check.py --output "$output/browser" --chromium "$chromium" > "$output/browser.log" 2>&1
"$interpreter" -m pip check > "$output/pip-check.txt"
git diff --check > "$output/diff-check.txt"
git status --porcelain > "$output/ending-status.txt"
printf 'COMPLETED MECHANISM PACK DONE; separate document egress gate is required\n'
