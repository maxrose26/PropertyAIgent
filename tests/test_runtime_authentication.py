import json,time
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
                c.execute=lambda *_a,**_k:SimpleNamespace(one=lambda:(role,role,True,'10s','3s','20s',True,worker,worker,worker,deadline))
                self.opened.append(c)
                try:yield c
                finally:c.closed=True
            return SimpleNamespace(connect=connect)
        def close(self,_):return dict(connection_attempts=self.attempts,driver_statements=self.statements,returned_data_value_bytes=self.returned_bytes,elapsed_seconds=0.1,connections_closed=True,cleanup='CLOSED',connection_diagnostics=self.diag)
    value=auth.qualify(runtime,deadline,budget_factory=Budget)
    assert (value['status']=='VERIFIED_BOTH_RESTRICTED_ROLES') is expected
    assert len(made)==attempts and runtime.run.totals()['connection_attempts']==attempts and value['source_requests']==0
    assert 'SENSITIVE_SENTINEL' not in json.dumps(value) and len(json.dumps(value))<8192

def test_insufficient_reserve_refuses_before_connection():
    runtime=SimpleNamespace(args=SimpleNamespace(period='fixed'),binding={},emit=lambda *_:None)
    result=auth.qualify(runtime,time.time()+1500,budget_factory=lambda **kw:pytest.fail('CONNECTED'))
    assert result['status']=='REFUSED' and result['attempts']==[]
