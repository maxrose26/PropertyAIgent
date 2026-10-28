"""Offline proof of the fixed Oldham read-only inspection (no database, no network, no credential). Synthetic rows only."""
import ast,hashlib,json,re,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest
from verification.ingestion_storage import oldham_inspection as oi
from verification.ingestion_storage import admin_connection_probe as ap
from verification.ingestion_storage.operational_preparation import STARTUP_OPTIONS

OWNER='ingestion_storage_owner';CONFIG=['search_path=pg_catalog']


def rows_for(inventory,*,owner=OWNER,config=CONFIG,arguments=None):
    out=[]
    for name,sha in sorted(inventory.items()):
        args=arguments if arguments is not None else (oi.OLDHAM_HELPER_ARGUMENTS if name==oi.OLDHAM_HELPER else '')
        out.append((name,sha,owner,config,name==oi.OLDHAM_HELPER or name.endswith('_stop'),args))
    return out


def e():return oi.expected_states()


# --- the closed statement list -----------------------------------------------------------------------------------------------------------------------------
def test_every_variant_fits_the_unchanged_twelve_statement_ceiling_and_the_maximum_is_eleven():
    sizes=[len(oi.planned(a,b,c)) for a in (True,False) for b in (True,False) for c in (True,False)]
    assert max(sizes)==oi.BOUND['planned_statements']==11 and min(sizes)==9 and oi.BOUND['driver_statements']==12      # the ceiling is not raised; rollback-after-failure still fits
    assert [n for n,_,_ in oi.planned()]==['begin','identity','control','roles','role_settings','memberships','sessions','functions','function_privileges','table_privileges','rollback']


def literal_free(statement):return re.sub(r"'[^']*'",'',statement)


def test_every_statement_is_a_single_plain_select_or_the_two_transaction_markers():
    for statement in oi.allowed():
        body=literal_free(statement)
        assert ';' not in body
        if statement in (oi.BEGIN,oi.ROLLBACK):continue
        assert body.lstrip().upper().startswith('SELECT')
        assert not re.search(r'\b(GRANT|REVOKE|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE|ALTER|DROP|TRUNCATE|COPY|CALL|LOCK|COMMIT|SET\s+ROLE|RESET|FOR\s+UPDATE|FOR\s+SHARE|INTO)\b',body,re.I),statement
    assert oi.BEGIN=='BEGIN READ ONLY' and oi.ROLLBACK=='ROLLBACK' and not [s for s in oi.allowed() if re.match(r'\s*(COMMIT|END|SET|GRANT)',s,re.I)]


def test_the_module_cannot_reach_a_mutating_capability():
    tree=ast.parse(Path(oi.__file__).read_text())
    imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
    modules={(n.module or '')+'.'+a.name if isinstance(n,ast.ImportFrom) else a.name for n in imports for a in n.names}
    forbidden=('github','credential_mapping','storage_controller','oldham_owner','operational_runner','operational_source','secret','requests','urllib','socket','http')
    assert not [m for m in modules if any(f in m.lower() for f in forbidden)],modules
    assert not hasattr(oi,'Owner') and not hasattr(oi,'OldhamOwner') and not hasattr(oi,'Runner')


def test_owner_is_never_instantiated(monkeypatch):
    from verification.ingestion_storage.operational_owner import Owner
    def boom(*a,**k):raise AssertionError('Owner constructed')
    monkeypatch.setattr(Owner,'__init__',boom)
    oi._EXPECTED=None;oi.expected_states();oi.classify_functions([]);oi.function_names();oi.planned()      # the inventories come from classmethods only


def test_the_gate_refuses_any_other_statement_and_the_bound_counts_every_driver_statement():
    class Conn:
        closed=False
        def __init__(self):self.sent=[]
        def execute(self,*a,**k):self.sent.append(a[0]);raise AssertionError('reached the driver')
    runner=oi.InspectionRunner.__new__(oi.InspectionRunner);runner.statements=0;runner.sent=[];runner.returned_bytes=0;runner.memory=None;runner.stop_file=Path('/nonexistent-stop');runner.started=__import__('time').monotonic();runner.database_seconds=0.0
    conn=Conn()
    for bad in ('SELECT 1','GRANT ingestion_storage_owner TO CURRENT_USER','SET ROLE ingestion_storage_owner','COMMIT',oi.CONTROL+';SELECT 1','select current_user'):
        with pytest.raises(ap.ProbeDenied,match='STATEMENT_UNEXPECTED'):runner.send(conn,'x',bad)
    assert conn.sent==[] and runner.statements==0


