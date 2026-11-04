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

@pytest.mark.parametrize('period',['b-dbpilot-20261027-1102-03','b-dbpilot-20261027-1102-04'])
@pytest.mark.parametrize('accepted',[True,False])
def test_stable_job_qualifies_on_actual_runtime_meter_before_daily(monkeypatch,accepted,period):
    import verification.ingestion_storage.daily_intake_runtime as daily_runtime
    import verification.ingestion_storage.runtime_authentication as authentication
    events=[]
    monkeypatch.setattr(sys,'argv',['job','--hostaddr','192.0.2.1','--period',period,'--deadline','1793740000'])
    monkeypatch.setattr(job.os,'environ',{'PATH':'/usr/bin','DATABASE_URL':'SECRET_SENTINEL','PROPERTYAIGENT_INTAKE_RENDER_API_KEY':'SECRET_SENTINEL'})
    sentinel=SimpleNamespace()
    monkeypatch.setattr(daily_runtime,'Runtime',lambda args:events.append('runtime') or sentinel)
    monkeypatch.setattr(authentication,'qualify',lambda runtime,deadline:events.append('qualification') or dict(status='VERIFIED_BOTH_RESTRICTED_ROLES' if accepted else 'REFUSED'))
    def daily(**kw):
        assert kw=={'prepared_runtime':sentinel};events.append('daily');return 0
    monkeypatch.setitem(sys.modules,'scripts.run_daily_councils',SimpleNamespace(main=daily))
    assert job.main()==(0 if accepted else 2)
    assert events==(['runtime','qualification','daily'] if accepted else ['runtime','qualification'])
    assert 'DATABASE_URL' not in job.os.environ
