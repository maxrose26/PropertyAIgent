"""One fixed READ ONLY inspection of the installed ingestion state needed before an authentic Oldham capture and screening (NOT AUTHORISED FOR EXECUTION).

It is a sibling of the single-statement administrative probe, not a mode of the operational Runner and not an Owner. It reuses the probe's skeleton (hidden input, route/TLS preparation, journal, memory
supervision, closure accounting) and the reviewed fixed SQL constants of `Owner.pipeline_readback`, and adds only plain SELECTs for what that readback does not cover: the application login, the Oldham
helper and worker function identities, the runtime EXECUTE and table privileges, and an honest account of which stop and barrier facts the installed control function does and does not expose.

`Owner` is imported ONLY for its pure classmethod function inventories and is never instantiated here (a test spies on that). Nothing here can install, grant, set a role, change a credential, map a secret,
call GitHub, touch the ledger or contact a council: the statement list is a closed constant, every statement is sent through one gate that rejects anything else, and the transaction is BEGIN READ ONLY
followed by ROLLBACK. READ ONLY is a server-side guard on THIS transaction; the connecting account is the existing administrative migration identity and is NOT thereby a restricted account.

The outcome is a report. A discrepancy is stated, never repaired, and never turned into an installation. Visibility the identity does not have is reported as UNKNOWN, not guessed.
"""
import argparse,hashlib,json,os,resource,subprocess,sys,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .admin_connection_probe import ProbeRunner,ProbeDenied,hidden_input,measured,ABSENT,ABSENT_CAPABILITIES
from .connection_diagnostics import safe_failure,PreparationFailure
from .operational_journal import Journal
from .operational_outcome import session,ACCOUNTING_SCHEMA
from .operational_preparation import Progress,prepare_connection
from .tls_trust import owned_resources,PEM_SHA256

MODE='OLDHAM_READONLY_INSPECTION_ONLY'
AUTHORITY='AUTHORISE_OLDHAM_READONLY_INSPECTION_ONCE_20261028'
STATUS='OWNER_APPROVED_OLDHAM_READONLY_INSPECTION_ONCE'
STATE='oldham-readonly-inspection-once-20261028'
EVIDENCE_DIRECTORY='docs/design/oldham-readonly-inspection-20261028'
EXPECTED_ADMIN='postgres'
LOGINS=('ingestion_worker_login','ingestion_effect_login','ingestion_application_login','ingestion_storage_login')
RUNTIME_LOGINS=('ingestion_worker_login','ingestion_effect_login','ingestion_application_login')
FUNCTIONS_OF_INTEREST=('ingestion_worker_step','ingestion_oldham_allowed','ingestion_acceptance_control','ingestion_bolton_allowed','ingestion_register_bolton_exception','ingestion_raise_stop','ingestion_recover_abandoned')
TABLES_OF_INTEREST=('applications','application_lifecycle_events','ingestion_work_items','ingestion_work_attempts')
OLDHAM_HELPER='ingestion_oldham_allowed'
OLDHAM_HELPER_ARGUMENTS='ctl jsonb, authority text, work_key text, subject jsonb'
CONTROL_FIELDS=('global_stop','manual_stop','hard_stop_generation','unexpired_grants')
NOT_EXPOSED_BY_CONTROL_FUNCTION=('last_hard_stop','stop_state_sha256','WRITE_INTENT_uncertainty_barrier_rows','oldham_allowances','per_grant_detail','bolton_exceptions')
KNOWN_MANUAL_STOPS=('STORAGE_TEST_STOP','IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE')
BOUND=dict(connection_attempts=1,driver_statements=12,planned_statements=11,rollbacks=1,commits=0,returned_data_value_bytes=32768,database_seconds=30,dns_subprocesses=1,dns_seconds=3,
           hidden_input_seconds=120,active_seconds=45,final_report_seconds=5,controller_memory_bytes=256*1024**2,aggregate_memory_bytes=1536*1024**2,persisted_evidence_bytes=65536,terminal_json_bytes=32768)
TIMING=dict(input_seconds=BOUND['hidden_input_seconds'],active_seconds=BOUND['active_seconds'],work_seconds=35,diagnostic_seconds=5,report_seconds=BOUND['final_report_seconds'],outer_seconds=180)
ABSENT_CAPABILITIES=tuple(ABSENT_CAPABILITIES)+('grant','set_role','function_installation','ledger_table_select','arbitrary_sql')      # the control row is read only through the installed SECURITY DEFINER control function

