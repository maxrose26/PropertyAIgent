"""Run from the exact #213 checkout; fixtures and settlement imports stay pinned.

Only synthetic fixture identity/source/configuration is substituted. No production
credentials or decryption claims. The successor runs before fixture teardown, on
the SAME database, in a separate interpreter rooted at #227.
"""
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from tests.test_bolton01_settlement_pg import (
    failed_bolton, succeeded10, ready10, ready09, failed09, failed08,
    settled08, failed07, world, Fault,
)
from verification.ingestion_storage import bolton01_settlement as s
from verification.ingestion_storage import intake_owner as op
from verification.ingestion_storage.daily_intake_runtime import Runtime

PIN = 'f027ba28af69ae70208eab5ed047e4a8a81c6337'


@pytest.fixture(autouse=True)
def fixed_fixture_run(succeeded10, monkeypatch):
    # Set the synthetic run identity BEFORE the real runtime records anything.
    # No receipt, evidence row or committed settlement is rewritten afterward.
    original = Runtime.__init__
    def initialise(self, args):
        original(self, args)
        if args.period == s.PERIOD:
            self.run_id = 'ee7cf0d9bc714f56951527b940937054'
    monkeypatch.setattr(Runtime, '__init__', initialise)


def test_pinned_settlement_then_successor(failed_bolton, monkeypatch, tmp_path):
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == PIN
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
    w = failed_bolton
    c = w['boot']
    seed = json.loads(os.environ['S4_SALFORD_SEED'])
    found = c.execute('SELECT to_jsonb(w) FROM ingestion_work_items w WHERE key=%s', (seed['key'],)).fetchone()
    if found is None:
        c.execute('INSERT INTO ingestion_work_items SELECT * FROM json_populate_record(NULL::ingestion_work_items,%s::json)', (json.dumps(seed),))
    else:
        assert found[0] == seed
    w['all_other'] = s.all_other_work_sha(c)
    assert op.stop_snapshot(op.control(c)) == s.STOP14
    before = op.ledger_sha(c)
    # Pre-COMMIT refusal rolls back; no replay after uncertain acknowledgement.
    with w['actor']() as actor:
        with pytest.raises(RuntimeError, match='SYNTHETIC_PRECOMMIT'):
            s.recover(Fault(actor, 'before'), w['binding'])
    assert op.ledger_sha(c) == before
    from scripts import owner_bolton01_settlement as cli
    class DB:
        @contextmanager
        def connection(self):
            with w['actor']() as actor:
                yield Fault(actor, 'lost')
    monkeypatch.setattr(cli.pilot, 'Database', DB)
    monkeypatch.setattr(s, 'binding', lambda db: w['binding'])
    monkeypatch.setenv('PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY', s.PERIOD)
    assert cli.main(['--action', 'settle']) == 2  # real COMMIT, lost acknowledgement
    with w['actor']() as fresh:
        receipt = s.inspect(fresh, w['binding'])
    assert receipt['status'] == 'COMMITTED_STATE_VERIFIED_READ_ONLY'
    assert receipt['stop'] == s.STOP15
    assert s.protected_sha(c) == w['protected']
    assert s.all_other_work_sha(c) == w['all_other']
    assert c.execute(op.MEMBERS).fetchall() == w['members']
    assert c.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall() == w['evidence_before']
    committed = op.ledger_sha(c)
    with w['actor']() as actor:
        with pytest.raises(op.Denied):
            s.recover(actor, w['binding'])
    assert op.ledger_sha(c) == committed
    # Synthetic credentials cross only the existing anonymous stdin pipe.
    with w['connect']('provisioning_migrator') as migrator:
        migrator_info = migrator.info.get_parameters()
        migrator_info['password'] = migrator.info.password
    state = dict(urls=w['urls'], migrator=migrator_info,
                 settlement=receipt, settlement_ledger_sha256=committed,
                 database_oid=c.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0])
    successor = Path(os.environ['S4_SUCCESSOR_ROOT']).resolve()
    env = dict(os.environ, PYTHONPATH=str(successor), DATABASE_URL='sqlite:///:memory:')
    for key in ('PROPERTYAIGENT_OWNER_SETTLEMENT_AUTHORITY', 'PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'):
        env.pop(key, None)
    result = subprocess.run([sys.executable, '-m', 'tests.daily_recovery_continuation',
                             str(tmp_path/'successor')], cwd=successor, env=env,
                            input=json.dumps(state), capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout[-12000:] + result.stderr[-12000:]
    report = json.loads(result.stdout.splitlines()[-1])
    assert report['same_database'] and report['status'] == 'CONNECTED_RECOVERY_PROVEN'
    Path(os.environ['S4_RECOVERY_REPORT']).write_text(json.dumps(report, sort_keys=True))
