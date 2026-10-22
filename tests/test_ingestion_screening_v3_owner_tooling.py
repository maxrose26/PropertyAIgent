"""The owner tooling of the screening-v3 activation (PR #175 follow-up): the registration renderer is validated by the runner's ACTUAL validator in a clean clone, and the two owner scripts are syntax-checked and driven
through their refusal paths under a pseudo-terminal in a fake home. Nothing is installed, registered or dispatched; no network, no database, no credential. NOT covered here (needs the owner's real terminal): the hidden
credential prompt, the systemd scope launch and the real gh session."""
import hashlib
import json
import os
import pty
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip('resource')      # the runner imports the Linux-only `resource` module (CI is Linux)

from verification.ingestion_storage import operational_runner as orr

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'docs/design/ingestion-screening-v3-activation-20261030'
WINDOW_DIR = ROOT / 'docs/design/ingestion-window-demonstration-20261023'
HEAD40 = 'a' * 40
SHA64 = 'b' * 64
AUDIT = dict(policy_events=SHA64, policy_final='c' * 64, control='d' * 64)


def text(path):
    return Path(path).read_bytes().decode('utf-8').replace('\r\n', '\n')


@pytest.fixture(scope='module')
def clone(tmp_path_factory):
    """A clean clone at the committed HEAD: the validator requires a clean checkout whose revision and tree match the registration."""
    target = tmp_path_factory.mktemp('clone') / 'repo'
    subprocess.run(['git', 'clone', '-q', '--no-hardlinks', str(ROOT), str(target)], check=True, timeout=300)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(['git', 'checkout', '-q', '--detach', head], cwd=target, check=True, timeout=120)
    return target


def render(clone, mode, minutes=25, extra=()):
    args = [sys.executable, '-I', '-B', str(clone / 'docs/design/ingestion-screening-v3-activation-20261030/render_registration.py'), '--mode', mode, '--minutes', str(minutes), '--evidence-head', HEAD40, *extra]
    done = subprocess.run(args, cwd=clone, capture_output=True, text=True, timeout=120)
    return done


def validate(clone, body_bytes):
    code = ('import os,sys; sys.path.insert(0,os.getcwd()); from verification.ingestion_storage.operational_runner import validate_registration; '
            'import hashlib; b=sys.stdin.buffer.read(); r=validate_registration(b,hashlib.sha256(b).hexdigest()); print(r["mode"])')
    return subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd=clone, input=body_bytes, capture_output=True, timeout=120)


def render_ok(clone, mode, **kw):
    extra = ()
    if mode == 'screening':
        extra = ('--policy-events-sha256', AUDIT['policy_events'], '--policy-final-sha256', AUDIT['policy_final'], '--control-sha256', AUDIT['control'])
    done = render(clone, mode, extra=extra, **kw)
    assert done.returncode == 0, done.stderr
    return done.stdout.encode(), json.loads(done.stdout), done.stderr.strip()


# ------------------------------------------------------------------------------------------------ the renderer, validated by the actual validator
@pytest.mark.parametrize('mode,runner_mode', [('policy', orr.SV3_POLICY_MODE), ('screening', orr.SV3_MODE)])
def test_each_rendered_registration_passes_the_runners_actual_validator_with_every_binding(clone, mode, runner_mode):
    body, r, sha = render_ok(clone, mode)
    assert hashlib.sha256(body).hexdigest() == sha
    done = validate(clone, body)
    assert done.returncode == 0 and done.stdout.decode().strip() == runner_mode, done.stderr
    head = subprocess.run(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=clone, capture_output=True, text=True).stdout.split()
    assert (r['revision'], r['tree']) == tuple(head) and r['evidence_head'] == HEAD40 and r['evidence_directory'] == orr.SV3_EVIDENCE_DIRECTORY
    assert r['manifest_sha256'] == hashlib.sha256((clone / orr.SV3_MANIFEST_PATH).read_bytes()).hexdigest() and r['controller_sha256'] == hashlib.sha256((clone / 'verification/ingestion_storage/operational_runner.py').read_bytes()).hexdigest()
    assert set(r['hashes']) == set(json.loads((clone / orr.SV3_MANIFEST_PATH).read_text())['bound_paths'])


