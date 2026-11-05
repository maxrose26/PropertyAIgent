"""Fixed read-only hosted preflight; no recovery or intake dispatcher.
Pure identity/receipt validators copied unchanged from PR207 54700366.
"""
import copy,hashlib,json,os,re
from contextlib import contextmanager
from . import intake_owner as op
from . import owner_pilot as pilot
from .database_evidence import canonical,verify_inventory

PERIOD='b-dbpilot-20261027-1102-06'
SUCCESSOR='b-dbpilot-20261027-1102-07'
SCOPE=dict(kind='DISCOVERY_SCOPE',council='tameside',start='2026-10-27',end='2026-11-02',semantics='RECEIVED')
RUN='f0afadd31d56467580ce61b51bbf19a3'
JOB='job-dblr422jnfac73d8eaeg'
KEY='dc8ae276a9c3f697b9905adf0ec8835398009769b69e788e4fd70e13216ee6fc'
AUTHORITY='INGESTION_CHAIN_TAMESIDE_CAPTURE_6111B8A8125C'
BINDING=dict(revision='da8959d06bea35da5104fe6638aa566952004853',workflow_sha256='5b87c6cbef2944fa05468314fc6daefc19b785644b04e04d1ff382b0596cadea',manifest_sha256='6e223d11ad74799688a9c18d3b245d3d2908abc4f806dc5507eb5c5ccab2c77a')
EVIDENCE={'final/result-before-publication.json':'3386dfb045fe64cd149faea835a0b377b7d25e3733eb53e31fd6687644de1e11','final/events-before-publication.json':'8a23b2641ce84002f7c726aa9de6681570b7d12ce8f874fc639910cf03ee0294'}
STOP6=dict(global_stop={'reason':'DAILY_INTAKE_SHARED_FAILURE'},manual_stop='DAILY_INTAKE_SHARED_FAILURE',last_hard_stop='DAILY_INTAKE_SHARED_FAILURE',hard_stop_generation=6)
STOP7=dict(STOP6,manual_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',last_hard_stop='ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP',hard_stop_generation=7)
ACCEPTED=dict(STOP7,global_stop=None,manual_stop=None)
ROLE='ingestion_recovery_operator'

def sha(value):return hashlib.sha256(canonical(value)).hexdigest()

def marker_valid(marker):
    op.require(type(marker) is dict and marker.get('id')==RUN and marker.get('period')==PERIOD and marker.get('state')=='OPEN' and marker.get('day')=='2026-11-02' and marker.get('publication_path')=='docs/design/ingestion-operational-execution-daily-intake/'+PERIOD+'/'+RUN+'/final/result-before-publication.json','A06_RUN_IDENTITY')

def receipt(marker):
    marker_valid(marker)
    return dict(version='ATTEMPT06_RECOVERY_V1',original_marker=copy.deepcopy(marker),period=PERIOD,run_id=RUN,job_id=JOB,
        execution_binding=BINDING,evidence=EVIDENCE,successor=SUCCESSOR,status='FAILED_RECONCILED',actual_requests=None,
        request_count_status='UNKNOWN',historical_cause='UNKNOWN',manchester='NOT_ATTEMPTED',recovered_key=KEY,
        recovered_fence=2,source_or_write_replay_authorised=False,stop_before=STOP6,stop_after=STOP7)

def predecessor06(state,*,snapshot):
    """Reuse existing encrypted credentials only from the exact closed Attempt06 job."""
    op.require(type(state) is dict and state.get('period')==PERIOD and state.get('status')=='CLOSED' and state.get('job',{}).get('id')==JOB
        and state.get('binding',{}).get('period')==PERIOD and state['binding'].get('execution_binding')==BINDING
        and state.get('access',{}).get('state')=='DATABASE_CLOSURE_ACKNOWLEDGED'
        and state['access'].get('render',{}).get('state') in ('RESTORATION_ACKNOWLEDGED','RESTORATION_VERIFIED_BY_READBACK')
        and state.get('closure_verification',{}).get('status')=='VERIFIED'
        and state.get('closure_verification',{}).get('authorities_closed') is True
        and state.get('closure_verification',{}).get('sessions')==0
        and state.get('final_service')==dict(suspended=True,configuration_equal=True,environment_equal=True)
        and state.get('stable_credentials',{}).get('version')=='STABLE_RESTRICTED_V1'
        and set(state['stable_credentials'].get('passwords',{}))==set(op.ROLES)
        and set(state['stable_credentials'].get('verifier_sha256',{}))==set(op.ROLES),'A06_PREDECESSOR_CLOSURE')
    return dict(period=PERIOD,job_id=JOB,snapshot=snapshot,state_sha256=sha(state),source_requests='UNKNOWN',manchester='NOT_ATTEMPTED',execution_identity=SUCCESSOR)


RELEASE=dict(revision='54700366bab5434a5cda30abc853e0dc6dcc5d33',workflow_sha256='e5289d43dbd05f2ffa051529c4feeb6aa32fb719c621de00df3638e077bf78e4',manifest_sha256='482e137a9a62fdd1007ee351845a4fc2c0825693dfc3472217c2ac8d4c3b74fc')
CHECKS=('identity_inventory','journal','dormant','permissions','attempt06','evidence','successor_unused','release','provider')

class ReadOnly:
    """Additional statement boundary, on top of PostgreSQL READ ONLY."""
    def __init__(self,c):self.c=c
    def execute(self,statement,params=None):
        op.require(type(statement) is str and statement.lstrip().upper().startswith('SELECT ') and ';' not in statement,'P07_SELECT_ONLY')
        return self.c.execute(statement,params)

@contextmanager
def same_connection(db,c):
    class View:
        key=db.key
        @contextmanager
        def connection(self):yield c
    yield View()

def permissions(c):
    op.owner_absent(c);op.admin_capabilities(c)
    for role in ('ingestion_storage_owner','ingestion_recovery_operator','ingestion_barrier_releaser'):
        rows=c.execute('SELECT grantor::regrole::text,admin_option,inherit_option,set_option FROM pg_auth_members WHERE roleid=%s::regrole AND member=current_user::regrole',(role,)).fetchall()
        op.require(len(rows)==1 and rows[0][0]!='postgres' and rows[0][1:]==(True,False,False),'P07_ADMIN_ONLY_REQUIRED')
        op.require(c.execute("SELECT pg_has_role(current_user,%s,'USAGE'),pg_has_role(current_user,%s,'SET')",(role,role)).fetchone()==(False,False),'P07_TEMPORARY_PERMISSION_PRESENT')
    op.require(c.execute("SELECT has_function_privilege('ingestion_recovery_operator','public.ingestion_recover_abandoned(text,integer,boolean)','EXECUTE')").fetchone()==(True,),'P07_RECOVERY_EXECUTE')
    op.require(c.execute("SELECT has_function_privilege(current_user,'public.ingestion_intake_owner_state(text,text,text,bytea)','EXECUTE'),has_function_privilege(current_user,'public.ingestion_intake_evidence_read(text,text,text)','EXECUTE')").fetchone()==(True,True),'P07_OWNER_READERS')
    op.require(c.execute("SELECT count(*) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a WHERE n.nspname='public' AND a.grantee=current_user::regrole AND a.privilege_type='CREATE' AND a.is_grantable").fetchone()[0]>0,'P07_SCHEMA_GRANTABILITY')

def attempt(c,ctl):
    marker_valid(ctl.get('intake_run'))
    op.require(op.stop_snapshot(ctl)==STOP6,'A06_STOP_DRIFT')
    p=ctl.get('intake_periods',{}).get(PERIOD,{})
    op.require(p.get('execution_binding')==BINDING and p.get('evidence_backend')=='POSTGRES_PILOT_V1' and p.get('fixed_window')=={'start':'2026-10-27','end':'2026-11-02'} and p.get('max_runs')==1 and set(p.get('councils',{}))=={'tameside','manchester'} and p.get('days')=={'2026-11-02':{'tameside':KEY}} and not p.get('failed_runs') and not p.get('failure_disposition'),'A06_PERIOD_BINDING')
    g=ctl.get('grants',{}).get(AUTHORITY,{})
    op.require(g.get('intake_run')==RUN and g.get('intake_period')==PERIOD and g.get('capture_key')==KEY and g.get('execution_binding')==BINDING and type(g.get('expires_at')) is int and g['expires_at']==0,'A06_GRANT_BINDING')
    op.retained_cleanup(c,ctl)
    op.require(all(type(g.get('expires_at')) in (int,float) and g['expires_at']==0 for g in ctl.get('grants',{}).values()),'P07_AUTHORITY_NOT_CLOSED')
    row=c.execute('SELECT authority,revision,state,phase,fence,attempt_count,checkpoint,lease_until<extract(epoch FROM clock_timestamp()),task,contract,subject::jsonb FROM public.ingestion_work_items WHERE key=%s',(KEY,)).fetchone()
    op.require(row==(AUTHORITY,PERIOD+'-2026-11-02-tameside','CLAIMED','SOURCE_INTENT',1,1,None,True,'DISCOVERY','tameside-screening-metadata-five-v1',SCOPE),'A06_ITEM_BINDING')
    op.require(c.execute('SELECT fence,phase,finished_at,checkpoint,authority FROM public.ingestion_work_attempts WHERE work_key=%s',(KEY,)).fetchall()==[(1,'SOURCE_INTENT',None,None,AUTHORITY)],'A06_ATTEMPT_BINDING')
    op.require(c.execute("SELECT count(*) FROM public.ingestion_work_items WHERE key<>%s AND (phase IN ('SOURCE_INTENT','WRITE_INTENT') OR state='PERSISTENCE_UNCERTAIN' OR revision=%s OR authority=%s)",(KEY,PERIOD+'-2026-11-02-manchester',AUTHORITY)).fetchone()==(0,),'A06_OTHER_WORK')

def evidence(c):
    # One existing owner-only read interface; no raw source/event bodies exported.
    for name,h in EVIDENCE.items():
        op.require(c.execute("SELECT encode(sha256(public.ingestion_intake_evidence_read(%s,%s,%s)),'hex')",(PERIOD,RUN,name)).fetchone()==(h,),'A06_EVIDENCE')
    # Direct table access is not assumed. Exact absence of other archives is
    # checked only if this identity already has SELECT; no temporary grant.
    if not c.execute("SELECT has_table_privilege(current_user,'public.ingestion_run_evidence','SELECT')").fetchone()[0]:return 'UNVERIFIED'
    op.require(c.execute('SELECT name FROM public.ingestion_run_evidence WHERE period=%s AND run_id=%s ORDER BY name',(PERIOD,RUN)).fetchall()==[(n,) for n in sorted(EVIDENCE)],'A06_EVIDENCE')
    return 'PASS'

def provider(api):
    service=api.call('GET');pilot.service_guard(service)
    op.require(service.get('id')==pilot.SERVICE and service.get('ownerId')==pilot.WORKSPACE and service.get('suspended')=='suspended' and service.get('autoDeploy')=='no' and service['serviceDetails']['plan']=='standard' and service['serviceDetails']['envSpecificDetails']['startCommand']=='/bin/true','P07_SCRAPER_STATE')
    pilot.complete_inventory(api.call('GET','/jobs?limit=100'),'job')
    pilot.complete_inventory(api.call('GET','/deploys?limit=100'),'deploy')
    op.require(api.call('GET','/secret-files?limit=100')==[],'P07_SECRET_FILES')
    # Compare names only; provider values stay in process and are never returned.
    env=pilot.env_values(api.call('GET','/env-vars?limit=100'))
    op.require(set(env)=={'DATABASE_URL','PLANNING_STATUS_VERIFICATION_ENABLED','PLAYWRIGHT_BROWSERS_PATH','PYTHONUNBUFFERED'},'P07_SCRAPER_ENVIRONMENT')

class Refusal(Exception):pass

def run(*,db_factory=pilot.Database,render_factory=None,environ=None):
    env=os.environ if environ is None else environ
    out=dict(version='PERIOD07_READONLY_PREFLIGHT_V1',period=SUCCESSOR,status='REFUSED',checks={k:'UNVERIFIED' for k in CHECKS},database_writes=0,journal_writes=0,provider_mutations=0,job_submissions=0,transaction='NOT_STARTED',
      capabilities={'actual_grant_execution':'UNVERIFIED','deployment_permission':'UNVERIFIED','inherited_dashboard_isolation':'UNVERIFIED','successor_artifact_readback':'UNVERIFIED','exact_archive_inventory':'UNVERIFIED'},binding_hashes={})
    def check(name,fn):
        try:value=fn();out['checks'][name]='PASS';return value
        except Exception as exc:
            out['checks'][name]='REFUSED'
            # Phase labels are fixed, not exception messages or private values.
            state=getattr(exc,'sqlstate',None)
            if state in ('42501','28P01','28000','57014','25006'):out.setdefault('sqlstates',{})[name]=state
            raise Refusal() from None
    try:
        db=db_factory()
        with db.connection() as raw:
            raw.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');out['transaction']='READ_ONLY'
            try:
                c=ReadOnly(raw)
                def inventory():op.identity(c);op.inventory(c);verify_inventory(c)
                check('identity_inventory',inventory)
                def journal():
                    with same_connection(db,c) as view:
                        j=pilot.Journal(view,PERIOD);s=j.load()
                    predecessor06(s,snapshot=dict(ordinal=j.ordinal,bytes=j.ciphertext_bytes,sha256=j.previous))
                    out['binding_hashes']['journal_ciphertext']=j.previous
                    return s
                old=check('journal',journal)
                def dormant():
                    op.dormant(c,stable_verifiers=old['stable_credentials']['verifier_sha256'])
                    op.require(not c.execute('SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s)',(list(op.ROLES)+['ingestion_application_login','ingestion_recovery_login'],)).fetchall(),'P07_PIPELINE_SESSION')
                    op.require(c.execute("SELECT count(*) FROM pg_roles WHERE rolname IN ('ingestion_application_login','ingestion_recovery_login') AND rolcanlogin").fetchone()==(0,),'P07_OTHER_LOGIN_ENABLED')
                check('dormant',dormant);check('permissions',lambda:permissions(c))
                ctl=op.control(c);check('attempt06',lambda:attempt(c,ctl))
                out['binding_hashes']['recovery_receipt']=sha(receipt(ctl['intake_run']))
                out['capabilities']['exact_archive_inventory']=check('evidence',lambda:evidence(c))
                def unused():
                    op.require(SUCCESSOR not in ctl.get('intake_periods',{}),'P07_PERIOD_USED')
                    op.require(c.execute('SELECT count(*) FROM public.ingestion_work_items WHERE revision LIKE %s',(SUCCESSOR+'-%',)).fetchone()==(0,),'P07_SUCCESSOR_WORK_EXISTS')
                check('successor_unused',unused)
            finally:raw.execute('ROLLBACK');out['transaction']='ROLLED_BACK'
    except Exception:
        if all(v=='UNVERIFIED' for v in out['checks'].values()):out['checks']['identity_inventory']='REFUSED'
    def release():
        r=json.loads(env['PROPERTYAIGENT_INTAKE_SOURCE_RELEASE'])
        op.require(r.get('execution_binding')==RELEASE and r.get('tree')=='95bfb2677cddfe539b8b69945d870f6c8b5eb62e' and r.get('branch')=='prep/b-timing-pg17-current-20261103','P07_RELEASE_BINDING')
        out['binding_hashes']['successor_execution']=sha(RELEASE)
    try:check('release',release)
    except Refusal:pass
    api=None
    try:
        api=(render_factory or (lambda:pilot.Render(env['PROPERTYAIGENT_INTAKE_RENDER_API_KEY'])))()
        check('provider',lambda:provider(api))
    except Exception:out['checks']['provider']='REFUSED'
    finally:
        if api is not None:api.close()
    if all(v=='PASS' for v in out['checks'].values()):out['status']='READ_ONLY_CHECKS_PASSED_WITH_UNVERIFIED_CAPABILITIES'
    op.require(len(canonical(out))<=8192,'P07_OUTPUT_BOUND')
    return out