# --- the closed statement list (each entry: name, SQL, fixed parameters). Nothing else can ever be sent. -------------------------------------------------------------------------------------
_ROLE_OID="(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='%s')"
IDENTITY=("SELECT current_user,session_user,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,"
          "pg_catalog.pg_has_role(current_user,"+_ROLE_OID%'ingestion_storage_owner'+",'USAGE'),pg_catalog.pg_has_role(current_user,"+_ROLE_OID%'ingestion_storage_owner'+",'SET'),"
          "pg_catalog.pg_has_role(current_user,"+_ROLE_OID%'ingestion_barrier_releaser'+",'USAGE'),pg_catalog.pg_has_role(current_user,"+_ROLE_OID%'ingestion_barrier_releaser'+",'SET'),"
          "pg_catalog.pg_has_role(current_user,'pg_read_all_stats','USAGE'),pg_catalog.pg_has_role(current_user,'pg_signal_backend','USAGE'),"
          "pg_catalog.has_column_privilege(current_user,'pg_catalog.pg_authid','rolpassword','SELECT') AND pg_catalog.has_column_privilege(current_user,'pg_catalog.pg_authid','rolname','SELECT'),"
          "pg_catalog.has_function_privilege(current_user,pg_catalog.to_regprocedure('public.ingestion_acceptance_control()'),'EXECUTE'),"
          "pg_catalog.to_regprocedure('public.ingestion_acceptance_control()') IS NOT NULL "
          "FROM pg_catalog.pg_roles r WHERE r.rolname=current_user")
CONTROL="SELECT public.ingestion_acceptance_control()"
ROLES_WITH_PASSWORD_PRESENCE=("SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NOT NULL,r.rolvaliduntil,r.rolconnlimit,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication "
                              "FROM pg_catalog.pg_roles r JOIN pg_catalog.pg_authid a ON a.rolname=r.rolname WHERE r.rolname=ANY(%s) ORDER BY r.rolname")
ROLES_WITHOUT_PASSWORD_PRESENCE=("SELECT r.rolname,r.rolcanlogin,NULL::boolean,r.rolvaliduntil,r.rolconnlimit,r.rolsuper,r.rolcreaterole,r.rolcreatedb,r.rolbypassrls,r.rolreplication "
                                 "FROM pg_catalog.pg_roles r WHERE r.rolname=ANY(%s) ORDER BY r.rolname")
ROLE_SETTINGS=("SELECT r.rolname,r.rolconfig,(SELECT count(*) FROM pg_catalog.pg_db_role_setting s WHERE s.setrole=r.oid AND s.setdatabase<>0) FROM pg_catalog.pg_roles r WHERE r.rolname=ANY(%s) ORDER BY r.rolname")
MEMBERSHIPS=("SELECT mr.rolname,ro.rolname,m.admin_option,m.inherit_option,m.set_option FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles mr ON mr.oid=m.member "
             "JOIN pg_catalog.pg_roles ro ON ro.oid=m.roleid WHERE mr.rolname=ANY(%s) ORDER BY 1,2")
SESSIONS=("SELECT usename,state,backend_type FROM pg_catalog.pg_stat_activity WHERE usename=ANY(%s) OR (usename IS NULL AND backend_type='client backend' AND pid<>pg_catalog.pg_backend_pid()) ORDER BY pid")
FUNCTIONS=("SELECT p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),r.rolname,p.proconfig,p.prosecdef,pg_catalog.pg_get_function_identity_arguments(p.oid) "
           "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace JOIN pg_catalog.pg_roles r ON r.oid=p.proowner WHERE n.nspname='public' AND p.proname=ANY(%s) ORDER BY p.proname,p.oid")
FUNCTION_PRIVILEGES=("SELECT p.proname,r.rolname,pg_catalog.has_function_privilege(r.oid,p.oid,'EXECUTE') FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
                     "CROSS JOIN pg_catalog.pg_roles r WHERE n.nspname='public' AND p.proname=ANY(%s) AND r.rolname=ANY(%s) ORDER BY 1,2")
TABLE_PRIVILEGES=("SELECT r.rolname,c.relname,pg_catalog.has_table_privilege(r.oid,c.oid,'SELECT'),pg_catalog.has_table_privilege(r.oid,c.oid,'INSERT'),pg_catalog.has_table_privilege(r.oid,c.oid,'UPDATE'),"
                  "pg_catalog.has_table_privilege(r.oid,c.oid,'DELETE'),pg_catalog.has_any_column_privilege(r.oid,c.oid,'INSERT'),pg_catalog.has_any_column_privilege(r.oid,c.oid,'UPDATE'),pg_catalog.has_any_column_privilege(r.oid,c.oid,'SELECT') "
                  "FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p') "
                  "AND c.relname=ANY(%s) AND r.rolname=ANY(%s) ORDER BY 1,2")
BEGIN='BEGIN READ ONLY'
ROLLBACK='ROLLBACK'


