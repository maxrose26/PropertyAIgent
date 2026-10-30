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


# Independent frozen inventory, job-dbi9o0mtlv9c7398ki6g: indices 0..109.
INVENTORY_110 = frozenset("""
BLACK
BLUE
BOLD
BUN_HOME
BUN_VERSIONS_DIR
CARGO_HOME
CYAN
DEBIAN_FRONTEND
DEFAULT_BUN_VERSION
DEFAULT_NODE_VERSION
DEFAULT_POETRY_VERSION
DEFAULT_PYTHON_VERSION
DEFAULT_UV_VERSION
DIM
ENTER_STANDOUT
EXIT_STANDOUT
FORWARDED_ALLOW_IPS
GATSBY_TELEMETRY_DISABLED
GREEN
GUNICORN_CMD_ARGS
HOME
HOSTNAME
IS_PULL_REQUEST
KUBERNETES_PORT
KUBERNETES_PORT_443_TCP
KUBERNETES_PORT_443_TCP_ADDR
KUBERNETES_PORT_443_TCP_PORT
KUBERNETES_PORT_443_TCP_PROTO
KUBERNETES_SERVICE_HOST
KUBERNETES_SERVICE_PORT
KUBERNETES_SERVICE_PORT_HTTPS
LANG
LC_ALL
MAGENTA
NEXT_TELEMETRY_DISABLED
NODES_ROOT
NODE_ENV
NODE_GYP_FORCE_PYTHON
NODE_MODULES_CACHE
NODE_ROOT
NODE_VERBOSE
NODE_VERSION
NPM_CONFIG_CACHE
NPM_CONFIG_DEVDIR
NPM_CONFIG_LOGLEVEL
NPM_CONFIG_STORE_DIR
OLDPWD
PATH
PIPENV_CACHE_DIR
PIPENV_QUIET
PIPENV_VENV_IN_PROJECT
PIPENV_YES
PIP_CACHE_DIR
PLAYWRIGHT_BROWSERS_PATH
POETRY_CACHE_DIR
POETRY_HOME
POETRY_VERSIONS_DIR
PWD
PYTHON_VERSIONS_DIR
RED
RENDER
RENDER_CPU_COUNT
RENDER_DIR
RENDER_DOCKER_LOCAL_CACHE
RENDER_ENV
RENDER_ENV_IS_DOCKER
RENDER_GIT_BRANCH
RENDER_GIT_COMMIT
RENDER_GIT_REPO_SLUG
RENDER_INSTANCE_ID
RENDER_INTERNAL_IP
RENDER_NATIVE_ENV_PATH
RENDER_NODE_INSTALLED
RENDER_NODE_VERSION
RENDER_NODE_VERSION_DETECTED
RENDER_PM_DIR
RENDER_PM_ROOT
RENDER_PRE_RUN_COMMAND
RENDER_PROJECT_DIR
RENDER_PROJECT_ROOT
RENDER_REPO_ROOT
RENDER_ROOT
RENDER_SERVICE_CONTEXT_ROOT
RENDER_SERVICE_ID
RENDER_SERVICE_NAME
RENDER_SERVICE_NS
RENDER_SERVICE_SLUG
RENDER_SERVICE_TYPE
RENDER_SRC_ROOT
RENDER_USE_BUILD_TOOL_NODE
RENDER_USE_SLIM_PYTHON_ARTIFACT
RESET
RUSTUP_HOME
SHLVL
TERM
TMPDIR
USER_RUN_COMMAND
UV_CACHE_DIR
UV_NO_MANAGED_PYTHON
UV_PYTHON_DOWNLOADS
UV_SYSTEM_PYTHON
UV_VERSIONS_DIR
VENV_ROOT
VIRTUAL_ENV
VIRTUAL_ENV_DISABLE_PROMPT
VIRTUAL_ENV_PROMPT
XDG_CACHE_HOME
YARN_CACHE_FOLDER
YELLOW
_
""".split())


