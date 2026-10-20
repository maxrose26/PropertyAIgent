"""Policy v3 installation and the Bolton FORM PROBE, end to end on a REAL disposable PostgreSQL 17 with the real installed ledger, REAL provisioning of the standing credentials, the reviewed successor policy,
the OBSERVED generation-2 stop state, the real owner controller (policy and probe modes), the real hosted controller as a separate process, a real `gh` against the loopback evidence store, the real policy-v3
SQL and a stateful memory stand-in that drives the real closed-envelope guard. Loopback only; nothing here is a production action."""
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.ingestion.ledger import digest
from verification.ingestion_storage import operational_owner as oo
from verification.ingestion_storage import operational_runner as orr
from verification.ingestion_storage import restricted_route as rr
from verification.ingestion_storage.operational_journal import Journal
from verification.ingestion_storage.operational_outcome import session
from verification.ingestion_storage.operational_owner import Owner
from verification.ingestion_storage.operational_publication import GitHub
from verification.ingestion_storage.operational_runner import Runner
from tests.storage_gh_fixture import real_gh_store
from tests.test_discovery_ingestion_provisioning_pg import ROLES as BASE_ROLES,PACKAGE

pytestmark=pytest.mark.parametrize('real_gh_store',['operational'],indirect=True)
WORKER='ingestion_worker_login';EFFECT='ingestion_effect_login'
IDOX='IDOX_CONTRACT_ACCOUNTING_OR_CLEANUP_FAILURE'
PROBE_NAME=orr.PROBE_AUTHORITY+'_PROBE'
V1=Path('docs/design/ingestion-operational-required-20261018/successor-policy.sql')