def function_names():
    return sorted(set(expected_states()['union'])|{OLDHAM_HELPER})      # exactly the names the reviewed states define; the control function is read in the privilege statement only


def planned(variant_roles_visible=True,variant_sessions_visible=True,control_executable=True):
    """The complete ordered statement list for one variant. At most 11; the ceiling is 12."""
    items=[('begin',BEGIN,None),('identity',IDENTITY,None)]
    if control_executable:items.append(('control',CONTROL,None))
    items.append(('roles',ROLES_WITH_PASSWORD_PRESENCE if variant_roles_visible else ROLES_WITHOUT_PASSWORD_PRESENCE,[list(LOGINS)]))
    items+=[('role_settings',ROLE_SETTINGS,[list(LOGINS)]),('memberships',MEMBERSHIPS,[list(LOGINS)])]
    if variant_sessions_visible:items.append(('sessions',SESSIONS,[list(LOGINS)]))
    items+=[('functions',FUNCTIONS,[function_names()]),('function_privileges',FUNCTION_PRIVILEGES,[list(FUNCTIONS_OF_INTEREST),list(RUNTIME_LOGINS)]),
            ('table_privileges',TABLE_PRIVILEGES,[list(TABLES_OF_INTEREST),list(RUNTIME_LOGINS)]),('rollback',ROLLBACK,None)]
    return items


ALLOWED=None
def allowed():
    global ALLOWED
    if ALLOWED is None:ALLOWED={s for v in ((a,b,c) for a in (True,False) for b in (True,False) for c in (True,False)) for _,s,_ in planned(*v)}
    return ALLOWED


# --- expected installed states (pure; Owner is used only for its classmethod inventories) --------------------------------------------------------------------------------------------------
_EXPECTED=None
def expected_states():
    global _EXPECTED
    if _EXPECTED is None:
        from .operational_owner import Owner
        from . import oldham_policy
        states,upgraded,_=Owner.reviewed_inventories(True)
        every={'ORIGINAL':states['ORIGINAL'],'SUCCESSOR_POLICY_APPLIED':upgraded,'GENERATION2_POLICY_APPLIED':Owner.generation2_inventory(),'GENERATION2_CAPTURE_POLICY_APPLIED':Owner.capture_inventory(),
               'GENERATION3_WINDOW_POLICY_APPLIED':Owner.window_inventory(),'GENERATION3_SCREENING_V3_POLICY_APPLIED':Owner.screening_v3_policy_inventory(),'GENERATION3_SCREENING_V3_APPLIED':Owner.screening_v3_inventory()}
        oldham={**Owner.screening_v3_inventory(),'ingestion_worker_step':oldham_policy.replacement().split('AS $fn$',1)[1].split('$fn$;',1)[0],
                OLDHAM_HELPER:oldham_policy.FUNCTION.split('AS $oldham$',1)[1].split('$oldham$;',1)[0]}
        sha=lambda body:hashlib.sha256(body.encode()).hexdigest()
        hashed={k:{n:sha(b) for n,b in v.items()} for k,v in every.items()}
        union={n for v in hashed.values() for n in v}|set(oldham)
        _EXPECTED=dict(pre_oldham=hashed,oldham={n:sha(b) for n,b in oldham.items()},union=sorted(union))
    return _EXPECTED


CLASSIFICATION_CHECKS=['body_sha256_equals_reviewed','owner','search_path','no_overloads','oldham_helper_signature_and_security_definer']
CLASSIFICATION_NOT_CHECKED=['security_definer_of_other_functions','volatility','strictness','function_acl_beyond_the_runtime_logins_in_privileges']


