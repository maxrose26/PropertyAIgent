"""Revocation-only invalidation of this execution's authorities, and the measured administrative budget of the owner lifecycle, against a SCRIPTED administrative connection (no database).

The scripted connection emulates exactly the statements the owner issues, including jsonb_set path updates, transactions (BEGIN/COMMIT/ROLLBACK) and RETURNING, so the tests exercise the real Owner code
and count its real statements. The disposable PG17 rehearsal repeats the lifecycle against a real server."""
import json,re
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import pytest
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage.operational_publication import Uncertain

BINDINGS=dict(revision='a'*40,workflow_sha256='b'*64,manifest_sha256='c'*64)
CAPTURE='AUTHORISE_X_CAPTURE';SCREEN='AUTHORISE_X_SCREEN'


class Cursor:
    def __init__(self,rows):
        self.rows=rows;self.description=[('x',)] if rows is not None else None;self.pgresult=None
    def fetchall(self):return self.rows


class ScriptedAdmin:
    """Emulates the control row and the owner's statements. `committed` is durable state; `working` is the open transaction."""
    def __init__(self,control,*,fail_commit=False,corrupt_update=False,ignore_update=False):
        self.committed=deepcopy(control);self.working=None;self.statements=[];self.fail_commit=fail_commit;self.corrupt_update=corrupt_update;self.ignore_update=ignore_update;self.closed=False
        self.updates=0;self.commits=0;self.rollbacks=0
    def execute(self,statement,params=None):
        text=' '.join(str(statement).split());self.statements.append(text[:60])
        view=self.working if self.working is not None else self.committed
        if text=='BEGIN' or text=='BEGIN READ ONLY':self.working=deepcopy(self.committed);return Cursor(None)
        if text.startswith('GRANT ') or text.startswith('REVOKE '):return Cursor(None)
        if text=='ROLLBACK':self.working=None;self.rollbacks+=1;return Cursor(None)
        if text=='COMMIT':
            if self.fail_commit:raise RuntimeError('connection lost during COMMIT')
            self.committed=self.working;self.working=None;self.commits+=1;return Cursor(None)
        if text.startswith('SELECT pg_has_role'):return Cursor([(False,)*5] if 'has_schema_privilege' in text else [(False,False)])
        if text.startswith('SELECT outcome'):return Cursor([(deepcopy(view),)])
        if text.startswith('SELECT key,state,checkpoint'):return Cursor([(k,'COMPLETE',{}) for k in params[0]])
        if text.startswith('SELECT public.ingestion_register_bolton_exception'):
            exception=json.loads(params[0]);self.working['bolton_exceptions']=dict(self.working.get('bolton_exceptions',{}),**{exception['authority']:dict(exception,expires_at=self.working['grants'][exception['authority']]['expires_at'])});return Cursor([(1,)])
        if text.startswith('INSERT INTO public.ingestion_work_items'):self.working.setdefault('_items',[]).append(json.loads(params[0])['key']);return Cursor(None)
        if text.startswith('UPDATE public.ingestion_work_items') and 'RETURNING' in text:
            self.updates+=1
            paths=re.findall(r"ARRAY\['(grants|bolton_exceptions)',%s,'expires_at'\]",text)
            assert len(paths)==len(params)
            if not self.ignore_update:
                for (section,),authority in zip([(p,) for p in paths],params):
                    if authority in self.working.get(section,{}):self.working[section][authority]['expires_at']=0
            if self.corrupt_update:self.working['manual_stop']='SOMETHING_ELSE_CHANGED'
            return Cursor([(deepcopy(self.working),)])
        if text.startswith('UPDATE public.ingestion_work_items'):self.working=json.loads(params[0]);return Cursor(None)
        raise AssertionError('unscripted statement: '+text)
    def close(self):self.closed=True


def grant(authority,*,expires=9e9,binding=BINDINGS,source_calls=0):
    return dict(keys=['k'],expires_at=expires,source_calls=source_calls,writes=0,login='ingestion_worker_login',execution_binding=binding)


def exception_for(g,authority,*,expires=9e9):
    return dict(authority=authority,transport='REQUESTS_IDOX',grant_binding={k:v for k,v in g.items() if k not in ('source_calls','writes')},expires_at=expires,hard_stop_generation=1)


def control(*,generation=1,manual='STORAGE_TEST_STOP',global_stop=oo.STOP,extra=True):
    c=dict(global_stop=global_stop,manual_stop=manual,hard_stop_generation=generation,last_hard_stop='EARLIER',council_deferred_until={'bolton':0},grants={},bolton_exceptions={})
    for a in (CAPTURE,SCREEN):
        g=grant(a);c['grants'][a]=g;c['bolton_exceptions'][a]=exception_for(g,a)
    if extra:      # an unrelated, still-live authority and an expired earlier one: neither may be touched
        u=grant('OTHER_LIVE');c['grants']['OTHER_LIVE']=u;c['bolton_exceptions']['OTHER_LIVE']=exception_for(u,'OTHER_LIVE')
        c['grants']['OLD_EXPIRED']=grant('OLD_EXPIRED',expires=0)
    return c


