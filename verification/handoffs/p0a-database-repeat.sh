#!/usr/bin/env bash
# WSL operator wrapper. Does not modify the frozen candidate runner.
set -euo pipefail
if [ "${1:-}" = --inner ]; then
 set -euo pipefail
 cd "$HOME/p0a-work/PropertyAIgent"
 [ "$(ls /sys/class/net)" = lo ] || exit 2
 [ "$(id -u)" != 0 ] || exit 2
 [ "$(git rev-parse HEAD)" = "$P0A_EXPECTED_COMMIT" ] || exit 2
 [ -z "$(git status --porcelain)" ] || exit 2
 output="$P0A_OUTPUT_DIR"
 git rev-parse HEAD > "$output/candidate-commit.txt"
 git status --porcelain > "$output/working-tree.txt"
 python --version > "$output/python-version.txt"
 python -m pip list --format=freeze > "$output/actual-dependencies.txt"
 diff -u verification/p0a-python-environment.txt "$output/actual-dependencies.txt"
 sha256sum "$HOME/p0a-handoff/p0a-database-repeat.sh" > "$output/targeted-runner-sha256.txt"
 export PYTEST_ADDOPTS='-o junit_family=legacy'
 scratch=$(mktemp -d /tmp/p0a-database-repeat.XXXXXX)
 cleanup_database() {
  pg_ctl -D "$scratch/pg" -m immediate -w stop > "$output/postgres-stop.log" 2>&1 || true
 }
 trap cleanup_database EXIT
