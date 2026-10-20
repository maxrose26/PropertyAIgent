"""Hidden-input pre-check for the observation successor: an invalid value exits with a fixed code BEFORE anything is consumed; a valid value is handed once, in memory, to the existing path; nothing secret is
ever written, printed or exported. Offline."""
import json
import re
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from verification.ingestion_storage import operational_runner as orr

GOOD='postgresql://postgres.zcikcfgpblzuzpanpdqd:SECRETVALUE123@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'
SECRET='SECRETVALUE123'


def reader_for(value):
    return lambda:value


# ---------------------------------------------------------------- the pre-check itself
@pytest.mark.parametrize('value,code',[
    ('','ROUTE_MALFORMED_INPUT'),
    ('not a url at all SECRETVALUE123','ROUTE_MALFORMED_INPUT'),
    ('x'*9000,'ROUTE_MALFORMED_INPUT'),
    ('postgresql://postgres.zcikcfgpblzuzpanpdqd:SECRETVALUE123@other-host.example.com:5432/postgres','ROUTE_HOST_MISMATCH'),
    ('postgresql://postgres.zcikcfgpblzuzpanpdqd:SECRETVALUE123@aws-0-eu-west-2.pooler.supabase.com:6543/postgres','ROUTE_PORT_MISMATCH'),
    ('postgresql://postgres.zcikcfgpblzuzpanpdqd:SECRETVALUE123@aws-0-eu-west-2.pooler.supabase.com:5432/other','ROUTE_DATABASE_MISMATCH'),
    ('postgresql://wrong.user:SECRETVALUE123@aws-0-eu-west-2.pooler.supabase.com:5432/postgres','ROUTE_USERNAME_MISMATCH'),
    ('postgresql://postgres.zcikcfgpblzuzpanpdqd:SECRETVALUE123@aws-0-eu-west-2.pooler.supabase.com:5432/postgres?sslmode=disable','ROUTE_QUERY_FORBIDDEN'),
])
def test_an_invalid_value_exits_with_a_fixed_code_and_never_echoes_the_value(value,code,capsys):
    with pytest.raises(SystemExit) as caught:orr.observer_precheck_input(reader_for(value))
    assert caught.value.code=='INPUT_REJECTED_NOT_CONSUMED:'+code
    out=capsys.readouterr();assert SECRET not in out.out+out.err+str(caught.value.code)+repr(caught.value)
    assert re.fullmatch('INPUT_REJECTED_NOT_CONSUMED:[A-Z_]+',caught.value.code)      # a fixed code only


def test_a_password_less_route_is_refused():
    with pytest.raises(SystemExit) as caught:orr.observer_precheck_input(reader_for('postgresql://postgres.zcikcfgpblzuzpanpdqd@aws-0-eu-west-2.pooler.supabase.com:5432/postgres'))
    assert caught.value.code=='INPUT_REJECTED_NOT_CONSUMED:PASSWORD_ABSENT'


def test_an_unreadable_prompt_exits_without_consuming_and_the_timer_is_disarmed():
    def failing():raise EOFError('no terminal SECRETVALUE123')
    with pytest.raises(SystemExit) as caught:orr.observer_precheck_input(failing)
    assert caught.value.code=='INPUT_NOT_READ_NOT_CONSUMED' and SECRET not in repr(caught.value)
    assert signal.getitimer(signal.ITIMER_REAL)[0]==0


def test_a_prompt_that_outlasts_its_bound_is_stopped():
    import time
    def hang():time.sleep(5)
    began=time.monotonic()
    with pytest.raises(SystemExit) as caught:orr.observer_precheck_input(hang,seconds=0.2)
    assert caught.value.code=='INPUT_NOT_READ_NOT_CONSUMED' and time.monotonic()-began<2 and signal.getitimer(signal.ITIMER_REAL)[0]==0


def test_a_valid_value_is_returned_unchanged_with_its_duration_and_the_timer_is_disarmed():
    value,seconds=orr.observer_precheck_input(reader_for(GOOD))
    assert value==GOOD and 0<=seconds<5 and signal.getitimer(signal.ITIMER_REAL)[0]==0


def test_the_precheck_uses_the_existing_route_validator_not_a_copy():
    import verification.discovery.route_validation as rv
    source=Path(orr.__file__).read_text()
    assert 'from verification.discovery.route_validation import validate_route,RouteRejection' in source and rv.validate_route.__module__=='verification.discovery.route_validation'