def owner_for(db,authorities=(CAPTURE,SCREEN)):
    events=[]
    o=oo.Owner(lambda:db,lambda e,p=None:events.append((e,p)),lambda:None,identity='postgres',expiry=datetime.now(timezone.utc)+timedelta(hours=1),bindings=BINDINGS,limits=orr.PIPELINE_OWNER_LIMITS)
    o.authorities=list(authorities);o.tearing_down=True
    return o,events


def last(events,kind):
    return [p for e,p in events if e==kind][-1]


def only_ours_changed(before,after,ours=(CAPTURE,SCREEN)):
    expected=deepcopy(before)
    for a in ours:
        if a in expected['grants']:expected['grants'][a]['expires_at']=0
        if a in expected['bolton_exceptions']:expected['bolton_exceptions'][a]['expires_at']=0
    return after==expected


def test_only_the_expiry_of_this_executions_authorities_changes_and_the_revocation_is_confirmed_by_readback():
    before=control();db=ScriptedAdmin(before);o,events=owner_for(db)
    assert o.invalidate_authorities()=='ACKNOWLEDGED_READBACK'
    assert only_ours_changed(before,db.committed)
    assert db.committed['grants']['OTHER_LIVE']['expires_at']==9e9 and db.committed['bolton_exceptions']['OTHER_LIVE']['expires_at']==9e9 and db.committed['grants']['OLD_EXPIRED']['expires_at']==0
    assert len(db.statements)==12 and db.updates==1 and db.commits==1      # exactly the measured statements: lock, revoke, verify in the transaction, commit, readback
    assert o.invalidation=='ACKNOWLEDGED_READBACK' and last(events,'authorities_invalidated')['readback']=='CONFIRMED' and last(events,'authorities_invalidated')['revoked']==[CAPTURE,SCREEN]


@pytest.mark.parametrize('label,kwargs',[
    ('a newer generation',dict(generation=2)),
    ('the manual stop replaced by the fail-safe',dict(manual='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE',generation=2)),
    ('a changed manual stop',dict(manual='SOMETHING_NEWER')),
    ('a changed global stop',dict(global_stop={'reason':'A_NEWER_GLOBAL_STOP','run':'1'})),
    ('no global stop recorded',dict(global_stop=None))])
def test_revocation_never_depends_on_any_stop_state_and_preserves_the_newer_stop(label,kwargs):
    before=control(**kwargs);db=ScriptedAdmin(before);o,_=owner_for(db)
    assert o.invalidate_authorities()=='ACKNOWLEDGED_READBACK',label
    assert only_ours_changed(before,db.committed),label
    for field in ('global_stop','manual_stop','hard_stop_generation','last_hard_stop','council_deferred_until'):assert db.committed[field]==before[field],(label,field)      # the newer stop is preserved exactly


def test_an_authority_the_execution_did_not_register_is_never_touched():
    before=control();db=ScriptedAdmin(before);o,_=owner_for(db,authorities=(CAPTURE,))
    assert o.invalidate_authorities()=='ACKNOWLEDGED_READBACK'
    assert only_ours_changed(before,db.committed,ours=(CAPTURE,)) and db.committed['grants'][SCREEN]['expires_at']==9e9


def test_a_grant_whose_execution_binding_is_not_ours_is_refused_and_nothing_is_written():
    before=control();before['grants'][CAPTURE]['execution_binding']=dict(BINDINGS,revision='d'*40)
    db=ScriptedAdmin(before);o,events=owner_for(db,authorities=(CAPTURE,))
    assert o.invalidate_authorities()=='UNCERTAIN_RECONCILE'
    assert db.committed==before and db.updates==0 and last(events,'authority_invalidation_refused')['refused']==[CAPTURE]


def test_an_exception_whose_binding_does_not_correspond_to_its_grant_is_refused():
    before=control();before['bolton_exceptions'][CAPTURE]['grant_binding']['keys']=['different']
    db=ScriptedAdmin(before);o,events=owner_for(db,authorities=(CAPTURE,))
    assert o.invalidate_authorities()=='UNCERTAIN_RECONCILE' and db.committed==before and db.updates==0 and last(events,'authority_invalidation_refused')['refused']==[CAPTURE]


