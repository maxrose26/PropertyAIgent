#!/bin/bash
set -euo pipefail
interpreter=${1:?test interpreter}; output=${2:?evidence directory}
mkdir -p "$output"; output=$(realpath "$output")
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 STAGE26B_DIFFERENTIAL_OUTPUT="$output/qualified-differential.json" STAGE26B_UNIVERSE_OUTPUT="$output/universe-differential.json" \
 "$interpreter" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin \
 tests/test_stage26b_integrity.py tests/test_stage26b_containment.py tests/test_stage26b_differential.py --junitxml="$output/focused.xml" | tee "$output/focused.log"
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 "$interpreter" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin \
 tests/test_scheme_reconciliation.py tests/test_planning_status_verification.py tests/test_material_planning_change_detection.py tests/test_affordable_housing_scope.py tests/test_ah_scope_consumers.py tests/test_extraction_fidelity.py tests/test_residential_mix.py \
 --junitxml="$output/relevant.xml" | tee "$output/relevant.log"
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 "$interpreter" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_command_positive_plugin \
 tests/test_evidence_driven_intelligence_refresh.py --junitxml="$output/refresh.xml" | tee "$output/refresh.log"