def classify_functions(rows):
    """Distinguish a recognised pre-Oldham installation, the exact reviewed Oldham installation, missing objects and an unexpected or mixed installation. Pure; rows are fixed-shape tuples."""
    expected=expected_states()
    seen={};overloaded=False
    for name,sha,owner,config,secdef,arguments in rows:
        if name in seen:overloaded=True
        seen[name]=dict(sha=sha,owner=owner,config=config,secdef=secdef,arguments=arguments)
    observed={n:v['sha'] for n,v in seen.items()}
    detail=dict(observed_count=len(seen),overloaded=overloaded,
                owner_and_search_path_as_reviewed=all(v['owner']=='ingestion_storage_owner' and v['config']==['search_path=pg_catalog'] for v in seen.values()) if seen else None,
                oldham_helper_present=OLDHAM_HELPER in seen,
                oldham_helper_signature_and_definer_as_reviewed=(seen[OLDHAM_HELPER]['arguments']==OLDHAM_HELPER_ARGUMENTS and seen[OLDHAM_HELPER]['secdef'] is True) if OLDHAM_HELPER in seen else None)
    if overloaded:return dict(detail,state='UNEXPECTED_OR_MIXED',reason='OVERLOADED_FUNCTION_NAME',recognised=None)
    if not observed:return dict(detail,state='NOT_INSTALLED',reason='NO_REVIEWED_FUNCTION_PRESENT',recognised=None)
    exact=next((k for k,v in expected['pre_oldham'].items() if observed==v),None)
    if exact is not None:
        state='RECOGNISED_PRE_OLDHAM'
        if not detail['owner_and_search_path_as_reviewed']:return dict(detail,state='UNEXPECTED_OR_MIXED',reason='OWNER_OR_SEARCH_PATH_CHANGED',recognised=exact)
        return dict(detail,state=state,reason='BODY_OWNER_SEARCH_PATH_MATCH',recognised=exact,is_the_retained_v3_state=exact=='GENERATION3_SCREENING_V3_APPLIED',checked=CLASSIFICATION_CHECKS,not_checked=CLASSIFICATION_NOT_CHECKED)
    if observed==expected['oldham']:
        if not detail['owner_and_search_path_as_reviewed'] or detail['oldham_helper_signature_and_definer_as_reviewed'] is not True:
            return dict(detail,state='UNEXPECTED_OR_MIXED',reason='OWNER_OR_SEARCH_PATH_OR_SIGNATURE_CHANGED',recognised='OLDHAM_EXACT')
        return dict(detail,state='OLDHAM_EXACT_INSTALLATION',reason='BODY_OWNER_SEARCH_PATH_MATCH',recognised='OLDHAM_EXACT',checked=CLASSIFICATION_CHECKS,not_checked=CLASSIFICATION_NOT_CHECKED)
    # A strict subset whose every present body is consistent with a reviewed state is "missing objects". Several reviewed states share most bodies, so EVERY consistent state is named and none is chosen.
    candidates=dict(expected['pre_oldham'],OLDHAM_EXACT=expected['oldham'])
    fits={key:sorted(set(inventory)-set(observed)) for key,inventory in candidates.items() if set(observed)<set(inventory) and all(inventory[n]==h for n,h in observed.items())}
    if len(fits)==1:
        (key,missing),=fits.items();return dict(detail,state='MISSING_OBJECTS',reason='PARTIAL_OF_ONE_REVIEWED_STATE',recognised=key,missing=missing)
    if fits:return dict(detail,state='MISSING_OBJECTS',reason='PARTIAL_CONSISTENT_WITH_SEVERAL_REVIEWED_STATES',recognised=None,candidates=sorted(fits),missing_by_candidate=fits)
    return dict(detail,state='UNEXPECTED_OR_MIXED',reason='CONTENT_NOT_A_REVIEWED_STATE',recognised=None)


EXPECTED_FUNCTION_EXECUTE={('ingestion_raise_stop','ingestion_worker_login'):True,('ingestion_worker_step','ingestion_worker_login'):True,('ingestion_worker_step','ingestion_effect_login'):True,('ingestion_worker_step','ingestion_application_login'):False}
# Reviewed grants: application-writer.sql (applications: SELECT, column-level INSERT/UPDATE; lifecycle events: column SELECT(id) and INSERT) and install.sql (the worker may SELECT the work-item ledger). Everything else: none.
EXPECTED_TABLES={('ingestion_application_login','applications'):(True,False,False,False,True,True,True),('ingestion_application_login','application_lifecycle_events'):(False,True,False,False,True,False,True),
                 ('ingestion_worker_login','ingestion_work_items'):(True,False,False,False,False,False,True),('ingestion_worker_login','ingestion_work_attempts'):(True,False,False,False,False,False,True)}


def expected_function_execute(function,login):
    return EXPECTED_FUNCTION_EXECUTE.get((function,login),False)


def expected_table(login,table):
    return EXPECTED_TABLES.get((login,table),(False,)*7)


def evaluate_privileges(function_rows,table_rows):
    """Compare observed privileges with the reviewed grants. Output is fixed codes built only from allow-listed names."""
    discrepancies=[];function_matrix=[];table_matrix=[]
    seen_functions={(f,l) for f,l,_ in function_rows}
    for function,login,granted in function_rows:
        want=expected_function_execute(function,login);function_matrix.append([function,login,granted,want])
        if granted!=want:discrepancies.append('EXECUTE_DIFFERS:%s:%s'%(function,login))
    for function in FUNCTIONS_OF_INTEREST:
        for login in RUNTIME_LOGINS:
            if (function,login) not in seen_functions:function_matrix.append([function,login,None,expected_function_execute(function,login)])      # object or role absent: not a grant either way
    seen_tables={(l,t) for l,t,*_ in table_rows}
    for login,table,*values in table_rows:
        want=expected_table(login,table);table_matrix.append([login,table,list(values),list(want)])
        if tuple(values)!=want:discrepancies.append('TABLE_PRIVILEGE_DIFFERS:%s:%s'%(login,table))
    for login in RUNTIME_LOGINS:
        for table in TABLES_OF_INTEREST:
            if (login,table) not in seen_tables:table_matrix.append([login,table,None,list(expected_table(login,table))])
    return dict(function_execute=function_matrix,table_privileges=table_matrix,columns_of_table_privileges=['select','insert','update','delete','any_column_insert','any_column_update','any_column_select'],discrepancies=sorted(set(discrepancies)))