# ---------------------------------------------------------------- main(): non-consumption and handoff
class Harness:
    def __init__(self,tmp_path,monkeypatch,value):
        self.home=tmp_path/'home';self.home.mkdir();self.prompts=0;self.value=value;self.session_calls=[]
        monkeypatch.setattr(Path,'home',lambda:self.home)
        monkeypatch.setattr(sys,'platform','linux')
        monkeypatch.setattr(sys.stdin,'isatty',lambda:True,raising=False);monkeypatch.setattr(sys.stderr,'isatty',lambda:True,raising=False)
        registration=dict(mode=orr.OBSERVER_MODE,authority=orr.OBSERVER_AUTHORITY,expires_at='2099-01-01T00:00:00+00:00')
        monkeypatch.setattr(orr,'validate_registration',lambda body,sha:registration)
        reg=tmp_path/'registration.json';reg.write_text('{}')
        monkeypatch.setattr(sys,'argv',['x','--registration',str(reg),'--registration-sha256','a'*64])
        import verification.ingestion_storage.operational_memory as om
        monkeypatch.setattr(om,'OperationalMemory',lambda:SimpleNamespace(source=None,close=lambda:dict(owned_groups_removed=True,owned_survivors=0)))
        import verification.ingestion_storage.credential_mapping as cm
        def prompt():
            self.prompts+=1;return self.value
        monkeypatch.setattr(cm,'secure_migration_input',prompt)
        import verification.ingestion_storage.operational_outcome as oc
        def session(journal,expiry,reader,prepare,**kw):
            first=reader();second=reader()      # the handoff yields the value exactly once
            self.session_calls.append((first,second,kw.get('timing')))
            return dict(status='X',cleanup='CLOSED')
        monkeypatch.setattr(oc,'session',session)
        monkeypatch.setattr(orr,'prepare_runner',lambda *a,**k:None)
    @property
    def namespace(self):return self.home/'.local/state/propertyaigent'/orr.OBSERVER_STATE


def test_main_refuses_malformed_input_without_creating_the_namespace_or_consuming(tmp_path,monkeypatch,capsys):
    h=Harness(tmp_path,monkeypatch,'garbled SECRETVALUE123 not a url')
    with pytest.raises(SystemExit) as caught:orr.main()
    assert caught.value.code=='INPUT_REJECTED_NOT_CONSUMED:ROUTE_MALFORMED_INPUT'
    assert h.prompts==1 and not h.namespace.exists() and h.session_calls==[]
    base=h.home/'.local/state/propertyaigent'
    assert not base.exists() or not any(base.iterdir())      # no journal, no state of any kind
    out=capsys.readouterr();assert SECRET not in out.out+out.err


def test_a_refused_value_leaves_the_registration_usable_for_a_second_start(tmp_path,monkeypatch):
    h=Harness(tmp_path,monkeypatch,'bad')
    with pytest.raises(SystemExit):orr.main()
    h.value=GOOD
    with pytest.raises(SystemExit) as caught:orr.main()
    assert caught.value.code==0 and h.namespace.exists()      # the second start consumed it, and only now


def test_main_hands_a_valid_value_to_the_existing_path_once_and_asks_once(tmp_path,monkeypatch,capsys):
    h=Harness(tmp_path,monkeypatch,GOOD)
    with pytest.raises(SystemExit) as caught:orr.main()
    assert caught.value.code==0
    assert h.prompts==1      # asked exactly once
    first,second,timing=h.session_calls[0]
    assert first==GOOD and second is None and timing==orr.OBSERVER_TIMING      # handed once, then forgotten; unchanged numerical limits
    assert h.namespace.exists()
    events=[json.loads(l) for l in (h.namespace/'events.jsonl').read_text().splitlines()]
    assert [e['event'] for e in events][:2]==['consumed','hidden_input_prechecked'] and events[1]['payload']['value_exported'] is False
    everything=(h.namespace/'events.jsonl').read_text()+capsys.readouterr().out
    for path in h.home.rglob('*'):
        if path.is_file():everything+=path.read_text(errors='replace')
    assert SECRET not in everything and GOOD not in everything      # nowhere on disk, in the audit or in the output


def test_the_value_is_never_an_argument_or_environment_variable(tmp_path,monkeypatch):
    h=Harness(tmp_path,monkeypatch,GOOD)
    with pytest.raises(SystemExit):orr.main()
    import os
    assert SECRET not in ' '.join(sys.argv) and not any(SECRET in v for v in os.environ.values())


def test_other_modes_keep_their_prompt_inside_the_session(tmp_path,monkeypatch):
    registration=dict(mode=orr.PIPELINE_MODE,authority=orr.PIPELINE_AUTHORITY,expires_at='2099-01-01T00:00:00+00:00')
    h=Harness(tmp_path,monkeypatch,'ignored')
    monkeypatch.setattr(orr,'validate_registration',lambda body,sha:registration)
    with pytest.raises(SystemExit):orr.main()
    first,second,_=h.session_calls[0]
    assert first=='ignored' and second=='ignored'      # the session received the ORIGINAL prompt function (the stub session called it twice itself): no handoff reader for any other mode
    events=[json.loads(l)['event'] for l in (h.home/'.local/state/propertyaigent'/orr.PIPELINE_STATE/'events.jsonl').read_text().splitlines()]
    assert 'hidden_input_prechecked' not in events and events[0]=='consumed'      # no pre-check, and the registration is consumed before the prompt exactly as before


