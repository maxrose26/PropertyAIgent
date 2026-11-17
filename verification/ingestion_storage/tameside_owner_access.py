"""Inactive campaign adaptation of #213's existing credential lifecycle.

No connections, credentials, journalling or provider operations are created by
this module. The caller supplies the existing pinned owner connection and an
existing encrypted journal callback. Production use awaits operational review.
"""
import ast
import copy
import hashlib
import json
import math
import re
import time
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
from psycopg import sql
from app.ingestion.ledger import Denied
from .operational_owner import Owner,ROLES,ROLE_SETTINGS,ROLE_SETTINGS_SQL,ROLE_SETTING_VALUE

PIN='f027ba28af69ae70208eab5ed047e4a8a81c6337'
SOURCE_SHA='3c347954de6e296d1ac50a24fe1b7fd2192da2d40f28ba51dc717015a07daf78'
PERIOD='S4_FINITE_677f555670666bcf21f45860'
EXPIRY=1795032000.0
HELPERS=('require','json_equal','stop_snapshot','identity','owner_absent','admin_capabilities',
 'enter_owner','leave_owner','control','dormant','settings','set_settings','ledger_sha',
 'begin','prepare_activation','activate','close')


def expected_functions(policy):
    """Source-derived installed bodies, never an observed-state expectation."""
    from .release_candidate import installed_campaign_sql
    from app.ingestion.private_evidence import READ_FUNCTION_SHA256,WRITE_FUNCTION_SHA256
    bodies=Owner.daily_intake_inventory()
    result={n:dict(sha256=hashlib.sha256(body.encode()).hexdigest(),
                   security_definer=n!='ingestion_bolton_allowed') for n,body in bodies.items()}
    # The old registrar is preserved, not replaced by current generic scope SQL.
    # Pinned #213 intake_successor.function_inventory(), independently compared
    # offline; the other five bodies are identical to current source.
    result['ingestion_register_bolton_exception']['sha256']='b1cb4b54493ce2b1ed2a90acb996a70e96cce9545171f57f7c9efd03ae4b382a'
    compiled=installed_campaign_sql(PERIOD,policy,datetime.fromtimestamp(policy['expires_at']-1915,timezone.utc))
    campaign={m[1]:m[3] for m in Owner.FUNCTION_PATTERN.finditer(compiled)}
    result['ingestion_register_campaign_once']=dict(sha256=hashlib.sha256(campaign['ingestion_register_campaign_once'].encode()).hexdigest(),security_definer=True)
    for name,h in [('read',READ_FUNCTION_SHA256),('write',WRITE_FUNCTION_SHA256)]:
        result['ingestion_intake_evidence_'+name]=dict(sha256=h,security_definer=True)
    return result


