"""The teardown session policy and the bounded admin statement, against a disposable server that logs every statement (real sessions, real termination, real privilege differences).

Policy: disable first; bounded session reads; terminate at most two precisely identified restricted-login sessions ONLY with proven existing privileges; delete the temporary secrets
independently once DISABLED status is verified; extra, unidentifiable or unprivileged cases stay UNRESOLVED and are reported, never closed. No privilege is ever granted."""
import re,threading,time
from datetime import datetime,timezone,timedelta
import psycopg,pytest
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage.operational_owner import Owner,ROLES,SECRETS
from verification.ingestion_storage.operational_publication import Uncertain
from tests.test_ingestion_admin_connection_probe import cluster      # noqa: F401

WORKER='ingestion_worker_login';EFFECT='ingestion_effect_login'


def superuser(cluster):return psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user='postgres',autocommit=True)


class GitHubFake:
    def __init__(self):self.calls=[];self.present={'DATABASE_URL',*SECRETS.values()}
    def call(self,method,path,body=None):
        self.calls.append((method,path))
        if method=='DELETE':self.present.discard(path.rsplit('/',1)[1])
    def names(self):return set(self.present)


def setup(cluster,*,limit1=True,admin_name='postgres'):
    with superuser(cluster) as c:
        for r in ('admin_np',WORKER,EFFECT,'ingestion_worker','ingestion_effect_broker'):
            c.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename=%s',(r,));time.sleep(.05)
            c.execute(f'DROP OWNED BY {r}') if c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(r,)).fetchone() else None
            c.execute(f'DROP ROLE IF EXISTS {r}')
        if admin_name!='postgres':
            c.execute(f'CREATE ROLE {admin_name} LOGIN CREATEROLE')
            c.execute(f'GRANT SELECT(rolname,rolpassword) ON pg_catalog.pg_authid TO {admin_name}')      # the same column-level read the production migration identity holds
        creator=admin_name
    with psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user=creator,autocommit=True) as a:
        a.execute('CREATE ROLE ingestion_worker NOLOGIN');a.execute('CREATE ROLE ingestion_effect_broker NOLOGIN')
        extra=' CONNECTION LIMIT 1' if limit1 else ''
        a.execute(f'CREATE ROLE {WORKER} LOGIN{extra}');a.execute(f'CREATE ROLE {EFFECT} LOGIN{extra}')
        a.execute(f'GRANT ingestion_worker TO {WORKER} WITH INHERIT TRUE, SET FALSE');a.execute(f'GRANT ingestion_effect_broker TO {EFFECT} WITH INHERIT TRUE, SET FALSE')
    return creator


def make_owner(cluster,creator):
    events=[]
    owner=Owner(lambda:psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user=creator,autocommit=True),lambda e,p:events.append((e,p)),lambda:None,
                identity=creator,expiry=datetime.now(timezone.utc)+timedelta(minutes=10),bindings={})
    owner.sleep=lambda s:time.sleep(.05)
    owner.urls={WORKER:'u1',EFFECT:'u2'}
    return owner,events


def hold(cluster,role):return psycopg.connect(host='127.0.0.1',port=cluster.port,dbname='postgres',user=role,autocommit=True)


def alive(cluster,pid):
    with superuser(cluster) as c:return bool(c.execute('SELECT 1 FROM pg_stat_activity WHERE pid=%s',(pid,)).fetchone())


def role_state(cluster):
    with superuser(cluster) as c:
        return c.execute('SELECT rolname,rolcanlogin,rolpassword IS NULL FROM pg_authid WHERE rolname=ANY(%s) ORDER BY rolname',([WORKER,EFFECT],)).fetchall(),c.execute("SELECT count(*) FROM pg_auth_members WHERE member::regrole::text=ANY(%s)",([WORKER,EFFECT],)).fetchone()[0]


def test_no_session_disables_and_deletes_the_secrets(cluster):
    creator=setup(cluster);owner,events=make_owner(cluster,creator);gh=GitHubFake()
    owner.teardown(gh)
    assert role_state(cluster)==([(EFFECT,False,True),(WORKER,False,True)],0) and gh.names()=={'DATABASE_URL'} and owner.session_disposition=='NONE' and owner.urls=={} and owner.terminations==0