def test_a_verified_authority_is_still_revoked_when_another_is_refused():
    before=control();before['grants'][SCREEN]['execution_binding']=dict(BINDINGS,revision='d'*40)
    db=ScriptedAdmin(before);o,events=owner_for(db)
    assert o.invalidate_authorities()=='UNCERTAIN_RECONCILE'      # the refusal is reported for reconciliation...
    assert db.committed['grants'][CAPTURE]['expires_at']==0 and db.committed['grants'][SCREEN]['expires_at']==9e9      # ...but the verified one is ended and the refused one is untouched


def test_an_already_invalidated_authority_is_a_confirmed_no_op_without_a_write():
    before=control()
    for a in (CAPTURE,SCREEN):before['grants'][a]['expires_at']=0;before['bolton_exceptions'][a]['expires_at']=0
    db=ScriptedAdmin(before);o,events=owner_for(db)
    assert o.invalidate_authorities()=='ALREADY_INVALIDATED_READBACK'
    assert db.committed==before and db.updates==0 and db.commits==0 and db.rollbacks>=1


def test_an_authority_that_was_never_inserted_is_reported_absent_not_assumed_revoked():
    before=control()
    del before['grants'][CAPTURE];del before['bolton_exceptions'][CAPTURE]
    db=ScriptedAdmin(before);o,events=owner_for(db,authorities=(CAPTURE,))
    assert o.invalidate_authorities()=='ALREADY_INVALIDATED_READBACK' and last(events,'authorities_invalidated')['absent']==[CAPTURE] and db.committed==before


def test_an_unexpected_change_inside_the_transaction_is_rolled_back_and_never_committed():
    before=control();db=ScriptedAdmin(before,corrupt_update=True);o,events=owner_for(db)
    assert o.invalidate_authorities()=='UNCERTAIN_RECONCILE'
    assert db.committed==before and db.commits==0 and last(events,'authority_invalidation_uncertain')['stopped']=='INVALIDATION_UNEXPECTED_CHANGE'


def test_an_uncertain_commit_is_never_retried_and_is_reported_for_reconciliation_with_a_read_only_observation():
    before=control();db=ScriptedAdmin(before,fail_commit=True);o,events=owner_for(db)
    assert o.invalidate_authorities()=='UNCERTAIN_RECONCILE'
    assert db.updates==1 and o.effect_uncertain is True      # exactly one UPDATE: no blind retry
    payload=last(events,'authority_invalidation_uncertain')
    assert payload['stopped']=='ADMIN_EFFECT_UNCERTAIN' and payload['observation'] in ('NOT_REVOKED_OBSERVED','REVOKED_OBSERVED','UNOBSERVABLE')


def test_a_committed_revocation_that_the_readback_does_not_show_is_not_claimed_confirmed():
    before=control();db=ScriptedAdmin(before,ignore_update=True);o,events=owner_for(db)      # the UPDATE reports success but the row is unchanged
    assert o.invalidate_authorities()=='UNCERTAIN_RECONCILE'
    assert [e for e,_ in events if e in ('authority_invalidation_uncertain','authority_invalidation_unconfirmed')]


def test_a_prior_uncertain_administrative_effect_does_not_prevent_ending_the_authority():
    before=control();db=ScriptedAdmin(before);o,_=owner_for(db);o.effect_uncertain=True
    assert o.invalidate_authorities()=='ACKNOWLEDGED_READBACK' and only_ours_changed(before,db.committed) and o.effect_uncertain is True      # revocation cannot create authority; the run's closure stays uncertain


def test_no_authority_registered_means_nothing_is_read_or_written():
    db=ScriptedAdmin(control());o,_=owner_for(db,authorities=())
    assert o.invalidate_authorities()=='NOT_REQUIRED_NO_AUTHORITY' and db.statements==[]


# ------------------------------------------------------------------ the measured administrative budget of the owner lifecycle
def lifecycle_counts(batches=12):
    """Run the REAL Owner methods against the scripted connection and count their statements/connections. The fixed read-only readback is 9 statements (asserted by the disposable PG17 rehearsal)."""
    def fresh():
        db=ScriptedAdmin(dict(global_stop=oo.STOP,manual_stop='STORAGE_TEST_STOP',hard_stop_generation=1,grants={},bolton_exceptions={}));return db
    db=fresh();events=[]
    o=oo.Owner(lambda:db,lambda e,p=None:events.append(e),lambda:None,identity='postgres',expiry=datetime.now(timezone.utc)+timedelta(hours=1),bindings=BINDINGS,limits=dict(connections=(99,99),commands=(999,999,999)))
    o.expected_generation=1;o.grant_expiry=datetime.now(timezone.utc)+timedelta(minutes=55)
    counts={}
    def measure(label,call):
        before=(o.commands,o.connections);call();counts[label]=(o.commands-before[0],o.connections-before[1])
    root=oo.item(dict(subject=oo.SCOPE,task='DISCOVERY',contract=orr.CONTRACT,revision='c'*64),max_attempts=1)
    measure('register_capture',lambda:o.register([root],CAPTURE,capture_key=root['key'],source_calls=1))
    measure('read_capture',lambda:o.read_items([root['key']]))
    children=[oo.item(dict(subject=dict(kind='LISTING_BATCH',n=i),task='LISTING_METADATA',contract='listing-batch-v1',revision='r%d'%i)) for i in range(batches)]
    measure('register_screening',lambda:o.register(children,SCREEN,capture_key=root['key'],source_calls=0,prepared=[root]))
    measure('read_batches',lambda:o.read_items([c['key'] for c in children]))
    o.tearing_down=True
    measure('invalidate',o.invalidate_authorities)
    return counts


