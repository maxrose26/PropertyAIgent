#!/bin/bash
# No production inputs. Outputs stay outside the checkout.
set -euo pipefail
interpreter=${1:?test interpreter}; output=${2:?evidence directory}
mkdir -p "$output"
output=$(realpath "$output")
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 "$interpreter" verification/ah-offline-pytest.py -q -p no:cacheprovider \
 verification/test_ah_classification_presentation.py verification/test_ah_count_threshold.py verification/test_ah_tenure_presentation.py \
 tests/test_ah_scope_consumers.py tests/test_gate2b2b1_trusted_consumer_alignment.py tests/test_opportunity_feed.py tests/test_affordable_housing_scope.py tests/test_residential_mix.py tests/test_site_profile.py tests/test_ownership_control_reporting.py \
 --junitxml="$output/tests.xml" | tee "$output/tests.log"
env -i HOME=/tmp PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
 "$interpreter" verification/web_ah/walkthrough.py > "$output/walkthrough.log" 2>&1
"$interpreter" - "$output" <<'PY'
from pathlib import Path
import shutil
import sys
out=Path(sys.argv[1])
lines=(out/'walkthrough.log').read_text().splitlines()
source=Path(next(line[5:] for line in reversed(lines) if line.startswith('DONE ')))
for path in source.iterdir():
    if path.suffix in ('.json','.csv'):
        shutil.copyfile(path,out/path.name)
print('Walkthrough passed; selected CSV bytes and rendered output retained.')
PY
