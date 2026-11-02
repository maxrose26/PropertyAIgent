"""Finite owner connection for the installed intake; never invoked by intake runtime.

No SQL installation, role creation, period issuance, source or job submission.
The terminal client supplies one connection and the existing 60s/64KiB envelope.
These phase functions are also exercised on the existing disposable PG17 service.
"""
import copy
import hashlib
import json
import re
import secrets
import time
from pathlib import Path
from datetime import datetime, timezone

from psycopg import sql
from app.ingestion.ledger import Denied, digest
from .operational_owner import Owner, ROLES, ROLE_SETTINGS, ROLE_SETTINGS_SQL, ROLE_SETTING_VALUE
OLDHAM = 'INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5'
HISTORICAL_SHA = '00610d4c27b210e598d075b010f1657d197e229b200deb613e52c38b259f9867'
APPLICATION_BINDING = dict(revision='db05f5d48ce0c70c048c99f538d8765dae669c17',
    workflow_sha256='5b87c6cbef2944fa05468314fc6daefc19b785644b04e04d1ff382b0596cadea',
    manifest_sha256='3c04373b83801b89dd4b5fc0077ee5a533ae94bed4ee807b31bbe9e42b91d60e')

CONTROL = '0' * 64
RECOVERED = ('3f0dba235de9b9efcd52ef3b281ba8c967491f57824404c695ed2b32fae4c045',
             'e92a8e220bbbbcefb2425d6f97a60920bc447bc1fe097d600ea28e3e9d87588e')
STOP = dict(global_stop=dict(reason='CONSUMED_SALFORD_GLOBAL_STOP', run='38884069913'),
            manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',
            last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP', hard_stop_generation=5)
ACCEPTED_STOP = dict(STOP, global_stop=None, manual_stop=None)
DECISIONS = ('DISPOSE_CONSUMED_SALFORD_BARRIER_38884069913',
             'ACCEPT_GUARDED_REENTRY_WITH_HISTORICAL_CONTROLLER_CLOSURE_UNKNOWN')
ROLE_QUERY = """SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NULL,r.rolsuper,
 r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication,r.rolinherit,r.rolconnlimit
 FROM pg_roles r JOIN pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY 1"""
MEMBERS = """SELECT roleid::regrole::text,member::regrole::text,grantor::regrole::text,
 admin_option,inherit_option,set_option FROM pg_auth_members ORDER BY roleid,member,grantor"""
OWNER_MEMBERS = """SELECT grantor::regrole::text,admin_option,inherit_option,set_option
 FROM pg_auth_members WHERE roleid='ingestion_storage_owner'::regrole
 AND member=current_user::regrole ORDER BY grantor"""


def stop_snapshot(ctl):
    """The unchanged runtime's four-field snapshot, without importing its browser chain."""
    return {k:ctl.get(k,0 if k=='hard_stop_generation' else None) for k in
            ('global_stop','manual_stop','last_hard_stop','hard_stop_generation')}


def require(value, reason):
    if not value:
        raise Denied(reason)


def json_equal(c,left,right):
    """PostgreSQL JSON identity: booleans are never mistaken for numeric zero/one."""
    return c.execute('SELECT %s::jsonb=%s::jsonb',(json.dumps(left),json.dumps(right))).fetchone()[0] is True


# Five remaining60s owner/preflight phases +960s B +5s grace +three60s closures.
# This narrows latest activation; it does not increase any existing limit.
MINT_START_MIN_SECONDS = 5*60 + 960 + 5 + 3*60


def validate_binding(b, *, opening=False, now=None):
    require(isinstance(b, dict) and b.get('version') == 'FINITE_INTAKE_OWNER_V1', 'OWNER_BINDING')
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,60}', b.get('period', '')), 'OWNER_PERIOD')
    require(b.get('route') in ('POOLER', 'DIRECT'), 'OWNER_ROUTE')
    import ipaddress
    require(ipaddress.ip_address(b.get('hostaddr', '')).version == 4, 'OWNER_IPV4')
    require(ipaddress.ip_address(b.get('owner_hostaddr', '')).version == 4, 'OWNER_ADMIN_IPV4')
    e = b.get('execution_binding', {})
    require(set(e) == {'revision', 'workflow_sha256', 'manifest_sha256'} and
            all(re.fullmatch('[a-f0-9]{%s}' % n, e.get(k, '')) for k, n in
                [('revision', 40), ('workflow_sha256', 64), ('manifest_sha256', 64)]), 'OWNER_CODE_BINDING')
    require(e==APPLICATION_BINDING,'EXACT_REVIEWED_APPLICATION_REQUIRED')
    require(b.get('accepted_stop') == ACCEPTED_STOP, 'OWNER_STOP_BINDING')
    if 'publication_mint' in b:
        m=b['publication_mint']
        require(type(m) is dict and set(m)=={'authority_sha256','receipt_sha256','expires_at'} and
                all(type(m[k]) is str and re.fullmatch('[a-f0-9]{64}',m[k]) for k in ('authority_sha256','receipt_sha256')) and
                type(m['expires_at']) in (int,float) and m['expires_at']==b.get('publication_valid_until')==b.get('valid_until'),
                'MINT_RECEIPT_BINDING')
    if opening:
        now = time.time() if now is None else now
        require(type(b.get('valid_until')) in (int, float) and
                960 < b['valid_until'] - now <= 2100, 'FINITE_OWNER_VALIDITY')
        if 'publication_mint' in b:
            require(b['valid_until']-now > MINT_START_MIN_SECONDS,'MINT_B_AND_CLOSURE_WINDOW')
    return b


