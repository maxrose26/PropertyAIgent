#!/bin/bash
# Synthetic SQLite only; syscall guards prevent outbound access during tests.
set -euo pipefail
interpreter=${1:?test interpreter}; output=${2:?evidence directory}
mkdir -p "$output"
output=$(realpath "$output")
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 "$interpreter" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin \
 tests/test_stage2_commercial_evidence.py tests/test_stage2_unit_phasing.py \
 tests/test_buyer_matching.py tests/test_buyer_mandate_v2_phase_b2.py tests/test_nesten_canonical_mandate.py tests/test_wholly_affordable_state.py tests/test_acquisition_subject_identity.py tests/test_agent_evaluation_persistence.py \
 --junitxml="$output/stage2.xml" | tee "$output/stage2.log"
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 "$interpreter" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider \
 verification/test_stage1_access.py verification/test_stage1_buyer_scope.py verification/test_stage1_call_sites.py verification/test_stage1_commands.py \
 --junitxml="$output/security.xml" | tee "$output/security.log"
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 "$interpreter" verification/stage2_ui_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin \
 tests/test_stage2_profile_journey.py verification/test_ui_session_lifecycle.py \
 --junitxml="$output/journey.xml" | tee "$output/journey.log"