# --- function-state classification --------------------------------------------------------------------------------------------------------------------------
def test_the_retained_v3_installation_is_recognised_as_pre_oldham():
    got=oi.classify_functions(rows_for(e()['pre_oldham']['GENERATION3_SCREENING_V3_APPLIED']))
    assert (got['state'],got['recognised'],got['is_the_retained_v3_state'],got['oldham_helper_present'])==('RECOGNISED_PRE_OLDHAM','GENERATION3_SCREENING_V3_APPLIED',True,False)


def test_every_other_historical_reviewed_state_is_recognised_but_not_called_the_retained_one():
    for name,inventory in e()['pre_oldham'].items():
        if name=='GENERATION3_SCREENING_V3_APPLIED':continue
        got=oi.classify_functions(rows_for(inventory))
        assert got['state']=='RECOGNISED_PRE_OLDHAM' and e()['pre_oldham'][got['recognised']]==inventory and got['is_the_retained_v3_state'] is False


def test_the_exact_reviewed_oldham_installation_is_recognised():
    got=oi.classify_functions(rows_for(e()['oldham']))
    assert (got['state'],got['recognised'],got['oldham_helper_signature_and_definer_as_reviewed'])==('OLDHAM_EXACT_INSTALLATION','OLDHAM_EXACT',True)


def test_nothing_installed_is_reported_as_not_installed_not_as_a_failure():
    assert oi.classify_functions([])['state']=='NOT_INSTALLED'


def test_missing_objects_are_distinguished_from_unexpected_content():
    inventory=dict(e()['pre_oldham']['GENERATION3_SCREENING_V3_APPLIED']);inventory.pop('ingestion_register_bolton_exception')
    got=oi.classify_functions(rows_for(inventory))
    assert (got['state'],got['reason'],got['recognised'],got['missing'])==('MISSING_OBJECTS','PARTIAL_OF_ONE_REVIEWED_STATE','GENERATION3_SCREENING_V3_APPLIED',['ingestion_register_bolton_exception'])
    changed=dict(e()['pre_oldham']['GENERATION3_SCREENING_V3_APPLIED']);changed['ingestion_bolton_allowed']='0'*64
    assert oi.classify_functions(rows_for(changed))['state']=='UNEXPECTED_OR_MIXED'


def test_a_mixed_installation_is_never_blended_into_either_state():
    v3=dict(e()['pre_oldham']['GENERATION3_SCREENING_V3_APPLIED']);old=e()['oldham']
    helper_with_v3_worker={**v3,oi.OLDHAM_HELPER:old[oi.OLDHAM_HELPER]}            # the Oldham helper beside the unsubstituted v3 worker
    got=oi.classify_functions(rows_for(helper_with_v3_worker))
    assert got['state']=='UNEXPECTED_OR_MIXED' and got['recognised'] is None and got['oldham_helper_present'] is True
    worker_without_helper={**v3,'ingestion_worker_step':old['ingestion_worker_step']}   # the Oldham worker whose helper is absent: named as missing, never as either complete state
    got=oi.classify_functions(rows_for(worker_without_helper))
    assert (got['state'],got['recognised'],got['missing'],got['oldham_helper_present'])==('MISSING_OBJECTS','OLDHAM_EXACT',[oi.OLDHAM_HELPER],False)


def test_owner_search_path_signature_and_overloads_are_unexpected_even_when_bodies_match():
    v3=e()['pre_oldham']['GENERATION3_SCREENING_V3_APPLIED']
    assert oi.classify_functions(rows_for(v3,owner='postgres'))['state']=='UNEXPECTED_OR_MIXED'
    assert oi.classify_functions(rows_for(v3,config=['search_path=public']))['state']=='UNEXPECTED_OR_MIXED'
    assert oi.classify_functions(rows_for(v3,config=None))['state']=='UNEXPECTED_OR_MIXED'
    assert oi.classify_functions(rows_for(e()['oldham'],arguments='x integer'))['state']=='UNEXPECTED_OR_MIXED'
    twice=rows_for(v3)+[rows_for(v3)[0]]
    got=oi.classify_functions(twice);assert (got['state'],got['reason'])==('UNEXPECTED_OR_MIXED','OVERLOADED_FUNCTION_NAME')


