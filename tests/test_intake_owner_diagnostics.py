"""Offline diagnostic envelope only; no source, database or provider operation."""
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from app.ingestion.ledger import Denied
from verification.ingestion_storage import intake_owner_client as client


@pytest.mark.parametrize('phase,code,error_type', [
    ('activate','RUNTIME_NOT_DORMANT',Denied),
    ('close','SESSIONS_UNRESOLVED',Denied),
    ('stop-disposition','EXACT_GENERATION5_STOP_REQUIRED',Denied),
    ('readback','INDEPENDENT_PUBLICATION_BINDING',Denied),
    ('handoff','RENDER_RESPONSE_UNCERTAIN_NO_RETRY',RuntimeError),
    ('inspect','PRIVATE_VAULT_REQUIRED',Denied),
    ('qualify','REVIEWED_CA_HASH_MISMATCH',ValueError),
    ('readback','BINDING_HASH_REFUSED',SystemExit),
])
def test_known_failures_preserve_distinct_phase_and_literal_reason(phase,code,error_type):
    result=json.loads(client.failure_output(phase,error_type(code)))
    assert result['phase']==phase and result['failure_reason']==code
    assert result['status']=='STOP_PHASE_REQUIRES_REVIEW_NO_RETRY'
    assert result['retry'] is False and result['transaction_outcome']=='NOT_INFERRED_RECONCILE_NO_RETRY'



@pytest.mark.parametrize('exc', [
    Exception('SESSIONS_UNRESOLVED'), KeyError('OWNER_BINDING'),
    ValueError('password=synthetic-sensitive-value'),
    Denied('OWNER_BINDING', 'synthetic-sensitive-value'),
    Denied('OWNER_BINDING\nsynthetic-sensitive-value'),
    SystemExit(137), KeyboardInterrupt(),
])
def test_unknown_failures_have_fixed_code_and_no_exception_text(exc):
    result=client.failure_output('close',exc)
    assert json.loads(result)['failure_reason']=='UNKNOWN_FAILURE'
    assert 'synthetic-sensitive-value' not in result and '137' not in result


def test_unprintable_unknown_and_causes_environment_or_sized_values_never_exported(monkeypatch):
    secret='postgresql://synthetic-user:synthetic-password@example.invalid/db?token=synthetic-token'
    monkeypatch.setenv('SYNTHETIC_DIAGNOSTIC_SECRET',secret)
    class Unprintable(Exception):
        def __str__(self):raise AssertionError('must not stringify')
        @property
        def args(self):raise AssertionError('must not inspect unknown args')
    exc=Unprintable(secret)
    exc.__cause__=ValueError(secret)
    for phase in (secret, 'X'*1000000, None, ['activate']):
        raw=client.failure_output(phase,exc)
        result=json.loads(raw)
        assert result['phase']=='UNKNOWN_PHASE' and result['failure_reason']=='UNKNOWN_FAILURE'
        assert secret not in raw and 'synthetic' not in raw
    for phase in client.PHASES:
        for reason in client.FAILURE_REASONS:
            raw=client.failure_output(phase,Denied(reason))
            assert len(raw.encode())+1<=client.DIAGNOSTIC_BYTES==1024
    assert json.loads(client.failure_output('inspect',Denied('X'*1000000)))['failure_reason']=='UNKNOWN_FAILURE'