def sentinel_environment(tmp_path):
    marker = tmp_path/'PARENT_VALUE_EXECUTED'
    value = 'PARENT_SENTINEL; touch ' + str(marker) + '; $(touch ' + str(marker) + ')'
    return dict.fromkeys(INVENTORY_110, value), marker


def test_complete_inventory_passes_environment_without_using_values(tmp_path, monkeypatch, capsys):
    env, marker = sentinel_environment(tmp_path)
    env.update(RENDER_SERVICE_ID=a.r.SERVICE, RENDER_GIT_COMMIT='a'*40)
    monkeypatch.setattr(a.os, 'environ', env)
    assert len(INVENTORY_110) == 110
    assert len(INVENTORY_110 - a.ENV) == 93
    assert a.main([]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)['failing_check'] == 'arguments'
    assert 'PARENT_SENTINEL' not in output and not marker.exists()


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
 worker="import sys;from verification.ingestion_storage import render_acceptance_a as a;import os;assert not (set(os.environ) & a.PARENT_PLATFORM_ENV);assert 'PARENT_SENTINEL' not in str(dict(os.environ));a.r.source_context=lambda p:True;raise SystemExit(a.main(['--worker',sys.argv[1]]+(['--hold'] if sys.argv[2]=='True' else [])))"
 return original([sys.executable,'-c',worker,command[4],str('--hold' in command)],**kw)
