"""Local processes and synthetic kernel readbacks; not live Render/browser proof."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import psutil
import pytest
from app.ingestion.ledger import Denied
from verification.ingestion_storage import render_intake as r
from verification.ingestion_storage.operational_supervisor import supervise


def profile(tmp_path):
    import playwright
    registry=json.loads((Path(playwright.__file__).parent/'driver/package/browsers.json').read_text())
    revision=next(b['revision'] for b in registry['browsers'] if b['name']=='chromium-headless-shell')
    cache=tmp_path/'browsers';executable=cache/f'chromium_headless_shell-{revision}/chrome-headless-shell-linux64/chrome-headless-shell'
    executable.parent.mkdir(parents=True);executable.write_bytes(b'SYNTHETIC_BROWSER_IDENTITY_NOT_EXECUTED')
    return dict(mode=r.MODE,service_id=r.SERVICE,revision='a'*40,browser_path=str(cache),browser_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        aggregate_bytes=2048*r.MiB,source_rss_bytes=1536*r.MiB,controller_rss_bytes=256*r.MiB,reserve_bytes=256*r.MiB,source_seconds=1)


@pytest.mark.parametrize('fault',['service','revision','hash','limit','path'])
def test_profile_refuses_wrong_identity_browser_and_unjustified_bounds(tmp_path,fault):
    p=profile(tmp_path);assert r.validate_profile(p,revision='a'*40)==p
    if fault=='service':p['service_id']='other'
    if fault=='revision':p['revision']='b'*40
    if fault=='hash':p['browser_sha256']='0'*64
    if fault=='limit':p['reserve_bytes']=0
    if fault=='path':p['browser_path']='relative'
    with pytest.raises(Denied):r.validate_profile(p,revision='a'*40)


@pytest.mark.parametrize('fault',['normal_exit','deadline','cancel','monitor_failure','rss'])
def test_supervisor_reaps_unsampled_session_orphan_on_all_exits(tmp_path,fault):
    if int(Path('/proc/self/stat').read_text().split()[0])!=os.getpid():
        if os.environ.get('CI'):pytest.fail('native PID namespace required')
        pytest.skip('local /proc is outside PID namespace; native hosted test required')
    p=profile(tmp_path)
    if fault=='rss':p['source_rss_bytes']=24*r.MiB
    # Leader exits without waiting. Descendant creates another session BEFORE
    # its parent exits and outlives it. Kernel adoption, not sampled PPID, owns it.
    pidfile=tmp_path/'orphan.pid'
    worker="import os,time;from pathlib import Path;os.setsid();Path(%r).write_text(str(os.getpid()));"%str(pidfile)
    worker+=("x=bytearray(64*1024**2);" if fault=='rss' else '')+'time.sleep(30)'
    leader="import subprocess,sys,time;from pathlib import Path;subprocess.Popen([sys.executable,'-c',%r]);\nwhile not Path(%r).exists():time.sleep(.005)\n"%(worker,str(pidfile))
    if fault!='normal_exit':leader+='time.sleep(30)'
    stop=tmp_path/'STOP'
    def check():
        if pidfile.exists():
            if fault=='cancel':stop.touch()
            if fault=='monitor_failure':raise RuntimeError('synthetic monitor failure')
    result=supervise([sys.executable,'-c',leader],environment={'INGESTION_SOURCE_PRIVATE':'ONCE'},root=tmp_path/'owned',
        source=True,seconds=1,stop_file=stop,execution_budget='BROWSER_SOURCE_V2',render_profile=p,check=check)
    assert pidfile.exists(),result
    pid=int(pidfile.read_text())
    assert not psutil.pid_exists(pid),result
    assert result['cleanup']==('UNCERTAIN' if fault=='monitor_failure' else 'CLOSED'),result
    if fault=='normal_exit':assert result['exit_code']==0 and result['limit_hit'] is None
    elif fault=='deadline':assert result['limit_hit']=='DEADLINE'
    elif fault=='cancel':assert result['limit_hit']=='OWNER_STOP'
    elif fault=='rss':assert result['limit_hit'] in ('PROCESS_RSS','AGGREGATE_RSS')


def test_read_only_memory_samples_refuse_growth_lost_limits_and_missing_counters(tmp_path,monkeypatch):
    p=profile(tmp_path);group=tmp_path/'cgroup';group.mkdir()
    fields={'memory.max':p['aggregate_bytes'],'memory.current':100*r.MiB,'memory.swap.max':0,'memory.peak':110*r.MiB,
            'memory.events':'max 0\noom 0\noom_kill 0\n'}
    for k,v in fields.items():(group/k).write_text(str(v))
    monkeypatch.setattr(r,'memory_group',lambda:group)
    from types import SimpleNamespace
    monkeypatch.setattr(r.psutil,'Process',lambda:SimpleNamespace(memory_info=lambda:SimpleNamespace(rss=64*r.MiB)))
    monitor=r.MemoryMonitor(p);assert monitor.evidence()['guaranteed_peak'] is False
    (group/'memory.current').write_text(str(1900*r.MiB))
    with pytest.raises(Denied,match='HEADROOM'):monitor.check()
    (group/'memory.current').write_text(str(100*r.MiB));(group/'memory.events').write_text('max 1\noom 0\noom_kill 0\n')
    with pytest.raises(Denied,match='MEMORY_EVENT'):monitor.check()
    (group/'memory.events').unlink()
    with pytest.raises(Denied,match='ACCOUNTING_UNAVAILABLE'):monitor.check()


def test_historical_host_modes_unchanged():
    from verification.direct_reference.instrumented_probe import execution_environment_allowed
    assert execution_environment_allowed('trafford','render-disposable',{'RENDER_SERVICE_ID':r.SERVICE})
    assert not execution_environment_allowed('discovery_manchester_ui_window','render-disposable',{'RENDER_SERVICE_ID':r.SERVICE})
    assert not execution_environment_allowed('discovery_manchester_ui_window',r.MODE,{'RENDER_SERVICE_ID':r.SERVICE})