port=$(python -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
# env -i removes locale inputs: explicitly select UTF-8 rather than C/SQL_ASCII.
initdb -D "$scratch/pg" --encoding=UTF8 --locale=C -A trust -U p0a_local > "$output/initdb.log"
pg_ctl -D "$scratch/pg" -l "$output/postgres.log" -o "-h 127.0.0.1 -p $port -k $scratch -c log_statement=all -c log_duration=on" -w start
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
 for attempt in 1 2 3 4 5; do
  echo "Database attempt $attempt of 5"
  set +e
  PYTHONPATH=tests:. python -m pytest -p p0a_offline_guard -ra \
   --basetemp="$output/attempt-$attempt-tmp" \
   --junitxml="$output/attempt-$attempt.xml" \
   tests/test_p0a_release_corrections.py::test_pg_real_timeout_retry_and_subsequent_work \
   > "$output/attempt-$attempt.log" 2>&1
  result=$?
  set -e
  printf '%s\n' "$result" > "$output/attempt-$attempt-exit.txt"
  # Do not conceal an application failure with repeated retries. Namespace
  # teardown is containment only, never evidence that application cleanup passed.
  [ "$result" = 0 ] || break
 done
 python - <<'PY'
import json, os, pathlib, xml.etree.ElementTree as ET
p=pathlib.Path(os.environ['P0A_OUTPUT_DIR']); rows=[]
for i in range(1,6):
 f=p/f'attempt-{i}.xml'
 if not f.exists():break
 root=ET.parse(f); cases=list(root.iter('testcase'))
 ok=len(cases)==1 and all(c.find(x) is None for c in cases for x in ('failure','error','skipped'))
 rows.append({'attempt':i,'passed':ok,'test_cases':len(cases),
  'measurements':[v.attrib for c in cases for v in c.findall('properties/property')],
  'effective_settings_before_and_after_asserted_by_test': {'statement_timeout':'15s','lock_timeout':'5s','idle_in_transaction_session_timeout':'30s'} if ok else 'inspect XML properties and traceback',
  'rollback_and_connection_reuse_asserted_by_test':ok})
result={'candidate':(p/'candidate-commit.txt').read_text().strip(),'attempts':rows,
 'all_five_passed':len(rows)==5 and all(x['passed'] for x in rows),
 'scope':'Only database timeout and recovery; baseline not rerun; no production readiness claim'}
(p/'targeted-summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['all_five_passed'] else 1)
PY
 exit $?
fi
task_root="$HOME/p0a-work"
repo="$task_root/PropertyAIgent"
venv="$task_root/venv"
: "${1:?Pass the exact reviewed candidate SHA}"
candidate="$1"
[ "$candidate" = 06b978c59ece44bb20efc6d5b26009d769a22b5d ] || { echo "STOP: targeted runner requires reviewed 06b978c"; exit 2; }
[[ "$candidate" =~ ^[0-9a-f]{40}$ ]] || { echo "STOP: require full candidate SHA"; exit 2; }
if [ "$(id -u)" = 0 ]; then echo 'Run as your normal Ubuntu user, without sudo.'; exit 2; fi
# Reject, never print values or silently discard production inputs.
while IFS= read -r key; do
 case "$key" in DATABASE_URL|RENDER*|OPENAI*|ANTHROPIC*|SUPABASE*|PG*|PROPERTYAIGENT_*|P0A_TEST_POSTGRES_URL)
  echo "STOP: inherited $key is present; use a clean test terminal."; exit 2;; esac
done < <(compgen -e)
path_check="$repo"
while :; do
 [ ! -e "$path_check/.env" ] || { echo "STOP: .env present at $path_check; do not delete it or use this checkout."; exit 2; }
 [ "$path_check" = / ] && break
 path_check=$(dirname "$path_check")
done
[ "$(git -C "$repo" rev-parse HEAD)" = "$candidate" ] || { echo 'STOP: wrong candidate'; exit 2; }
[ -z "$(git -C "$repo" status --porcelain)" ] || { echo 'STOP: dirty checkout'; exit 2; }
[ "$(git -C "$repo" hash-object verification/p0a_gate_a.sh)" = aa27ee294e57ff87c7aafa58a71b56df1e6336d7 ] || exit 2
[ -x "$venv/bin/python" ] || { echo 'STOP: create the isolated venv first'; exit 2; }
[ -x /usr/lib/postgresql/16/bin/initdb ] || { echo 'STOP: PostgreSQL 16 tools missing'; exit 2; }
for tool in sudo unshare mount ip tini runuser; do command -v "$tool" >/dev/null; done
task_user=$(id -un)
task_home="$HOME"
output="$task_root/database-repeat-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$output"
printf '%s\n' 'Python 3.12.3 is accepted for integration verification subject to pinned dependencies and matched baseline; prior evidence used 3.12.14.' > "$output/environment-decision.txt"
# sudo is only for temporary Linux namespaces. PostgreSQL/tests run as task_user.
# Private mounts leave the WSL host mount table and network untouched.
set +e
sudo /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
 /usr/bin/unshare --mount --net --pid --fork --mount-proc --propagation private --kill-child \
 /bin/bash -c '
 set -euo pipefail
 mount -t sysfs -o nosuid,nodev,noexec sysfs /sys
 ip link set lo up
 [ "$(ls /sys/class/net)" = lo ]
 exec /usr/bin/tini -- /usr/sbin/runuser -u "$1" -- /usr/bin/env -i \
  HOME="$2" USER="$1" LOGNAME="$1" \
  PATH="$3/venv/bin:/usr/lib/postgresql/16/bin:/usr/bin:/bin" \
  PLAYWRIGHT_BROWSERS_PATH="$3/browsers" PYTHONDONTWRITEBYTECODE=1 \
  P0A_EXPECTED_COMMIT="$5" P0A_OUTPUT_DIR="$4" \
  /bin/bash -c '\''cd "$1/PropertyAIgent"; exec bash "$1/../p0a-handoff/p0a-database-repeat.sh" --inner'\'' bash "$3"
 ' bash "$task_user" "$task_home" "$task_root" "$output" "$candidate" 2>&1 | tee "$output/operator-console.log"
result=${PIPESTATUS[0]}
set -e
printf '%s\n' "$result" > "$output/runner-exit-code.txt"
tar -czf "$output.tar.gz" -C "$task_root" "$(basename "$output")"
echo "Return this file: $output.tar.gz"
echo "Runner exit $result. Failures/skips require assessment; this script does not approve Gate A."
exit "$result"
