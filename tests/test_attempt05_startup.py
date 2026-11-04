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