def identity(c, *, containment=False):
    r = c.execute("SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls "
                  "FROM pg_roles WHERE rolname=current_user").fetchone()
    require(r[:4] == ('postgres', 'postgres', False, True) if containment else
            r == ('postgres', 'postgres', False, True, True, True), 'OWNER_IDENTITY')
    if not containment:
        require(c.execute("SELECT pg_has_role(current_user,'pg_read_all_stats','USAGE')").fetchone()[0] is True,
                'OWNER_SESSION_VISIBILITY')


def owner_absent(c):
    require(c.execute("SELECT pg_has_role(current_user,'ingestion_storage_owner','SET'),"
                      "pg_has_role(current_user,'ingestion_storage_owner','USAGE')").fetchone() == (False, False),
            'TEMPORARY_OWNER_CAPABILITY_REMAINS')


def admin_capabilities(c, *, logins_only=False):
    required = list(ROLES) + ([] if logins_only else list(ROLES.values()))
    rows = c.execute('SELECT DISTINCT roleid::regrole::text FROM pg_auth_members '
                     'WHERE member=current_user::regrole AND admin_option AND roleid=ANY(%s::regrole[])',
                     (required,)).fetchall()
    require(sorted(r[0] for r in rows) == sorted(required), 'EXISTING_RUNTIME_ADMIN_CAPABILITIES_REQUIRED')


def enter_owner(c):
    rows = c.execute(OWNER_MEMBERS).fetchall()
    require(len(rows) == 1 and rows[0][0] != 'postgres' and rows[0][1:] == (True, False, False),
            'OWNER_ADMIN_ONLY_BASELINE')
    owner_absent(c)
    c.execute('GRANT ingestion_storage_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE GRANTED BY postgres')
    c.execute('SET LOCAL ROLE ingestion_storage_owner')


def leave_owner(c):
    c.execute('RESET ROLE')
    c.execute('REVOKE ingestion_storage_owner FROM postgres GRANTED BY postgres RESTRICT')
    owner_absent(c)


