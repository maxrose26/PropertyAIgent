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


def test_real_browser_native_command(tmp_path):
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
 worker="import sys;from verification.ingestion_storage import render_acceptance_a as a;a.r.source_context=lambda p:True;a.worker(sys.argv[1],sys.argv[2]=='True')"
 return original([sys.executable,'-c',worker,command[4],str('--hold' in command)],**kw)
a.supervise=supervise
raise SystemExit(a.main(sys.argv[1:]))
'''
    env=dict(PATH='/usr/bin:/bin',HOME=str(tmp_path),RENDER_SERVICE_ID=a.r.SERVICE,RENDER_GIT_COMMIT='a'*40,PLAYWRIGHT_BROWSERS_PATH=cache)
    reaper=OwnedSubreaper()
    try:
        result=subprocess.run(['timeout','--signal=TERM','--kill-after=5s','190s',sys.executable,'-c',bootstrap,
            '--profile',str(cfg),'--output',str(tmp_path/'run')],env=env,capture_output=True,text=True,timeout=200)
        (tmp_path/'captured-log.txt').write_text(result.stdout+result.stderr)
        assert result.returncode in (137,-9),result.stdout+result.stderr
        phases=[json.loads(line)['phase'] for line in result.stdout.splitlines()]
        assert 'NORMAL_CLEANUP_OBSERVED' in phases and phases[-1]=='CONTROLLER_SIGKILL_INTENT'
    finally:reaper.close()  # test teardown, never reported as Render evidence