def lifecycle(pinned_root, *, policy, manifest, expected_inventory=None):
    """Rebind only scope/inventory/history checks; retain actual SQL lifecycle."""
    root=Path(pinned_root)
    path=root/'verification/ingestion_storage/intake_owner.py'
    source=path.read_text()
    if hashlib.sha256(source.encode()).hexdigest()!=SOURCE_SHA:
        raise ValueError('PINNED_ACCESS_SOURCE_DRIFT')
    from .release_candidate import render_release
    render_release(manifest,expires_at=manifest['expires_at'])
    if (policy.get('release_manifest_sha256')!=manifest['manifest_binding_sha256']
            or policy.get('expected_stop')!={'global_stop':None,'manual_stop':None,
                'last_hard_stop':'ABANDONED_EFFECT_OR_UNCERTAIN_CLEANUP','hard_stop_generation':16}
            or policy.get('max_runs')!=1
            or policy.get('campaign_batch')!={'council':'tameside','semantics':'RECEIVED','start':'2026-09-15','end':'2026-09-21'}):
        raise ValueError('CAMPAIGN_ACCESS_PACKAGE_BINDING')
    policy=copy.deepcopy(policy);manifest=copy.deepcopy(manifest)
    if policy.get('test_evidence') and policy.get('route')!='DISPOSABLE':
        raise ValueError('CAMPAIGN_ACCESS_TEST_ROUTE')
    derived=expected_functions(policy) if not policy.get('test_evidence') else None
    if derived is not None:
        if expected_inventory is not None and expected_inventory!=derived:
            raise ValueError('CAMPAIGN_INVENTORY_NOT_SOURCE_DERIVED')
        expected_inventory=derived
    if (not expected_inventory or not all(type(k) is str and re.fullmatch('[a-z_]+',k)
        and type(v) is dict and set(v)=={'sha256','security_definer'}
        and re.fullmatch('[a-f0-9]{64}',v['sha256']) and type(v['security_definer']) is bool
        for k,v in expected_inventory.items())):
        raise ValueError('CAMPAIGN_ACCESS_INVENTORY')
    expected_inventory=copy.deepcopy(expected_inventory)
    scope=dict(copy=copy,hashlib=hashlib,json=json,re=re,time=time,Path=Path,
        datetime=datetime,timezone=timezone,sql=sql,Denied=Denied,Owner=Owner,ROLES=ROLES,
        ROLE_SETTINGS=ROLE_SETTINGS,ROLE_SETTINGS_SQL=ROLE_SETTINGS_SQL,
        ROLE_SETTING_VALUE=ROLE_SETTING_VALUE,CONTROL='0'*64)
    tree=ast.parse(source)
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('ROLE_QUERY','MEMBERS','OWNER_MEMBERS') for t in node.targets):
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in HELPERS:
            text=ast.get_source_segment(source,node)
            if node.name=='activate':
                # These literal old-period guards are replaced by exact manifest
                # hashes and complete campaign-policy equality UNDER the same locks.
                start=text.index('        from .attempt06_recovery import successor_guard')
                end=text.index('        retained_cleanup(c, ctl); no_hazards(c, ctl)',start)
                text=text[:start]+text[end:]
            exec(compile(text,str(path),'exec'),scope)
    require=scope['require']
    def validate_binding(b,*,opening=False,now=None):
        require(type(b) is dict and b.get('version')=='FINITE_INTAKE_OWNER_V1'
            and b.get('period')==PERIOD and b.get('route')==policy['route']=='POOLER'
            and b.get('hostaddr')==policy['hostaddr'] and b.get('owner_hostaddr')==policy['hostaddr']
            and b.get('execution_binding')==policy['execution_binding']
            and b.get('accepted_stop')==policy['expected_stop']
            and b.get('evidence_backend')=='POSTGRES_PILOT_V1'
            and b.get('credential_policy')=='STABLE_RESTRICTED_V1'
            and type(b.get('credential_verifier_sha256')) is dict
            and set(b['credential_verifier_sha256'])==set(ROLES)
            and all(type(x) is str and re.fullmatch('[a-f0-9]{64}',x) for x in b['credential_verifier_sha256'].values()),'CAMPAIGN_ACCESS_BINDING')
        require(type(b.get('valid_until')) in (int,float) and math.isfinite(b['valid_until'])
            and type(b.get('runtime_deadline')) in (int,float)
            and b['runtime_deadline']==policy['expires_at']==b['valid_until']-185
            and b['valid_until']<=EXPIRY,'CAMPAIGN_ACCESS_EXPIRY')
        if opening:
            now=time.time() if now is None else now
            require(1500<b['valid_until']-now<=2100,'CAMPAIGN_ACCESS_SETUP_RESERVE')
        return b
    def inventory(c):
        rows=c.execute("SELECT p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),r.rolname,p.proconfig,p.prosecdef FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner WHERE n.nspname='public' AND p.proname=ANY(%s) ORDER BY 1",(sorted(expected_inventory),)).fetchall()
        require(rows==[(k,v['sha256'],'ingestion_storage_owner',['search_path=pg_catalog'],v['security_definer']) for k,v in sorted(expected_inventory.items())],'CAMPAIGN_ACCESS_INSTALLED_FUNCTIONS')
        acl=c.execute("SELECT p.proname,coalesce(bool_and(x.privilege_type='EXECUTE' AND NOT x.is_grantable AND (x.grantee='ingestion_worker'::regrole OR (p.proname='ingestion_intake_evidence_read' AND x.grantee='postgres'::regrole))),false) FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x WHERE p.oid IN ('public.ingestion_intake_evidence_read(text,text,text)'::regprocedure,'public.ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure) AND x.grantee<>p.proowner GROUP BY p.proname ORDER BY p.proname").fetchall()
        require(acl==[('ingestion_intake_evidence_read',True),('ingestion_intake_evidence_write',True)],'CAMPAIGN_PRIVATE_EVIDENCE_ACL')

    def retained_cleanup(c,ctl):
        require(ctl.get('owner_shared_stop_release',{}).get('manifest_binding_sha256')==manifest['manifest_binding_sha256'],'CAMPAIGN_ACCESS_RELEASE_MANIFEST')
        # Old historical statuses are not asserted after reviewed disposition.
        # Exact seven work+attempt hashes preserve all historical evidence.
        rows=c.execute("SELECT w.key,encode(sha256(convert_to(to_jsonb(w)::text,'UTF8')),'hex'),(SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(a) ORDER BY fence)::text,'[]'),'UTF8')),'hex') FROM public.ingestion_work_attempts a WHERE a.work_key=w.key) FROM public.ingestion_work_items w WHERE key=ANY(%s) ORDER BY key",(sorted(e['key'] for e in manifest['effects']),)).fetchall()
        require(rows==sorted((e['key'],e['work_sha256'],e['attempts_sha256']) for e in manifest['effects']),'CAMPAIGN_ACCESS_HISTORY_CHANGED')
        registered=ctl.get('intake_periods',{}).get(PERIOD)
        require(type(registered) is dict and {k:v for k,v in registered.items() if k not in ('days','registered_at')}==policy,'CAMPAIGN_ACCESS_REGISTERED_POLICY')
    def no_hazards(c,ctl):
        require(not ctl.get('intake_run'),'CAMPAIGN_ACCESS_PRIOR_RUN')
        require(c.execute("SELECT count(*) FROM public.ingestion_work_items WHERE phase IN ('SOURCE_INTENT','WRITE_INTENT') OR state IN ('CLAIMED','PERSISTENCE_UNCERTAIN')").fetchone()==(0,),'CAMPAIGN_ACCESS_PENDING_WORK')
        require(not c.execute('SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s)',(list(ROLES)+['ingestion_application_login','ingestion_recovery_login'],)).fetchall(),'CAMPAIGN_ACCESS_SESSION')
        require(not any(type(g.get('expires_at')) not in (int,float) or g['expires_at']>time.time() for g in ctl.get('grants',{}).values()),'CAMPAIGN_ACCESS_GRANT')
    def activation_gate(c,*,database=False):
        require(database,'CAMPAIGN_PRIVATE_ONLY')
        text=(root/'docs/design/ingestion-operational-required-20261018/activate.sql').read_text()
        require(hashlib.sha256(text.encode()).hexdigest()=='1d3c0ed5c1d275049a16fc1aa90003855b96d28c085dee0ec7ad611326dd8fb7','PINNED_ACTIVATION_GATE_DRIFT')
        text=text.split('ALTER ROLE ingestion_worker_login LOGIN;')[0]
        marker="   AND has_function_privilege(login,p.oid,'EXECUTE'))"
        require(text.count(marker)==1 and text.count('BEGIN;')==1,'CAMPAIGN_ACTIVATION_GATE_SOURCE')
        allowed="'public.ingestion_register_bolton_exception(jsonb)'::regprocedure,'public.ingestion_register_campaign_once(jsonb)'::regprocedure,'public.ingestion_intake_evidence_write(text,text,text,bytea)'::regprocedure,'public.ingestion_intake_evidence_read(text,text,text)'::regprocedure"
        text=text.replace(marker,"   AND NOT (login='ingestion_worker_login' AND p.oid IN ("+allowed+"))\n"+marker)
        c.execute(text.replace('BEGIN;','',1))
    scope.update(validate_binding=validate_binding,inventory=inventory,retained_cleanup=retained_cleanup,
        no_hazards=no_hazards,activation_gate=activation_gate)
    return SimpleNamespace(**{k:scope[k] for k in ('prepare_activation','activate','close','validate_binding','inventory','retained_cleanup')})


