"""Real source worker + supervisor, offline fixtures; no council transport."""
import json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from app.ingestion.ledger import Denied
from verification.ingestion_storage.daily_intake_runtime import Runtime,source_boundary_diagnostic
from verification.ingestion_storage.intake_budget import IntakeRun
from verification.ingestion_storage.operational_controller import DatabaseBudget

@pytest.mark.parametrize('scenario',['valid','invalid_json','export_bound','missing_fixture'])
def test_actual_worker_supervisor_boundary(tmp_path,scenario):
 r=object.__new__(Runtime);r.root=tmp_path/'out';r.root.mkdir();sources=tmp_path/'fixtures';sources.mkdir()
 r.args=SimpleNamespace(period='offline-boundary',disposable_sources=str(sources));r.test=True;r.policy={};r.run=IntakeRun();r.memory=None;r.events=[]
 raw=json.dumps(dict(requests=3,decoded_bytes=1,encoded_bytes=1,outbound_payload_bytes=0,supervisor_seconds=1))
 if scenario=='invalid_json':raw='not-json SECRET_SENTINEL'
 if scenario=='export_bound':raw=json.dumps(dict(padding='x'*524288))
 if scenario!='missing_fixture':(sources/'manchester.json').write_text(raw)
 @contextmanager
 def connection(**kw):yield None,DatabaseBudget()
 r.connection=connection;r.policy_read=lambda c:None;r.archive=lambda raw:None
 if scenario=='valid':
  _,outer=r.collect(dict(council='manchester'))
  assert outer['cleanup']=='CLOSED' and outer['live_owned_survivors']==0
  assert r.run.totals()['requests']==3
 else:
  with pytest.raises(Denied,match='SOURCE_OR_CLEANUP_UNCERTAIN_NO_REPLAY'):r.collect(dict(council='manchester'))
  d=r.events[-1]['data'];assert d['worker_exit_state']=='NONZERO' and d['output']=='MISSING_OR_NOT_FILE'
  assert d['process_cleanup']=='CLOSED' and d['limit']=='NONE'
  assert r.run.totals()['requests'] is None and r.run.totals()['requests_status']=='UNKNOWN'
  assert 'SECRET' not in json.dumps(r.events)

@pytest.mark.parametrize('field,value,expected',[('cleanup','UNCERTAIN',('process_cleanup','UNVERIFIED')),('exit_code',-9,('worker_exit_state','NONZERO')),('limit_hit','OUTPUT_BOUND',('limit','OUTPUT_BOUND')),('limit_hit','SECRET',('limit','UNCLASSIFIED'))])
def test_bounded_independent_failure_dimensions(tmp_path,field,value,expected):
 out=tmp_path/'out';out.write_text('{}')
 outer=dict(cleanup='CLOSED',exit_code=0,limit_hit=None);outer[field]=value
 d=source_boundary_diagnostic(outer,out);assert d[expected[0]]==expected[1]
 assert 'SECRET' not in json.dumps(d) and str(tmp_path) not in json.dumps(d)

def test_output_dimensions(tmp_path):
 outer=dict(cleanup='CLOSED',exit_code=0,limit_hit=None);p=tmp_path/'output'
 assert source_boundary_diagnostic(outer,p)['output']=='MISSING_OR_NOT_FILE'
 p.write_bytes(b'x'*524289)
 assert source_boundary_diagnostic(outer,p)['output']=='TOO_LARGE'