def project_control(raw):
    """Only the four fields the installed control function exposes, allow-listed. Values are compared with the reviewed constants and never echoed as free text."""
    from .operational_owner import STOP,GENERATION3_STOP
    if not isinstance(raw,dict) or set(raw)!=set(CONTROL_FIELDS):return dict(status='UNEXPECTED_SHAPE')
    generation=raw['hard_stop_generation'];grants=raw['unexpired_grants'];manual=raw['manual_stop']
    return dict(status='OBSERVED',global_stop='MATCHES_CONSUMED_SALFORD_GLOBAL_STOP' if raw['global_stop']==STOP else 'DIFFERS' if raw['global_stop'] is not None else 'ABSENT',
                manual_stop=manual if manual in KNOWN_MANUAL_STOPS else None if manual is None else 'UNRECOGNISED',
                manual_stop_matches_generation3=manual==GENERATION3_STOP['manual_stop'],
                hard_stop_generation=generation if type(generation) is int and 0<=generation<=99 else 'UNRECOGNISED',
                unexpired_grants=grants if type(grants) is int and 0<=grants<=999 else 'UNRECOGNISED',
                exposed_fields=list(CONTROL_FIELDS),not_exposed_by_this_function=list(NOT_EXPOSED_BY_CONTROL_FUNCTION),
                absence_of_uncertainty_barriers='NOT_ESTABLISHED_BY_THIS_INSPECTION',
                reading='The control function reports the global stop, the manual stop, the stop generation and a COUNT of unexpired grants. It does not report last_hard_stop, WRITE_INTENT uncertainty rows, '
                        'per-grant detail or Oldham allowances, so this inspection cannot prove those absent.')


KNOWN_ROLE_NAMES=frozenset(LOGINS)|{'ingestion_worker','ingestion_effect_broker','ingestion_application_writer','ingestion_storage_operator','ingestion_recovery_operator','ingestion_storage_owner','ingestion_barrier_releaser'}
KNOWN_SETTINGS=('statement_timeout','lock_timeout','idle_in_transaction_session_timeout')
KNOWN_STATES=frozenset({'active','idle','idle in transaction','idle in transaction (aborted)','fastpath function call','disabled'})
import re as _re
_DURATION=_re.compile(r'^\d{1,9}(ms|s|min|h)?$')


def reviewed_settings(config):
    """Only the three reviewed timeout settings, and only a plain duration value; everything else is a count, never text."""
    shown={};other=0
    for item in config or []:
        name,_,value=str(item).partition('=')
        if name in KNOWN_SETTINGS and _DURATION.match(value):shown[name]=value
        else:other+=1
    return dict(reviewed=shown,other_settings_count=other)


def project_roles(role_rows,setting_rows,membership_rows,password_visible):
    roles={r[0]:r for r in role_rows};settings={r[0]:r for r in setting_rows}
    members={}
    for member,role,admin,inherit,set_ in membership_rows:members.setdefault(member,[]).append([role if role in KNOWN_ROLE_NAMES else 'OTHER_ROLE',admin,inherit,set_])
    out=[]
    for login in LOGINS:
        r=roles.get(login)
        if r is None:out.append(dict(login=login,exists=False));continue
        s=settings.get(login)
        out.append(dict(login=login,exists=True,can_login=r[1],password_present=r[2] if password_visible else 'UNKNOWN',valid_until=r[3].isoformat() if r[3] else None,connection_limit=r[4],
                        superuser=r[5],createrole=r[6],createdb=r[7],bypassrls=r[8],replication=r[9],settings=reviewed_settings(s[1]) if s else reviewed_settings([]),database_level_settings=s[2] if s else None,
                        memberships=sorted(members.get(login,[]))))
    return out


def project_sessions(rows,visible):
    if not visible:return dict(visibility='UNKNOWN',reason='IDENTITY_LACKS_PG_READ_ALL_STATS')
    counts={};unattributed=0
    for usename,state,backend in rows:
        if usename is None:unattributed+=1;continue
        key=(usename if usename in LOGINS else 'OTHER_ROLE',state if state in KNOWN_STATES else 'OTHER_STATE');counts[key]=counts.get(key,0)+1
    return dict(visibility='PROVEN_BY_PG_READ_ALL_STATS',by_login_and_state=[[u,s,n] for (u,s),n in sorted(counts.items(),key=lambda kv:(str(kv[0][0]),str(kv[0][1])))],unattributed_client_backends=unattributed)


