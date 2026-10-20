"""Control observation (specification 032 section 10): one connection, a fixed projection of the control record, nothing committed, no authority, no source request, no GitHub request. Offline."""
import json
import re
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path

import pytest

from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_publication import GitHub,Uncertain

NOW=1_800_000_000.0
STOP=oo.STOP


def control():
    def grant(expires,keys=3):
        return dict(keys=['k%d'%i for i in range(keys)],expires_at=expires,source_calls=1,writes=0,login='ingestion_worker_login',effect_login='ingestion_effect_login',bindings={'k0':{'secret-looking':'binding'}},
                    execution_binding=dict(revision='a'*40,workflow_sha256='b'*64,manifest_sha256='c'*64))
    def exception(authority,g,expires,gen=1):
        return dict(authority=authority,transport='REQUESTS_IDOX',grant_binding={k:v for k,v in g.items() if k not in ('source_calls','writes')},expires_at=expires,hard_stop_generation=gen)
    g1,g2,g3=grant(NOW-10),grant(0),grant(NOW+600)
    return dict(global_stop=STOP,manual_stop='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE',last_hard_stop='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE',hard_stop_generation=2,council_deferred_until={'bolton':0},
                grants={'OLD':g1,'REVOKED':g2,'LIVE':g3},bolton_exceptions={'OLD':exception('OLD',g1,NOW-10),'REVOKED':exception('REVOKED',g2,0),'LIVE':dict(exception('LIVE',g3,NOW+600),grant_binding={'tampered':True})})


class Cursor:
    def __init__(self,rows):self.rows=rows;self.description=[('x',)] if rows is not None else None;self.pgresult=None
    def fetchall(self):return self.rows or []


class FakeAdmin:
    """Scripted connection: records every statement; refuses COMMIT and anything unscripted."""
    def __init__(self,ctl,*,capability=(False,False),identity=('postgres','postgres',False,True,True,True)):
        self.ctl=ctl;self.statements=[];self.capability=capability;self.identity=identity;self.closed=False;self.in_tx=False
    def execute(self,statement,params=None):
        text=' '.join(str(statement).split());self.statements.append(text)
        if text.startswith('SELECT current_user,session_user'):return Cursor([self.identity])
        if text=='BEGIN':self.in_tx=True;return Cursor(None)
        if text.startswith('GRANT ingestion_storage_owner TO CURRENT_USER'):assert self.in_tx;return Cursor(None)
        if text.startswith('SELECT outcome::jsonb'):assert self.in_tx;return Cursor([(deepcopy(self.ctl),NOW)])
        if text=='ROLLBACK':self.in_tx=False;return Cursor(None)
        if text.startswith('SELECT pg_has_role'):assert not self.in_tx;return Cursor([self.capability])
        raise AssertionError('unscripted statement: '+text)
    def close(self):self.closed=True


def owner_for(db,events):
    return oo.Owner(lambda:db,lambda e,p=None:events.append((e,p)),lambda:None,identity='postgres',expiry=datetime.now(timezone.utc)+timedelta(minutes=20),bindings={},limits=orr.OBSERVER_OWNER_LIMITS)


# ---------------------------------------------------------------- the projection
def test_the_projection_names_identities_and_expiry_states_and_nothing_else():
    p=oo.Owner.project_control(control(),NOW)
    assert (p['hard_stop_generation'],p['manual_stop'],p['last_hard_stop'],p['global_stop'])==(2,'IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE','IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE',STOP)
    assert {g['authority']:g['state'] for g in p['grants']}=={'LIVE':'UNEXPIRED','OLD':'EXPIRED','REVOKED':'REVOKED_ZERO'}
    assert {e['authority']:(e['state'],e['grant_binding_matches']) for e in p['bolton_exceptions']}=={'OLD':('EXPIRED',True),'REVOKED':('REVOKED_ZERO',True),'LIVE':('UNEXPIRED',False)}
    assert p['counts']==dict(grants=3,grants_unexpired=1,exceptions=3,exceptions_unexpired=1)
    dumped=json.dumps(p)
    for forbidden in ('secret-looking','tampered','"keys"','k0','workflow_sha256','manifest_sha256'):assert forbidden not in dumped      # no binding content and no key list
    assert re.fullmatch('[0-9a-f]{64}',p['stop_state_sha256']) and re.fullmatch('[0-9a-f]{64}',p['control_sha256'])
    assert p['stop_state_sha256']!=oo.Owner.project_control(dict(control(),hard_stop_generation=1),NOW)['stop_state_sha256']      # the stop digest binds the generation
    same_stop_other_grants=dict(control(),grants={})
    assert oo.Owner.project_control(same_stop_other_grants,NOW)['stop_state_sha256']==p['stop_state_sha256'] and oo.Owner.project_control(same_stop_other_grants,NOW)['control_sha256']!=p['control_sha256']