# --- privileges ---------------------------------------------------------------------------------------------------------------------------------------------
def reviewed_privileges():
    functions=[(f,l,oi.expected_function_execute(f,l)) for f in oi.FUNCTIONS_OF_INTEREST for l in oi.RUNTIME_LOGINS]
    tables=[(l,t,*oi.expected_table(l,t)) for l in oi.RUNTIME_LOGINS for t in oi.TABLES_OF_INTEREST]
    return functions,tables


def test_reviewed_privileges_report_no_discrepancy():
    assert oi.evaluate_privileges(*reviewed_privileges())['discrepancies']==[]


@pytest.mark.parametrize('index,login,function,code',[(0,'ingestion_worker_login','ingestion_oldham_allowed','EXECUTE_DIFFERS:ingestion_oldham_allowed:ingestion_worker_login'),
    (1,'ingestion_application_login','ingestion_worker_step','EXECUTE_DIFFERS:ingestion_worker_step:ingestion_application_login'),(2,'ingestion_effect_login','ingestion_acceptance_control','EXECUTE_DIFFERS:ingestion_acceptance_control:ingestion_effect_login')])
def test_function_privilege_discrepancies_are_reported_as_fixed_codes(index,login,function,code):
    functions,tables=reviewed_privileges()
    functions=[(f,l,(not g) if (f,l)==(function,login) else g) for f,l,g in functions]
    assert oi.evaluate_privileges(functions,tables)['discrepancies']==[code]


def test_table_privilege_discrepancies_and_missing_objects_are_distinguished():
    functions,tables=reviewed_privileges()
    widened=[row if (row[0],row[1])!=('ingestion_application_login','applications') else (row[0],row[1],True,True,False,False,True,True,True) for row in tables]
    assert oi.evaluate_privileges(functions,widened)['discrepancies']==['TABLE_PRIVILEGE_DIFFERS:ingestion_application_login:applications']
    result=oi.evaluate_privileges([f for f in functions if f[0]!='ingestion_oldham_allowed'],tables)
    assert result['discrepancies']==[] and [r for r in result['function_execute'] if r[0]=='ingestion_oldham_allowed' and r[2] is None]      # an absent object is not a grant either way
    assert not oi.evaluate_privileges(functions,[t for t in tables if t[0]!='ingestion_application_login'])['discrepancies']      # an absent login yields no grant claim


# --- the control function's honesty ------------------------------------------------------------------------------------------------------------------------
def test_control_projection_states_exactly_what_the_function_exposes_and_does_not_prove_barriers_absent():
    from verification.ingestion_storage.operational_owner import STOP
    got=oi.project_control(dict(global_stop=STOP,manual_stop='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE',hard_stop_generation=3,unexpired_grants=0))
    assert got['status']=='OBSERVED' and got['global_stop']=='MATCHES_CONSUMED_SALFORD_GLOBAL_STOP' and got['manual_stop_matches_generation3'] is True and got['hard_stop_generation']==3 and got['unexpired_grants']==0
    assert got['exposed_fields']==['global_stop','manual_stop','hard_stop_generation','unexpired_grants']
    assert {'last_hard_stop','WRITE_INTENT_uncertainty_barrier_rows','oldham_allowances','per_grant_detail'}<=set(got['not_exposed_by_this_function'])
    assert got['absence_of_uncertainty_barriers']=='NOT_ESTABLISHED_BY_THIS_INSPECTION' and 'cannot prove those absent' in got['reading']


def test_control_values_are_allow_listed_never_echoed_as_free_text():
    hostile=dict(global_stop={'reason':'x'*500},manual_stop='SECRET postgresql://u:p@h/db',hard_stop_generation=10**9,unexpired_grants='postgresql://u:p@h/db')
    got=oi.project_control(hostile);blob=json.dumps(got)
    assert 'postgresql' not in blob and 'xxxx' not in blob and got['manual_stop']=='UNRECOGNISED' and got['hard_stop_generation']=='UNRECOGNISED' and got['global_stop']=='DIFFERS'
    assert oi.project_control({'unexpected':1})['status']=='UNEXPECTED_SHAPE' and oi.project_control('postgresql://x')['status']=='UNEXPECTED_SHAPE'


