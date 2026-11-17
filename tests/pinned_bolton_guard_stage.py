"""Run in the unchanged #213 checkout with the new guard loaded by file path."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.test_bolton01_settlement_pg import (
    failed_bolton, succeeded10, ready10, ready09, failed09, failed08,
    settled08, failed07, world, Fault,
)
from verification.ingestion_storage import bolton01_settlement as recovery
from verification.ingestion_storage import intake_owner as owner

spec = importlib.util.spec_from_file_location('candidate_guard',
    Path(os.environ['S4_SUCCESSOR_ROOT']) / 'verification/ingestion_storage/bolton_recovery_guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.fixture(autouse=True)
def fixed_run(succeeded10, monkeypatch):
    from verification.ingestion_storage.daily_intake_runtime import Runtime
    original=Runtime.__init__
    def initialise(self,args):
        original(self,args)
        if args.period==recovery.PERIOD:
            self.run_id='ee7cf0d9bc714f56951527b940937054'
    monkeypatch.setattr(Runtime,'__init__',initialise)


def test_guarded_real_recovery_and_lost_ack(failed_bolton,tmp_path):
    w = failed_bolton
    boot = w['boot']
    if 'S4_SALFORD_SEED' in os.environ:
        seed=json.loads(os.environ['S4_SALFORD_SEED'])
        boot.execute('INSERT INTO ingestion_work_items SELECT * FROM json_populate_record(NULL::ingestion_work_items,%s::json)',(json.dumps(seed),))
    ctl=owner.control(boot)
    for policy in ctl['intake_periods'].values():policy['expires_at']=0
    boot.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
    w['all_other']=recovery.all_other_work_sha(boot)
    before = owner.ledger_sha(boot)
    # Previously missed state/phase, different authority: refuse under the
    # original table/controller locks, before any recovery write.
    boot.execute("INSERT INTO ingestion_work_items SELECT (jsonb_populate_record(NULL::ingestion_work_items,to_jsonb(w)||%s::jsonb)).* FROM ingestion_work_items w WHERE key=repeat('0',64)",
                 (json.dumps(dict(key='f'*64, state='CLAIMED', phase='IDLE', authority='unrelated')),))
    blocked = owner.ledger_sha(boot)
    with w['actor']() as actor:
        with pytest.raises(owner.Denied, match='OTHER_WORK'):
            guard.recover(actor, w['binding'], pinned_module=recovery)
    assert owner.ledger_sha(boot) == blocked
    boot.execute('DELETE FROM ingestion_work_items WHERE key=%s', ('f'*64,))
    assert owner.ledger_sha(boot) == before
    preparation_spec=importlib.util.spec_from_file_location('stopped_preparation_proof',
        Path(os.environ['S4_SUCCESSOR_ROOT'])/'tests/stopped_preparation_proof.py')
    preparation=importlib.util.module_from_spec(preparation_spec)
    preparation_spec.loader.exec_module(preparation)
    preparation_result=preparation.exercise(w,recovery,tmp_path)
    assert preparation_result['boundaries']==19 and preparation_result['recovery_commits']==1
    # No repeat mutation after uncertain COMMIT: fresh connection readback.
    result = preparation_result['recovery_readback']
    assert result['status'] == 'COMMITTED_STATE_VERIFIED_READ_ONLY'
    assert result['stop'] == recovery.STOP15
    assert recovery.all_other_work_sha(boot) == w['all_other']
    assert boot.execute(owner.MEMBERS).fetchall() == w['members']
    after=boot.execute('SELECT period,run_id,name,body,sha256 FROM ingestion_run_evidence ORDER BY period,run_id,name').fetchall()
    assert all(row in after for row in w['evidence_before'])
    if 'S4_SALFORD_SEED' in os.environ:
        with w['actor']() as actor:
            actor_info=actor.info.get_parameters();actor_info['password']=actor.info.password
        with w['connect']('provisioning_migrator') as migrator:
            migrator_info=migrator.info.get_parameters();migrator_info['password']=migrator.info.password
        state=dict(owner=actor_info,migrator=migrator_info,urls=w['urls'],preparation=preparation_result,
                   database_oid=boot.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0])
        root=Path(os.environ['S4_SUCCESSOR_ROOT'])
        result=subprocess.run([sys.executable,'-m','tests.candidate_recovery_continuation',str(tmp_path/'candidate')],
            cwd=root,env=dict(os.environ,PYTHONPATH=str(root)),input=json.dumps(state),
            capture_output=True,text=True,timeout=90)
        assert result.returncode==0,result.stdout[-14000:]+result.stderr[-5000:]
        assert json.loads(result.stdout.splitlines()[-1])['status']=='SYNTHETIC_RELEASE_RUNTIME_READBACK_PASSED'