def test_an_unreadable_expiry_is_reported_as_such_never_guessed():
    c=control();c['grants']['LIVE']['expires_at']='tomorrow'
    assert {g['authority']:g['state'] for g in oo.Owner.project_control(c,NOW)['grants']}['LIVE']=='UNREADABLE'
    with pytest.raises(ValueError):oo.Owner.project_control([],NOW)
    with pytest.raises(ValueError):oo.Owner.project_control(dict(control(),grants=[]),NOW)


# ---------------------------------------------------------------- the observation
def test_the_observation_is_six_statements_on_one_connection_and_commits_nothing():
    db=FakeAdmin(control());events=[]
    o=owner_for(db,events)
    record=o.control_observation()
    assert len(db.statements)==6 and record['statements']==6 and o.connections==1 and o.opened==1 and o.closed==1 and db.closed
    assert db.statements[1]=='BEGIN' and db.statements[2].startswith('GRANT ingestion_storage_owner') and db.statements[4]=='ROLLBACK' and not any(s.startswith(('COMMIT','UPDATE','INSERT','DELETE','CREATE','ALTER','REVOKE')) for s in db.statements)
    assert record['committed_writes']==0 and record['transient_owner_capability']=='ROLLED_BACK_AND_READ_BACK_ABSENT' and record['query_text_read'] is False and record['password_values_read'] is False
    assert [e for e,_ in events].count('control_observation')==1
    assert record['projection']['hard_stop_generation']==2 and 'outcome' not in json.dumps(record)


def test_a_remaining_capability_or_a_wrong_identity_is_a_stop():
    with pytest.raises(Uncertain,match='TEMPORARY_OWNER_CAPABILITY_REMAINS'):owner_for(FakeAdmin(control(),capability=(True,False)),[]).control_observation()
    with pytest.raises(ValueError,match='MIGRATION_IDENTITY'):owner_for(FakeAdmin(control(),identity=('other','other',False,True,True,True)),[]).control_observation()
    with pytest.raises(ValueError,match='MIGRATION_IDENTITY'):owner_for(FakeAdmin(control(),identity=('postgres','postgres',True,True,True,True)),[]).control_observation()


def test_the_limits_are_enforced_by_the_owner_itself():
    assert orr.OBSERVER_OWNER_LIMITS==dict(connections=(1,1),commands=(12,12,12))
    o=owner_for(FakeAdmin(control()),[]);o.control_observation()
    with pytest.raises(ValueError,match='ADMIN_CONNECTION_BOUND'):o.control_observation()      # a second connection is refused
    o2=owner_for(FakeAdmin(control()),[]);o2.commands=7
    with pytest.raises(ValueError,match='ADMIN_COMMAND_BOUND'):o2.control_observation()      # the 12-statement ceiling is not exceeded
    o3=owner_for(FakeAdmin(control()),[]);o3.connection_active=0
    original=o3.q
    def slow(c,statement,params=None,*,effect=False):
        out=original(c,statement,params,effect=effect);o3.connection_active+=21;return out
    o3.q=slow
    with pytest.raises(Uncertain,match='OBSERVER_DB_ACTIVE_BOUND'):o3.control_observation()


# ---------------------------------------------------------------- the runner mode
def registration(**over):
    base=dict(mode=orr.OBSERVER_MODE,authority=orr.OBSERVER_AUTHORITY,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat(),revision='a'*40,tree='d'*40,controller_sha256='b'*64,manifest_sha256='c'*64,evidence_head='1'*40,
              evidence_directory='docs/design/ingestion-operational-execution-control-observation-20261021',hashes={},ca_sha256='e'*64)
    base.update(over);return base


def runner_for(tmp_path,db):
    holder={}
    journal=Journal(tmp_path/'j')
    github=GitHub(journal.emit,lambda:holder['r'].check(),bound=0)
    r=orr.Runner(registration(),journal,lambda:db,source_reader=lambda row:(_ for _ in ()).throw(AssertionError('no source request')),github=github,url_factory=None,identity='postgres')
    holder['r']=r;return r