def test_the_mode_specific_fields_are_exactly_the_reviewed_ones(clone):
    _, p, _ = render_ok(clone, 'policy')
    assert p['authority'] == orr.SV3_POLICY_AUTHORITY and p['execution_authority'] == 'NONE' and p['state_directory'] == orr.SV3_POLICY_STATE and p['predecessor'] == json.loads(json.dumps(orr.SV3_POLICY_PREDECESSOR))
    assert p['policy']['named_allowance'] == orr.SV3_NAME and p['policy']['rollback_function'] == str(orr.SV3_WORKER_ROLLBACK) and p['policy']['rollback_policy'] == str(orr.GENERATION3_WINDOW_POLICY)
    assert p['owner_limits'] == dict(connections=list(orr.SV3_POLICY_OWNER_LIMITS['connections']), commands=list(orr.SV3_POLICY_OWNER_LIMITS['commands'])) and not {'screening_v3', 'window', 'capture', 'pipeline'} & set(p)
    _, s, _ = render_ok(clone, 'screening')
    assert s['authority'] == orr.SV3_AUTHORITY and s['state_directory'] == orr.SV3_STATE and s['screening_v3'] == json.loads(json.dumps(orr.SV3_BINDING)) and s['control_sha256'] == AUDIT['control']
    assert s['policy_ceremony_audit'] == dict(events_sha256=AUDIT['policy_events'], final_result_sha256=AUDIT['policy_final']) and s['predecessor'] == json.loads(json.dumps(orr.SV3_PREDECESSOR))
    assert s['owner_limits'] == dict(connections=list(orr.SV3_OWNER_LIMITS['connections']), commands=list(orr.SV3_OWNER_LIMITS['commands'])) and not {'window', 'capture', 'pipeline', 'probe'} & set(s)


def test_the_expiry_windows_are_the_validators_and_are_enforced(clone):
    assert render(clone, 'policy', minutes=31).returncode != 0      # the renderer refuses what the validator would refuse (policy: at most 30 minutes)
    assert render(clone, 'screening', minutes=121, extra=('--policy-events-sha256', SHA64, '--policy-final-sha256', SHA64, '--control-sha256', SHA64)).returncode != 0
    for mode, minutes in (('policy', 30), ('screening', 120)):
        body, r, _ = render_ok(clone, mode, minutes=minutes)
        assert validate(clone, body).returncode == 0      # the maximum is accepted
        expired = json.dumps(dict(r, expires_at='2020-01-01T00:00:00+00:00')).encode()
        done = validate(clone, expired)
        assert done.returncode != 0 and b'ORIGINAL_OPERATIONAL_EXPIRY' in done.stderr


@pytest.mark.parametrize('mode', ['policy', 'screening'])
def test_every_binding_is_enforced_a_tampered_registration_is_refused(clone, mode):
    _, r, _ = render_ok(clone, mode)
    cases = {
        'revision': (dict(r, revision='0' * 40), b'CLEAN_REVIEWED_CHECKOUT'),
        'tree': (dict(r, tree='0' * 40), b'CLEAN_REVIEWED_CHECKOUT'),
        'authority': (dict(r, authority='AUTHORISE_SOMETHING_ELSE'), b'EXACT_OPERATIONAL_APPROVAL_REQUIRED'),
        'state': (dict(r, state_directory='another-state'), b'BINDING'),
        'limits': (dict(r, owner_limits=dict(connections=[99, 99], commands=[999, 999, 999])), b'BINDING'),
        'predecessor': (dict(r, predecessor={}), b'BINDING'),
        'hash': (dict(r, hashes=dict(r['hashes'], **{next(iter(r['hashes'])): '0' * 64})), b'REVIEWED_CONTENT_BINDING'),
        'controller': (dict(r, controller_sha256='0' * 64), b'CONTROLLER_CA_EVIDENCE_BINDING'),
        'extra_mode_key': (dict(r, pipeline={}), b'BINDING')}
    for name, (tampered, expected) in cases.items():
        done = validate(clone, json.dumps(tampered).encode())
        assert done.returncode != 0 and expected in done.stderr, (name, done.stderr[-300:])


def test_the_screening_registration_requires_the_installation_audit_and_control_digest(clone):
    args = ('--policy-events-sha256', SHA64, '--policy-final-sha256', SHA64)
    assert render(clone, 'screening', extra=args).returncode != 0      # no control digest
    assert render(clone, 'screening', extra=('--control-sha256', 'xyz', *args)).returncode != 0
    assert render(clone, 'screening', extra=('--control-sha256', SHA64)).returncode != 0      # no audit
    _, r, _ = render_ok(clone, 'screening')
    for broken in (dict(r, policy_ceremony_audit={'events_sha256': SHA64}), dict(r, policy_ceremony_audit=dict(events_sha256='short', final_result_sha256=SHA64)), dict(r, control_sha256='nothex')):
        done = validate(clone, json.dumps(broken).encode())
        assert done.returncode != 0 and b'BOLTON_SCREENING_V3_BINDING' in done.stderr