def inventory(c):
    expected = Owner.daily_intake_inventory()
    rows = c.execute("""SELECT p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),
     r.rolname,p.proconfig,p.prosecdef FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
     JOIN pg_roles r ON r.oid=p.proowner WHERE n.nspname='public' AND p.proname=ANY(%s) ORDER BY 1""",
                     (list(expected),)).fetchall()
    require(rows == [(n, hashlib.sha256(body.encode()).hexdigest(), 'ingestion_storage_owner',
                      ['search_path=pg_catalog'], n != 'ingestion_bolton_allowed')
                     for n, body in sorted(expected.items())], 'INTAKE_OWNER_FUNCTION_INVENTORY')
    acl = c.execute("""SELECT
     has_function_privilege('ingestion_worker','public.ingestion_register_bolton_exception(jsonb)','EXECUTE'),
     has_function_privilege('ingestion_effect_broker','public.ingestion_register_bolton_exception(jsonb)','EXECUTE'),
     has_function_privilege('ingestion_worker','public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)','EXECUTE'),
     has_function_privilege('ingestion_effect_broker','public.ingestion_worker_step(text,text,integer,text,text,jsonb,jsonb)','EXECUTE')""").fetchone()
    require(acl == (True, False, True, True), 'INTAKE_OWNER_CAPABILITY_ACL')
    require(c.execute("""SELECT x.is_grantable FROM pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) x
     WHERE p.oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure
     AND x.grantee='ingestion_worker'::regrole AND x.privilege_type='EXECUTE'
     AND x.grantor='ingestion_storage_owner'::regrole""").fetchall() == [(False,)], 'REGISTRAR_NARROW_ACL')


def activation_gate(c):
    """Existing two-login gate; only the reviewed worker registrar ACL is newly allowed."""
    text = Path('docs/design/ingestion-operational-required-20261018/activate.sql').read_text()
    text = text.split('ALTER ROLE ingestion_worker_login LOGIN;')[0]
    require(text.count('BEGIN;') == 1, 'ACTIVATION_GATE_DERIVATION')
    marker = "   AND has_function_privilege(login,p.oid,'EXECUTE'))"
    require(text.count(marker) == 1, 'ACTIVATION_GATE_DERIVATION')
    text = text.replace(marker, "   AND NOT (login='ingestion_worker_login' AND "
        "p.oid='public.ingestion_register_bolton_exception(jsonb)'::regprocedure)\n" + marker)
    c.execute(text.replace('BEGIN;', '', 1))


def control(c, *, locked=False):
    return c.execute("SELECT outcome::jsonb FROM public.ingestion_work_items WHERE key=%s" +
                     (' FOR UPDATE' if locked else ''), (CONTROL,)).fetchone()[0]


