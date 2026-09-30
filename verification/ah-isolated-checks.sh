#!/usr/bin/env bash
# Called only inside the WSL wrapper's network namespace, as normal user.
set -euo pipefail
repo="$1"; output="$2"; venv="$3"
[ "$DATABASE_URL" = sqlite:///:memory: ] || exit 2
# A fresh network namespace has only a DOWN loopback and no external interfaces.
[ "$(ls /sys/class/net)" = lo ] || { echo 'STOP: network namespace unavailable'; exit 2; }
[ "$(cat /sys/class/net/lo/operstate)" = down ] || { echo 'STOP: loopback unexpectedly active'; exit 2; }
"$venv/bin/python" -c 'import sys, pytest, sqlalchemy, pandas; print(sys.version)' > "$output/runtime.txt"
"$venv/bin/python" -m pip freeze > "$output/dependencies.txt"
checks=(tests/test_agent_ready_fact_foundation.py tests/test_affordable_housing_scope.py tests/test_buyer_matching.py tests/test_buyer_mandate_v2_phase_b2.py tests/test_agent_evaluation_persistence.py)
cd "$repo"
set +e
timeout --kill-after=10s 300s "$venv/bin/python" -m pytest -q -p no:cacheprovider \
 "${checks[@]}" --junitxml="$output/candidate.xml" > "$output/candidate.log" 2>&1
candidate_result=$?
printf '%s\n' "$candidate_result" > "$output/candidate-exit.txt"
timeout --kill-after=10s 300s "$venv/bin/python" -m pytest -q -p no:cacheprovider \
 tests/test_ah_downstream_consumption.py tests/test_ah_buyer_trust.py --junitxml="$output/new-tests.xml" > "$output/new-tests.log" 2>&1
new_result=$?
printf '%s\n' "$new_result" > "$output/new-tests-exit.txt"
timeout --kill-after=10s 300s "$venv/bin/python" -m pytest -q -p no:cacheprovider \
 tests/test_ah_qualified_discovery.py verification/test_ah_assessment.py verification/test_ah_count_threshold.py \
 --junitxml="$output/spec020.xml" > "$output/spec020.log" 2>&1
spec020_result=$?
printf '%s\n' "$spec020_result" > "$output/spec020-exit.txt"
timeout --kill-after=10s 300s "$venv/bin/python" -m pytest -q -p no:cacheprovider \
 tests/test_ah_source_claims.py --junitxml="$output/provenance.xml" > "$output/provenance.log" 2>&1
provenance_result=$?
printf '%s\n' "$provenance_result" > "$output/provenance-exit.txt"
cd "$output/baseline"
timeout --kill-after=10s 300s "$venv/bin/python" -m pytest -q -p no:cacheprovider \
 "${checks[@]}" --junitxml="$output/baseline.xml" > "$output/baseline.log" 2>&1
baseline_result=$?
printf '%s\n' "$baseline_result" > "$output/baseline-exit.txt"
cd "$repo"
"$venv/bin/python" -m pytest -q -p no:cacheprovider verification/test_ah_filter.py --junitxml="$output/filter.xml" > "$output/filter.log" 2>&1
filter_result=$?
printf '%s\n' "$filter_result" > "$output/filter-exit.txt"
set -e
"$venv/bin/python" "$repo/verification/ah-result-summary.py" "$output"
printf 'Candidate exit: %s; baseline exit: %s; new-test exit: %s; filter exit: %s\n' "$candidate_result" "$baseline_result" "$new_result" "$filter_result"
[ "$candidate_result" = 0 ] && [ "$baseline_result" = 0 ] && [ "$new_result" = 0 ] && [ "$filter_result" = 0 ] && [ "$spec020_result" = 0 ] && [ "$provenance_result" = 0 ]
