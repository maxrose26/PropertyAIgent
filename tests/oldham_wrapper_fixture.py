"""Fixed disposable backend for the ACTUAL owner command. Never imported in live mode.

Sources and GitHub APIs are synthetic; role/ledger/admission SQL and private source
children are real. Bootstrap/cleanup SQL belongs to disposable test infrastructure,
not operational authority or measured runtime. No council or GitHub contact.
"""
import argparse,base64,copy,json,os,subprocess,sys,time
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
from unittest.mock import patch
from sqlalchemy.engine import make_url
from psycopg import sql
from app.ingestion.ledger import digest
from verification.ingestion_storage import oldham_owner_package as pkg
from verification.ingestion_storage.oldham_authority import STOP_STATE
from verification.ingestion_storage.operational_publication import canonical
from tests.e2e_connection_support import idox_audit,idox_supervised,entry,SCHEME,EXTENSION
from tests.e2e_chain_caller import START,END,snapshot,changed_tables

CONTROL=dict(STOP_STATE,grants={},bolton_exceptions={})


def packet(root,*,records=2,nominees=1,tag='success',supervised=True,single_page=False,accept=None,transition=False,reuse=False):
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    start,end=(date(2026,10,15),date(2026,10,21)) if reuse else (START,END)
    entries=[entry(f'SYNTHETIC/{i}',SCHEME if i<nominees else EXTENSION) for i in range(records)]
    audit=idox_audit('oldham',entries,start,end,single_page_no_pager=single_page)
    acceptance=None
    if accept is not None:      # TEST-ONLY acceptance for this synthetic single-page audit, installed by the calling test (never the production registry entry)
        from tests.e2e_connection_support import make_test_acceptance,install_test_acceptance
        acceptance=install_test_acceptance(accept,make_test_acceptance(audit,'oldham',start,end))
    if supervised:source,outer=idox_supervised(root,audit)
    else:
        from tests.e2e_connection_support import outer as synthetic_outer
        source,outer=audit,synthetic_outer()
    q=dict(kind='DISPOSABLE_TEST_QUALIFICATION',council='oldham',live_authority=False)
    values=dict(source=source,outer=dict(source_sha256=digest(source),outer_supervisor=outer,scope=dict(council='oldham',semantics='RECEIVED',start=start.isoformat(),end=end.isoformat())),qualification=q)
    descriptors={}
    for name,value in values.items():
        raw=canonical(value);(root/(name+'.json')).write_bytes(raw);descriptors[name]=dict(name=name+'.json',sha256=pkg.sha(raw))
    deps=pkg.dependencies();scope=dict(kind='DISCOVERY_SCOPE',council='oldham',start=start.isoformat(),end=end.isoformat(),semantics='RECEIVED')
    p=dict(version=pkg.VERSION_ACCEPTED if acceptance else pkg.VERSION,mode='DISPOSABLE_TEST',release_id='oldham-owner-test-'+tag.replace('_','-'),revision=pkg.git('rev-parse','HEAD'),tree=pkg.git('rev-parse','HEAD^{tree}'),dependencies=deps,packages=pkg.packages(),scope=scope,
           **descriptors,qualification_binding=dict(qualification_sha256=descriptors['qualification']['sha256'],source_sha256=digest(source),outer_sha256=digest(outer),scope=scope,dependencies_sha256=digest(deps),**(dict(owner_acceptance_sha256=acceptance.sha256) if acceptance else {})),
           **(dict(owner_acceptance=acceptance.key) if acceptance else {}),
           control_sha256=digest(CONTROL),evidence_head='1'*40,origin=dict(commit='1'*40,source_path='docs/design/ingestion-operational-execution-disposable-input/slot-0/source.json',slot_path='docs/design/ingestion-operational-execution-disposable-input/slot-0/receipt.json'),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),risk_acceptance=pkg.RISK)
    if transition:
        from verification.ingestion_storage import oldham_transition as t
        inspection=dict(status='OLDHAM_READONLY_INSPECTION_COMPLETE',outcome=dict(closure='VERIFIED'),inspection=dict(functions=dict(state='RECOGNISED_PRE_OLDHAM',recognised=t.PREDECESSOR,owner_and_search_path_as_reviewed=True)),evidence_label='DISPOSABLE_INSPECTION_STAND_IN_NOT_PRODUCTION')
        raw=canonical(inspection);(root/'inspection.json').write_bytes(raw)
        install,rollback=t.texts(t.PREDECESSOR)
        p.update(version=pkg.VERSION_CAPTURE_SCREENING,operation=t.OPERATION,risk_acceptance=t.RISK,
            transition=dict(inspection=dict(name='inspection.json',sha256=pkg.sha(raw)),predecessor=t.PREDECESSOR,retire_standing=True,external_consumers_confirmed=True,installation_sha256=pkg.sha(install.encode()),rollback_sha256=pkg.sha(rollback.encode())))
        p.pop('control_sha256');p['control_stop_sha256']=digest(STOP_STATE)
    if reuse:
        from verification.ingestion_storage import oldham_reuse as r
        descriptions={}
        for name in ('failed_claim','original_result','reconciliation'):
            value=dict(evidence_label='DISPOSABLE_RECONCILED_STATE')
            raw=canonical(value);(root/(name+'.json')).write_bytes(raw);descriptions[name]=dict(name=name+'.json',sha256=pkg.sha(raw))
        event=dict(sequence=0,event='synthetic_consumed_history',payload={},previous_sha256='0'*64)
        raw=canonical(dict(event,sha256=digest(event)))+b'\n';(root/'original-audit.jsonl').write_bytes(raw)
        descriptions['original_audit']=dict(name='original-audit.jsonl',sha256=pkg.sha(raw))
        p.update(version=pkg.VERSION_INSTALLED,operation='CAPTURE_SCREENING_ONLY',risk_acceptance=__import__('verification.ingestion_storage.oldham_transition',fromlist=['RISK']).RISK,
            control_stop_sha256=digest(STOP_STATE),reuse=dict(authority=r.AUTHORITY,registration_sha256=r.REGISTRATION,failed_package_sha256=r.FAILED_PACKAGE,failed_release_id=r.FAILED_RELEASE,role_settings=r.SETTINGS,**descriptions))
        p.pop('control_sha256')
    raw=canonical(p);path=root/'package.json';path.write_bytes(raw)
    return path,pkg.sha(raw)


