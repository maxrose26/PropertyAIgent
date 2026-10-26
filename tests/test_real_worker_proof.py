"""Regression proof of the REAL worker chain (docs/design/real-worker-proof-20261026/SPEC.md section 4).

Opt-in (`REAL_WORKER_PROOF=1`): needs a Linux host with a systemd user manager and memory delegation, unprivileged user/network/mount
namespaces, and an installed Playwright headless shell. It runs the unmodified `Source.run` (production command, environment, process
layers, cgroup attach, worker, `finite.read`, supervisors, real Chromium / real `requests`) in a real V2 user scope inside a network
namespace that has only loopback, against local fixtures. The interpreter is an overlay venv created here that borrows the packages of
`REAL_WORKER_PROOF_BASE_PYTHON` (default: the interpreter running pytest); to prove the launch interpreter itself, point that variable
at it after the owner installs the dependency. The fixture server and namespace setup always run under the pytest interpreter. Nothing is installed anywhere; no council, database or external network is contacted.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('REAL_WORKER_PROOF_BASE_PYTHON') or sys.executable
HOSTS = ('account.rochdale.gov.uk', 'publicaccess.tameside.gov.uk', 'planningpa.oldham.gov.uk')
MARKER = '# real-worker-proof fixture hosts'
UNIT = 'propertyaigent-operational-once'
V2 = 'THREE_COUNCIL_SOURCE_RELEASE_V2'

pytestmark = pytest.mark.skipif(os.environ.get('REAL_WORKER_PROOF') != '1', reason='opt-in native proof: set REAL_WORKER_PROOF=1')


def run(command, **kwargs):
    return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, **kwargs)


def prerequisites():
    for tool in ('systemd-run', 'systemctl', 'unshare', 'nsenter', 'mount'):
        if shutil.which(tool) is None:
            return f'{tool} is not available'
    if run(['unshare', '-rnm', 'true'], timeout=20).returncode:
        return 'unprivileged user+network+mount namespaces are unavailable'
    shell = Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or Path.home() / '.cache/ms-playwright')
    if not list(shell.glob('chromium_headless_shell-*')):
        return 'no Playwright headless shell is installed'
    if run(['systemctl', '--user', 'list-units', '--all', f'{UNIT}*', '--no-legend']).stdout.strip():
        return 'a propertyaigent operational scope is already present'
    if run(['pgrep', '-x', 'chrome-headless-shell']).returncode == 0 or run(['pgrep', '-x', 'chrome']).returncode == 0:
        return 'a browser process is already running'
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable')))
    if available * 1024 < 3 * 1024 ** 3:
        return 'less than 3 GiB of memory is available'
    probe = run(['systemd-run', '--user', '--scope', '--quiet', '--unit=propertyaigent-real-worker-proof-probe',
                 '-p', 'Delegate=memory', '-p', 'MemoryMax=268435456', 'true'], timeout=30)
    return None if probe.returncode == 0 else 'a delegated user scope cannot be created: ' + probe.stderr.strip()[-120:]


def certificates(work):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key, key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'real-worker-proof fixture CA (test only)')])
    window = dict(not_valid_before=now - datetime.timedelta(minutes=5), not_valid_after=now + datetime.timedelta(hours=2))
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(window['not_valid_before']).not_valid_after(window['not_valid_after'])
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False).sign(ca_key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOSTS[0])])).issuer_name(ca_name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(window['not_valid_before']).not_valid_after(window['not_valid_after'])
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in HOSTS]), False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False).sign(ca_key, hashes.SHA256()))
    pem = serialization.Encoding.PEM
    (work / 'ca.pem').write_bytes(ca.public_bytes(pem))
    server = work / 'server.pem'
    fd = os.open(server, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(key.private_bytes(pem, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        stream.write(leaf.public_bytes(pem))


def overlay(work, name, blocked=()):
    """A venv that borrows the base interpreter's packages and carries the proof hook. Nothing is installed or modified."""
    path = work / name
    assert run([BASE, '-m', 'venv', '--without-pip', str(path)], timeout=120).returncode == 0
    site = next(path.glob('lib/python*/site-packages'))
    base_paths = json.loads(run([BASE, '-c', 'import json,sys;print(json.dumps(sys.path))']).stdout)
    lines = [p for p in base_paths if p and Path(p).is_dir() and ('site-packages' in p or 'dist-packages' in p)]
    (site / 'real_worker_proof_hook.py').write_text((ROOT / 'tests/real_worker_proof_hook.py').read_text())
    if blocked:
        (site / 'blocked.txt').write_text('\n'.join(blocked) + '\n')
    (site / 'proof.pth').write_text('\n'.join(lines + ['import real_worker_proof_hook']) + '\n')
    return path / 'bin/python'


class Proof:
    pass