# --- logins and sessions ------------------------------------------------------------------------------------------------------------------------------------
def test_a_missing_application_login_and_hidden_password_presence_are_reported_not_guessed():
    when=datetime(2027,1,17,tzinfo=timezone.utc)
    roles=[('ingestion_worker_login',True,None,when,1,False,False,False,False,False)]
    out=oi.project_roles(roles,[],[('ingestion_worker_login','ingestion_worker',False,True,False)],password_visible=False)
    by={r['login']:r for r in out}
    assert by['ingestion_application_login']=={'login':'ingestion_application_login','exists':False} and by['ingestion_worker_login']['password_present']=='UNKNOWN'
    assert by['ingestion_worker_login']['memberships']==[['ingestion_worker',False,True,False]]


def test_sessions_are_unknown_without_pg_read_all_stats_and_counted_with_it():
    assert oi.project_sessions([],False)['visibility']=='UNKNOWN'
    got=oi.project_sessions([('ingestion_worker_login','idle','client backend'),('ingestion_worker_login','idle','client backend'),(None,None,'client backend')],True)
    assert got['by_login_and_state']==[['ingestion_worker_login','idle',2]] and got['unattributed_client_backends']==1


# --- registration -------------------------------------------------------------------------------------------------------------------------------------------
def registration(**changes):
    r=dict(mode=oi.MODE,authority=oi.AUTHORITY,status=oi.STATUS,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),revision='a'*40,tree='b'*40,hashes={'x':'0'*64},controller_sha256='c'*64,
           ca_sha256=oi.PEM_SHA256,evidence_directory=oi.EVIDENCE_DIRECTORY,limits=dict(oi.BOUND),absent_capabilities=list(oi.ABSENT_CAPABILITIES),statements_sha256=oi.statements_sha256(),state_directory=oi.STATE)
    r.update(changes);return r