class InspectionRunner(ProbeRunner):
    """Capability-free, like the probe it extends: a connect closure, a journal, a progress record and the native-memory object. Every statement passes `send`."""
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        self.rollbacks=0;self.commits=0;self.inspection=None;self.sent=[];self.in_transaction=False

    def check(self):
        if self.memory is not None:self.memory.snapshot()
        if time.monotonic()-self.started>=BOUND['active_seconds']:raise ProbeDenied('ACTIVE_WINDOW_EXHAUSTED')
        if self.stop_file.exists():raise ProbeDenied('OWNER_STOP')

    def send(self,connection,name,statement,params=None):
        if statement not in allowed():raise ProbeDenied('STATEMENT_UNEXPECTED')           # nothing but the reviewed constants can ever be sent
        if self.statements>=BOUND['driver_statements']:raise ProbeDenied('STATEMENT_BOUND')
        self.check()
        if self.database_seconds_used()>=BOUND['database_seconds']:raise ProbeDenied('ACTIVE_WINDOW_EXHAUSTED')
        self.statements+=1;self.sent.append(name)
        cursor=connection.execute(statement,params) if params is not None else connection.execute(statement)
        rows=cursor.fetchall() if cursor.description else []
        result=cursor.pgresult
        if result is not None:self.returned_bytes+=sum(len(result.get_value(r,k) or b'') for r in range(result.ntuples) for k in range(result.nfields))
        if self.returned_bytes>BOUND['returned_data_value_bytes']:raise ProbeDenied('RESPONSE_BOUND')
        return rows

    def database_seconds_used(self):
        return self.database_seconds+(time.monotonic()-self.connected_at if getattr(self,'connected_at',None) else 0.0)

    def observe(self,connection):
        s=lambda name,statement,params=None:self.send(connection,name,statement,params)
        s('begin',BEGIN);self.in_transaction=True
        identity=tuple(s('identity',IDENTITY)[0])
        if len(identity)!=15:raise ProbeDenied('RESPONSE_SHAPE')
        password_visible=identity[12] is True;sessions_visible=identity[10] is True;control_function_exists=identity[14] is True;control_executable=control_function_exists and identity[13] is True
        control=None
        if control_executable:
            got=s('control',CONTROL);raw=got[0][0] if got and got[0] else None
            control=project_control(raw if isinstance(raw,dict) else json.loads(raw)) if raw is not None else dict(status='SENTINEL_ABSENT',exposed_fields=[],not_exposed_by_this_function=list(NOT_EXPOSED_BY_CONTROL_FUNCTION),absence_of_uncertainty_barriers='NOT_ESTABLISHED_BY_THIS_INSPECTION')
        else:control=dict(status='UNKNOWN',reason='CONTROL_FUNCTION_ABSENT' if not control_function_exists else 'CONTROL_FUNCTION_NOT_EXECUTABLE_BY_THIS_IDENTITY',exposed_fields=[],not_exposed_by_this_function=list(NOT_EXPOSED_BY_CONTROL_FUNCTION),absence_of_uncertainty_barriers='NOT_ESTABLISHED_BY_THIS_INSPECTION')
        roles=s('roles',ROLES_WITH_PASSWORD_PRESENCE if password_visible else ROLES_WITHOUT_PASSWORD_PRESENCE,[list(LOGINS)])
        settings=s('role_settings',ROLE_SETTINGS,[list(LOGINS)]);members=s('memberships',MEMBERSHIPS,[list(LOGINS)])
        sessions=s('sessions',SESSIONS,[list(LOGINS)]) if sessions_visible else []
        functions=s('functions',FUNCTIONS,[function_names()])
        function_privileges=s('function_privileges',FUNCTION_PRIVILEGES,[list(FUNCTIONS_OF_INTEREST),list(RUNTIME_LOGINS)])
        table_privileges=s('table_privileges',TABLE_PRIVILEGES,[list(TABLES_OF_INTEREST),list(RUNTIME_LOGINS)])
        s('rollback',ROLLBACK);self.in_transaction=False;self.rollbacks+=1
        names=('current_user','session_user','superuser','createrole','createdb','bypassrls','storage_owner_usage','storage_owner_set','barrier_releaser_usage','barrier_releaser_set','pg_read_all_stats','pg_signal_backend',
               'pg_authid_password_presence_visible','control_function_executable','control_function_exists')
        view=dict(zip(names,identity))
        about=dict(identity=dict(current_user=view['current_user'] if view['current_user']==EXPECTED_ADMIN else 'OTHER_ACCOUNT',session_user=view['session_user'] if view['session_user']==EXPECTED_ADMIN else 'OTHER_ACCOUNT',is_the_expected_administrative_migration_account=view['current_user']==EXPECTED_ADMIN and view['session_user']==EXPECTED_ADMIN,
                                 superuser=view['superuser'],createrole=view['createrole'],createdb=view['createdb'],bypassrls=view['bypassrls'],
                                 holds_ingestion_storage_owner=dict(usage=view['storage_owner_usage'],set=view['storage_owner_set']),holds_ingestion_barrier_releaser=dict(usage=view['barrier_releaser_usage'],set=view['barrier_releaser_set']),
                                 pg_read_all_stats=view['pg_read_all_stats'],pg_signal_backend=view['pg_signal_backend'],pg_authid_password_presence_visible=password_visible,
                                 character='ADMINISTRATIVE_MIGRATION_ACCOUNT_NOT_A_RESTRICTED_ACCOUNT_READ_ONLY_IS_A_PER_TRANSACTION_GUARD'),
                   control=control,logins=project_roles([tuple(r) for r in roles],[tuple(r) for r in settings],[tuple(r) for r in members],password_visible),
                   sessions=project_sessions([tuple(r) for r in sessions],sessions_visible),functions=classify_functions([tuple(r) for r in functions]),
                   privileges=evaluate_privileges([tuple(r) for r in function_privileges],[tuple(r) for r in table_privileges]))
        return about

    def common(self,components):
        return dict(super().common(components),mode=MODE,inspection_bound=BOUND)

    def rollback_after_failure(self,connection):
        """One bounded ROLLBACK attempt on the failure path, counted like any statement; a broken connection is simply closed (the server aborts an open transaction when the session ends)."""
        if connection is None or not self.in_transaction or getattr(connection,'closed',True) or self.statements>=BOUND['driver_statements']:return
        try:
            self.statements+=1;self.sent.append('rollback_after_failure');connection.execute(ROLLBACK);self.rollbacks+=1
        except BaseException:pass
        self.in_transaction=False

    def execute(self):
        try:
            self.emit('inspection_intent',dict(bound=BOUND,planned_statements=[n for n,_,_ in planned()],statement_sha256s={n:hashlib.sha256(sql.encode()).hexdigest() for n,sql,_ in planned()},absent_capabilities=list(ABSENT_CAPABILITIES)))
            self.check()
            if self.attempts>=BOUND['connection_attempts']:raise ProbeDenied('CONNECTION_ATTEMPT_BOUND')
            self.attempts+=1;begun=time.monotonic();self.phase='DRIVER_CONNECT'
            try:
                self.conn=self.connect();self.opened+=1;self.connected_at=time.monotonic()
                self.emit('connection_opened',dict(attempt=self.attempts))
                self.phase='EXECUTION'
                try:self.inspection=self.observe(self.conn)
                except BaseException:
                    self.rollback_after_failure(self.conn);raise
            finally:
                self.database_seconds+=time.monotonic()-begun;self.connected_at=None
                self.close_connection()
            return self.finish()
        except BaseException as exc:return self.failed(exc)

    def accounting(self):
        base=super().accounting()
        admin=base['administration']
        admin['driver_statements']=dict(value=self.statements,basis='CLIENT_COUNTED_INCLUDING_BEGIN_AND_ROLLBACK',names=list(self.sent),ceiling=BOUND['driver_statements'],planned_maximum=BOUND['planned_statements'])
        admin['rollbacks']=measured(self.rollbacks);admin['commits']=measured(self.commits)
        admin['returned_data_value_bytes']=measured(self.returned_bytes)
        for key in ('role_changes','function_installations','grants_or_exceptions','queue_mutations','credential_generations','secret_mappings','council_requests'):admin[key]=dict(ABSENT)
        return base

    def finish(self):
        components=self.closure();verified=components['overall']=='CLOSED'
        outcome=dict(preparation='COMPLETED',administrative_connection='QUALIFIED_FOR_THIS_INSPECTION_ONLY',failure='NONE',closure='VERIFIED' if verified else 'UNCERTAIN',scope='READ_ONLY_INSPECTION_OF_INSTALLED_STATE',
                     worker_authentication_qualified=False,route_qualified_for_restricted_roles=False,tls_verification='PERFORMED_BY_THE_EXISTING_ROUTE_MECHANISM_AT_THIS_CONNECTION_ONLY')
        return dict(status='OLDHAM_READONLY_INSPECTION_COMPLETE' if verified else 'OLDHAM_READONLY_INSPECTION_COMPLETE_CLOSURE_UNCERTAIN',outcome=outcome,inspection=self.inspection,
                    **self.common(components))