READBACK_STATEMENTS=9      # BEGIN READ ONLY, identity, control, roles, memberships, role settings, sessions, function inventory, ROLLBACK


def test_the_measured_lifecycle_fits_the_normal_teardown_and_failure_allowances_with_reserve():
    c=lifecycle_counts(batches=12)
    normal=READBACK_STATEMENTS+c['register_capture'][0]+c['read_capture'][0]+c['register_screening'][0]+c['read_batches'][0]
    through_end=normal+c['invalidate'][0]+READBACK_STATEMENTS
    connections=1+c['register_capture'][1]+c['read_capture'][1]+c['register_screening'][1]+c['read_batches'][1]+c['invalidate'][1]+1
    diagnostics=7      # Owner.diagnostics(): BEGIN READ ONLY, roles, memberships, sessions, control, (role config), ROLLBACK
    worst_failure=normal+c['invalidate'][0]+diagnostics      # a failure at the very end of the normal path, then the reserved invalidation and the diagnostics
    caps=orr.PIPELINE_OWNER_LIMITS
    print('MEASURED_OWNER_LIFECYCLE',json.dumps(dict(per_phase=c,readback=READBACK_STATEMENTS,normal=normal,through_end=through_end,worst_failure=worst_failure,connections=connections)))
    assert normal<=caps['commands'][0] and through_end<=caps['commands'][1] and worst_failure<=caps['commands'][2]      # every path fits its own allowance
    assert caps['commands'][0]-normal>=2 and caps['commands'][1]-through_end>=4 and caps['commands'][2]-worst_failure>=8      # with a reserve for invalidation and diagnostics, not an exact fit
    assert connections<=caps['connections'][0] and connections+3<=caps['connections'][1]      # the rehearsal measured 9 on a failure after the normal path (7 + the reserved invalidation + the diagnostics): the allowance keeps a reserve above it
    assert caps['commands'][0]<caps['commands'][1]<caps['commands'][2]


def test_the_old_placeholder_limit_would_have_been_exhausted_by_the_normal_path():
    c=lifecycle_counts(batches=12)
    normal=READBACK_STATEMENTS+c['register_capture'][0]+c['read_capture'][0]+c['register_screening'][0]+c['read_batches'][0]
    assert normal>48      # the reproduced command-limit exhaustion: the placeholder normal allowance of 48 cannot cover the lifecycle


def test_after_an_uncertain_commit_a_later_call_only_observes_and_never_writes_again():
    before=control();db=ScriptedAdmin(before,fail_commit=True);o,events=owner_for(db)
    assert o.invalidate_authorities()=='UNCERTAIN_RECONCILE' and db.updates==1 and o.commit_uncertain is True
    statements_after_first=len(db.statements)
    assert o.invalidate_authorities()=='UNCERTAIN_RECONCILE'      # the commit did not persist (the scripted server lost it): still unreconciled
    assert db.updates==1 and db.commits==0      # no second UPDATE, no second COMMIT
    assert last(events,'authority_invalidation_uncertain')['stopped']=='PRIOR_COMMIT_UNCERTAIN_OBSERVE_ONLY' and last(events,'authority_invalidation_uncertain')['observation']=='NOT_REVOKED_OBSERVED'
    assert len(db.statements)-statements_after_first==5      # one read-only observation: begin, capability grant, read, rollback, capability check
    persisted=ScriptedAdmin(control(),fail_commit=False);o2,_=owner_for(persisted);o2.commit_uncertain=True
    for a in (CAPTURE,SCREEN):persisted.committed['grants'][a]['expires_at']=0;persisted.committed['bolton_exceptions'][a]['expires_at']=0      # the earlier commit DID persist
    assert o2.invalidate_authorities()=='ALREADY_INVALIDATED_READBACK' and persisted.updates==0
