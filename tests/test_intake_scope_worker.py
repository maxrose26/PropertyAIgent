"""Actual source_worker -> finite worker -> Idox boundary; synthetic HTTP only."""
import json,sys,os
from pathlib import Path
import pytest
from verification.ingestion_storage.intake_scope_policy import BOLTON
from verification.ingestion_storage.operational_supervisor import supervise
from verification.ingestion_storage.daily_intake_runtime import Runtime
from app.ingestion.ledger import DEFAULT_LIMITS

@pytest.mark.parametrize('count',[24,60])
def test_actual_nested_bolton_worker(tmp_path,count):
 plan=tmp_path/'plan.json';output=tmp_path/'audit.json'
 plan.write_text(json.dumps(dict(row=BOLTON.row(),fixture=None)))
 command=[sys.executable,'-c',f'from tests.bolton_worker_transport import worker;worker({str(plan)!r},{str(output)!r},{count})']
 outer=supervise(command,environment={'INGESTION_SOURCE_PRIVATE':'ONCE'},root=tmp_path/'owned',source=True,seconds=45)
 assert outer['exit_code']==0 and outer['cleanup']=='CLOSED' and outer['live_owned_survivors']==0 and outer['limit_hit'] is None,outer
 raw=output.read_bytes();assert len(raw)<=512*1024 and b'SYNTHETIC_STATE_DO_NOT_EXPORT' not in raw
 audit=json.loads(raw);runtime=object.__new__(Runtime);runtime.test=False;runtime.policy=dict(councils=BOLTON.councils())
 contract=runtime.contract(BOLTON.row());receipt=contract.project(audit,outer,DEFAULT_LIMITS,source_bytes_limit=512*1024)
 assert len(receipt['records'])==count and audit['enumeration_evidence']=='COUNT_RECONCILED'
 assert audit['resource']['requests_attempted']==4+(count-1)//10 and audit['resource']['retries']==0
 assert audit['resource']['received_bytes']<=3_000_000 and audit['resource']['elapsed_seconds']<=45
 if count==24 and os.environ.get('BOLTON_WORKER_AUDIT'):Path(os.environ['BOLTON_WORKER_AUDIT']).write_bytes(raw)