def prepare_inspection(r,raw,started,*,journal,memory,progress,baseline,dns_run=subprocess.run,dns_command=None,connect_factory=None):
    prepared=prepare_connection(r,raw,progress=progress,dns_run=dns_run,dns_command=dns_command)
    connect=prepared.connect
    if connect_factory is not None:
        def connect():
            progress.database_connection_calls+=1
            return connect_factory()
    with progress.stage('RUNNER_CONSTRUCTION'):
        try:return InspectionRunner(journal,connect,progress,memory,baseline=baseline,started=started)
        except (KeyError,TypeError,ValueError,AttributeError):raise PreparationFailure('RUNNER_CONSTRUCTION','RUNNER_CONSTRUCTION_FAILED') from None


REGISTRATION_KEYS=frozenset({'mode','authority','status','expires_at','revision','tree','hashes','controller_sha256','ca_sha256','evidence_directory','limits','absent_capabilities','statements_sha256','state_directory'})


def statements_sha256():
    return hashlib.sha256(json.dumps(sorted(allowed()),sort_keys=True).encode()).hexdigest()


def validate_registration(body,sha):
    if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('REGISTRATION_SHA256')
    r=json.loads(body)
    if not isinstance(r,dict) or set(r)!=REGISTRATION_KEYS:raise ValueError('REGISTRATION_EXACT_KEYS')
    if r['mode']!=MODE or r['authority']!=AUTHORITY or r['status']!=STATUS or r['state_directory']!=STATE:raise ValueError('EXACT_INSPECTION_APPROVAL_REQUIRED')
    if r['limits']!=BOUND or r['absent_capabilities']!=list(ABSENT_CAPABILITIES) or r['statements_sha256']!=statements_sha256():raise ValueError('INSPECTION_LIMITS_OR_BOUNDARY_BINDING')
    expiry=datetime.fromisoformat(r['expires_at']);now=datetime.now(timezone.utc)
    if expiry.tzinfo is None or not now<expiry<=now+timedelta(hours=2):raise ValueError('INSPECTION_EXPIRY')
    if r['evidence_directory']!=EVIDENCE_DIRECTORY or not isinstance(r['hashes'],dict) or not r['hashes']:raise ValueError('EVIDENCE_BINDING')
    manifest=json.loads((Path(EVIDENCE_DIRECTORY)/'MANIFEST.json').read_text())
    if set(r['hashes'])!=set(manifest['bound_paths']):raise ValueError('HASHES_MUST_EQUAL_MANIFEST')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if revision!=r['revision'] or subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip()!=r['tree'] or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('CLEAN_REVIEWED_CHECKOUT')
    for path,digest_ in r['hashes'].items():
        p=Path(path)
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest_:raise ValueError('REVIEWED_CONTENT_BINDING')
    if r['controller_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest() or r['ca_sha256']!=PEM_SHA256:raise ValueError('CONTROLLER_CA_BINDING')
    return r


def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',type=Path,required=True);p.add_argument('--registration-sha256',required=True);a=p.parse_args()
    if sys.platform!='linux' or not sys.stdin.isatty() or not sys.stderr.isatty():raise SystemExit('OWNER_LINUX_SECURE_TTY_REQUIRED')
    if any(k.startswith('PG') for k in os.environ):raise SystemExit('LIBPQ_ENVIRONMENT_OVERRIDE')
    if any(os.environ.get(k) for k in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN')):raise SystemExit('NO_GITHUB_CREDENTIAL_PERMITTED_IN_INSPECTION')
    if a.registration.is_symlink() or a.registration.stat().st_size>16384:raise SystemExit('REGISTRATION_BOUND')
    r=validate_registration(a.registration.read_bytes(),a.registration_sha256)
    from .operational_memory import OperationalMemory
    memory=OperationalMemory()                                                  # positive kernel enforcement BEFORE any credential is read
    state=Path.home()/'.local/state/propertyaigent';state.mkdir(mode=0o700,exist_ok=True,parents=True)
    journal=Journal(state/r['state_directory'])                                 # exclusive create: a second use of the same authority cannot start
    journal.emit('consumed',dict(authority=r['authority'],registration_sha256=a.registration_sha256))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    progress=Progress();baseline=owned_resources()
    prepare=lambda raw,started:prepare_inspection(r,raw,started,journal=journal,memory=memory,progress=progress,baseline=baseline)
    result=session(journal,r['expires_at'],hidden_input,prepare,memory=memory,timing=TIMING,progress=progress,baseline=baseline)
    ok=result.get('status')=='OLDHAM_READONLY_INSPECTION_COMPLETE' and result.get('cleanup')=='CLOSED'
    raise SystemExit(0 if ok else 1)


if __name__=='__main__':main()