# ------------------------------------------------------------------------------------------------ the owner scripts
SCRIPTS = {'policy': ('owner-run-policy.sh', orr.SV3_POLICY_MODE, orr.SV3_POLICY_STATE, 'operational-bolton-policy-screening-v3-registration-20261030.json'),
           'screening': ('owner-run-screening.sh', orr.SV3_MODE, orr.SV3_STATE, 'operational-bolton-screening-v3-retained-registration-20261030.json')}


@pytest.mark.parametrize('kind', SCRIPTS)
def test_the_scripts_have_valid_syntax_and_no_stale_names(kind):
    name, mode, state, registration = SCRIPTS[kind]
    path = DIR / name
    assert subprocess.run(['bash', '-n', str(path)], capture_output=True, timeout=30).returncode == 0
    source = text(path)
    assert 'BOLTON_%s' % mode.removeprefix('BOLTON_') in source and ('STATE_DIRECTORY=' + state) in source and registration in source
    for stale in ('BOLTON_POLICY_WINDOW_ALLOWANCE', 'BOLTON_WINDOW_DEMONSTRATION', 'owner-run-window.sh', 'policy-v5 ceremony (Bolton', 'operational-bolton-window-demonstration-registration', 'POLICY V5.', 'capture allowance (source_calls=1)'):
        assert stale not in source, stale
    assert re.search(r'USAGE: %s <commit40> <tree40> <registration-sha256>' % re.escape(name), source) and 'docs/design/ingestion-screening-v3-activation-20261030/' + name in source


@pytest.mark.parametrize('kind', SCRIPTS)
def test_the_credential_handoff_and_refusal_order_are_those_of_the_proven_scripts(kind):
    name, mode, state, _ = SCRIPTS[kind]
    source = text(DIR / name)
    for forbidden in ('read -s', 'read -r -s', 'PASSWORD', 'DATABASE_URL', 'export ', 'GH_TOKEN', 'curl ', 'psql ', '--password'):
        assert forbidden not in source, forbidden      # the credential exists only at the controller's own hidden prompt
    order = ['[[ -t 0 && -t 2 ]]', 'test -z "$(git status --porcelain)"', 'test "$(git rev-parse HEAD)" = "$COMMIT"', "test \"$(git rev-parse 'HEAD^{tree}')\" = \"$TREE\"", 'sha256sum --check', 'test ! -e "$STATE_ROOT/$STATE_DIRECTORY"',
             'SCOPE_PRESENT_OR_UNKNOWN', 'validate_registration', 'systemd-run --user --scope']
    positions = [source.index(x) for x in order]
    assert positions == sorted(positions)      # every refusal precedes the launch; the registration is validated before anything is consumed
    assert source.count('systemd-run') == 1 and '--registration "$REGISTRATION" --registration-sha256 "$REGISTRATION_SHA256"' in source and 'MemoryMax=1610612736' in source and 'MemorySwapMax=0' in source


@pytest.mark.parametrize('kind,proven', [('policy', 'owner-run-policy.sh'), ('screening', 'owner-run-window.sh')])
def test_the_launch_block_equals_the_proven_predecessors_except_the_stated_values(kind, proven):
    new, old = text(DIR / SCRIPTS[kind][0]), text(WINDOW_DIR / proven)
    block = lambda s: s[s.index('set +e\n'):]
    assert block(new) == block(old)      # same launch, scope readback and audit-hash printing as the scripts that ran in production
    assert ('RuntimeMaxSec=300s' if kind == 'policy' else 'RuntimeMaxSec=4600s') in new


def test_the_attendance_window_is_derived_from_this_modes_deadlines_and_the_77_minutes_is_the_inherited_outer_limit():
    b, d, t = orr.SV3_BINDING, orr.PIPELINE_DEADLINES, orr.PIPELINE_TIMING
    in_grant = b['ready_wait_seconds'] + b['grant_lifetime_seconds']      # READY wait (outside the grant) + the grant
    assert in_grant == 2700 and in_grant + 600 <= d['job'] == 4200      # 45 minutes of waiting plus a 10-minute allowance for preparation and the publication, inside the 70-minute job deadline
    assert d['job'] + d['diagnostic_window'] <= t['work_seconds'] < t['outer_seconds'] < 4600      # the systemd RuntimeMaxSec (4600 s = 76.7 minutes) is the inherited kernel outer limit above all of it
    screening = text(DIR / 'owner-run-screening.sh')
    assert '4200 s job deadline (70 minutes)' in screening and 'INHERITED kernel outer limit' in screening and 'RuntimeMaxSec=4600s' in screening
    assert 'up to about 77 minutes' not in screening


