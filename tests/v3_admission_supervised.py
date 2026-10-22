"""CI fixture harness, not a production entrypoint; only fixed disposable PG."""
import json
import os
from pathlib import Path
import sys

from verification.ingestion_storage.operational_supervisor import supervise


def main():
    import psycopg
    raw = os.environ['INGESTION_PROVISIONING_TEST_URL']
    info = psycopg.conninfo.conninfo_to_dict(raw)
    if (info.get('host'), info.get('port'), info.get('dbname'), info.get('user')) != ('127.0.0.1', '5432', 'ingestion_provisioning_test', 'provisioning_bootstrap'):
        raise ValueError('FIXED_DISPOSABLE_ONLY')
    root = Path(sys.argv[1])
    receipt = supervise([sys.executable, '-m', 'pytest', 'tests/test_ingestion_v3_admission_pg.py', '-q', '--junitxml=' + str(root / 'results.xml')],
                        environment=dict(DATABASE_URL='sqlite:///:memory:', INGESTION_PROVISIONING_TEST_URL=raw), root=root, seconds=150)
    (root / 'supervisor.json').write_text(json.dumps(receipt, sort_keys=True))
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt['exit_code'] == 0 and receipt['cleanup'] == 'CLOSED' and receipt['live_owned_survivors'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
