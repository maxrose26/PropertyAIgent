import copy,json,hashlib
from types import SimpleNamespace
from contextlib import contextmanager
import pytest
from tests.test_owner_pilot_continuation import closed as closed04
from verification.ingestion_storage import owner_pilot as p,owner_pilot_continuation as step
from verification.ingestion_storage.database_evidence import ATTEMPT06_OWNER_SQL,DIAGNOSTIC02_CAP_OWNER_SQL
S={'ordinal':54,'bytes':18000,'sha256':'1db4809eeaaddb353244542ccd7a021cb34b8af8eccc3702a0c735731d9be01e'}
D={'ordinal':44,'bytes':14280,'sha256':'4f9f08eed67e11420b5df197be90340973ced669afb840e98f1977ba3cc6dc96'}
def states():
 s=closed04();s.update(period=p.PREDECESSOR,job={'id':'job-dblke3bm8hqs739hgmmg'},status='CLOSED',closure_verification=dict(status='VERIFIED',authorities_closed=True,configuration_equal=True,environment_equal=True,runtime_memberships=0,sessions=0,stable_verifiers='MATCH',suspended=True,temporary_owner_absent=True))
 s['closure_receipt'].update(outcome='COMMIT_ACKNOWLEDGED',open_run_requires_reconciliation=False)
 d=copy.deepcopy(s);d.update(period='b-qualification-20261104-02',job={'id':'job-dblphcp5efls73adq1h0'},runtime_qualification={'source_requests':0})
 return s,d

def test_closed_predecessors_and_exact_namespace_no_limit_change():
 s,d=states();assert step.predecessor(s,snapshot=S)['execution_identity']==p.PERIOD=='b-dbpilot-20261027-1102-06'
 assert step.diagnostic02_closed(d,snapshot=D,stable_credentials=s['stable_credentials'])['snapshot']==D
 assert ATTEMPT06_OWNER_SQL.replace(",'b-dbpilot-20261027-1102-06_owner'",'')==DIAGNOSTIC02_CAP_OWNER_SQL
 assert p.cleanup_reserve_policy(p.PERIOD)['normal_plaintext_ceiling']==16534
 assert p.Journal(None).owner_period=='b-dbpilot-20261027-1102-06_owner'
 assert p.WINDOW==dict(start='2026-10-27',end='2026-11-02')

@pytest.mark.parametrize('kind',['snapshot','job','open','render','closure','old04'])
def test_predecessor_drift_refuses(kind):
 s,d=states();snap=copy.deepcopy(S)
 if kind=='snapshot':snap['sha256']='0'*64
 if kind=='job':s['job']['id']='unexpected'
 if kind=='open':s['status']='OPEN'
 if kind=='render':s['access']['render']['state']='UNKNOWN'
 if kind=='closure':s['closure_verification']['sessions']=1
 if kind=='old04':s=closed04()
 with pytest.raises(p.op.Denied,match='PREDECESSOR'):step.predecessor(s,snapshot=snap)

@pytest.mark.parametrize('kind',['snapshot','open','credentials','source'])
def test_diagnostic_drift_refuses(kind):
 s,d=states();snap=copy.deepcopy(D)
 if kind=='snapshot':snap['ordinal']+=1
 if kind=='open':d['status']='OPEN'
 if kind=='credentials':d['stable_credentials']['passwords']={}
 if kind=='source':d['runtime_qualification']['source_requests']=1
 with pytest.raises(p.op.Denied,match='PREDECESSOR'):step.diagnostic02_closed(d,snapshot=snap,stable_credentials=s['stable_credentials'])

def test_actual_preparation_preserves_both_closed_journals(monkeypatch):
 s,d=states();s['stable_configuration']={};before=copy.deepcopy((s,d));events=[]
 @contextmanager
 def connection():yield object()
 obj=object.__new__(p.Pilot);obj.db=SimpleNamespace(connection=connection)
 obj.journal=SimpleNamespace(load=lambda:None,ordinal=1,ciphertext_bytes=1600,previous='a'*64)
 def journal(db,period):
  state,snap=(s,S) if period==p.PREDECESSOR else (d,D)
  return SimpleNamespace(load=lambda:state,ordinal=snap['ordinal'],ciphertext_bytes=snap['bytes'],previous=snap['sha256'])
 monkeypatch.setattr(p,'Journal',journal)
 monkeypatch.setattr(step,'migrate_owner_namespace',lambda *a,**k:events.append(('namespace',k['attempt06'])))
 obj.save=lambda:None;obj.build=lambda:events.append('build');obj.startup_preflight=lambda:events.append('startup');obj.verify_release_binding=lambda:events.append('readiness') or {}
 obj.prepare_continuation()
 assert events==[('namespace',True),'build','startup','readiness'] and before==(s,d)
 assert obj.state['predecessor']['snapshot']==S and obj.state['diagnostic_closure']['snapshot']==D
 assert not any(k in obj.state for k in ('access','job','period_journal','binding'))
