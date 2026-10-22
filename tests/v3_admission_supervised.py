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


def race():
    """Competing disposable delivery: real restricted writer, no ledger access."""
    from sqlalchemy.engine import make_url
    from dataclasses import fields
    from datetime import date, datetime
    from app.pipeline.discovery_contract import DiscoveryEnvelope, WindowEvidence
    from app.pipeline.discovery_admission import admit_identity
    from verification.ingestion_storage.operational_controller import DatabaseBudget
    raw = os.environ.pop('V3_DISPOSABLE_WRITER_URL')
    u = make_url(raw)
    if (u.host, u.port, u.database, u.username) != ('127.0.0.1', 5432, 'ingestion_provisioning_test', 'ingestion_application_login'):
        raise ValueError('FIXED_RESTRICTED_DISPOSABLE_WRITER')
    value = json.load(sys.stdin)
    for k in ('requested_start', 'requested_end', 'applied_start', 'applied_end'):
        value['window'][k] = date.fromisoformat(value['window'][k]) if value['window'][k] else None
    value['window'] = WindowEvidence(**value['window'])
    value['discovered_at'] = datetime.fromisoformat(value['discovered_at'])
    value['displayed_references'] = tuple(value['displayed_references'])
    value['fields'] = tuple(value['fields'])
    budget = DatabaseBudget()
    engine = budget.engine(raw)
    try:
        result = admit_identity(engine, DiscoveryEnvelope(**value))
    finally:
        costs = budget.close([])
    print(json.dumps(dict(outcome=result['outcome'], costs=costs)))


if __name__ == '__main__':
    raise SystemExit(race() if sys.argv[1] == 'race' else main())