def provider_io(pinned_root,access):
    """Reuse pinned handoff/restore, with Tameside-specific HTTP-only transport."""
    import os
    from .restricted_route import url
    from .operational_publication import canonical
    path=Path(pinned_root)/'verification/ingestion_storage/intake_owner_io.py'
    source=path.read_text()
    if hashlib.sha256(source.encode()).hexdigest()!='49b1acca2f5c66a65e845f2290ab5d65c4ada806099d6f381e6a86e66f3dcc0c':
        raise ValueError('PINNED_PROVIDER_IO_DRIFT')
    def require(ok,reason):
        if not ok:raise Denied(reason)
    scope=dict(hashlib=hashlib,json=json,os=os,Path=Path,time=time,url=url,canonical=canonical,
        require=require,validate_binding=access.validate_binding,op=access,
        SERVICE='crn-d9sv93vavr4c73f98rb0',
        KEEP={'PYTHONUNBUFFERED','LANG','TZ','OPENBLAS_NUM_THREADS'})
    names=('env_values','service_guard','operation_observation','boundary','handoff',
           'submission_check','reconcile_handoff','submission_ack_timing','restore_handoff')
    for node in ast.parse(source).body:
        if isinstance(node,ast.FunctionDef) and node.name in names:
            text=ast.get_source_segment(source,node)
            text=text.replace('    from . import intake_owner as op\n','')
            text=text.replace('    from .intake_owner_operations import installation_token_allowed\n','')
            text=text.replace("    require(publication_token is None if database else installation_token_allowed(publication_token), 'SELF_REVOCABLE_INSTALLATION_TOKEN_REQUIRED')", "    require(database and publication_token is None, 'PRIVATE_DATABASE_HANDOFF_ONLY')")
            if node.name=='handoff':
                entry="    b = state['binding']; boundary(b,observation)"
                if text.count(entry)!=1:raise ValueError('PINNED_HTTP_ENTRY_DRIFT')
                text=text.replace(entry, "    b = state['binding']\n"
                    "    require(b.get('period')=='S4_FINITE_677f555670666bcf21f45860' and b.get('timing_policy',{}).get('version')=='SEPARATE_EXPIRY_V2_RESERVE', 'TAMESIDE_HTTP_SCOPE_REQUIRED')\n"
                    "    validate_binding(b,opening=True); boundary(b,observation)")
                # The frozen #213 browser guards remain unchanged for Manchester.
                # Tameside uses the HTTP Idox source and must not inherit them.
                browser_start="    require('PLAYWRIGHT_BROWSERS_PATH' in new, 'RENDER_PROFILE_MAPPING_REQUIRED')"
                role_start="    for role, name in [('ingestion_worker_login', 'INGESTION_WORKER_DATABASE_URL'),"
                if text.count(browser_start)!=1 or text.count(role_start)!=1:
                    raise ValueError('PINNED_HTTP_HANDOFF_SOURCE_DRIFT')
                start=text.index(browser_start)
                end=text.index(role_start,start)
                text=text[:start]+(
                    "    # Reject any stale browser profile binding.\n"
                    "    require(b.get('render_profile') is None, 'TAMESIDE_HTTP_PROFILE_NOT_PERMITTED')\n"
                    "    require('PLAYWRIGHT_BROWSERS_PATH' not in new and\n"
                    "            'INGESTION_RENDER_PROFILE' not in new, 'TAMESIDE_HTTP_BROWSER_ENV')\n"
                    )+text[end:]
            exec(compile(text,str(path),'exec'),scope)
    return SimpleNamespace(**{k:scope[k] for k in names})
