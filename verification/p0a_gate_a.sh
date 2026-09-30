#!/usr/bin/env bash
# Run only inside the authorised non-production Linux runtime described in the handoff.
set -euo pipefail
repo=$(git rev-parse --show-toplevel)
cd "$repo"
: "${P0A_EXPECTED_COMMIT:?Set the reviewed candidate commit}"
[ "$(git rev-parse HEAD)" = "$P0A_EXPECTED_COMMIT" ] || { echo 'Wrong candidate commit'; exit 2; }
[ -z "$(git status --porcelain)" ] || { echo 'Dirty candidate tree'; exit 2; }
[ "$(id -u)" != 0 ] || { echo 'Use a non-root test account'; exit 2; }
[ "$(ls /sys/class/net)" = lo ] || { echo 'Require an isolated network namespace with loopback only'; exit 2; }
for tool in initdb pg_ctl; do command -v "$tool" >/dev/null; done
# Do not load any real application environment. Refuse inherited production inputs.
while IFS= read -r var; do
 case "$var" in
 DATABASE_URL|RENDER*|OPENAI*|ANTHROPIC*|SUPABASE*|PG*|PROPERTYAIGENT_*|P0A_TEST_POSTGRES_URL)
  echo "Remove inherited $var from test runtime"; exit 2;;
 esac
done < <(compgen -e)
path_check="$repo"
while :; do
 [ ! -e "$path_check/.env" ] || { echo 'Remove ancestor/repository .env from isolated runtime'; exit 2; }
 [ "$path_check" = / ] && break
 path_check=$(dirname "$path_check")
done
unset PYTHONPATH PYTHONHOME PYTEST_ADDOPTS PYTEST_PLUGINS
export PYTEST_ADDOPTS='-o junit_family=legacy'
python - <<'PY'
import os,subprocess,sys,psutil
from pathlib import Path
from playwright.sync_api import sync_playwright
assert psutil.Process(os.getpid()).create_time() > 0
p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'],start_new_session=True)
try:
 assert psutil.Process(p.pid).create_time()>0
 assert p.pid in [c.pid for c in psutil.Process().children()]
finally:p.kill();p.wait()
with sync_playwright() as runtime:
 assert Path(runtime.chromium.executable_path).is_file(), 'Matching Chromium binary missing'
PY
scratch=$(mktemp -d /tmp/p0a-verification.XXXXXX)
output=${P0A_OUTPUT_DIR:-"$scratch/results"}
mkdir -p "$output"
export P0A_OUTPUT_DIR="$output"
git rev-parse HEAD > "$output/candidate-commit.txt"
git hash-object verification/p0a_gate_a.sh > "$output/runner-blob.txt"
sha256sum verification/p0a-python-environment.txt > "$output/dependency-snapshot-sha256.txt"
git status --porcelain > "$output/working-tree.txt"
python --version > "$output/python-version.txt"
python -m pip list --format=freeze > "$output/actual-dependencies.txt"
diff -u verification/p0a-python-environment.txt "$output/actual-dependencies.txt"
baseline="$scratch/baseline"
cleanup() {
 pg_ctl -D "$scratch/pg" -m immediate -w stop >/dev/null 2>&1 || true
 git worktree remove --force "$baseline" >/dev/null 2>&1 || true
 # Preserve results and cluster evidence; operator may remove this unique scratch path.
 echo "Verification evidence: $output"
}
trap cleanup EXIT
port=$(python -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
# env -i removes locale inputs: explicitly select UTF-8 rather than C/SQL_ASCII.
initdb -D "$scratch/pg" --encoding=UTF8 --locale=C -A trust -U p0a_local > "$output/initdb.log"
pg_ctl -D "$scratch/pg" -l "$output/postgres.log" -o "-h 127.0.0.1 -p $port -k $scratch" -w start
export P0A_TEST_POSTGRES_URL="postgresql+psycopg://p0a_local@127.0.0.1:$port/p0a_test_gate_a"
python - <<'PY'
import os
import psycopg
from sqlalchemy.engine import make_url
url=make_url(os.environ['P0A_TEST_POSTGRES_URL'])
with psycopg.connect(host=url.host,port=url.port,user=url.username,dbname='postgres',autocommit=True) as c:
 assert c.execute('SHOW server_encoding').fetchone()[0] == 'UTF8'
 c.execute('CREATE DATABASE p0a_test_gate_a')
 with open(os.path.join(os.environ['P0A_OUTPUT_DIR'], 'postgres-encoding.txt'), 'w') as evidence:
  evidence.write('server_encoding=UTF8\n')
PY
files=(tests/test_daily_discovery_portal_resilience.py tests/test_render_daily_discovery_memory_audit.py tests/test_render_daily_discovery_runtime_failure_hotfix.py tests/test_council_recovery_circuit_breaker.py tests/test_salford_document_memory_diagnosis.py tests/test_targeted_evidence_refresh.py tests/test_pr2_final_amendment_migration_and_intelligence_processing.py tests/test_migration.py tests/test_salford_child_process_memory_diagnosis.py tests/test_pr2_scraper_freshness_and_scheduling.py tests/test_pr2_premerge_ai_cost_and_migration_safety.py)
set +e
PYTHONPATH=tests:. python -m pytest -p p0a_offline_guard -ra --junitxml="$output/candidate.xml" tests/test_p0a_bounded_discovery.py tests/test_p0a_chromium_integration.py tests/test_p0a_release_corrections.py "${files[@]}" -k 'not page_recycling_keeps_renderer_rss_flat_across_navigations' > "$output/candidate.log" 2>&1
candidate_result=$?
set -e
git worktree add --detach "$baseline" 301a56b3cde781f37e5f5bb0ffaded6537d5ca14
cd "$baseline"
set +e
PYTHONPATH="$repo/tests:." python -m pytest -p p0a_offline_guard -ra --junitxml="$output/baseline.xml" "${files[@]}" -k 'not page_recycling_keeps_renderer_rss_flat_across_navigations' > "$output/baseline.log" 2>&1
baseline_result=$?
set -e
printf 'Candidate exit: %s; baseline exit: %s\n' "$candidate_result" "$baseline_result"
# No "passed" claim from equivalent nonzero exits; inspect each failure/skip.
exit "$candidate_result"