class Backend:
    def __init__(self,path):
        from tests.test_discovery_four_council_release import API
        self.path=Path(path);self.p=json.loads(self.path.read_bytes());self.native=os.environ.get('OLDHAM_WRAPPER_NATIVE')=='1'
        self.capture_screening_only=self.p['version'] in pkg.CAPTURE_SCREENING_VERSIONS
        self.reuse=self.p['version']==pkg.VERSION_INSTALLED
        self.scenario=os.environ.get('OLDHAM_WRAPPER_SCENARIO','success');self.gen=None;self.world=None;self.inputs=0;self.closed=False;self.patchers=[];self.names={'DATABASE_URL'};self.source_calls=0
        self.api=object.__new__(API);self.api.head=self.p['evidence_head'];self.api.trees={'2'*40:{}};self.api.commits={self.api.head:'2'*40};self.api.blobs={};self.api.calls=[];self.api.fail=None;self.api.lost=False;self.api.ref_moved=False
        if self.p['version'] in (pkg.VERSION_ACCEPTED,*pkg.CAPTURE_SCREENING_VERSIONS):      # TEST-ONLY: this fixture backend is imported only by the disposable command; it installs a labelled acceptance for the package's synthetic audit. The production registry is never touched in live mode.
            from types import MappingProxyType
            from app.ingestion import owner_acceptance
            from tests.e2e_connection_support import make_test_acceptance
            acceptance=make_test_acceptance(json.loads((self.path.parent/self.p['source']['name']).read_bytes()),'oldham',date.fromisoformat(self.p['scope']['start']),date.fromisoformat(self.p['scope']['end']))
            owner_acceptance.ACCEPTANCES=MappingProxyType({acceptance.key:acceptance})
        if self.capture_screening_only and not self.reuse:self.names.update(('INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'))
        raw=(self.path.parent/self.p['qualification']['name']).read_bytes()
        self.api.trees['2'*40][str(pkg.QUALIFICATION)]=self.api.blob(raw);self.patches=0
        for key,description in [('source_path','source'),('slot_path','outer')]:
            self.api.trees['2'*40][self.p['origin'][key]]=self.api.blob((self.path.parent/self.p[description]['name']).read_bytes())

    def github(self,command,*,input=None,**kw):
        if command[:3]==['gh','secret','set']:
            assert input and b'postgresql' in input;self.names.add(command[3])
            return subprocess.CompletedProcess(command,0,b'',b'')
        method,path=command[3:5]
        if '/environments/stage4-production-canary/secrets' in path:
            if method=='DELETE':
                self.names.discard(path.rsplit('/',1)[-1])
                if self.scenario=='cs_secret_ack':raise TimeoutError('SYNTHETIC_SECRET_ACK_LOSS')
                return subprocess.CompletedProcess(command,0,b'HTTP/2.0 204 No Content\r\n',b'')
            assert method=='GET';return subprocess.CompletedProcess(command,0,canonical(dict(total_count=len(self.names),secrets=[dict(name=n) for n in sorted(self.names)])),b'')
        if method=='GET' and '/compare/' in path:return subprocess.CompletedProcess(command,0,canonical(dict(status='identical',base_commit=dict(sha=self.p['origin']['commit']))),b'')
        if method=='PATCH':
            self.patches+=1
            if self.scenario=='publication_uncertain' and self.patches==3:self.api.lost=True
        return self.api.runner(command,input=input,**kw)

    def input(self):
        # Explicit fixture input, not a live credential or hidden-input substitute.
        # Live mode ALWAYS calls the reviewed secure_migration_input directly.
        self.inputs+=1
        return 'DISPOSABLE_FIXTURE_INPUT_ONLY'

    def prepare(self,raw,op):
        assert raw=='DISPOSABLE_FIXTURE_INPUT_ONLY'
        from tests.e2e_pg_world import disposable_world,RESTRICTED
        from verification.ingestion_storage import oldham_policy
        from verification.ingestion_storage.operational_owner import PKG,GENERATION3_SCREENING_V3_POLICY
        self.gen=disposable_world();self.world=next(self.gen);w=self.world
        with w['connect']('provisioning_migrator') as c:
            c.execute((PKG/'successor-policy.sql').read_text());c.execute(GENERATION3_SCREENING_V3_POLICY.read_text())
            if self.capture_screening_only and not self.reuse:
                from verification.ingestion_storage import screening_v3_worker_sql as v3
                c.execute(v3.installation_script())
            else:c.execute(oldham_policy.installation_script())
        w['boot'].execute('ALTER ROLE provisioning_migrator CREATEDB BYPASSRLS') # accepted OWNER flags; runtime roles unchanged
        w['boot'].execute('GRANT SELECT (rolname,rolpassword) ON pg_authid TO provisioning_migrator')
        w['boot'].execute('GRANT pg_read_all_stats TO provisioning_migrator WITH INHERIT TRUE, SET FALSE')
        for r in RESTRICTED:
            w['boot'].execute(sql.SQL('ALTER ROLE {} NOLOGIN PASSWORD NULL').format(sql.Identifier(r)))
        w['boot'].execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(CONTROL),))
        if self.capture_screening_only and not self.reuse:
            for role in ('ingestion_worker_login','ingestion_effect_login'):
                w['boot'].execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal('SYNTHETIC_STANDING_FIXTURE_ONLY')))
            if self.scenario=='cs_barrier':w['boot'].execute("UPDATE ingestion_work_items SET phase='WRITE_INTENT' WHERE key=repeat('0',64)")
            if self.scenario=='cs_predecessor':
                w['boot'].execute(oldham_policy.installation_script()) # unexpected installed successor, never replay
            if self.scenario=='cs_missing_create_grant':
                w['boot'].execute('REVOKE GRANT OPTION FOR CREATE ON SCHEMA public FROM provisioning_migrator')
            if self.scenario=='cs_self_grant':
                with w['connect']('provisioning_migrator') as c:
                    # A legal self-granted row with no inherited/SET capability.
                    # ADMIN TRUE would create a circular administration dependency
                    # during fixture setup, before the actual command guard runs.
                    c.execute('GRANT ingestion_storage_owner TO CURRENT_USER WITH ADMIN FALSE, INHERIT FALSE, SET FALSE')
                    row=c.execute("SELECT admin_option,inherit_option,set_option FROM pg_auth_members WHERE roleid='ingestion_storage_owner'::regrole AND member=current_user::regrole AND grantor=current_user::regrole").fetchone()
                    assert row==(False,False,False)
        if self.reuse:
            from verification.ingestion_storage import oldham_reuse as r
            b=w['boot']
            b.execute('CREATE SCHEMA extensions');b.execute('REVOKE ALL ON SCHEMA extensions FROM PUBLIC')
            b.execute("CREATE EXTENSION pg_stat_statements WITH SCHEMA extensions VERSION '1.11'")
            grants=b.execute("SELECT grantor::regrole::text FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a WHERE d.datname=current_database() AND a.grantee='ingestion_recovery_login'::regrole").fetchall()
            for (grantor,) in grants:
                if grantor==b.info.user:b.execute('REVOKE ALL ON DATABASE ingestion_provisioning_test FROM ingestion_recovery_login')
                else:
                    assert grantor=='provisioning_migrator'
                    with w['connect'](grantor) as issuer:issuer.execute('REVOKE ALL ON DATABASE ingestion_provisioning_test FROM ingestion_recovery_login')
            b.execute('DROP OWNED BY ingestion_recovery_login');b.execute('DROP ROLE ingestion_recovery_login')
            for role in ('ingestion_worker_login','ingestion_effect_login'):
                for setting in r.SETTINGS:
                    name,value=setting.split('=',1);b.execute(sql.SQL('ALTER ROLE {} SET {} TO {}').format(sql.Identifier(role),sql.Identifier(name),sql.Literal(value)))
            ctl=copy.deepcopy(CONTROL)
            from types import SimpleNamespace
            old_g,old_a=r.expected_historical(SimpleNamespace(q=lambda c,s,p:c.execute(s,p).fetchall()),b)
            ctl['grants'][r.AUTHORITY]=old_g;ctl['oldham_allowances']={r.AUTHORITY:old_a}
            if self.scenario=='reuse_counter':ctl['grants'][r.AUTHORITY]['source_calls']=1
            if self.scenario=='reuse_target':ctl['oldham_allowances'][r.AUTHORITY]['package']['targets']={'unexpected':{}}
            if self.scenario=='reuse_barrier':b.execute("UPDATE ingestion_work_items SET phase='WRITE_INTENT' WHERE key=repeat('0',64)")
            if self.scenario=='reuse_stop':ctl['hard_stop_generation']+=1
            if self.scenario=='reuse_revoked':ctl['oldham_allowances'][r.AUTHORITY]['revoked']=True
            b.execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
            if self.scenario=='reuse_metadata':b.execute('ALTER VIEW extensions.pg_stat_statements_info SET (security_invoker=true)')
            if self.scenario=='reuse_policy':b.execute("ALTER FUNCTION public.ingestion_oldham_allowed(jsonb,text,text,jsonb) VOLATILE")
            if self.scenario=='reuse_settings':b.execute("ALTER ROLE ingestion_worker_login SET statement_timeout='11s'")
            if self.scenario=='reuse_secret':self.names.add('INGESTION_WORKER_DATABASE_URL')
            # Replica differences are fixture setup, never measured production effects.
        if self.scenario=='existing':
            from sqlalchemy.orm import Session
            from app.db.models import Application
            first=json.loads((self.path.parent/self.p['source']['name']).read_bytes())['records'][0]
            with Session(w['app']) as session:
                session.add(Application(council_code='oldham',reference=first['reference'],unit_confirmation_status='discovery_pending'));session.commit()
        self.before=snapshot(w['boot'])
        def url_factory(role,password):
            if self.capture_screening_only:assert role in ('ingestion_worker_login','ingestion_effect_login')
            return make_url(w['urls'][role]).set(password=password).render_as_string(hide_password=False)
        connector=lambda:w['connect']('provisioning_migrator')
        if self.scenario in ('cs_retire_ack','cs_install_ack','cs_install_readback','reuse_cleanup_ack','reuse_cleanup_readback'):
            commits=[];lost=[];original=connector;scenario=self.scenario
            class Proxy:
                def __init__(self,c):self.c=c
                def __getattr__(self,n):return getattr(self.c,n)
                def execute(self,q,params=None):
                    result=self.c.execute(q,params)
                    text=q if isinstance(q,str) else q.as_string(self.c)
                    if text.strip().rstrip(';')=='COMMIT':
                        commits.append(True)
                        target=1 if scenario in ('cs_retire_ack','reuse_cleanup_ack') else 2
                        if scenario not in ('cs_install_readback','reuse_cleanup_readback') and len(commits)==target and not lost:
                            lost.append(True);raise ConnectionError('SYNTHETIC_COMMIT_ACK_LOSS')
                    if scenario=='reuse_cleanup_readback' and len(commits)==1 and 'SELECT outcome' in text and not lost:
                        lost.append(True);raise ConnectionError('SYNTHETIC_CLEANUP_READBACK_LOSS')
                    if scenario=='cs_install_readback' and len(commits)==2 and 'SELECT p.proname,p.prosrc' in text and not lost:
                        lost.append(True);raise ConnectionError('SYNTHETIC_INSTALL_READBACK_LOSS')
                    return result
            connector=lambda:Proxy(original())
        return dict(connect=connector,identity='provisioning_migrator',url_factory=url_factory)

    def after_screening(self,op):
        w=self.world
        assert w['boot'].execute('SELECT count(*) FROM applications').fetchone()[0]==(1 if self.scenario=='existing' else 0)
        if self.scenario=='cancel':(op.journal.root/'STOP').touch();op.check()
        if self.scenario=='stop':
            ctl=copy.deepcopy(op.owner.original_control);ctl['hard_stop_generation']+=1
            w['boot'].execute("UPDATE ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),))
        if self.scenario=='expiry':op.owner.grant_expiry=datetime.now(timezone.utc)-timedelta(seconds=1)
        if self.scenario in ('export_boundary','export_overflow'):
            local=sum(f.stat().st_size for f in op.journal.root.rglob('*') if f.is_file())
            op.published=2*1024**2-128*1024-local+(self.scenario=='export_overflow')
            op.result['accounting_injection']='SYNTHETIC_EXPORT_BOUNDARY';op.check()
        if self.scenario=='deadline':
            op.started=time.monotonic()-461;op.result['accounting_injection']='SYNTHETIC_CLOCK_BOUNDARY';op.check()
        if self.scenario=='application_uncertain':
            import app.pipeline.discovery_admission as admission
            original=admission.admit_identity
            def lost(*a,**k):original(*a,**k);raise RuntimeError('SYNTHETIC_APPLICATION_ACK_LOSS')
            p=patch.object(admission,'admit_identity',lost);p.start();self.patchers.append(p)
        if self.scenario=='ledger_ack_uncertain':
            from app.ingestion.sql_ledger import SQLLedger
            original=SQLLedger._step
            def lost(ledger,operation,key,*a,**k):
                result=original(ledger,operation,key,*a,**k)
                if operation=='resolve_effect' and ledger.get(key)['phase']=='WRITE_INTENT':raise RuntimeError('SYNTHETIC_LEDGER_ACK_LOSS')
                return result
            p=patch.object(SQLLedger,'_step',lost);p.start();self.patchers.append(p)
        if self.scenario=='uncertain_commit':
            connector=op.owner.connector;lost=[]
            class Proxy:
                def __init__(self,c):self.c=c
                def __getattr__(self,n):return getattr(self.c,n)
                def execute(self,q,params=None):
                    result=self.c.execute(q,params)
                    if q=='COMMIT' and not lost:lost.append(True);raise ConnectionError('SYNTHETIC_ACK_LOSS')
                    return result
            op.owner.connector=lambda:Proxy(connector())

    def detail(self,reader,adm,op):
        from verification.direct_reference.fixtures import summary
        from verification.ingestion_storage import operational_supervisor as supervisor
        body=op.journal.root/('synthetic-detail-'+str(self.source_calls)+'.html')
        body.write_bytes(summary(adm.nominee.reference,status='Decided',decision='Approve',date='Mon 28 Sep 2026'))
        if self.scenario=='b2_uncertain':
            from sqlalchemy import event
            def fail(connection,cursor,statement,parameters,context,many):
                if statement.lstrip().startswith('UPDATE applications'):raise RuntimeError('SYNTHETIC_B2_READBACK_FAILURE')
            event.listen(adm.co.ledger.engine,'after_cursor_execute',fail)
        actual=supervisor.subprocess.Popen
        def launch(command,**kw):
            assert command[1:3]==['-m','verification.ingestion_storage.operational_source']
            assert not any('DATABASE' in k or 'TOKEN' in k or 'PASSWORD' in k for k in kw['env'])
            self.source_calls+=1
            return actual([command[0],'-m','tests.closed_idox_source_fixture',*command[3:],'--fixture-html',str(body)],**kw)
        def run(row):
            with patch.object(supervisor.subprocess,'Popen',launch):return reader(row)
        return run

    def close(self):
        if self.closed:return
        self.closed=True
        for p in reversed(self.patchers):p.stop()
        if self.world is not None:
            if self.scenario in ('cs_missing_create_grant','cs_self_grant'):
                boot=self.world['boot']
                rows=boot.execute("SELECT r.rolname,r.rolcanlogin,a.rolpassword IS NOT NULL FROM pg_roles r JOIN pg_authid a ON a.oid=r.oid WHERE r.rolname=ANY(%s) ORDER BY 1",(['ingestion_worker_login','ingestion_effect_login'],)).fetchall()
                assert len(rows)==2 and all(r[1] and r[2] for r in rows)
                assert self.names=={'DATABASE_URL','INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL'}
                if self.scenario=='cs_self_grant':
                    row=boot.execute("SELECT admin_option,inherit_option,set_option FROM pg_auth_members WHERE roleid='ingestion_storage_owner'::regrole AND member='provisioning_migrator'::regrole AND grantor='provisioning_migrator'::regrole").fetchone()
                    assert row==(False,False,False)
            changed=set(changed_tables(self.before,snapshot(self.world['boot'])))
            if self.capture_screening_only:assert not changed and self.source_calls==0
            else:assert changed<={'applications','application_lifecycle_events'}
        if self.gen is not None:
            if self.reuse:
                self.world['boot'].execute('DROP EXTENSION IF EXISTS pg_stat_statements CASCADE; DROP SCHEMA IF EXISTS extensions CASCADE')
                self.world['boot'].execute('CREATE ROLE ingestion_recovery_login NOLOGIN') # fixture-only recreation for the unchanged harness teardown
            try:next(self.gen)
            except StopIteration:pass


def native():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--capture-screening-only',action='store_true');parser.add_argument('--installed-reuse',action='store_true');a=parser.parse_args()
    if a.installed_reuse:
        from pytest import MonkeyPatch
        path,sha=packet(a.root,tag='native-installed-reuse',records=5,nominees=0,single_page=True,accept=MonkeyPatch(),reuse=True)
        os.environ['OLDHAM_WRAPPER_SCENARIO']='reuse_zero'
    elif a.capture_screening_only:
        from pytest import MonkeyPatch
        path,sha=packet(a.root,tag='native-capture-screening',records=5,nominees=0,single_page=True,accept=MonkeyPatch(),transition=True)
        os.environ['OLDHAM_WRAPPER_SCENARIO']='cs_zero'
    else:path,sha=packet(a.root,tag='native')
    os.environ['OLDHAM_WRAPPER_NATIVE']='1'
    if a.installed_reuse:
        os.execv('/bin/bash',['bash','docs/design/oldham-activation-correction-20261028/owner-run.sh',str(Path.cwd()),sys.executable,str(path),sha,'--disposable-test'])
    else:
        os.execv(sys.executable,[sys.executable,'-m','verification.ingestion_storage.oldham_owner_once','--package',str(path),'--package-sha256',sha,'--disposable-test'])

if __name__=='__main__':native()
