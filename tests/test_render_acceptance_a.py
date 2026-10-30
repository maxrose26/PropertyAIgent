"""Fixed A command tests. Runtime counters are synthetic; never Render proof."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from verification.ingestion_storage import render_acceptance_a as a
from tests.test_render_intake import profile


def test_command_refuses_ambient_credentials_without_values(tmp_path):
    env=dict(PATH='/usr/bin:/bin', HOME=str(tmp_path), OPENAI_API_KEY='DO_NOT_PRINT')
    p=subprocess.run([sys.executable,'-m',a.MODULE],env=env,capture_output=True,text=True,timeout=10)
    assert p.returncode==2 and 'REFUSED' in p.stdout and 'DO_NOT_PRINT' not in p.stdout


def test_output_is_bounded(capsys):
    log=a.Log()
    with pytest.raises(RuntimeError,match='LOG_BOUND'):log('x',data='x'*a.OUTPUT_BYTES)
    assert capsys.readouterr().out==''


def test_startup_failure_never_reaches_kill(tmp_path,monkeypatch):
    p=profile(tmp_path)
    monkeypatch.setattr(a.psutil,'Process',lambda:None)
    monkeypatch.setattr(a,'identity',lambda p:{'synthetic':True})
    monkeypatch.setattr(a.r,'MemoryMonitor',lambda _:type('M',(),{'check':lambda s:None,'evidence':lambda s:{'synthetic':True}})())
    monkeypatch.setattr(a,'supervise',lambda *args,**kw:dict(exit_code=1,limit_hit=None,cleanup='CLOSED'))
    events=[]
    with pytest.raises(RuntimeError,match='PHASE_FAILED'):a.run(p,tmp_path,lambda phase,**kw:events.append(phase))
    assert events==['PREFLIGHT','PHASE_START','PHASE_REFUSED']


def test_gnu_outer_timeout_escalates_independently():
    # Same GNU timeout escalation semantics as the supported 190s/5s command,
    # accelerated locally; controller ignores TERM, so independent KILL is needed.
    p=subprocess.run(['timeout','--signal=TERM','--kill-after=0.2s','0.2s',sys.executable,'-c',
        'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("READY",flush=True);time.sleep(10)'],capture_output=True,text=True,timeout=5)
    assert p.returncode in (137,-9) and 'READY' in p.stdout


def test_outer_command_preserves_intentional_sigkill_failure():
    p=subprocess.run(['timeout','--signal=TERM','--kill-after=5s','190s',sys.executable,'-c',
        'import os,signal;print("CONTROLLER_SIGKILL_INTENT",flush=True);os.kill(os.getpid(),signal.SIGKILL)'],capture_output=True,text=True,timeout=5)
    assert p.returncode in (137,-9) and 'CONTROLLER_SIGKILL_INTENT' in p.stdout


@pytest.mark.parametrize('scenario',['interrupt','startup_failure','timeout'])
def test_real_browser_native_command(tmp_path,scenario):
    """Real browser + actual run/main/supervisor; only host/cgroup checks modelled.

    Harness reaps survivors after controller kill, modelling platform teardown.
    This is not evidence that Render performed that teardown.
    """
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():pytest.skip('native PID namespace unavailable')
    cache=os.environ.get('A_TEST_BROWSER_PATH')
    if not cache:pytest.skip('installed Playwright shell not supplied')
    import hashlib
    from verification.direct_reference.prepared_font_cache import headless_shell_executable
    from verification.ingestion_storage.render_intake import OwnedSubreaper
    p=profile(tmp_path);p.update(browser_path=cache,browser_sha256=hashlib.sha256(Path(headless_shell_executable(cache)).read_bytes()).hexdigest(),
        source_rss_bytes=1024*a.r.MiB,reserve_bytes=512*a.r.MiB,source_seconds=75)
    if scenario=='startup_failure':
        fake=profile(tmp_path/'broken');p.update(browser_path=fake['browser_path'],browser_sha256=fake['browser_sha256'])
    cfg=tmp_path/'profile.json';cfg.write_text(json.dumps(p))
    # No production command switch bypasses host/cgroup checks. This isolated
    # test bootstrap substitutes only runtime allocation observation.
    bootstrap='''
import sys
from verification.ingestion_storage import render_acceptance_a as a
class M:
 def __init__(self,p):pass
 def check(self):pass
 def evidence(self):return {'synthetic_cgroup':True}
a.r.MemoryMonitor=M
original=a.supervise
def supervise(command,**kw):
 worker="import sys;from verification.ingestion_storage import render_acceptance_a as a;a.r.source_context=lambda p:True;raise SystemExit(a.main(['--worker',sys.argv[1]]+(['--hold'] if sys.argv[2]=='True' else [])))"
 return original([sys.executable,'-c',worker,command[4],str('--hold' in command)],**kw)
a.supervise=supervise
raise SystemExit(a.main(sys.argv[1:]))
'''
    if scenario=='timeout':
        bootstrap=bootstrap.replace('a.r.MemoryMonitor=M', 'a.r.MemoryMonitor=M\na.PHASE_SECONDS=1').replace("raise SystemExit(a.main(['--worker',sys.argv[1]]+(['--hold'] if sys.argv[2]=='True' else [])))", 'import time;time.sleep(10)')
    env=dict(PATH='/usr/bin:/bin',HOME=str(tmp_path),RENDER_SERVICE_ID=a.r.SERVICE,RENDER_GIT_COMMIT='a'*40,PLAYWRIGHT_BROWSERS_PATH=cache)
    reaper=OwnedSubreaper()
    try:
        result=subprocess.run(['timeout','--signal=TERM','--kill-after=5s','190s',sys.executable,'-c',bootstrap,
            '--profile',str(cfg),'--output',str(tmp_path/'run')],env=env,capture_output=True,text=True,timeout=200)
        (tmp_path/'captured-log.txt').write_text(result.stdout+result.stderr)
        phases=[json.loads(line)['phase'] for line in result.stdout.splitlines()]
        if scenario=='interrupt':
            assert result.returncode in (137,-9),result.stdout+result.stderr
            assert 'NORMAL_CLEANUP_OBSERVED' in phases and phases[-1]=='CONTROLLER_SIGKILL_INTENT'
        else:
            assert result.returncode==2,result.stdout+result.stderr
            assert phases[-1]=='REFUSED' and 'CONTROLLER_SIGKILL_INTENT' not in phases
            if scenario=='timeout':assert '"limit_hit": "DEADLINE"' in result.stdout
    finally:reaper.close()  # test teardown, never reported as Render evidence


def test_effective_allocation_uses_readback_not_plan_label(tmp_path,monkeypatch):
    p=profile(tmp_path);p['aggregate_bytes']=None
    monkeypatch.setattr(a.r,'memory_group',lambda:tmp_path)
    monkeypatch.setattr(a.r,'memory_sample',lambda _: {'memory.max':2000000000})
    got=a.effective_profile(p)
    assert got['aggregate_bytes']==2000000000 and p['aggregate_bytes'] is None
    monkeypatch.setattr(a.r,'memory_sample',lambda _: {'memory.max':'max'})
    with pytest.raises(RuntimeError,match='ALLOCATION_UNAVAILABLE'):a.effective_profile(p)

@pytest.mark.parametrize('case,check,code',[
    ('environment','environment','A_ENVIRONMENT_NOT_ALLOWLISTED'),
    ('service','service_binding','A_SERVICE_BINDING'),
    ('revision','revision_binding','A_REVISION_BINDING'),
    ('arguments','arguments','A_ARGUMENTS'),
    ('allocation','effective_allocation','A_EFFECTIVE_ALLOCATION_UNAVAILABLE'),
    ('cgroup','effective_allocation','RENDER_CGROUP_PATH_UNAVAILABLE'),
    ('unknown','effective_allocation','A_UNKNOWN_FAILURE'),
])
def test_safe_refusal_details(tmp_path,monkeypatch,capsys,case,check,code):
    env=dict(PATH='/usr/bin',RENDER_SERVICE_ID=a.r.SERVICE,RENDER_GIT_COMMIT='a'*40)
    if case=='environment':env.update({f'PRIVATE_{i}':'SECRET_VALUE' for i in range(40)})
    if case=='service':env['RENDER_SERVICE_ID']='SECRET_VALUE'
    if case=='revision':env['RENDER_GIT_COMMIT']='SECRET_VALUE'
    monkeypatch.setattr(a.os,'environ',env)
    cfg=tmp_path/'p.json';cfg.write_text('{"aggregate_bytes":null}')
    monkeypatch.setattr(a.r,'memory_group',lambda:tmp_path)
    monkeypatch.setattr(a.r,'memory_sample',lambda _: {'memory.max':'max'})
    if case in ('cgroup','unknown'):
        def fail():
            if case=='cgroup':raise a.r.Denied('RENDER_CGROUP_PATH_UNAVAILABLE')
            raise RuntimeError('SECRET_VALUE')
        monkeypatch.setattr(a.r,'memory_group',fail)
    args=[] if case=='arguments' else ['--profile',str(cfg),'--output',str(tmp_path/'run')]
    assert a.main(args)==2
    output=capsys.readouterr().out
    record=json.loads(output)
    assert record['reason_code']==code and record['failing_check']==check
    assert record['phase']=='REFUSED' and record['successful_intake'] is False
    assert 'SECRET_VALUE' not in output and len(output.encode())<8192
    if case=='environment':
        assert len(record['unexpected_names'])==32 and record['names_truncated']
        assert record['unexpected_count']==40
    if case=='allocation':assert record['memory_max']=='max'
    if case=='cgroup':assert record['readback_status']=='unavailable'