a.supervise=supervise
raise SystemExit(a.main(sys.argv[1:]))
'''
    if scenario=='timeout':
        bootstrap=bootstrap.replace('a.r.MemoryMonitor=M', 'a.r.MemoryMonitor=M\na.PHASE_SECONDS=1').replace("raise SystemExit(a.main(['--worker',sys.argv[1]]+(['--hold'] if sys.argv[2]=='True' else [])))", 'import time;time.sleep(10)')
    env, sentinel_marker = sentinel_environment(tmp_path)
    env.update(PATH='/usr/bin:/bin',HOME=str(tmp_path),RENDER_SERVICE_ID=a.r.SERVICE,RENDER_GIT_COMMIT='a'*40,PLAYWRIGHT_BROWSERS_PATH=cache)
    reaper=OwnedSubreaper()
    try:
        result=subprocess.run(['timeout','--signal=TERM','--kill-after=5s','190s',sys.executable,'-c',bootstrap,
            '--profile',str(cfg),'--output',str(tmp_path/'run')],env=env,capture_output=True,text=True,timeout=200)
        (tmp_path/'captured-log.txt').write_text(result.stdout+result.stderr)
        assert not sentinel_marker.exists()
        assert 'PARENT_SENTINEL' not in result.stdout + result.stderr
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
    record=json.loads(output.splitlines()[-1])
    assert record['reason_code']==code and record['failing_check']==check
    assert record['phase']=='REFUSED' and record['successful_intake'] is False
    assert 'SECRET_VALUE' not in output and len(output.encode())<8192
    if case=='environment':
        assert record['reported_count']==40 and record['inventory_complete']
        assert record['unexpected_count']==40
    if case=='allocation':assert record['memory_max']=='max'
    if case=='cgroup':assert record['readback_status']=='unavailable'


def test_unicode_environment_names_fit_log_bound(monkeypatch,capsys):
    monkeypatch.setattr(a.os,'environ',{str(i)+'\U0001f600'*200:'SECRET_VALUE' for i in range(40)})
    assert a.main([])==2
    output=capsys.readouterr().out
    record=json.loads(output.splitlines()[-1])
    assert record['reason_code']=='A_ENVIRONMENT_NOT_ALLOWLISTED'
    assert len(output.encode())<a.OUTPUT_BYTES and 'SECRET_VALUE' not in output
    assert 0 < record['reported_count'] < 40 and not record['inventory_complete']


@pytest.mark.parametrize('name', sorted(a.PARENT_PLATFORM_ENV))
def test_reviewed_platform_parent_only(name, monkeypatch, capsys):
    monkeypatch.setattr(a.os, 'environ', {name: 'PLATFORM_VALUE_SENTINEL'})
    assert a.main([]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)['failing_check'] == 'service_binding'
    assert 'PLATFORM_VALUE_SENTINEL' not in output


@pytest.mark.parametrize('name', ['UNREVIEWED_PLATFORM_NAME', 'RENDER_UNKNOWN', 'RENDER_API_KEY',
    'DATABASE_URL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GITHUB_TOKEN',
    'APPLICATION_SECRET', 'AWS_SECRET_ACCESS_KEY', 'CUSTOM_PASSWORD'])
def test_unknown_and_credentials_still_refuse(name, monkeypatch, capsys):
    monkeypatch.setattr(a.os, 'environ', {'IS_PULL_REQUEST': 'false', name: 'SECRET_SENTINEL'})
    assert a.main([]) == 2
    output = capsys.readouterr().out
    records = [json.loads(line) for line in output.splitlines()]
    assert records[-1]['reason_code'] == 'A_ENVIRONMENT_NOT_ALLOWLISTED'
    assert records[-1]['inventory_complete'] and records[-1]['reported_count'] == 1
    assert records[0]['unexpected_names'] == [name]
    assert 'SECRET_SENTINEL' not in output


@pytest.mark.parametrize('count,width,complete', [(93, 64, True), (1000, 64, False), (1, 40000, False)])
def test_inventory_complete_or_explicit_overflow(count, width, complete, monkeypatch, capsys):
    names = sorted(f'UNKNOWN_{i:04d}_' + 'x'*width for i in range(count))
    monkeypatch.setattr(a.os, 'environ', dict.fromkeys(names, 'SECRET_SENTINEL'))
    assert a.main([]) == 2
    output = capsys.readouterr().out
    records = [json.loads(line) for line in output.splitlines()]
    terminal = records[-1]
    reported = [n for r in records[:-1] for n in r['unexpected_names']]
    assert terminal['phase'] == 'REFUSED'
    assert terminal['unexpected_count'] == count
    assert terminal['reported_count'] == len(reported)
    assert terminal['inventory_complete'] is complete
    assert terminal['names_truncated'] is (not complete)
    assert reported == names[:len(reported)]
    if complete: assert reported == names
    assert len(output.encode()) <= a.OUTPUT_BYTES
    assert all(len(line.encode()) + 1 <= a.INVENTORY_CHUNK_BYTES for line in output.splitlines()[:-1])
    assert 'SECRET_SENTINEL' not in output


def test_parent_names_and_values_not_in_source_environment(tmp_path, monkeypatch):
    from verification.ingestion_storage import operational_supervisor as supervisor
    for name in a.PARENT_PLATFORM_ENV:
        monkeypatch.setenv(name, 'PARENT_PLATFORM_SENTINEL')
    monkeypatch.setenv('OPENAI_API_KEY', 'PARENT_SECRET_SENTINEL')
    captured = []
    def capture(command, **kwargs):
        captured.append(kwargs['env'])
        raise OSError('synthetic launch failure')
    monkeypatch.setattr(supervisor.subprocess, 'Popen', capture)
    monkeypatch.setattr(a.r, 'validate_profile', lambda p: p)
    class Reaper:
        def close(self): pass
    monkeypatch.setattr(a.r, 'OwnedSubreaper', Reaper)
    p = profile(tmp_path/'profile')
    result = supervisor.supervise([sys.executable, '-c', 'pass'],
        environment={'INGESTION_SOURCE_PRIVATE':'ONCE',
                     'PLAYWRIGHT_BROWSERS_PATH':p['browser_path'],
                     'INGESTION_RENDER_PROFILE':json.dumps(p)},
        root=tmp_path/'child', source=True, seconds=1,
        execution_budget='BROWSER_SOURCE_V2', render_profile=p)
    assert result['cleanup'] == 'UNCERTAIN'
    assert len(captured) == 1 and set(captured[0]) <= a.r.SOURCE_ENV
    assert not (a.PARENT_PLATFORM_ENV & set(captured[0]))
    assert 'OPENAI_API_KEY' not in captured[0]
    assert 'PARENT_PLATFORM_SENTINEL' not in json.dumps(captured)
    assert 'PARENT_SECRET_SENTINEL' not in json.dumps(captured)