def seal(r):
    body=json.dumps(r,sort_keys=True).encode();return body,hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize('change,code',[(dict(mode='OTHER'),'EXACT_INSPECTION_APPROVAL_REQUIRED'),(dict(authority='AUTHORISE_OTHER'),'EXACT_INSPECTION_APPROVAL_REQUIRED'),(dict(state_directory='x'),'EXACT_INSPECTION_APPROVAL_REQUIRED'),
    (dict(limits={**oi.BOUND,'driver_statements':13}),'INSPECTION_LIMITS_OR_BOUNDARY_BINDING'),(dict(statements_sha256='0'*64),'INSPECTION_LIMITS_OR_BOUNDARY_BINDING'),
    (dict(absent_capabilities=[]),'INSPECTION_LIMITS_OR_BOUNDARY_BINDING'),(dict(expires_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()),'INSPECTION_EXPIRY'),
    (dict(expires_at=(datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()),'INSPECTION_EXPIRY'),(dict(evidence_directory='docs/design/other'),'EVIDENCE_BINDING')])
def test_registration_is_exact_single_use_and_short_lived(change,code):
    body,sha=seal(registration(**change))
    with pytest.raises(ValueError,match=code):oi.validate_registration(body,sha)


def test_registration_hash_and_key_set_are_exact():
    body,sha=seal(registration())
    with pytest.raises(ValueError,match='REGISTRATION_SHA256'):oi.validate_registration(body,'0'*64)
    extra=registration();extra['surprise']=1;body,sha=seal(extra)
    with pytest.raises(ValueError,match='REGISTRATION_EXACT_KEYS'):oi.validate_registration(body,sha)


def test_main_refuses_without_a_secure_terminal_and_the_historical_probe_is_untouched(monkeypatch):
    monkeypatch.setattr(sys,'argv',['x','--registration','/nonexistent','--registration-sha256','0'*64])
    with pytest.raises(SystemExit,match='OWNER_LINUX_SECURE_TTY_REQUIRED'):oi.main()
    assert ap.STATEMENT=='SELECT current_user' and ap.LIMITS['driver_statements']==1 and ap.MODE=='ADMIN_CONNECTION_PROBE_ONLY'


def test_the_package_manifest_is_complete_and_the_registration_renders_offline():
    root=Path(__file__).resolve().parent.parent;d=root/'docs/design/oldham-readonly-inspection-20261028'
    manifest=json.loads((d/'MANIFEST.json').read_text())
    assert not [p for p in manifest['bound_paths'] if not (root/p).is_file()] and manifest['status']=='PREPARED_FOR_REVIEW_NOT_RELEASED'
    assert {'verification/ingestion_storage/oldham_inspection.py','docs/design/oldham-readonly-inspection-20261028/owner-run.sh','specifications/038-oldham-readonly-inspection.md'}<=set(manifest['bound_paths'])
    sys.path.insert(0,str(d));import render_registration
    r=render_registration.render(root=root,minutes=30)
    assert set(r)==oi.REGISTRATION_KEYS and r['limits']==oi.BOUND and r['statements_sha256']==oi.statements_sha256() and set(r['hashes'])==set(manifest['bound_paths'])
    text=(d/'PACKAGE.md').read_text()
    for statement in oi.allowed():assert statement in text      # the package lists every statement the controller can send, including the variant forms
    assert 'NOT AUTHORISED FOR EXECUTION' in text and 'NOT AUTHORISED FOR EXECUTION' in (d/'owner-run.sh').read_text()


def test_a_partial_installation_that_fits_several_reviewed_states_names_all_and_chooses_none():
    lone=e()['pre_oldham']['GENERATION3_SCREENING_V3_APPLIED']['ingestion_bolton_allowed']
    got=oi.classify_functions(rows_for({'ingestion_bolton_allowed':lone}))
    assert got['state']=='MISSING_OBJECTS' and got['recognised'] is None and got['reason']=='PARTIAL_CONSISTENT_WITH_SEVERAL_REVIEWED_STATES' and len(got['candidates'])>1 and 'GENERATION3_SCREENING_V3_APPLIED' in got['candidates']
    inventory=dict(e()['pre_oldham']['GENERATION3_SCREENING_V3_APPLIED']);inventory.pop('ingestion_register_bolton_exception')
    wrong_owner=oi.classify_functions(rows_for(inventory,owner='provisioning_bootstrap'))      # a partial installation with a changed owner is not offered as merely 'missing objects'
    assert wrong_owner['state']=='UNEXPECTED_OR_MIXED' and wrong_owner['reason']=='PARTIAL_WITH_OWNER_OR_SEARCH_PATH_CHANGED'


def test_the_verdict_states_what_it_checked_and_what_it_did_not():
    got=oi.classify_functions(rows_for(e()['oldham']))
    assert got['reason']=='BODY_OWNER_SEARCH_PATH_MATCH' and 'volatility' in got['not_checked'] and 'body_sha256_equals_reviewed' in got['checked']


def test_free_text_from_the_database_is_never_echoed():
    out=oi.reviewed_settings(['statement_timeout=10s','application_name=canary-77','lock_timeout=postgresql://u:p@h/db','search_path=canary'])
    assert out=={'reviewed':{'statement_timeout':'10s'},'other_settings_count':3} and 'canary' not in json.dumps(out)
    roles=[('ingestion_worker_login',True,True,None,1,False,False,False,False,False)]
    got=oi.project_roles(roles,[('ingestion_worker_login',['application_name=canary-77'],0)],[('ingestion_worker_login','canary-role',False,True,False)],True)
    assert 'canary' not in json.dumps(got) and got[0]['memberships']==[['OTHER_ROLE',False,True,False]]
    sess=oi.project_sessions([('canary_user','canary state','client backend'),('ingestion_worker_login','idle','client backend')],True)
    assert 'canary' not in json.dumps(sess) and ['OTHER_ROLE','OTHER_STATE',1] in sess['by_login_and_state']


def test_the_reviewed_privilege_matrix_covers_seven_functions_and_four_tables_with_source_backed_expectations():
    assert len(oi.FUNCTIONS_OF_INTEREST)==7 and len(oi.TABLES_OF_INTEREST)==4
    assert oi.expected_function_execute('ingestion_raise_stop','ingestion_worker_login') is True and oi.expected_function_execute('ingestion_raise_stop','ingestion_effect_login') is False
    assert oi.expected_function_execute('ingestion_recover_abandoned','ingestion_worker_login') is False
    assert oi.expected_table('ingestion_worker_login','ingestion_work_attempts')==(True,False,False,False,False,False,True)