# ---------------------------------------------------------------- the successor namespace
def test_the_successor_has_fresh_names_and_binds_the_consumed_attempt():
    assert orr.OBSERVER_AUTHORITY.endswith('SUCCESSOR_2_ONCE_20261021') and 'successor-2' in orr.OBSERVER_STATE
    consumed=orr.OBSERVER_PREDECESSOR['consumed_observation_attempt']
    assert consumed['authority']!=orr.OBSERVER_AUTHORITY and consumed['state_directory']!=orr.OBSERVER_STATE
    assert consumed['registration_sha256']=='da5dce7f31b389c4661a2918464c83dd65d8c2829a138f51dfa42089a266d99f'
    assert consumed['events_sha256'].startswith('842139208adb') and consumed['final_result_sha256'].startswith('7505156e6c45')
    assert 'UNOBSERVED' in consumed['outcome']      # the cause of the first rejection is not attributed to anyone or anything


def test_the_owner_script_checks_the_consumed_audit_and_uses_the_successor_names():
    text=(Path(__file__).resolve().parents[1]/'docs/design/ingestion-control-observation-20261021/owner-run.sh').read_text()
    assert 'operational-control-observation-successor-2-registration-20261021.json' in text and 'STATE_DIRECTORY=operational-control-observation-successor-2-once-20261021' in text
    assert 'CONSUMED_DIRECTORY=operational-control-observation-once-20261021' in text and '842139208adb04e180e2776790f8111216510277d9c433cbea7a1ebf3c0107a4' in text
    assert 'you are asked once' in text and 'consumes nothing' in text and 'gh ' not in text.replace('# ','')
    assert 'test ! -e "$STATE_ROOT/$STATE_DIRECTORY"' in text


def test_the_observation_statements_and_limits_are_unchanged():
    assert orr.OBSERVER_OWNER_LIMITS==dict(connections=(1,1),commands=(12,12,12))
    assert orr.OBSERVER_TIMING==dict(input_seconds=120,active_seconds=30,work_seconds=24,diagnostic_seconds=3,report_seconds=2,outer_seconds=180)
    from verification.ingestion_storage import operational_owner as oo
    assert oo.Owner.OBSERVER_MAX_STATEMENTS==12 and oo.Owner.OBSERVER_MAX_DB_ACTIVE_SECONDS==20


# ---------------------------------------------------------------- review additions
def test_the_core_limit_is_zero_and_the_memory_scope_exists_before_the_prompt(tmp_path,monkeypatch):
    order=[]
    h=Harness(tmp_path,monkeypatch,GOOD)
    import resource
    real_setrlimit=resource.setrlimit
    monkeypatch.setattr(resource,'setrlimit',lambda which,limits:(order.append(('setrlimit',which,limits)),real_setrlimit(which,limits))[1])
    import verification.ingestion_storage.operational_memory as om
    original_memory=om.OperationalMemory
    monkeypatch.setattr(om,'OperationalMemory',lambda:(order.append(('memory',)),original_memory())[1])
    import verification.ingestion_storage.credential_mapping as cm
    original_prompt=cm.secure_migration_input
    monkeypatch.setattr(cm,'secure_migration_input',lambda:(order.append(('prompt',)),original_prompt())[1])
    with pytest.raises(SystemExit):orr.main()
    kinds=[o[0] if o[0]!='setrlimit' else ('core' if o[1]==resource.RLIMIT_CORE and o[2]==(0,0) else 'other') for o in order]
    assert kinds.index('memory')<kinds.index('core')<kinds.index('prompt')      # scope first, then the core limit, then the single prompt


def test_the_real_session_accepts_the_one_shot_reader_and_the_audit_stays_truthful(tmp_path):
    from verification.ingestion_storage.operational_outcome import session
    from verification.ingestion_storage.operational_journal import Journal
    journal=Journal(tmp_path/'j');box=[GOOD]
    def reader():
        value,box[0]=box[0],None;return value
    seen=[]
    class Worker:
        def execute(self):return dict(status='CONTROL_OBSERVED_NO_COMMITTED_MUTATION',cleanup='CLOSED')
        def failed(self,exc):return dict(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN')
    def prepare(raw,started):
        seen.append(raw);return Worker()
    result=session(journal,'2099-01-01T00:00:00+00:00',reader,prepare,timing=orr.OBSERVER_TIMING,output=lambda *a,**k:None)
    assert seen==[GOOD] and result['status']=='CONTROL_OBSERVED_NO_COMMITTED_MUTATION' and box==[None]
    events=[json.loads(l) for l in (tmp_path/'j'/'events.jsonl').read_text().splitlines()]
    done=[e for e in events if e['event']=='credential_input_completed'][0]
    assert done['payload']['elapsed_seconds']<1      # the session saw an immediate reader; the real prompt time is in hidden_input_prechecked.seconds
    assert SECRET not in (tmp_path/'j'/'events.jsonl').read_text()