def test_a_session_that_leaves_during_the_bounded_wait_is_cleared_without_termination(cluster):
    creator=setup(cluster);held=hold(cluster,WORKER);owner,events=make_owner(cluster,creator);gh=GitHubFake()
    owner.sleep=lambda s:(held.close() if not held.closed else None,time.sleep(.1))[1]
    owner.teardown(gh)
    assert owner.session_disposition=='CLEARED_BY_WAIT' and owner.terminations==0 and gh.names()=={'DATABASE_URL'}


def test_a_surviving_session_is_terminated_exactly_when_privileges_are_proven(cluster):
    creator=setup(cluster);held=hold(cluster,WORKER);pid=held.info.backend_pid;owner,events=make_owner(cluster,creator);gh=GitHubFake()
    with superuser(cluster) as c:log_before=len(re.findall(r'.',cluster.log.read_text()))
    owner.teardown(gh)
    assert owner.session_disposition=='TERMINATED_VERIFIED_ABSENT' and owner.terminations==1 and not alive(cluster,pid) and gh.names()=={'DATABASE_URL'}
    terminations=[p for e,p in events if e=='session_termination'];assert len(terminations)==1 and terminations[0]['pid']==pid and terminations[0]['role']==WORKER and terminations[0]['acknowledged'] is True
    assert role_state(cluster)==([(EFFECT,False,True),(WORKER,False,True)],0)
    statements=[s for s in re.findall(r'(?:statement|execute [^:]*): (.*)',cluster.log.read_text())]
    assert not [s for s in statements if re.match(r'(GRANT|CREATE ROLE|ALTER ROLE [^N])',s.strip()) and ('pg_signal_backend' in s or 'pg_read_all_stats' in s)]      # no privilege is granted to make this possible


def test_without_the_privileges_nothing_is_terminated_and_the_secrets_are_still_removed(cluster):
    creator=setup(cluster,admin_name='admin_np');held=hold(cluster,WORKER);pid=held.info.backend_pid;owner,events=make_owner(cluster,creator);gh=GitHubFake()
    with pytest.raises(Uncertain,match='TEARDOWN_SESSIONS_UNRESOLVED'):owner.teardown(gh)
    assert owner.session_disposition=='UNRESOLVED_PRIVILEGE_NOT_PROVEN' and owner.terminations==0 and alive(cluster,pid)
    assert gh.names()=={'DATABASE_URL'} and role_state(cluster)==([(EFFECT,False,True),(WORKER,False,True)],0)            # disabled, secrets gone, the session reported unresolved
    held.close()


def test_more_than_two_sessions_are_not_terminated(cluster):
    creator=setup(cluster,limit1=False);helds=[hold(cluster,WORKER) for _ in range(3)];owner,events=make_owner(cluster,creator);gh=GitHubFake()
    with pytest.raises(Uncertain,match='TEARDOWN_SESSIONS_UNRESOLVED'):owner.teardown(gh)
    assert owner.session_disposition=='UNRESOLVED_EXTRA_OR_UNIDENTIFIABLE' and owner.terminations==0 and all(alive(cluster,h.info.backend_pid) for h in helds) and gh.names()=={'DATABASE_URL'}
    [h.close() for h in helds]


def test_at_most_two_terminations_and_a_signal_that_does_not_end_the_session_is_reported(cluster):
    creator=setup(cluster);a=hold(cluster,WORKER);b=hold(cluster,EFFECT);owner,events=make_owner(cluster,creator);gh=GitHubFake()
    owner.teardown(gh)
    assert owner.session_disposition=='TERMINATED_VERIFIED_ABSENT' and owner.terminations==2 and not alive(cluster,a.info.backend_pid) and not alive(cluster,b.info.backend_pid)
    creator=setup(cluster);held=hold(cluster,WORKER);owner,events=make_owner(cluster,creator);gh=GitHubFake()
    real=owner.q
    def no_effect(c,statement,params=None,*,effect=False):
        if statement==oo.TERMINATE_SQL:return [(False,)]                              # the server declines: not terminated
        return real(c,statement,params,effect=effect)
    owner.q=no_effect
    with pytest.raises(Uncertain,match='TEARDOWN_SESSIONS_UNRESOLVED'):owner.teardown(gh)
    assert owner.session_disposition=='TERMINATION_SIGNALLED_NOT_VERIFIED' and alive(cluster,held.info.backend_pid)
    held.close()