@pytest.fixture
def world(tmp_path,real_gh_store,monkeypatch):
    raw=os.environ.get('INGESTION_PROVISIONING_TEST_URL')
    if not raw:pytest.skip('fixed disposable PG17 required')
    info=psycopg.conninfo.conninfo_to_dict(raw)
    assert (info['host'],info['port'],info['dbname'],info['user'])==('127.0.0.1','5432','ingestion_provisioning_test','provisioning_bootstrap')
    password=secrets.token_urlsafe(48);role='provisioning_migrator'
    metadata,secret,ciphertexts,requests=real_gh_store
    def connector():return psycopg.connect(**{**info,'user':role,'password':password},autocommit=True,prepare_threshold=None,connect_timeout=3)
    registration=dict(expires_at=(datetime.now(timezone.utc)+timedelta(minutes=60)).isoformat(),revision='a'*40,controller_sha256='b'*64,manifest_sha256='c'*64,evidence_head='1'*40,evidence_directory=orr.PROBE_EVIDENCE_DIRECTORY)
    extra=['ingestion_effect_login','ingestion_effect_broker','ingestion_recovery_operator']
    mapped_values={}
    def cli(command,**kwargs):
        if command[1:3]==['secret','set']:mapped_values[command[3]]=kwargs['input'].decode()
        if command[1:4]==['api','--method','GET']:kwargs['allow_failure']=True
        return metadata.cli(command,**kwargs)
    with psycopg.connect(raw,autocommit=True) as boot:
        boot.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER CREATEROLE CREATEDB BYPASSRLS NOINHERIT PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
        boot.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA public TO {} WITH GRANT OPTION').format(sql.Identifier(role)))
        boot.execute(sql.SQL('GRANT CONNECT ON DATABASE ingestion_provisioning_test TO {} WITH GRANT OPTION').format(sql.Identifier(role)))
        boot.execute(sql.SQL('GRANT SELECT(rolname,rolpassword) ON pg_catalog.pg_authid TO {}').format(sql.Identifier(role)))
        boot.execute(sql.SQL('GRANT pg_read_all_stats TO {} WITH INHERIT TRUE').format(sql.Identifier(role)))
        boot.execute('CREATE SCHEMA extensions')
        boot.execute("CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions VERSION '1.11'")
        boot.execute(sql.SQL('GRANT USAGE ON SCHEMA extensions TO {}').format(sql.Identifier(role)))
        try:
            with connector() as c:
                c.execute((PACKAGE/'install.sql').read_text())
                c.execute('REVOKE ingestion_worker FROM ingestion_worker_login')
                c.execute('REVOKE ingestion_storage_operator FROM ingestion_storage_login')
            boot.execute("SELECT public.ingestion_raise_stop('STORAGE_TEST_STOP')")
            prov_journal=Journal(tmp_path/'provisioning');holder={}
            github=GitHub(prov_journal.emit,lambda:holder['runner'].check(),runner=cli)
            def uri(r,p):return rr.url('POOLER',r,p)
            runner=Runner(dict(registration,mode=orr.STABLE_PROVISION_MODE),prov_journal,connector,source_reader=lambda row:None,github=github,url_factory=uri,identity=role,memory=None);holder['runner']=runner
            installer=Owner(connector,lambda *_:None,lambda:None,identity=role,expiry=runner.expiry,bindings=runner.bindings)
            installer.install()
            boot.execute('ALTER ROLE ingestion_worker_login NOLOGIN PASSWORD NULL');boot.execute('ALTER ROLE ingestion_effect_login NOLOGIN PASSWORD NULL')
            with connector() as migration:
                migration.execute('REVOKE ingestion_worker FROM ingestion_worker_login GRANTED BY CURRENT_USER');migration.execute('REVOKE ingestion_effect_broker FROM ingestion_effect_login GRANTED BY CURRENT_USER')
            ctl=boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            ctl['hard_stop_generation']=1;ctl['last_hard_stop']='OPERATIONAL_FIRST_CONNECTION_FAILURE_CLEANUP_20261018'
            boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
            runner.owner.reuse_installed=True;runner.owner.baseline_control_sha256=digest(ctl)
            with installer.connection() as c_:installer.script(c_,V1)      # the reviewed 18 October successor policy
            prov=session(prov_journal,registration['expires_at'],lambda:'hidden fixture input',lambda raw_,started:runner,output=lambda *a,**k:None,timing=orr.MATRIX_TIMING)
            assert prov['status']=='STABLE_CREDENTIALS_PROVISIONED_LOGIN_ENABLED' and prov['cleanup']=='CLOSED'
            urls={WORKER:mapped_values['INGESTION_WORKER_DATABASE_URL'],EFFECT:mapped_values['INGESTION_EFFECT_DATABASE_URL']}
            def control():return boot.execute("SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)").fetchone()[0]
            def set_control(c):boot.execute("UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(c),))
            def roles_state():return boot.execute("SELECT rolname,rolcanlogin,rolpassword IS NOT NULL,rolvaliduntil,rolconnlimit FROM pg_authid WHERE rolname=ANY(%s) ORDER BY rolname",([WORKER,EFFECT],)).fetchall()
            def memberships():return [tuple(m) for m in boot.execute("SELECT member::regrole::text,roleid::regrole::text FROM pg_auth_members WHERE member=ANY(%s::regrole[]) ORDER BY 1",([WORKER,EFFECT],)).fetchall()]
            def role_configs():return {r:sorted(c or []) for r,c in boot.execute('SELECT rolname,rolconfig FROM pg_roles WHERE rolname=ANY(%s)',([WORKER,EFFECT],)).fetchall()}
            def items():return boot.execute("SELECT key,state FROM public.ingestion_work_items WHERE key<>repeat('0',64) ORDER BY key").fetchall()
            def functions():
                rows=boot.execute("SELECT p.proname,md5(pg_get_functiondef(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' ORDER BY 1").fetchall()
                return dict(rows)
            standing=(roles_state(),memberships(),role_configs());valid_until=min(r[3] for r in standing[0]).astimezone(timezone.utc).isoformat()
            # ---------------------------------------------------------------- the OBSERVED generation-2 state, reproduced: stops as observed, two revoked historical grants and exceptions (the cap leaves one slot)
            ctl=control();ctl['manual_stop']=IDOX;ctl['last_hard_stop']=IDOX;ctl['hard_stop_generation']=2
            ctl.setdefault('bolton_exceptions',{});ctl.setdefault('grants',{})
            for i in range(2):
                name='HISTORICAL_%d'%i
                ctl['grants'][name]=dict(keys=['k'],expires_at=0,source_calls=0,writes=0,login='ingestion_worker_login',bindings={'k':{}})
                ctl['bolton_exceptions'][name]=dict(authority=name,transport='REQUESTS_IDOX',grant_binding={},expires_at=0,hard_stop_generation=1)
            set_control(ctl)
            projection=Owner.project_control(control(),time.time())
            assert projection['stop_state_sha256']==oo.GENERATION2_STOP['stop_state_sha256']      # the digest of the observed production stop state is reproduced exactly by the same code on this record
            monkeypatch.setitem(oo.GENERATION2_STOP,'control_sha256',digest(control()));monkeypatch.setitem(orr.PROBE_BINDING,'control_sha256',digest(control()))
            monkeypatch.setitem(orr.PROBE_BINDING,'valid_until',valid_until);monkeypatch.setitem(orr.PROBE_BINDING,'poll_seconds',1.0);monkeypatch.setitem(orr.PROBE_BINDING,'hosted_wait_seconds',120)
            yield SimpleNamespace(boot=boot,info=info,role=role,connector=connector,registration=registration,cli=cli,metadata=metadata,uri=uri,urls=urls,control=control,set_control=set_control,items=items,functions=functions,
                                  roles_state=roles_state,memberships=memberships,role_configs=role_configs,standing=standing,tmp_path=tmp_path,installer=installer,passwords={})
        finally:
            boot.execute('DROP TABLE IF EXISTS public.ingestion_work_attempts,public.ingestion_work_items CASCADE')
            boot.execute('DROP EXTENSION IF EXISTS pg_stat_statements')
            boot.execute('DROP SCHEMA IF EXISTS extensions')
            for r in [*extra,*BASE_ROLES,role]:
                if boot.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(r,)).fetchone():boot.execute(sql.SQL('DROP OWNED BY {} CASCADE').format(sql.Identifier(r)))
            for r in [*extra,*BASE_ROLES,role]:boot.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(r)))