def retained_cleanup(c, ctl):
    require((ctl.get('grants', {}).get(OLDHAM) or {}).get('expires_at') == 0 and
            (ctl.get('oldham_allowances', {}).get(OLDHAM) or {}).get('revoked') is True,
            'OLDHAM_REVOKED_STATE_CHANGED')
    raw=Path('docs/design/b-owner-finite-20261031/oldham-historical-bindings.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest()==HISTORICAL_SHA,'OLDHAM_RETAINED_BINDINGS_HASH')
    historical=json.loads(raw);grant,allowance=historical['grant'],historical['allowance']
    package_sha=c.execute("SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",
                          (json.dumps(allowance['package']),)).fetchone()[0]
    grant['oldham_package_sha256']=package_sha;allowance['package_sha256']=package_sha
    allowance['grant_binding']['oldham_package_sha256']=package_sha
    grant['expires_at'] = 0; allowance['revoked'] = True
    require(json_equal(c,ctl['grants'][OLDHAM],grant) and json_equal(c,ctl['oldham_allowances'][OLDHAM],allowance),
            'OLDHAM_HISTORICAL_BINDING_CHANGED')
    historical_root=allowance['package']['registration']['rows'][0]
    actual=c.execute("SELECT (SELECT jsonb_object_agg(e.key,e.value) FROM jsonb_each(to_jsonb(w)) e "
                     "WHERE e.key=ANY(%s))=%s::jsonb FROM public.ingestion_work_items w WHERE key=%s",
                     (list(historical_root),json.dumps(historical_root),historical_root['key'])).fetchone()
    require(actual == (True,),
            'OLDHAM_HISTORICAL_ROOT_CHANGED')
    rows = c.execute("SELECT key,state,phase,fence,owner,lease_until FROM public.ingestion_work_items "
                     "WHERE key=ANY(%s) ORDER BY key", (list(RECOVERED),)).fetchall()
    require(rows == [(k, 'SAFETY_BLOCKED', 'RECOVERED', 2, None, None) for k in sorted(RECOVERED)],
            'RECOVERED_ROOT_CHANGED')
    require(c.execute("SELECT count(*) FROM public.ingestion_work_attempts WHERE work_key=ANY(%s) "
                      "AND (finished_at IS NULL OR phase<>'RECOVERED')", (list(RECOVERED),)).fetchone()[0] == 0,
            'RECOVERED_ATTEMPT_CHANGED')
    require(c.execute("SELECT count(DISTINCT work_key) FROM public.ingestion_work_attempts WHERE work_key=ANY(%s) "
                      "AND phase='RECOVERED' AND finished_at IS NOT NULL", (list(RECOVERED),)).fetchone()[0] == 2,
            'RECOVERED_ATTEMPT_MISSING')


def no_hazards(c, ctl):
    require(not ctl.get('intake_run') or ctl['intake_run'].get('state') == 'VERIFIED', 'UNFINISHED_INTAKE_RUN')
    require(c.execute("SELECT count(*) FROM public.ingestion_work_items WHERE phase IN "
                      "('SOURCE_INTENT','WRITE_INTENT') OR state='PERSISTENCE_UNCERTAIN'").fetchone()[0] == 0,
            'UNRESOLVED_EFFECT_INTENT')
    require(not c.execute("SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s)",
                          (list(ROLES) + ['ingestion_application_login', 'ingestion_recovery_login'],)).fetchall(),
            'EXISTING_PIPELINE_SESSION')
    require(not any(type(g.get('expires_at')) not in (int, float) or g['expires_at'] > time.time()
                    for g in ctl.get('grants', {}).values()), 'UNEXPIRED_OR_UNREADABLE_AUTHORITY')


def dormant(c):
    rows = c.execute(ROLE_QUERY, (list(ROLES),)).fetchall()
    require(rows == [(r, False, True, False, False, False, False, False, False, 1) for r in sorted(ROLES)],
            'RUNTIME_NOT_DORMANT')
    members = c.execute(MEMBERS).fetchall()
    require(not any(m[1] in ROLES for m in members), 'RUNTIME_MEMBERSHIP_PRESENT')
    require(not any(c.execute("SELECT pg_has_role(%s,%s,'MEMBER')", (r, cap)).fetchone()[0]
                    for r in ROLES for cap in ROLES.values()), 'INDIRECT_RUNTIME_CAPABILITY')
    return members


def settings(c):
    rows = c.execute(ROLE_SETTINGS_SQL, (list(ROLES),)).fetchall()
    require([r[0] for r in rows] == sorted(ROLES) and not any(r[2] for r in rows), 'ROLE_SETTINGS_SCOPE')
    result = {r: list(config or []) for r, config, _ in rows}
    require(all(ROLE_SETTING_VALUE.fullmatch(v) for entries in result.values()
                for v in Owner._split(entries)[0].values()), 'ROLE_SETTINGS_VALUE')
    return result


def set_settings(c, prior=None):
    for role in sorted(ROLES):
        was = dict(ROLE_SETTINGS) if prior is None else Owner._split(prior[role])[0]
        for param, _ in ROLE_SETTINGS:
            if param in was:
                c.execute(sql.SQL('ALTER ROLE {} SET {} TO {}').format(
                    sql.Identifier(role), sql.Identifier(param), sql.Literal(was[param])))
            else:
                c.execute(sql.SQL('ALTER ROLE {} RESET {}').format(sql.Identifier(role), sql.Identifier(param)))


def ledger_sha(c, replacement=None):
    return c.execute("""SELECT encode(sha256(convert_to(jsonb_build_object(
     'items',(SELECT coalesce(jsonb_agg(CASE WHEN key=repeat('0',64) AND %s::jsonb IS NOT NULL
       THEN to_jsonb(w)||jsonb_build_object('outcome',%s::jsonb) ELSE to_jsonb(w) END ORDER BY key),'[]')
       FROM public.ingestion_work_items w),
     'attempts',(SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY work_key,fence),'[]') FROM public.ingestion_work_attempts a)
     )::text,'UTF8')),'hex')""", (json.dumps(replacement) if replacement is not None else None,)*2).fetchone()[0]


def begin(c, *, containment=False):
    identity(c, containment=containment)
    c.execute('BEGIN')
    c.execute("SET LOCAL statement_timeout='10s';SET LOCAL lock_timeout='3s';SET LOCAL idle_in_transaction_session_timeout='20s'")


def stop_disposition(c, decisions):
    require(tuple(decisions) == DECISIONS, 'BOTH_EXPLICIT_STOP_DECISIONS_REQUIRED')
    begin(c)
    try:
        inventory(c); before_members = dormant(c)
        enter_owner(c)
        c.execute('LOCK TABLE public.ingestion_work_items,public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE')
        ctl = control(c, locked=True)
        require(stop_snapshot(ctl) == STOP, 'EXACT_GENERATION5_STOP_REQUIRED')
        retained_cleanup(c, ctl); no_hazards(c, ctl)
        after = copy.deepcopy(ctl); after.update(global_stop=None, manual_stop=None)
        expected_ledger = ledger_sha(c, after)
        c.execute('UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=%s', (json.dumps(after), CONTROL))
        require(control(c) == after and ledger_sha(c) == expected_ledger, 'STOP_POSTCONDITION')
        leave_owner(c)
        require(c.execute(MEMBERS).fetchall() == before_members, 'STOP_PRIVILEGE_CLEANUP')
        c.execute('COMMIT')
    except BaseException:
        c.execute('ROLLBACK'); raise
    owner_absent(c)
    require(stop_snapshot(control(c)) == ACCEPTED_STOP, 'STOP_COMMITTED_READBACK')
    return dict(outcome='COMMIT_ACKNOWLEDGED', stop=ACCEPTED_STOP, historical_controller_closure='UNKNOWN')


def activate(c, b, save, *, password_factory=None):
    """Persist encrypted closure baseline BEFORE any access effect; one atomic activation."""
    validate_binding(b, opening=True)
    passwords = {r: (password_factory or (lambda: secrets.token_urlsafe(48)))() for r in ROLES}
    require(all(isinstance(v, str) and len(v) >= 48 for v in passwords.values()), 'PASSWORD_ENTROPY_BOUND')
    begin(c)
    try:
        admin_capabilities(c); inventory(c); members = dormant(c); ctl = control(c)
        server_now=c.execute('SELECT extract(epoch FROM clock_timestamp())').fetchone()[0]
        require(960 < b['valid_until'] - float(server_now) <= 2100, 'SERVER_FINITE_VALIDITY')
        if 'publication_mint' in b:
            validate_binding(b,opening=True,now=float(server_now))
        enter_owner(c)
        c.execute('LOCK TABLE public.ingestion_work_items,public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE')
        ctl=control(c,locked=True)
        require(stop_snapshot(ctl) == b['accepted_stop'], 'ACTIVATION_STOP_CHANGED')
        retained_cleanup(c, ctl); no_hazards(c, ctl)
        leave_owner(c)
        prior = settings(c); original_ledger = ledger_sha(c)
        state = dict(version='FINITE_INTAKE_ACCESS_STATE_V1', binding=copy.deepcopy(b), state='ARMED_BEFORE_ACTIVATION',
                     prior_settings=prior, original_memberships=[list(m) for m in members], passwords=passwords)
        save(state)  # must fsync encrypted owner-local recovery data before COMMIT is possible
        set_settings(c)
        for role, cap in ROLES.items():
            c.execute(sql.SQL('GRANT {} TO {} WITH ADMIN FALSE, INHERIT TRUE, SET FALSE GRANTED BY postgres').format(
                sql.Identifier(cap), sql.Identifier(role)))
        activation_gate(c)
        for role in ROLES:
            verifier = c.pgconn.encrypt_password(passwords[role].encode(), role.encode(), algorithm=b'scram-sha-256').decode()
            c.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {} VALID UNTIL {}').format(sql.Identifier(role),
                sql.Literal(verifier), sql.Literal(datetime.fromtimestamp(b['valid_until'], timezone.utc).isoformat())))
        require(ledger_sha(c) == original_ledger, 'ACTIVATION_LEDGER_CHANGED')
        inventory(c); owner_absent(c)
        want_members = sorted(members + [(cap, role, 'postgres', False, True, False) for role, cap in ROLES.items()])
        require(sorted(c.execute(MEMBERS).fetchall()) == want_members, 'ACTIVATION_MEMBERSHIP_POSTCONDITION')
        require(all(Owner._split(v)[0] == dict(ROLE_SETTINGS) and Owner._split(v)[1] == Owner._split(prior[r])[1]
                    for r, v in settings(c).items()), 'ACTIVATION_SETTINGS_POSTCONDITION')
        c.execute('COMMIT')
    except BaseException:
        c.execute('ROLLBACK'); raise
    rows = c.execute(ROLE_QUERY, (list(ROLES),)).fetchall()
    require(rows == [(r, True, False, False, False, False, False, False, False, 1) for r in sorted(ROLES)],
            'ACTIVATION_COMMITTED_READBACK')
    state['state'] = 'ACTIVATION_ACKNOWLEDGED'; save(state)
    return dict(outcome='COMMIT_ACKNOWLEDGED', runtime_roles=sorted(ROLES), credentials='ENCRYPTED_LOCAL_ONLY',
                valid_until=b['valid_until'])


