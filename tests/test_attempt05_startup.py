import json,sys,subprocess
import pytest
from verification.ingestion_storage import owner_pilot as p

@pytest.mark.parametrize('kind',['clean','dirty','git_failure'])
def test_actual_runtime_guard_preflight_never_qualifies(monkeypatch,tmp_path,capsys,kind):
    from scripts import owner_pilot_job as job
    from verification.ingestion_storage import daily_intake_runtime as native,runtime_authentication as auth
    from scripts import run_daily_councils as daily
    Real=native.Runtime
    monkeypatch.setattr(native,'execution_binding',lambda:{'revision':'1'*40})
    monkeypatch.setattr(auth,'qualify',lambda *x:pytest.fail('AUTHENTICATION_REACHED'))
    monkeypatch.setattr(daily,'main',lambda **x:pytest.fail('COLLECTION_REACHED'))
    monkeypatch.setattr(native.DatabaseBudget,'engine',lambda *x,**kw:pytest.fail('DATABASE_REACHED'))
    def constructor(args):args.output=str(tmp_path/'source');return Real(args)
    monkeypatch.setattr(native,'Runtime',constructor)
    def git(command,*args,**kw):
        if command==['git','status','--porcelain','--untracked-files=no']:
            if kind=='git_failure':raise subprocess.CalledProcessError(128,command)
            return ' M safe.sh\n' if kind=='dirty' else ''
        return '2'*40+'\n'
    monkeypatch.setattr(subprocess,'check_output',git)
    monkeypatch.setattr(job.os,'environ',{'PATH':'/usr/bin','RENDER_GIT_COMMIT':'1'*40,'DATABASE_URL':'SENSITIVE_SENTINEL'})
    monkeypatch.setattr(sys,'argv',['job','--period',p.PERIOD,'--hostaddr','127.0.0.1','--startup-check-only'])
    assert job.main()==(0 if kind=='clean' else 2)
    raw=capsys.readouterr().out;assert 'SENSITIVE_SENTINEL' not in raw
    r=json.loads(raw.split('DATABASE_PILOT_STARTUP_GUARD ')[1])
    assert r['authentication_attempts']==r['source_requests']==0
    assert r['status']==('CLEAN_CHECKOUT_VERIFIED_BEFORE_QUALIFICATION' if kind=='clean' else 'REFUSED')
    assert r.get('reason')==({'dirty':'CLEAN_REVIEWED_CHECKOUT_REQUIRED','git_failure':'GIT_STATUS_UNVERIFIED'}.get(kind))


@pytest.mark.parametrize('status',['VERIFIED_BOTH_RESTRICTED_ROLES','REFUSED'])
def test_qualification_only_never_reaches_daily_on_either_outcome(monkeypatch,capsys,status):
    from scripts import owner_pilot_job as job
    from scripts import run_daily_councils as daily
    from verification.ingestion_storage import daily_intake_runtime as native,runtime_authentication as auth
    from types import SimpleNamespace
    monkeypatch.setattr(native,'Runtime',lambda args:SimpleNamespace())
    monkeypatch.setattr(auth,'qualify',lambda *a:{'status':status,'source_requests':0})
    monkeypatch.setattr(daily,'main',lambda **kw:pytest.fail('DAILY_OR_COUNCIL_REACHED'))
    monkeypatch.setattr(job.os,'environ',{'PATH':'/usr/bin','DATABASE_URL':'SECRET_SENTINEL'})
    monkeypatch.setattr(sys,'argv',['job','--period',p.PERIOD,'--hostaddr','127.0.0.1','--deadline','9999999999','--qualification-only'])
    assert job.main()==(0 if status=='VERIFIED_BOTH_RESTRICTED_ROLES' else 2)
    raw=capsys.readouterr().out
    assert 'SECRET_SENTINEL' not in raw and 'DATABASE_PILOT_RUNTIME_QUALIFICATION' in raw


def test_observation_modes_are_exclusive_and_legacy_period_cannot_bypass_native_gate(monkeypatch):
    from scripts import owner_pilot_job as job
    for args in (['--startup-check-only','--qualification-only'],['--qualification-only','--period','b-dbpilot-20261027-1102-01']):
        monkeypatch.setattr(sys,'argv',['job','--hostaddr','127.0.0.1']+args)
        with pytest.raises(SystemExit) as exc:job.main()
        assert exc.value.code==2
