#!/bin/bash
# Complete local evidence pack. Final egress gate exits nonzero while unresolved.
set -euo pipefail
interpreter=${1:?isolated Python}; output=$(realpath -m "${2:?external evidence}"); chromium=${3:?Chromium}; office=${4:?LibreOffice}
mkdir -p "$output"
bash verification/stage1-check.sh "$interpreter" "$output" "$chromium"
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$interpreter" verification/ah-offline-pytest.py -q -p no:cacheprovider verification/test_stage1_cli_positive.py --junitxml="$output/cli-positive.xml" > "$output/cli-positive.log" 2>&1
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 STAGE1_COMMAND_EVIDENCE="$output/command-positive-actions.json" "$interpreter" verification/stage1_spawn_offline_pytest.py -q --tb=short -p no:cacheprovider -p verification.stage1_command_positive_plugin verification/test_stage1_command_positives.py tests/test_review.py tests/test_monitor.py tests/test_report_discovery.py tests/test_local_plan_summary.py tests/test_allocation_intelligence_summary.py tests/test_cross_site_intelligence.py tests/test_agent_evaluation_persistence.py tests/test_plan_evidence_extraction.py tests/test_report_driven_extraction.py tests/test_visual_evidence.py tests/test_applicant_intelligence.py tests/test_evidence_driven_intelligence_refresh.py tests/test_allocation_web_research.py tests/test_pr2_final_amendment_migration_and_intelligence_processing.py::test_process_intelligence_backlog_selects_only_outstanding_applications tests/test_pr2_final_amendment_migration_and_intelligence_processing.py::test_process_intelligence_backlog_enforces_extraction_limit_across_councils tests/test_pr2_final_amendment_migration_and_intelligence_processing.py::test_process_intelligence_backlog_workload_is_bounded_not_unlimited --junitxml="$output/command-positive.xml" > "$output/command-positive.log" 2>&1
env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" verification/stage1_spreadsheet_check.py "$output/spreadsheet" "$office" > "$output/spreadsheet.log" 2>&1
"$interpreter" - "$output" <<'PY'
from pathlib import Path
import json,sys
out=Path(sys.argv[1]);manifest=json.loads(Path('verification/stage1_service_manifest.json').read_text());records=json.loads((out/'command-positive-actions.json').read_text())['completed']
actions={a.removeprefix('paid:') for functions in manifest.values() for a in functions.values() if a!='read'}
matrix={action:{'positive_tests':sorted({r['test'] for r in records if r['action']==action}), 'denial':'verification/test_stage1_commands.py::test_service_denial_before_inputs; paid switches additionally tested for paid families'} for action in sorted(actions)}
(out/'command-family-matrix.json').write_text(json.dumps(matrix,indent=2))
assert all(row['positive_tests'] for row in matrix.values()),'Missing command family positive evidence'
PY
git status --porcelain > "$output/ending-status.txt"
env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$interpreter" verification/stage1_document_egress_check.py "$output/document-egress" "$chromium" > "$output/document-egress.log" 2>&1
printf 'BOUNDED BASELINE PACK DONE; final renderer-process gate still required\n'