def test_the_mode_issues_nothing_and_closes(tmp_path):
    db=FakeAdmin(control());r=runner_for(tmp_path,db)
    assert r.observer_mode and r.owner.apply_policy is False and r.deadlines==orr.OBSERVER_DEADLINES
    result=r.execute()
    assert result['status']=='CONTROL_OBSERVED_NO_COMMITTED_MUTATION' and result['cleanup']=='CLOSED' and result['access']=='NO_AUTHORITY_ISSUED_STANDING_CREDENTIALS_UNCHANGED'
    assert (result['source_observations_attempted'],result['execution_grants_created'],result['application_writes'],result['committed_writes'],result['github_requests'])==(0,0,0,0,0)
    assert result['observation']['projection']['hard_stop_generation']==2


def test_a_failure_reports_and_closes_without_any_invalidation_teardown_or_github_call(tmp_path):
    db=FakeAdmin(control(),capability=(True,True));r=runner_for(tmp_path,db)
    result=r.execute()
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['stop_reason']=='TEMPORARY_OWNER_CAPABILITY_REMAINS' and result['authority_invalidation']=='NOT_REQUIRED_NO_AUTHORITY'
    assert result['committed_writes']==0 and result['source_observations_attempted']==0
    assert len(db.statements)==6      # no diagnostics query, no teardown, no invalidation: the failure path never touches the database again
    with pytest.raises(ValueError,match='GITHUB_REQUEST_BOUND'):r.github.call('GET','x')      # not a single GitHub request is admitted in this mode


def test_the_timing_constants_keep_the_session_invariants_and_the_stated_limits():
    t=orr.OBSERVER_TIMING;d=orr.OBSERVER_DEADLINES
    assert t['active_seconds']==30 and t['input_seconds']==120      # 30 supervised-active seconds after the hidden input
    assert d['job']+d['diagnostic_window']<=t['work_seconds'] and t['work_seconds']+d['diagnostic_window']<=d['diagnostic_total']<=t['active_seconds']-t['report_seconds']
    assert d['admin_pre']<d['admin_total']<d['admin_diagnostic']
    ceiling=3+orr.OBSERVER_STATEMENT_SECONDS+2+1      # connect + last statement + cancel + close, when no new statement starts after admin_pre
    assert d['admin_pre']+0<=8 and ceiling<=oo.Owner.OBSERVER_MAX_DB_ACTIVE_SECONDS and orr.OBSERVER_STATEMENT_SECONDS<oo.ADMIN_STATEMENT_HARD_SECONDS
    assert oo.Owner.OBSERVER_MAX_DB_ACTIVE_SECONDS==20 and oo.Owner.OBSERVER_MAX_STATEMENTS==12
    assert t['input_seconds']+t['active_seconds']+30>=t['outer_seconds'] and orr.OBSERVER_BACKSTOP_SECONDS>t['outer_seconds']


# ---------------------------------------------------------------- the registration binding
def test_the_registration_validator_binds_the_observation_exactly():
    base=json.loads((Path(__file__).resolve().parents[1]/'docs/design/ingestion-control-observation-20261021/base_constants.json').read_text())
    carried={k:v for k,v in base.items() if not k.startswith('_')}
    good=dict(carried,mode=orr.OBSERVER_MODE,authority=orr.OBSERVER_AUTHORITY,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).replace(microsecond=0).isoformat(),revision='a'*40,tree='b'*40,hashes={},controller_sha256='c'*64,
              ca_sha256='d'*64,manifest_sha256='e'*64,evidence_head='1'*40,evidence_directory='docs/design/ingestion-operational-execution-control-observation-20261021',predecessor=orr.OBSERVER_PREDECESSOR,
              state_directory=orr.OBSERVER_STATE,execution_authority='NONE',risk_application='THIS_FINITE_CONTROL_OBSERVATION_ONLY',
              owner_limits=dict(connections=list(orr.OBSERVER_OWNER_LIMITS['connections']),commands=list(orr.OBSERVER_OWNER_LIMITS['commands'])),
              observation=dict(statements=12,database_active_seconds=20,supervised_active_seconds=30,connections=1),
              execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=orr.OBSERVER_STATE),approval='OWNER_CONTROL_OBSERVATION_20261021')
    import hashlib
    def validate(r):
        body=json.dumps(r,sort_keys=True,indent=1).encode();return orr.validate_registration(body,hashlib.sha256(body).hexdigest())
    with pytest.raises(ValueError,match='CLEAN_REVIEWED_CHECKOUT'):validate(good)      # every binding passes; only the (deliberately wrong) checkout identity stops it
    for tamper in (dict(execution_authority='OWNER_GRANT_AND_EXCEPTION_FOR_THE_HOSTED_RESTRICTED_JOB'),dict(risk_application='THIS_FINITE_STABLE_PIPELINE_ONCE'),dict(state_directory='operational-stable-pipeline-once-20261020'),
                   dict(owner_limits=dict(connections=[2,2],commands=[12,12,12])),dict(owner_limits=dict(connections=[1,1],commands=[13,13,13])),dict(observation=dict(statements=24,database_active_seconds=20,supervised_active_seconds=30,connections=1)),
                   dict(predecessor=dict(orr.OBSERVER_PREDECESSOR,owner_events_sha256='0'*64)),dict(pipeline={'x':1}),dict(restricted_route='DIRECT')):
        with pytest.raises(ValueError,match='CONTROL_OBSERVATION_BINDING'):validate(dict(good,**tamper))
    with pytest.raises(ValueError,match='ORIGINAL_OPERATIONAL_EXPIRY'):validate(dict(good,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=45)).replace(microsecond=0).isoformat()))      # at most 30 minutes
    with pytest.raises(ValueError,match='EXACT_OPERATIONAL_APPROVAL_REQUIRED'):validate(dict(good,authority=orr.PIPELINE_AUTHORITY))


