import json,time
from datetime import datetime,timezone
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from verification.ingestion_storage import runtime_authentication as auth
from verification.ingestion_storage.intake_budget import IntakeRun

@pytest.mark.parametrize('failures,expected,attempts',[((),True,2),(('AUTHENTICATION_REJECTED',),True,3),(('AUTHENTICATION_REJECTED','AUTHENTICATION_REJECTED'),False,2),(('CIRCUIT_BREAKER_INDICATED',),False,1)])
def test_actual_meter_bounded_same_secret_reconnect_and_suppression(failures,expected,attempts):
    deadline=time.time()+2100;queue=list(failures);made=[]
    runtime=SimpleNamespace(args=SimpleNamespace(period='b-dbpilot-20261027-1102-03'),binding={'revision':'a'*40},run=IntakeRun(),urls={r:'SENSITIVE_SENTINEL' for r in auth.op.ROLES},options={},emit=lambda *_:None)
    class Budget:
        def __init__(self,**kw):
            assert kw['statements']==20 and kw['connections']==1 and kw['seconds']<=12
            self.statements=0;self.attempts=0;self.returned_bytes=0;self.prior_cancel_attempts=0;self.hard_deadline_events=[];self.opened=[];self.diag=[];made.append(self)
        def engine(self,*a,**kw):
            role=list(auth.op.ROLES)[len(runtime.runtime_qualification['roles'])];self.attempts=1
            @contextmanager
            def connect():
                if queue:
                    reason=queue.pop(0);self.diag=[dict(reason_code=reason,failed_native_connection_finished=True)]
                    raise RuntimeError('SENSITIVE_SENTINEL')
                self.statements=8;self.returned_bytes=120;c=SimpleNamespace(closed=False)
                worker=role=='ingestion_worker_login'
                c.execute=lambda *_a,**_k:SimpleNamespace(one=lambda:(role,role,True,'10s','3s','20s',True,worker,worker,worker,datetime.fromtimestamp(deadline,timezone.utc).timestamp()))
                self.opened.append(c)
                try:yield c
                finally:c.closed=True
            return SimpleNamespace(connect=connect)
        def close(self,_):return dict(connection_attempts=self.attempts,driver_statements=self.statements,returned_data_value_bytes=self.returned_bytes,elapsed_seconds=0.1,connections_closed=True,cleanup='CLOSED',connection_diagnostics=self.diag)
    value=auth.qualify(runtime,deadline,budget_factory=Budget)
    assert (value['status']=='VERIFIED_BOTH_RESTRICTED_ROLES') is expected
    assert all(a.get('profile_comparison',{}).get('status')=='MATCH' for a in value['attempts'] if a['driver_statements'])
    assert len(made)==attempts and runtime.run.totals()['connection_attempts']==attempts and value['source_requests']==0
    assert 'SENSITIVE_SENTINEL' not in json.dumps(value) and len(json.dumps(value))<8192

def test_insufficient_reserve_refuses_before_connection():
    runtime=SimpleNamespace(args=SimpleNamespace(period='fixed'),binding={},emit=lambda *_:None)
    result=auth.qualify(runtime,time.time()+1500,budget_factory=lambda **kw:pytest.fail('CONNECTED'))
    assert result['status']=='REFUSED' and result['attempts']==[]


@pytest.mark.parametrize('index',range(11))
def test_exact_old_comparison_and_fixed_field_diagnostics(index):
    deadline=1793806134.7721088
    for role in auth.op.ROLES:
        worker=role=='ingestion_worker_login'
        expected=(role,role,True,'10s','3s','20s',True,worker,worker,worker,datetime.fromtimestamp(deadline,timezone.utc).timestamp())
        assert auth.profile_comparison(expected,role,deadline)['status']=='MATCH'
        row=list(expected);row[index]='SECRET_SENTINEL_AND_ARBITRARY_DATABASE_VALUE'
        result=auth.profile_comparison(tuple(row),role,deadline)
        assert result['status']=='MISMATCH' and result['first_mismatch']==auth.PROFILE_FIELDS[index]
        assert list(result['checks'].values()).count(False)==1
        assert (tuple(row)==expected)==(result['status']=='MATCH')
        assert 'SECRET_SENTINEL' not in json.dumps(result) and len(json.dumps(result))<768


@pytest.mark.parametrize('row',[(),None,('SECRET_SENTINEL',)])
def test_wrong_shape_is_explicit_and_bounded(row):
    result=auth.profile_comparison(row,'ingestion_worker_login',time.time()+2100)
    assert result['first_mismatch']=='ROW_SHAPE' and result['status']=='MISMATCH'
    assert 'SECRET_SENTINEL' not in json.dumps(result)


@pytest.mark.parametrize('cleanup_fails',[False,True])
def test_first_comparison_failure_precedes_cleanup_and_survives_it(cleanup_fails):
    deadline=time.time()+2100;made=[]
    runtime=SimpleNamespace(args=SimpleNamespace(period='synthetic-qualification'),binding={'revision':'a'*40},run=IntakeRun(),urls={r:'SECRET_SENTINEL' for r in auth.op.ROLES},options={},emit=lambda *_:None)
    class Budget:
        statements=8;attempts=1;returned_bytes=229;prior_cancel_attempts=0;hard_deadline_events=[];opened=[]
        def __init__(self,**kw):made.append(self)
        def engine(self,*a,**kw):
            @contextmanager
            def connect():
                role='ingestion_worker_login'
                row=(role,role,True,'10s','3s','20s',True,True,False,True,datetime.fromtimestamp(deadline,timezone.utc).timestamp())
                yield SimpleNamespace(execute=lambda *_a,**_k:SimpleNamespace(one=lambda:row))
            return SimpleNamespace(connect=connect)
        def close(self,_):
            assert runtime.runtime_qualification['first_qualification_failure']['comparison']['first_mismatch']=='evidence_write_execute'
            if cleanup_fails:raise RuntimeError('SECRET_SENTINEL')
            return dict(connection_attempts=1,driver_statements=8,returned_data_value_bytes=229,elapsed_seconds=.1,connections_closed=True,cleanup='CLOSED',connection_diagnostics=[])
    result=auth.qualify(runtime,deadline,budget_factory=Budget)
    assert result['status']=='REFUSED' and len(made)==1 and result['source_requests']==0
    assert result['first_qualification_failure']['comparison']['checks']['evidence_write_execute'] is False
    assert result['first_qualification_failure']['comparison']['first_mismatch']=='evidence_write_execute'
    assert 'SECRET_SENTINEL' not in json.dumps(result)