def run_policy(w,name='policy'):
    journal=Journal(w.tmp_path/name);holder={}
    github=GitHub(journal.emit,lambda:holder['r'].check(),bound=0)
    r=Runner(dict(w.registration,mode=orr.POLICY_MODE),journal,w.connector,source_reader=lambda row:(_ for _ in ()).throw(AssertionError('no source request')),github=github,url_factory=None,identity=w.role,memory=None);holder['r']=r
    return r.execute(),r


# ================================================================================ the policy ceremony
def test_the_policy_ceremony_installs_exactly_the_reviewed_inventory_and_changes_nothing_else(world):
    w=world
    before=dict(functions=w.functions(),control=digest(w.control()),standing=(w.roles_state(),w.memberships(),w.role_configs()))
    with pytest.raises(psycopg.errors.Error,match='EXACT_SCOPED_DISPOSITION'):      # the installed (successor) policy refuses the observed state: this is the problem being solved
        w.boot.execute('SELECT public.ingestion_register_bolton_exception(%s::jsonb)',(json.dumps(dict(authority=PROBE_NAME,transport='REQUESTS_IDOX',grant_binding={},stop_checkpoint_sha256=oo.GENERATION2_STOP['stop_state_sha256'],hard_stop_generation=2,revision='a'*40,workflow_sha256='b'*64,manifest_sha256='c'*64)),))
    result,runner=run_policy(w)
    assert result['status']=='POLICY_GENERATION2_INSTALLED_CONTROL_RECORD_UNCHANGED' and result['cleanup']=='CLOSED' and result['inventory_verified'] is True and result['github_requests']==0
    assert result['transient_owner_capability']=='ABSENT_READ_BACK' and result['control_sha256_before']==result['control_sha256_after']==digest(w.control())
    after=dict(functions=w.functions(),control=digest(w.control()),standing=(w.roles_state(),w.memberships(),w.role_configs()))
    changed=sorted(k for k in before['functions'] if before['functions'][k]!=after['functions'].get(k))
    assert changed==['ingestion_bolton_allowed','ingestion_register_bolton_exception'] and set(before['functions'])==set(after['functions'])
    assert before['control']==after['control'] and before['standing']==after['standing']      # stops, grants, exceptions, credentials, memberships and settings: byte-for-byte unchanged
    assert runner.owner.commands<=orr.POLICY_OWNER_LIMITS['commands'][0] and runner.owner.connections<=orr.POLICY_OWNER_LIMITS['connections'][0]


def test_the_policy_ceremony_refuses_a_changed_baseline_before_any_definition_is_touched(world):
    w=world
    ctl=w.control();ctl['manual_stop']='SOMETHING_ELSE';w.set_control(ctl)
    before=w.functions()
    result,_=run_policy(w)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['stop_reason']=='OBSERVED_BASELINE_CHANGED' and result['committed_writes']==0
    assert w.functions()==before      # nothing installed


def test_the_policy_ceremony_refuses_an_unreviewed_installed_inventory(world):
    w=world
    w.boot.execute("CREATE OR REPLACE FUNCTION public.ingestion_acceptance_control() RETURNS jsonb LANGUAGE sql AS $$ SELECT '{}'::jsonb $$")      # a function that is not the reviewed one
    before=w.functions()
    result,_=run_policy(w)
    assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['committed_writes']==0
    assert w.functions()==before      # the reviewed v3 definitions were not installed over an unrecognised inventory
    assert result['installed_policy'].startswith('UNVERIFIED')