# ------------------------------------------------------------------------------------------------ refusal behaviour under a pseudo-terminal, in a fake home
@pytest.fixture()
def fake_home(tmp_path):
    home = tmp_path / 'home'
    owner = home / 'stage4-owner'
    checkout = owner / 'probe-checkout'
    (owner / 'storage-controller-venv/bin').mkdir(parents=True)
    (owner / 'storage-controller-venv/bin/python').symlink_to(sys.executable)
    checkout.mkdir()
    env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t', GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
    for cmd in (['git', 'init', '-q'], ['git', 'commit', '-q', '--allow-empty', '-m', 'x']):
        subprocess.run(cmd, cwd=checkout, env=env, check=True)
    marker = tmp_path / 'LAUNCHED'
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for tool in ('systemd-run', 'systemctl'):
        (bin_dir / tool).write_text('#!/bin/sh\necho "$0 $@" >> %s\nexit 99\n' % marker)
        (bin_dir / tool).chmod(0o755)
    (home / '.local/state/propertyaigent').mkdir(parents=True)
    return dict(home=home, checkout=checkout, marker=marker, bin=bin_dir, env=env)


def run(script, args, fake, tty=True):
    env = dict(os.environ, HOME=str(fake['home']), PATH=str(fake['bin']) + os.pathsep + os.environ['PATH'])
    for key in ('GH_TOKEN', 'GITHUB_TOKEN'):
        env.pop(key, None)
    if not tty:
        done = subprocess.run(['bash', str(script), *args], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout + done.stderr
    master, slave = pty.openpty()
    proc = subprocess.Popen(['bash', str(script), *args], env=env, stdin=slave, stdout=subprocess.PIPE, stderr=slave, text=True)
    os.close(slave)
    out = []
    deadline = time.time() + 60
    while time.time() < deadline:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            out.append(chunk.decode(errors='replace'))
        elif proc.poll() is not None:
            break
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    stdout = proc.stdout.read()
    os.close(master)
    return proc.returncode, stdout + ''.join(out)


@pytest.mark.parametrize('kind', SCRIPTS)
def test_the_scripts_refuse_before_any_launch(kind, fake_home):
    name, _, state, registration = SCRIPTS[kind]
    script = DIR / name
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=fake_home['checkout'], capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], cwd=fake_home['checkout'], capture_output=True, text=True).stdout.strip()
    reg = fake_home['home'] / 'stage4-owner' / registration
    reg.write_text('{}')
    sha = hashlib.sha256(b'{}').hexdigest()

    code, out = run(script, [], fake_home)
    assert code == 2 and 'USAGE' in out
    code, out = run(script, [commit, tree, 'nothex'], fake_home)
    assert code == 2 and 'USAGE' in out
    code, out = run(script, [commit, tree, sha], fake_home, tty=False)
    assert code == 2 and 'VISIBLE_INTERACTIVE_TTY_REQUIRED' in out
    (fake_home['checkout'] / 'dirty.txt').write_text('x')
    code, out = run(script, [commit, tree, sha], fake_home)
    assert code != 0 and 'namespace_absent' not in out      # an unclean checkout
    (fake_home['checkout'] / 'dirty.txt').unlink()
    code, out = run(script, ['1' * 40, tree, sha], fake_home)
    assert code != 0 and 'namespace_absent' not in out      # the wrong commit
    code, out = run(script, [commit, '2' * 40, sha], fake_home)
    assert code != 0 and 'namespace_absent' not in out      # the wrong tree
    code, out = run(script, [commit, tree, '3' * 64], fake_home)
    assert code != 0 and 'namespace_absent' not in out      # the registration bytes differ from the named digest
    (fake_home['home'] / '.local/state/propertyaigent' / state).mkdir()
    code, out = run(script, [commit, tree, sha], fake_home)
    assert code != 0 and 'namespace_absent' not in out      # the namespace is already used
    (fake_home['home'] / '.local/state/propertyaigent' / state).rmdir()
    code, out = run(script, [commit, tree, sha], fake_home)
    assert code != 0 and 'namespace_absent=%s' % state in out and ('No such file' in out or 'FAILED' in out)      # absent consumed-predecessor audits are refused
    assert not fake_home['marker'].exists()      # nothing was ever launched: neither systemd-run nor even the scope probe was reached
