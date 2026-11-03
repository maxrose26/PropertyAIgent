"""Real budget constructor, synthetic connections; no live authentication."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from verification.ingestion_storage import owner_pilot as p
from verification.ingestion_storage import operational_controller as runtime
from verification.ingestion_storage import tls_trust

def test_original_four_statement_budget_refuses_before_engine(monkeypatch):
    calls=[]
    monkeypatch.setattr(runtime.DatabaseBudget,'engine',lambda *a,**k:calls.append(True))
    with pytest.raises(p.op.Denied,match='CONTROLLER_CEILING'):
        runtime.DatabaseBudget(statements=4,connections=1,returned_bytes=8192,seconds=12)
    assert calls==[]
    assert p.safe_result(p.op.Denied('CONTROLLER_CEILING'))['reason']=='CONTROLLER_CEILING'

@pytest.mark.parametrize('failure',[None,'identity','query'])
def test_actual_qualification_constructor_query_and_cleanup(monkeypatch,failure):
    budgets=[];connections=[]
    monkeypatch.setattr(tls_trust,'verified_trust',lambda:(Path('/synthetic/ca.crt'),'a'*64))
    pilot=object.__new__(p.Pilot)
    pilot.state={'binding':{'hostaddr':'192.0.2.1'},'access':{'passwords':{r:'SENSITIVE_SENTINEL' for r in p.op.ROLES}}}
    def engine(budget,url,**kw):
        assert budget.statement_cap==20 and budget.connection_cap==1 and budget.returned_cap==8192 and budget.seconds==12
        assert kw=={'ssl':{'sslmode':'verify-full','sslrootcert':'/synthetic/ca.crt'},'hostaddr':'192.0.2.1','route':'POOLER'}
        role=list(p.op.ROLES)[len(budgets)];budgets.append(budget)
        class Connection:
            closed=False
            def execute(self,query,params):
                assert str(query).startswith('SELECT current_user,session_user,pg_has_role(')
                assert params=={'cap':p.op.ROLES[role]}
                if failure=='query':raise RuntimeError('SENSITIVE_SENTINEL')
                return SimpleNamespace(one=lambda:(role,role,failure!='identity','10s','3s','20s'))
            def close(self):self.closed=True
        c=Connection();connections.append(c);budget.opened.append(c);budget.attempts+=1
        @contextmanager
        def connect():
            try:yield c
            finally:c.close()
        return SimpleNamespace(connect=connect)
    monkeypatch.setattr(runtime.DatabaseBudget,'engine',engine)
    if failure:
        with pytest.raises((p.op.Denied,RuntimeError)):pilot.qualify()
    else:
        result=pilot.qualify()
        assert result==[{'role':r,'attempts':1,'closed':True} for r in p.op.ROLES]
        assert 'SENSITIVE_SENTINEL' not in json.dumps(result)
    assert all(c.closed for c in connections) and len(budgets)==(1 if failure else 2)

def test_closed_attempt_cannot_reopen_or_issue_another_period():
    pilot=object.__new__(p.Pilot)
    pilot.journal=SimpleNamespace(load=lambda:{'status':'CLOSED','intents':{'RELEASE':{'state':'INTENT_NO_RETRY'}}})
    with pytest.raises(p.op.Denied,match='OWNER_PRIOR_ATTEMPT_RECONCILE'):
        pilot.run(p.time.time())