# ================================================================================ the probe
FAULTS=['observed_form','refused_403','worker_audit_malformed','wrong_revision','owner_wait_expires','baseline_changed_blocks']


@pytest.mark.parametrize('fault',FAULTS)
def test_form_probe_lifecycle(world,fault,monkeypatch):
    w=world;tmp_path=w.tmp_path
    policy,_=run_policy(w)
    assert policy['status']=='POLICY_GENERATION2_INSTALLED_CONTROL_RECORD_UNCHANGED'      # the probe runs only after the real policy ceremony
    if fault=='baseline_changed_blocks':
        ctl=w.control();ctl['manual_stop']='SOMETHING_ELSE';w.set_control(ctl)
    ctl_before=w.control()
    owner_journal=Journal(tmp_path/'owner');holder={}
    github=GitHub(owner_journal.emit,lambda:holder['r'].check(),runner=w.cli,bound=orr.PROBE_GITHUB_BOUND)
    orunner=Runner(dict(w.registration,mode=orr.PROBE_MODE),owner_journal,w.connector,source_reader=lambda row:(_ for _ in ()).throw(AssertionError('owner never reads a source')),github=github,url_factory=w.uri,identity=w.role,memory=None);holder['r']=orunner
    orunner.pipeline_sleep=lambda s:time.sleep(min(s,1.0))
    if fault=='owner_wait_expires':monkeypatch.setitem(orr.PROBE_BINDING,'hosted_wait_seconds',3)
    stop_codes=[];import re
    original_failed=orunner.failed
    def failed_with_code(exc):
        text=exc.args[0] if getattr(exc,'args',None) and isinstance(exc.args[0],str) else ''
        stop_codes.append(dict(exception=type(exc).__name__,code=text if re.fullmatch(r'[A-Z][A-Z0-9_]{2,79}',text) else 'NOT_A_FIXED_CODE'))
        return original_failed(exc)
    orunner.failed=failed_with_code
    hosted_dir=tmp_path/'hosted-out';spawned=[]
    plan=dict(disposable='LOOPBACK_ONLY',fault=fault,dbname=w.info['dbname'],gh=w.metadata.gh,gh_env=w.metadata.fixture_env(),evidence_head=w.registration['evidence_head'],manifest_sha256=w.registration['manifest_sha256'],
              controller_sha256=w.registration['controller_sha256'],revision=w.registration['revision'],output=str(hosted_dir))
    plan_path=tmp_path/'plan.json';plan_path.write_text(json.dumps(plan))
    def start_hosted():
        env=dict(os.environ,INGESTION_ACCEPTANCE_DISPOSABLE='PG17_ONLY',REHEARSAL_URLS=json.dumps(w.urls),PYTHONPATH=str(Path.cwd()),PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(['sh','-c','"$0" -B -m tests.form_probe_rehearsal "$1" >"$2" 2>&1 &',sys.executable,str(plan_path),str(tmp_path/'hosted.log')],env=env,check=True,timeout=20)
        spawned.append(True)
    original_register=orunner.owner.register
    def register(items_,authority,**kw):
        out=original_register(items_,authority,**kw)
        if authority.endswith('_PROBE') and fault!='owner_wait_expires':start_hosted()      # the restricted job is dispatched only after the owner registered the named allowance
        return out
    orunner.owner.register=register
    lines=[]
    result=session(owner_journal,w.registration['expires_at'],lambda:'hidden fixture input',lambda raw_,started:orunner,output=lambda line,**kw:lines.append(line),timing=orr.PROBE_TIMING)
    if spawned:
        end=time.monotonic()+60
        while not (hosted_dir/'rehearsal-done').exists() and time.monotonic()<end:time.sleep(0.2)
    summary=dict(fault=fault,status=result.get('status'),cleanup=result.get('cleanup'),invalidation=result.get('authority_invalidation'),stop_codes=stop_codes,phase=result.get('operation_phase'),probe=result.get('probe'),
                 commands=orunner.owner.commands,connections=orunner.owner.connections,github_requests=orunner.github.requests)
    print('PROBE_OWNER_RESULT',json.dumps(summary,default=str,sort_keys=True))
    hosted_log=(tmp_path/'hosted.log').read_text() if (tmp_path/'hosted.log').exists() else ''
    hosted_final=json.loads((hosted_dir/'final-result.json').read_bytes()) if (hosted_dir/'final-result.json').exists() else None
    source_calls=int((hosted_dir/'rehearsal-source-calls').read_text()) if (hosted_dir/'rehearsal-source-calls').exists() else 0
    ctl_after=w.control()
    text=owner_journal.file.read_text()+json.dumps(result)+((hosted_dir/'events.jsonl').read_text() if (hosted_dir/'events.jsonl').exists() else '')
    assert 'postgresql://' not in text
    # ---------------------------------------------------------------- invariants on EVERY path: global stop, historical entries and standing credentials untouched; the named authority ended or never issued
    assert ctl_after['global_stop']==ctl_before['global_stop']
    assert (w.roles_state(),w.memberships(),w.role_configs())==w.standing
    for name in ('HISTORICAL_0','HISTORICAL_1'):assert ctl_after['grants'][name]==ctl_before['grants'][name] and ctl_after['bolton_exceptions'][name]==ctl_before['bolton_exceptions'][name]
    assert len(ctl_after['bolton_exceptions'])<=3      # the unchanged cap
    if fault=='baseline_changed_blocks':
        assert result['status']=='STOP_RECONCILE_NO_RETRY' and PROBE_NAME not in ctl_after['grants'] and not spawned and stop_codes[0]['code']=='PROBE_READBACK_MANUAL_STOP_CHANGED'
        return
    assert PROBE_NAME in ctl_after['grants'] and ctl_after['grants'][PROBE_NAME]['expires_at']==0 and ctl_after['bolton_exceptions'][PROBE_NAME]['expires_at']==0      # ended by invalidation, never merely by time
    assert ctl_after['bolton_exceptions'][PROBE_NAME]['hard_stop_generation']==2
    if fault=='owner_wait_expires':
        assert result['status']=='STOP_RECONCILE_NO_RETRY' and result['authority_invalidation']=='ACKNOWLEDGED_READBACK' and not spawned and source_calls==0 and stop_codes[0]['code']=='HOSTED_PUBLICATION_WAIT_EXPIRED'
        return
    assert spawned and hosted_final is not None,hosted_log[-1500:]
    closed_after=int((hosted_dir/'rehearsal-memory-closed-after-gh-calls').read_text());total=int((hosted_dir/'rehearsal-gh-calls-total').read_text())
    assert closed_after==total      # no GitHub request after the memory scope was closed; the result was published inside it
    assert hosted_final['closure_stage']=='FINAL_AFTER_PUBLICATION' and hosted_final['publication']=='PUBLISHED' and hosted_final['cleanup']=='CLOSED'
    if fault=='wrong_revision':
        assert source_calls==0 and result['status']=='STOP_RECONCILE_NO_RETRY' and stop_codes[0]['code']=='HOSTED_ENDED_BEFORE_PROBE_OBSERVATION' and hosted_final['stop_reason']=='CHECKOUT_BINDING_MISMATCH'
        assert ctl_after['hard_stop_generation']==2 and ctl_after['manual_stop']==IDOX      # a refused checkout raises no stop
        return
    if fault=='worker_audit_malformed':
        assert source_calls==1 and result['status']=='STOP_RECONCILE_NO_RETRY' and stop_codes[0]['code']=='HOSTED_ENDED_BEFORE_PROBE_OBSERVATION'
        assert ctl_after['hard_stop_generation']==3 and ctl_after['manual_stop']==IDOX      # an unaccountable outcome raises the ACCEPTED fail-safe stop, which advances the generation (never reset)
        return
    # ---------------------------------------------------------------- an observation: the form, or a council refusal
    assert source_calls==1 and result['status']=='BOLTON_FORM_PROBE_OBSERVED_AUTHORITY_INVALIDATED' and result['authority_invalidation']=='ACKNOWLEDGED_READBACK' and result['cleanup']=='CLOSED'
    assert result['diagnostic_only'] is True and result['not_a_capture'] is True and result['hosted']['cleanup']=='PENDING_MEMORY_SCOPE_CLOSURE'
    assert ctl_after['hard_stop_generation']==2 and ctl_after['manual_stop']==IDOX and ctl_after['last_hard_stop']==IDOX      # a council answer raises no stop; the generation is untouched
    probe=result['probe']
    if fault=='observed_form':assert probe['outcome']=='FORM_RECOGNISED' and probe['transport']['http_status']==200
    if fault=='refused_403':assert probe['outcome']=='REQUEST_REJECTED' and probe['transport']['http_status']==403
    states=dict(w.items());assert list(states.values())==['UNSUPPORTED_CONTRACT']      # the probe item is finished and can never be reused as a capture
    assert orunner.owner.commands<=orr.PROBE_OWNER_LIMITS['commands'][1] and orunner.owner.connections<=orr.PROBE_OWNER_LIMITS['connections'][0]+2