def test_the_observer_names_are_unused_by_every_consumed_mode():
    consumed={orr.PIPELINE_AUTHORITY,orr.PIPELINE_STATE}
    assert orr.OBSERVER_AUTHORITY not in consumed and orr.OBSERVER_STATE not in consumed and orr.OBSERVER_MODE not in (orr.PIPELINE_MODE,orr.STABLE_PROVISION_MODE,orr.STABLE_REVOKE_MODE)
    assert orr.OBSERVER_PREDECESSOR['consumed_run']['run_id']==39388007668


# ---------------------------------------------------------------- review fixes
def test_a_failure_after_the_grant_never_commits_and_the_connection_is_closed():
    class Failing(FakeAdmin):
        def execute(self,statement,params=None):
            text=' '.join(str(statement).split())
            if text.startswith('SELECT outcome::jsonb'):self.statements.append(text);raise RuntimeError('connection lost')
            return super().execute(statement,params)
    db=Failing(control());o=owner_for(db,[])
    with pytest.raises(RuntimeError):o.control_observation()
    assert db.closed and not any(s.startswith(('COMMIT','UPDATE','INSERT','CREATE','ALTER','DELETE')) for s in db.statements) and db.in_tx      # the open transaction is aborted by the disconnect, never committed


def test_the_statement_deadline_is_the_observer_s_own_and_other_modes_keep_twelve_seconds(tmp_path):
    r=runner_for(tmp_path,FakeAdmin(control()))
    assert r.owner.statement_hard_seconds==orr.OBSERVER_STATEMENT_SECONDS==4 and oo.Owner.statement_hard_seconds is None and oo.ADMIN_STATEMENT_HARD_SECONDS==12
    result=r.execute()
    assert result['status']=='CONTROL_OBSERVED_NO_COMMITTED_MUTATION'


def test_the_failure_result_says_the_capability_could_not_be_read_back_after_a_failure(tmp_path):
    result=runner_for(tmp_path,FakeAdmin(control(),capability=(True,True))).execute()
    assert 'UNVERIFIED' in result['transient_owner_capability'] and 'NOT_READ_BACK' in result['transient_owner_capability']


def test_pathological_values_are_bounded_or_withheld():
    c=control();c['manual_stop']='X'*5000;c['global_stop']={'reason':'Y'*5000};c['grants']['LIVE']['expires_at']='tomorrow';c['grants']['LIVE']['login']='L'*500;c['grants']['LIVE']['source_calls']='many'
    c['grants']['LIVE']['execution_binding']={'revision':'not-a-hash'};c['council_deferred_until']={str(i):i for i in range(500)}
    p=oo.Owner.project_control(c,NOW)
    assert len(p['manual_stop'])==512 and p['global_stop']=='OVERSIZE_NOT_EXPORTED' and p['council_deferred_until']=='OVERSIZE_NOT_EXPORTED'
    live=[g for g in p['grants'] if g['authority']=='LIVE'][0]
    assert live['state']=='UNREADABLE' and live['expires_at'] is None and len(live['login'])==100 and live['source_calls'] is None and live['execution_binding_revision'] is None
    assert len(json.dumps(p))<20000


def test_the_prepared_runner_gives_the_observer_a_zero_github_bound():
    source=Path(orr.__file__).read_text()
    assert "dict(bound=0) if r.get('mode')==OBSERVER_MODE" in source