@pytest.fixture(scope='module')
def proof(tmp_path_factory):
    reason = prerequisites()
    if reason:
        pytest.skip(reason)
    work = tmp_path_factory.mktemp('real-worker-proof')
    work.chmod(0o700)
    env = Proof()
    env.work = work
    certificates(work)
    (work / 'hosts').write_text(Path('/etc/hosts').read_text().rstrip('\n') + f"\n127.0.0.1 {' '.join(HOSTS)} {MARKER}\n")
    certifi_path = run([BASE, '-c', 'import certifi;print(certifi.where())']).stdout.strip()
    (work / 'bundle.pem').write_text(Path(certifi_path).read_text().rstrip('\n') + '\n' + (work / 'ca.pem').read_text())
    env.python_ok = overlay(work, 'overlay-ok')
    env.python_blocked = overlay(work, 'overlay-blocked', blocked=('rapidfuzz',))
    holder = subprocess.Popen(['unshare', '-rnm', 'sleep', '1800'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env.holder = holder
    try:
        for _ in range(100):
            if os.readlink(f'/proc/{holder.pid}/ns/net') != os.readlink('/proc/self/ns/net'):
                break
            time.sleep(0.1)
        env.enter = ['nsenter', '-U', '-n', '-m', '--preserve-credentials', '-t', str(holder.pid)]
        setup = run(env.enter + [sys.executable, str(ROOT / 'tests/real_worker_proof_nssetup.py'), str(work / 'hosts'), str(work / 'bundle.pem'), certifi_path], timeout=60)
        assert setup.returncode == 0 and 'ready' in setup.stdout, setup.stderr[-500:]
        yield env
    finally:
        holder.kill()
        holder.wait()


class Server:
    """The fixture server inside the proof namespace; one fresh instance per scenario (the Idox sequences are single-use)."""
    def __init__(self, proof, rows=12):
        self.proof, self.rows = proof, rows

    def __enter__(self):
        log = self.proof.work / 'server.log'
        log.write_text('')
        self.process = subprocess.Popen(self.proof.enter + [sys.executable, str(ROOT / 'tests/real_worker_proof_server.py'), str(self.proof.work), str(self.rows)],
                                        cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1'),
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert 'ready' in self.process.stdout.readline(), 'fixture server did not start'
        return self

    def __exit__(self, *exc):
        self.process.kill()
        self.process.wait()
        self.log = (self.proof.work / 'server.log').read_text().splitlines()


def scope_is_gone(timeout=15):
    for _ in range(timeout * 4):
        if not run(['systemctl', '--user', 'list-units', '--all', f'{UNIT}*', '--no-legend']).stdout.strip():
            return True
        time.sleep(0.25)
    return False


def scenario(proof, name, python, slots, *, precreate=None):
    runs = proof.work / name
    command = ['systemd-run', '--user', '--scope', '--quiet', f'--unit={UNIT}', '-p', 'Delegate=memory', '-p', 'MemoryMax=2147483648',
               '-p', 'MemorySwapMax=0', '-p', 'OOMPolicy=kill', '-p', 'RuntimeMaxSec=110s',
               'env', '-i', 'PATH=/usr/bin:/bin', f'HOME={Path.home()}', f'PYTHONPATH={ROOT}', 'PYTHONDONTWRITEBYTECODE=1'] + proof.enter + [
               str(python), str(ROOT / 'tests/real_worker_proof_runner.py'), str(runs), '--slots', slots]
    if precreate:
        command += ['--precreate-output', str(precreate)]
    with Server(proof) as server:
        done = run(command, timeout=150, cwd=ROOT)
    scope_result = run(['systemctl', '--user', 'show', '-p', 'Result', '--value', f'{UNIT}.scope']).stdout.strip()
    assert (runs / 'result.json').is_file(), (done.stdout[-800:], done.stderr[-800:])
    result = json.loads((runs / 'result.json').read_text())
    assert scope_is_gone(), 'the operational scope did not go away'
    return dict(result=result, server_log=server.log, scope_result=scope_result, exit=done.returncode, runs=runs,
                by_slot={entry['slot']: entry for entry in result['results']})


@pytest.fixture(scope='module')
def positive(proof):
    return scenario(proof, 'positive', proof.python_ok, '1,2,3')


@pytest.fixture(scope='module')
def missing(proof):
    return scenario(proof, 'missing-dependency', proof.python_blocked, '1,2,3')


@pytest.fixture(scope='module')
def crash(proof):
    return scenario(proof, 'deliberate-crash', proof.python_ok, '1', precreate=1)


# ---------------------------------------------------------------- the real chain, non-empty fixtures

def test_the_namespace_has_no_external_network(positive):
    isolation = positive['result']['isolation']
    assert isolation['dns_blocked'] is True and all(isinstance(errno, int) and errno != 0 for errno in isolation['connect'])


def test_the_scope_ran_clean_with_exact_v2_enforcement(positive):
    assert positive['result']['render_error'] is None
    assert positive['scope_result'] in {'success', ''} and positive['exit'] == 0
    close = positive['result']['close']
    assert close['groups_removed'] is True and close['survivors'] == 0
    for group, events in close['events'].items():
        assert events['max'] == events['oom'] == events['oom_kill'] == 0, group
    assert positive['result']['python'].endswith('overlay-ok/bin/python')


def test_rochdale_real_worker_chain(positive):
    entry = positive['by_slot'][1]
    assert entry['outcome'] == 'RETURNED' and entry['failure'] is None and entry['listing_failure'] is None
    assert entry['records'] == 12 and entry['segments'] == 2 and entry['enumeration_evidence'] == 'COUNT_RECONCILED'
    assert entry['screened'] == entry['records']                                     # every record carries `processing_screen`
    assert entry['public_ui_posts'] >= 1 and entry['execution_budget'] == 'BROWSER_SOURCE_V2'
    assert set(entry['stage_timings']) == {'NAVIGATION', 'READY', 'CRITERIA', 'SEGMENT'} and len(entry['stage_timings']['SEGMENT']) == 2
    assert entry['process_cleanup'] == 'CLOSED' and entry['live_owned_survivors'] == 0
    assert entry['accept'] == 'COMPLETE'                                              # the unmodified controller-side acceptance
    assert 'worker_exit' not in entry['closure']


@pytest.mark.parametrize('slot,council', [(2, 'tameside'), (3, 'oldham')])
def test_idox_real_worker_chain(positive, slot, council):
    entry = positive['by_slot'][slot]
    assert entry['council'] == council and entry['outcome'] == 'RETURNED' and entry['failure'] is None
    assert entry['records'] >= 1 and entry['screened'] == entry['records']
    assert entry['enumeration_evidence'] == 'COUNT_RECONCILED' and entry['accept'] == 'COMPLETE'
    assert 'worker_exit' not in entry['closure']


def test_every_slot_closed_completely_with_no_descendants(positive):
    for entry in positive['by_slot'].values():
        assert entry['closure']['source_group_closed'] is True and entry['closure']['child_reaped'] is True and entry['closure']['failures'] == []
        assert entry['descendants_after'] == 0


def test_the_fixture_server_saw_only_the_expected_hosts_and_sequences(positive):
    seen = [line.split()[2] for line in positive['server_log']]
    assert 'UNKNOWN_HOST' not in seen and set(seen) == {'rochdale', 'tameside', 'oldham'}
    assert seen.count('tameside') == 4 and seen.count('oldham') == 4             # form, search, sort, refine; nothing beyond
    assert any(' POST rochdale /pr/s/sfsites/aura' in line for line in positive['server_log'])


# ---------------------------------------------------------------- controls

def test_missing_dependency_control_fails_visibly_with_the_recorded_evidence(missing):
    assert set(missing['by_slot']) == {1, 2, 3}
    for slot, entry in missing['by_slot'].items():
        assert entry['outcome'] == 'SOURCE_FAILURE' and entry['code'] == 'SOURCE_CHILD_FAILURE' and entry['stage'] == 'SOURCE_PROCESS_EXIT', slot
        assert entry['closure']['worker_exit'] == dict(returncode=1, signal=None, reason='DEPENDENCY_UNAVAILABLE', reason_state='VALIDATED'), slot
        assert entry['closure']['source_group_closed'] is True and entry['closure']['child_reaped'] is True
        assert entry['descendants_after'] == 0
    assert missing['result']['close']['groups_removed'] is True


def test_deliberate_crash_control_records_a_generic_fixed_reason(crash):
    entry = crash['by_slot'][1]
    assert entry['outcome'] == 'SOURCE_FAILURE' and entry['code'] == 'SOURCE_CHILD_FAILURE'
    assert entry['closure']['worker_exit'] == dict(returncode=1, signal=None, reason='PREPARATION_FAILURE', reason_state='VALIDATED')
    assert entry['closure']['source_group_closed'] is True and entry['descendants_after'] == 0


def test_the_preflight_names_the_same_defect_in_the_blocked_interpreter(proof):
    env = dict(PATH='/usr/bin:/bin', HOME=str(Path.home()), PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    done = run([str(proof.python_blocked), '-m', 'verification.discovery.four_council_release', 'runtime-check', '--version', V2],
               cwd=ROOT, env=env, timeout=180)
    report = json.loads(done.stdout)
    assert done.returncode == 1 and report['ok'] is False
    assert 'rapidfuzz' in report['third_party_missing'] and ['app.pipeline.site_linking', 'ModuleNotFoundError'] in report['import_failures']
    ok = run([str(proof.python_ok), '-m', 'verification.discovery.four_council_release', 'runtime-check', '--version', V2],
             cwd=ROOT, env=env, timeout=180)
    assert ok.returncode == 0 and json.loads(ok.stdout)['ok'] is True


def test_nothing_is_left_running(proof):
    assert scope_is_gone()
    assert run(['pgrep', '-x', 'chrome-headless-shell']).returncode == 1
    assert run(['pgrep', '-f', r'^\S*python\S* \S*real_worker_proof_(server|runner)\.py']).returncode == 1