def test_roles_not_verified_disabled_never_delete_the_secrets(cluster):
    creator=setup(cluster);owner,events=make_owner(cluster,creator);gh=GitHubFake()
    real=owner.q
    def lie(c,statement,params=None,*,effect=False):
        rows=real(c,statement,params,effect=effect)
        if isinstance(statement,str) and 'rolcanlogin' in statement:return [(r,True,False) for r,_,_ in rows]
        return rows
    owner.q=lie
    with pytest.raises(Uncertain,match='TEARDOWN_RECONCILE'):owner.teardown(gh)
    assert not [c for c in gh.calls if c[0]=='DELETE'] and gh.names()>={'DATABASE_URL',*SECRETS.values()}


def test_a_blocked_admin_statement_is_bounded_cancelled_closed_and_accounted(cluster,monkeypatch):
    creator=setup(cluster);owner,events=make_owner(cluster,creator)
    monkeypatch.setattr(oo,'ADMIN_STATEMENT_HARD_SECONDS',1)
    c=owner.connector();pid=c.info.backend_pid
    started=time.monotonic()
    with pytest.raises(Uncertain,match='ADMIN_STATEMENT_HARD_DEADLINE'):owner.q(c,'SELECT pg_sleep(30)')
    elapsed=time.monotonic()-started
    assert 0.9<=elapsed<5 and c.closed and len(owner.cancel_events)==1 and owner.cancel_events[0]['cancel_outcome']=='CANCEL_SENT' and owner.cancel_events[0]['backend_closure']=='NOT_ESTABLISHED'
    deadline=time.monotonic()+5
    while alive(cluster,pid) and time.monotonic()<deadline:time.sleep(.1)
    assert not alive(cluster,pid) and owner.accounting()['admin_hard_deadline_events']==owner.cancel_events


def test_policy_constants_and_the_extra_command_cost_fit_the_matrix_ceilings():
    policy=oo.SESSION_POLICY
    extra=1+policy['wait_reads']+1+policy['max_terminations']+policy['post_reads']      # sessions read already counted; privilege read + reads + terminations
    from verification.ingestion_storage import operational_runner as orr
    teardown_base=9          # measured: BEGIN, 2x(ALTER,REVOKE), COMMIT, roles, memberships, sessions
    assert 37+teardown_base+extra<=orr.MATRIX_OWNER_LIMITS['commands'][1]      # preflight+install+mapping (37) + worst-case teardown fits the through-teardown ceiling (58)
    assert 37+teardown_base+extra+6<=orr.MATRIX_OWNER_LIMITS['commands'][2]    # ... and failure diagnostics (6) still fit the total (64)


def test_a_membership_without_inherited_privilege_does_not_count_as_proven(cluster):
    creator=setup(cluster,admin_name='admin_np')
    with superuser(cluster) as c:c.execute('GRANT pg_signal_backend, pg_read_all_stats TO admin_np WITH INHERIT FALSE')      # MEMBER is true, the privilege is not inherited
    held=hold(cluster,WORKER);pid=held.info.backend_pid;owner,events=make_owner(cluster,creator);gh=GitHubFake()
    with superuser(cluster) as c:assert c.execute("SELECT pg_has_role('admin_np','pg_signal_backend','MEMBER'),pg_has_role('admin_np','pg_signal_backend','USAGE')").fetchone()==(True,False)
    with pytest.raises(Uncertain,match='TEARDOWN_SESSIONS_UNRESOLVED'):owner.teardown(gh)
    assert owner.session_disposition=='UNRESOLVED_PRIVILEGE_NOT_PROVEN' and owner.terminations==0 and alive(cluster,pid)
    held.close()


def test_a_failed_session_read_does_not_suppress_secret_deletion(cluster):
    creator=setup(cluster);held=hold(cluster,WORKER);owner,events=make_owner(cluster,creator);gh=GitHubFake()
    real=owner.q;calls=[]
    def broken(c,statement,params=None,*,effect=False):
        if statement==oo.SESSIONS_SQL:
            calls.append(1)
            if len(calls)>1:raise Uncertain("ADMIN_STATEMENT_HARD_DEADLINE")
        return real(c,statement,params,effect=effect)
    owner.q=broken
    with pytest.raises(Uncertain,match="TEARDOWN_SESSIONS_UNRESOLVED"):owner.teardown(gh)
    assert owner.session_disposition=="UNRESOLVED_ERROR" and gh.names()=={"DATABASE_URL"} and role_state(cluster)==([(EFFECT,False,True),(WORKER,False,True)],0)
    held.close()