def test_real_child_invalid_binding_refuses_with_code_without_connection(tmp_path,monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    binding=tmp_path/'binding.json';binding.write_text('{}')
    r,w=os.pipe();os.write(w,b'{"owner_password":"SYNTHETIC_HIDDEN_PASSWORD"}');os.close(w)
    try:
        data,status=client.capture([sys.executable,'-B','-m',client.MODULE,'--child','--secrets-fd',str(r),
             '--phase','readback','--binding',str(binding),'--binding-sha256',hashlib.sha256(binding.read_bytes()).hexdigest()],
             dict(PATH='/usr/bin:/bin',PYTHONDONTWRITEBYTECODE='1',DATABASE_URL='sqlite:///:memory:'),
             seconds=4,ceiling=1024,pass_fds=(r,))
    finally:os.close(r)
    assert status['exit_code']==2 and status['reason'] is None
    assert json.loads(data)['failure_reason']=='OWNER_BINDING'
    assert b'SYNTHETIC_HIDDEN_PASSWORD' not in data and b'Traceback' not in data


@pytest.mark.parametrize('kind',['known','unknown','oversize-result'])
def test_child_failure_handler_uses_safe_envelope(monkeypatch,capsys,kind):
    r,w=os.pipe();os.write(w,b'{}');os.close(w)
    monkeypatch.setattr(client,'loaded',lambda *_:{})
    def worker(*_):
        if kind=='oversize-result':return {'value':'SENSITIVE_RESULT'*3000}
        if kind=='known':raise Denied('VAULT_BINDING_CHANGED')
        raise RuntimeError('password=SENSITIVE_EXCEPTION')
    monkeypatch.setattr(client,'worker',worker)
    assert client.main(['--child','--secrets-fd',str(r),'--phase','close','--binding','unused','--binding-sha256','unused'])==2
    out=capsys.readouterr()
    assert not out.err and 'SENSITIVE' not in out.out
    assert json.loads(out.out)['failure_reason']==dict(known='VAULT_BINDING_CHANGED',unknown='UNKNOWN_FAILURE',**{'oversize-result':'RESULT_BOUND'})[kind]
    assert len(out.out.encode())<=1024


def test_parent_binding_refusal_preserves_known_reason_before_hidden_input(monkeypatch,capsys):
    monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
    monkeypatch.setattr(client,'loaded',lambda *_:{})
    monkeypatch.setattr(client,'hidden',lambda *_:pytest.fail('no hidden prompt for invalid binding'))
    assert client.main(['--phase','activate','--binding','unused','--binding-sha256','unused'])==2
    assert json.loads(capsys.readouterr().out)['failure_reason']=='OWNER_BINDING'


def test_parent_unknown_setup_failure_is_fixed_and_does_not_print_traceback(monkeypatch,capsys):
    monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
    def loaded(*_):raise OSError('SENSITIVE_SETUP_VALUE')
    monkeypatch.setattr(client,'loaded',loaded)
    assert client.main(['--phase','close','--binding','unused','--binding-sha256','unused'])==2
    result=capsys.readouterr()
    assert not result.err and 'SENSITIVE' not in result.out and 'Traceback' not in result.out
    assert json.loads(result.out)['failure_reason']=='UNKNOWN_FAILURE'
    assert json.loads(result.out)['phase']=='close'


def test_invalid_cli_value_is_not_echoed_and_no_phase_is_guessed(capsys):
    assert client.main(['--phase','password=SENSITIVE_ARGUMENT'])==2
    result=capsys.readouterr()
    assert not result.err and 'SENSITIVE' not in result.out
    assert json.loads(result.out)['failure_reason']=='ARGUMENTS_REFUSED'
    assert json.loads(result.out)['phase']=='UNKNOWN_PHASE'


def test_interactive_phase_retained_for_setup_failure(monkeypatch,capsys):
    monkeypatch.setattr(client.sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(client.sys.stderr,'isatty',lambda:True)
    values=iter(['close','unused','unused'])
    monkeypatch.setattr('builtins.input',lambda *_:next(values))
    def loaded(*_):raise OSError('SENSITIVE_INTERACTIVE_VALUE')
    monkeypatch.setattr(client,'loaded',loaded)
    assert client.main([])==2
    result=capsys.readouterr()
    assert not result.err and 'SENSITIVE' not in result.out
    assert json.loads(result.out)['phase']=='close'
    assert json.loads(result.out)['failure_reason']=='UNKNOWN_FAILURE'