def close(c, state, save, *, emit=lambda *_: None):
    """Independent revocation; no stop/generation preflight and no source replay."""
    b = validate_binding(state['binding'])
    require(state.get('version') == 'FINITE_INTAKE_ACCESS_STATE_V1', 'CLOSURE_STATE')
    begin(c, containment=True)
    try:
        admin_capabilities(c,logins_only=True)
        # Containment must commit even when a later ledger/state check refuses.
        for role in ROLES:
            c.execute(sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL').format(sql.Identifier(role)))
        c.execute('COMMIT')
    except BaseException:
        c.execute('ROLLBACK'); raise
    state['state'] = 'ACCESS_DISABLED_ACKNOWLEDGED'; save(state)
    rows = c.execute(ROLE_QUERY, (list(ROLES),)).fetchall()
    require(rows == [(r,False,True,False,False,False,False,False,False,1) for r in sorted(ROLES)], 'ACCESS_DISABLE_READBACK')
    begin(c,containment=True)
    try:
        admin_capabilities(c)
        # Revoke only the exact self-issued member/grantor rows. Never CASCADE.
        membership_drift=False
        for role,cap in ROLES.items():
            rows = c.execute('SELECT admin_option,inherit_option,set_option FROM pg_auth_members '
                             'WHERE roleid=%s::regrole AND member=%s::regrole AND grantor=current_user::regrole',
                             (cap, role)).fetchall()
            if rows not in ([], [(False, True, False)]):membership_drift=True
            if rows == [(False, True, False)]:
                c.execute(sql.SQL('REVOKE {} FROM {} GRANTED BY postgres RESTRICT').format(
                    sql.Identifier(cap), sql.Identifier(role)))
        c.execute('COMMIT')
    except BaseException:
        c.execute('ROLLBACK'); raise
    state['membership_closure']='ACKNOWLEDGED' if not membership_drift else 'RECONCILIATION_REQUIRED';save(state)
    require(not membership_drift, 'ACCESS_DISABLED_BUT_MEMBERSHIP_RECONCILIATION_REQUIRED')
    begin(c,containment=True)
    try:
        inventory(c); enter_owner(c)
        c.execute('LOCK TABLE public.ingestion_work_items,public.ingestion_work_attempts IN SHARE ROW EXCLUSIVE MODE')
        ctl = control(c, locked=True); stop = stop_snapshot(ctl); retained_cleanup(c, ctl)
        original = copy.deepcopy(ctl)
        for role,entries in settings(c).items():
            before=state['prior_settings'][role]
            require(entries==before or (Owner._split(entries)[0]==dict(ROLE_SETTINGS) and
                    Owner._split(entries)[1]==Owner._split(before)[1]),'CLOSURE_SETTINGS_DRIFT')
        grants = {a: g for a, g in ctl.get('grants', {}).items() if g.get('intake_period') == b['period']}
        require(len(grants) <= 4, 'CLOSURE_AUTHORITY_BOUND')
        run = ctl.get('intake_run') or {};policy=ctl.get('intake_periods',{}).get(b['period'],{})
        require(not grants or (run.get('period') == b['period'] and policy.get('execution_binding') == b['execution_binding']),
                'CLOSURE_RUN_BINDING')
        for a, g in grants.items():
            require(g.get('execution_binding') == b['execution_binding'] and g.get('intake_run') == run.get('id') and
                    g.get('login') == 'ingestion_worker_login' and g.get('effect_login') == 'ingestion_effect_login',
                    'CLOSURE_AUTHORITY_BINDING')
            ctl['grants'][a]['expires_at'] = 0
        expected_ledger = ledger_sha(c, ctl)
        c.execute('UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=%s', (json.dumps(ctl), CONTROL))
        require(control(c) == ctl and stop_snapshot(ctl) == stop and ledger_sha(c) == expected_ledger,
                'CLOSURE_CONTROL_POSTCONDITION')
        leave_owner(c)
        set_settings(c, state['prior_settings'])
        require({r: sorted(v) for r, v in settings(c).items()} ==
                {r: sorted(v) for r, v in state['prior_settings'].items()}, 'CLOSURE_SETTINGS_POSTCONDITION')
        require([list(m) for m in c.execute(MEMBERS).fetchall()] == state['original_memberships'],
                'CLOSURE_UNRELATED_MEMBERSHIP_DRIFT')
        c.execute('COMMIT')
    except BaseException:
        c.execute('ROLLBACK'); raise
    owner_absent(c)
    require(all(control(c)['grants'][a]['expires_at'] == 0 for a in grants), 'CLOSURE_AUTHORITY_READBACK')
    identity(c)  # session closure needs proven monitoring; containment did not
    # Existing bounded wait/precise-termination primitive; no new privileges.
    o = Owner(None, emit, lambda: None, expiry=datetime.now(timezone.utc), bindings=b['execution_binding'])
    o.q = lambda conn, query, params=None, **_: conn.execute(query, params).fetchall()
    sessions = c.execute('SELECT pid,usename,state,backend_start FROM pg_stat_activity WHERE usename=ANY(%s)',
                         (list(ROLES),)).fetchall()
    if sessions:
        o.resolve_sessions(c, sessions)
        require(o.session_disposition in ('CLEARED_BY_WAIT', 'TERMINATED_VERIFIED_ABSENT'), 'SESSIONS_UNRESOLVED')
    state.update(state='DATABASE_CLOSURE_ACKNOWLEDGED', passwords={}); save(state)
    return dict(outcome='COMMIT_ACKNOWLEDGED', runtime_access='DISABLED', authorities=sorted(grants),
                authority_expiry=0, temporary_owner='REMOVED', sessions='ABSENT', stop_preserved=stop,
                intake_run_state=run.get('state'), open_run_requires_reconciliation=run.get('state')=='OPEN')


def finalisation(c, b, expected):
    """One independent, source-free bounded terminal read; no temp grant or stored function."""
    validate_binding(b)
    require(re.fullmatch('[a-f0-9]{32}', expected.get('run_id', '')), 'READBACK_RUN_ID')
    c.execute('BEGIN READ ONLY')
    try:
        ctl = control(c); run = ctl.get('intake_run') or {};policy=ctl.get('intake_periods',{}).get(b['period'],{})
        require(run.get('period') == b['period'] and run.get('id') == expected['run_id'] and
                policy.get('execution_binding') == b['execution_binding'] and run.get('state') == 'VERIFIED' and
                run.get('status') == 'RETAINED_AND_SCREENED', 'INDEPENDENT_FINALISATION_BINDING')
        pub = run.get('publication')
        require(isinstance(pub,dict) and json_equal(c,pub,expected.get('publication')) and pub.get('readback_verified') is True and
                re.fullmatch('[a-f0-9]{40}', pub.get('commit', '')) and
                re.fullmatch('[a-f0-9]{64}', pub.get('sha256', '')) and
                pub.get('path') == f"docs/design/ingestion-operational-execution-daily-intake/{b['period']}/{run['id']}/final/result-before-publication.json",
                'INDEPENDENT_PUBLICATION_BINDING')
        grants = {a: g for a, g in ctl.get('grants', {}).items() if g.get('intake_run') == run['id']}
        require(0 < len(grants) <= 4 and all(type(g.get('expires_at')) in (int,float) and g['expires_at'] == 0 and g.get('intake_period') == b['period'] and
                g.get('execution_binding') == b['execution_binding'] for g in grants.values()), 'INDEPENDENT_AUTHORITY_CLOSURE')
        roots = (ctl.get('intake_periods', {}).get(b['period'], {}).get('days') or {}).get(run.get('day')) or {}
        require(set(roots) == {'tameside', 'manchester'} and len(set(roots.values())) == 2, 'INDEPENDENT_COUNCILS')
        require(all(any(g.get('capture_key')==key for g in grants.values()) for key in roots.values()),
                'INDEPENDENT_BOTH_CAPTURE_AUTHORITIES')
        result = []
        for council, key in sorted(roots.items()):
            row = c.execute("SELECT state,checkpoint::jsonb,subject::jsonb FROM public.ingestion_work_items WHERE key=%s",
                            (key,)).fetchone()
            require(row is not None and row[0] == 'COMPLETE' and row[2].get('council') == council, 'INDEPENDENT_CAPTURE')
            receipt = row[1] or {}; records = receipt.get('records')
            archive=receipt.get('durable_archive') or {}
            require(receipt.get('kind') == 'LISTING_RECEIPT_V1' and receipt.get('council')==council and
                    archive.get('readback_verified') is True and re.fullmatch('[a-f0-9]{40}',archive.get('commit','')) and
                    re.fullmatch('[a-f0-9]{64}',archive.get('sha256','')) and archive['sha256']==receipt.get('source_sha256') and
                    re.fullmatch(re.escape(f"docs/design/ingestion-operational-execution-daily-intake/{b['period']}/{run['id']}/")+
                                 r'capture-[12]/source\.json',archive.get('path','')) and
                    isinstance(records, list) and len(records) <= 60 and (records or (council=='manchester' and receipt.get('explicit_zero') is True)),
                    'INDEPENDENT_ARCHIVE_OR_ZERO')
            n = len(records)
            screens = c.execute("SELECT count(*) FILTER (WHERE state='COMPLETE'),count(*) FROM public.ingestion_work_items "
                                "WHERE task='SCREENING' AND dependencies::jsonb=jsonb_build_array(%s::text)", (key,)).fetchone()
            batches = c.execute("SELECT count(*) FILTER (WHERE state='COMPLETE'),count(*) FROM public.ingestion_work_items "
                                "WHERE task='LISTING_METADATA' AND checkpoint::jsonb->'plan'->>'capture_key'=%s", (key,)).fetchone()
            require(screens == (n, n) and batches == ((n + 4)//5, (n + 4)//5), 'INDEPENDENT_SCREENING_BATCHES')
            result.append(dict(council=council, capture_key=key, record_count=n, screening_complete=n,
                               batches_complete=(n+4)//5, archive=receipt['durable_archive'],
                               source_sha256=receipt.get('source_sha256'), capture_sha256=digest(receipt)))
        value = dict(status='INDEPENDENT_DATABASE_VERIFIED_SUCCESS', period=b['period'], run_id=run['id'],
                     publication=pub, authorities={a: 0 for a in grants}, captures=result, stop=stop_snapshot(ctl),
                     independent_external_publication_check='REQUIRED', independent_render_terminal_check='REQUIRED')
        require(len(json.dumps(value).encode()) <= 49152, 'READBACK_EXPORT_BOUND')
        return value
    finally:
        c.execute('ROLLBACK')
