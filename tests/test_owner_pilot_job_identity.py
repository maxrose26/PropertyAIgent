"""Execute the real job wrapper, substituting only the daily entrypoint."""
import sys
from types import SimpleNamespace
import pytest
from scripts import owner_pilot_job as job

@pytest.mark.parametrize('period',['b-dbpilot-20261027-1102-01','b-dbpilot-20261027-1102-02'])
def test_explicit_execution_identity_and_restricted_environment(monkeypatch,period):
    observed=[]
    monkeypatch.setattr(sys,'argv',['job','--hostaddr','192.0.2.1','--period',period])
    monkeypatch.setattr(job.os,'environ',{'PATH':'/usr/bin','DATABASE_URL':'SECRET_SENTINEL','PROPERTYAIGENT_INTAKE_RENDER_API_KEY':'SECRET_SENTINEL','GH_TOKEN':'SECRET_SENTINEL','INGESTION_WORKER_DATABASE_URL':'SYNTHETIC_WORKER','INGESTION_EFFECT_DATABASE_URL':'SYNTHETIC_EFFECT'})
    monkeypatch.setitem(sys.modules,'scripts.run_daily_councils',SimpleNamespace(main=lambda:observed.append((list(sys.argv),dict(job.os.environ))) or 0))
    assert job.main()==0
    argv,env=observed[0]
    assert argv==['scripts.run_daily_councils','--period',period,'--output','/tmp/propertyaigent-'+period,'--hostaddr','192.0.2.1']
    assert env['PROPERTYAIGENT_COMMAND_IDENTITY']=='database-pilot-daily' and env['INGESTION_WORKER_DATABASE_URL']=='SYNTHETIC_WORKER'
    assert not set(env)&{'DATABASE_URL','GH_TOKEN','PROPERTYAIGENT_INTAKE_RENDER_API_KEY'}

def test_unapproved_execution_identity_refuses_before_daily(monkeypatch):
    monkeypatch.setattr(sys,'argv',['job','--hostaddr','192.0.2.1','--period','another-attempt'])
    with pytest.raises(SystemExit) as exc:job.main()
    assert exc.value.code==2
