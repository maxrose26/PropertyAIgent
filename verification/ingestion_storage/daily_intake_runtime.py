"""Existing daily entrypoint's bounded intake controller; no admission consumer.

Only restricted worker/effect credentials enter this process. An owner must
previously authorise a period through Owner.register_intake_period. The same
command supports fixed-loopback disposable acceptance with synthetic transports;
those switches are refused outside the disposable destination and test period.
"""
import argparse,hashlib,json,os,subprocess,sys,time
from contextlib import contextmanager
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from sqlalchemy import text
from app.ingestion.ledger import Denied,digest,bounded
from app.ingestion.listing_screening import ScreeningRule,RULE_V3
from app.ingestion.daily_intake import current_windows,intake_slot,backlog_page,contained_idox_failure
from .operational_controller import DatabaseBudget,ControllerLedger
from .operational_owner import Owner
from .operational_publication import GitHub,canonical,BRANCH,REPO
from .operational_supervisor import supervise
from .scope_binding import binding_for
from .chain_registration import capture_registration,screening_registration
from .chain_caller import ChainCaller,WORKER
from .intake_budget import IntakeRun,LIMITS

BOUND_FILES=('app/ingestion/daily_intake.py','app/ingestion/batching.py','app/ingestion/coordinator.py','app/ingestion/sql_ledger.py',
             'app/ingestion/arcus_adapter.py','app/ingestion/idox_adapter.py','verification/discovery/finite_acceptance.py',
             'verification/discovery/source_profiles.py','verification/discovery/idox_window.py','verification/discovery/arcus_ui_window.py',
             'verification/ingestion_storage/daily_intake_runtime.py','verification/ingestion_storage/intake_policy.py',
             'verification/ingestion_storage/intake_budget.py','verification/ingestion_storage/chain_caller.py',
             'verification/ingestion_storage/limit_reconciliation.py','verification/ingestion_storage/operational_supervisor.py','verification/ingestion_storage/operational_owner.py',
             'verification/ingestion_storage/chain_registration.py','scripts/run_daily_councils.py')

def execution_binding():
    import re
    deployed=os.environ.get('RENDER_GIT_COMMIT')
    try:revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):revision=deployed
    if not revision or not re.fullmatch('[a-f0-9]{40}',revision) or deployed and deployed!=revision:raise Denied('INTAKE_CODE_IDENTITY')
    return dict(revision=revision,
                workflow_sha256=hashlib.sha256(Path('.github/workflows/stage4-discovery-offline.yml').read_bytes()).hexdigest(),
                manifest_sha256=digest({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in BOUND_FILES}))


def stop_snapshot(ctl):
    return {k:ctl.get(k,0 if k=='hard_stop_generation' else None) for k in ('global_stop','manual_stop','last_hard_stop','hard_stop_generation')}


def require_source_context(councils,*,disposable):
    # The existing Arcus proof reader requires the dedicated owner-host cgroup
    # and exact credential-free environment. This controller does not establish
    # them; refuse BEFORE registration or any council source effect. A Render
    # container plan alone is not that kernel containment contract.
    if not disposable and 'manchester' in councils:
        raise Denied('ARCUS_INTAKE_EXECUTION_CONTEXT_UNSUPPORTED')


def registration_payload(period,reg,binding):
    rows=reg.rows if reg.kind=='CAPTURE' else [r for r in reg.rows if r['key']!=reg.root_key]
    if reg.kind=='CAPTURE':reg.grant['source_calls']=1
    return dict(operation='intake_capture' if reg.kind=='CAPTURE' else 'intake_screen',period=period,
                authority=reg.authority,execution_binding=binding,grant=reg.grant,rows=rows,
                identity_json={r['key']:canonical({k:r[k] for k in ('subject','task','contract','revision')}).decode() for r in rows})


class Runtime:
    def __init__(self,args):
        self.args=args;self.root=Path(args.output)
        if self.root.exists() or self.root.is_symlink():raise Denied('FRESH_OUTPUT_REQUIRED')
        self.root.mkdir(mode=0o700,parents=True)
        self.run=IntakeRun(stop_file=self.root/'STOP');self.binding=execution_binding();self.authorities=[]
        self.urls={r:os.environ[n] for r,n in [('ingestion_worker_login','INGESTION_WORKER_DATABASE_URL'),('ingestion_effect_login','INGESTION_EFFECT_DATABASE_URL')]}
        from sqlalchemy.engine import make_url
        parsed=[make_url(u) for u in self.urls.values()]
        disposable=all((u.host,u.port,u.database,u.username)==('127.0.0.1',5432,'ingestion_provisioning_test',r) for r,u in zip(self.urls,parsed))
        self.test=bool(args.disposable_sources or args.disposable_archive)
        if self.test and (not disposable or not args.disposable_sources or not args.disposable_archive):raise Denied('FIXED_DISPOSABLE_TRANSPORT_ONLY')
        if not self.test:
            forbidden=('DATABASE_URL','INGESTION_ADMIN_DATABASE_URL','INGESTION_APPLICATION_DATABASE_URL','SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY')
            if any(os.environ.get(k) for k in forbidden):raise Denied('UNNEEDED_PRIVILEGED_RUNTIME_CREDENTIAL')
            try:dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],text=True,stderr=subprocess.DEVNULL).strip()
            except (OSError,subprocess.CalledProcessError):dirty='' if os.environ.get('RENDER_GIT_COMMIT') else 'UNVERIFIED'
            if dirty:raise Denied('CLEAN_REVIEWED_CHECKOUT_REQUIRED')
        self.options={}
        self.route_name='DISPOSABLE'
        if not disposable:
            from .restricted_route import identify
            routes=[identify(u) for u in parsed]
            if any(r is None for r in routes) or routes[0][0]!=routes[1][0] or [r[1] for r in routes]!=list(self.urls):raise Denied('EXACT_SHARED_RESTRICTED_ROUTE')
            self.route_name=routes[0][0]
            import ipaddress
            if not args.hostaddr or ipaddress.ip_address(args.hostaddr).version!=4:raise Denied('REVIEWED_ADDRESS_REQUIRED')
            from .tls_trust import verified_trust
            ca,_=verified_trust();self.options={'ssl':{'sslmode':'verify-full','sslrootcert':str(ca)},'hostaddr':args.hostaddr,'route':self.route_name}
        self.events=[];self.github=None;self.head=None;self.archive_ordinal=0
        self.policy=None
        self.expected_functions={n:hashlib.sha256(body.encode()).hexdigest() for n,body in Owner.daily_intake_inventory().items()}

    def emit(self,event,data):
        value=dict(event=event,data=data)
        bounded(value,128*1024)
        self.events.append(value)
        if len(canonical(self.events))>128*1024:raise Denied('INTAKE_EVENT_EXPORT_BOUND')

    def stop_run(self,reason):
        # Preserve an already changed owner/shared stop instead of overwriting
        # the reason that actually interrupted this run.
        with self.connection() as (c,_):
            observed=c.execute(text("SELECT jsonb_build_object('global_stop',outcome::jsonb->'global_stop','manual_stop',outcome::jsonb->'manual_stop','last_hard_stop',outcome::jsonb->'last_hard_stop','hard_stop_generation',coalesce(outcome::jsonb->'hard_stop_generation','0'::jsonb)) FROM public.ingestion_work_items WHERE key=repeat('0',64)")).scalar_one()
            if self.policy is not None and observed==self.policy['expected_stop']:
                c.execute(text('SELECT public.ingestion_raise_stop(:reason)'),dict(reason=reason))

    @contextmanager
    def connection(self,role='ingestion_worker_login',*,seconds=90):
        budget=DatabaseBudget(**self.run.database_limits(dict(seconds=seconds)))
        self.run.budgets.append(budget)
        engine=budget.engine(self.urls[role],**self.options)
        try:
            with engine.begin() as c:yield c,budget
        finally:budget.close([])

    def policy_read(self,c,*,read_only=False):
        if not read_only:
            actual=c.execute(text("SELECT p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),r.rolname,p.proconfig,p.prosecdef FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace JOIN pg_catalog.pg_roles r ON r.oid=p.proowner WHERE n.nspname='public' AND p.proname=ANY(:names) ORDER BY p.proname"),dict(names=list(self.expected_functions))).all()
            expected=[(n,h,'ingestion_storage_owner',['search_path=pg_catalog'],n!='ingestion_bolton_allowed') for n,h in sorted(self.expected_functions.items())]
            if [tuple(r) for r in actual]!=expected:raise Denied('INTAKE_FUNCTION_INVENTORY_CHANGED')
        row=c.execute(text("SELECT outcome::jsonb->'intake_periods'->:period AS policy, jsonb_build_object('global_stop',outcome::jsonb->'global_stop','manual_stop',outcome::jsonb->'manual_stop','last_hard_stop',outcome::jsonb->'last_hard_stop','hard_stop_generation',coalesce(outcome::jsonb->'hard_stop_generation','0'::jsonb)) AS stop FROM public.ingestion_work_items WHERE key=repeat('0',64)"),dict(period=self.args.period)).one()
        if (not row.policy or row.policy['test_evidence'] is not self.test or row.policy.get('route')!=self.route_name or row.policy.get('hostaddr')!=self.args.hostaddr or not read_only and
            (row.policy['execution_binding']!=self.binding or row.policy['expected_stop']!=row.stop or row.policy['expires_at']<=time.time())):
            raise Denied('INTAKE_PERIOD_BINDING_OR_STOP')
        return row.policy

    def issue(self,reg):
        payload=registration_payload(self.args.period,reg,self.binding)
        self.authorities.append(reg.authority)  # intent precedes a possibly lost acknowledgement
        # One transaction at the actual supported issuer, no INSERT stand-in.
        with self.connection() as (c,_):
            got=c.execute(text('SELECT public.ingestion_register_bolton_exception(CAST(:payload AS jsonb))'),dict(payload=json.dumps(payload))).scalar_one()
        if got.get('already_consumed') is True:
            self.authorities.remove(reg.authority)
            self.emit('already_consumed_no_source',got)
            return got
        if got!={**reg.grant,'intake_period':self.args.period}:raise Denied('INTAKE_ISSUER_READBACK')
        self.emit('supported_registration',dict(kind=reg.kind,authority=reg.authority,keys=len(reg.bindings)))
        return None

    def archive(self,raw):
        if not isinstance(raw,bytes) or len(raw)>512*1024:raise Denied('SOURCE_AUDIT_BOUND')
        self.run.publication(len(raw),10)
        sha=hashlib.sha256(raw).hexdigest();self.archive_ordinal+=1
        directory='docs/design/ingestion-operational-execution-daily-intake/'+self.args.period+'/'+self.root.name+'/capture-'+str(self.archive_ordinal)
        if self.test:
            target=Path(self.args.disposable_archive);target.mkdir(exist_ok=True,parents=True)
            dest=target/(sha+'.json');dest.write_bytes(raw)
            if dest.read_bytes()!=raw:raise Denied('ARCHIVE_READBACK')
            commit=hashlib.sha1(b'TEST_ARCHIVE_NOT_LIVE_EVIDENCE'+raw).hexdigest()
        else:
            if self.github is None:
                self.run.publication(0,1)
                self.github=GitHub(self.emit,self.run.check,bound=LIMITS['github_calls'])
                self.head=self.github.call('GET',REPO+'/git/ref/heads/'+BRANCH)['object']['sha']
            self.head=self.github.publish({'source.json':raw},directory=directory,expected_head=self.head);commit=self.head
        return dict(commit=commit,path=directory+'/source.json',sha256=sha,bytes=len(raw),readback_verified=True)

    def contract(self,row):
        config=self.policy['councils'][row['council']];b=binding_for(row['council'])
        if b.family=='idox':
            from app.ingestion.idox_adapter import IdoxListingContract
            from verification.discovery.idox_window import WindowConfig
            return IdoxListingContract(config['contract'],WindowConfig(row['council'],row['semantics'],date.fromisoformat(row['start']),date.fromisoformat(row['end']),0,60),config['qualification_sha256'])
        from app.ingestion.arcus_adapter import ArcusListingContract
        from verification.discovery.arcus_ui_config import UI_CASES,assessment_dated_config
        from verification.discovery.arcus_ui_audit import validate
        from verification.discovery.arcus_ui_window import qualify_segment
        case='discovery_'+row['council']+'_ui_window'
        return ArcusListingContract(config['contract'],assessment_dated_config(UI_CASES[case],row['start'],row['end']),case,validate,qualify_segment,config['qualification_sha256'],'BROWSER_SOURCE_V2',retain_explicit_zero=True,compact_retained=True)

    def collect(self,row):
        plan=dict(row=row,fixture=str(Path(self.args.disposable_sources).resolve()/(row['council']+'.json')) if self.test else None)
        plan_path=self.root/(row['council']+'-plan.json');plan_path.write_bytes(canonical(plan))
        output=self.root/(row['council']+'-source.json')
        # One persistent, metered restricted connection polls the DB stop while
        # the existing credential-free owned-process supervisor runs the reader.
        with self.connection(seconds=90) as (c,budget):
            import threading
            done=threading.Event();errors=[]
            self.policy_read(c)
            def poll():
                while not done.wait(2):
                    try:self.policy_read(c)
                    except BaseException as error:errors.append(error);return
            def check():
                self.run.check();budget.check()
                if errors:raise Denied('SOURCE_STOP_OR_ACCESS_CHANGED')
            watcher=threading.Thread(target=poll,daemon=True);watcher.start()
            try:
                outer=supervise([sys.executable,'-m',__name__,'--source-worker','--plan',str(plan_path),'--output',str(output)],
                                environment={'INGESTION_SOURCE_PRIVATE':'ONCE'},root=self.root/(row['council']+'-owned'),
                                source=True,seconds=75 if row['council']=='manchester' else 45,stop_file=self.root/'STOP',check=check,
                                execution_budget='BROWSER_SOURCE_V2' if row['council']=='manchester' else None)
            finally:
                done.set();watcher.join(timeout=14)
            if watcher.is_alive():raise Denied('STOP_POLL_CLOSURE_UNCERTAIN')
            if errors:raise Denied('SOURCE_STOP_OR_ACCESS_CHANGED')
            self.policy_read(c)
        if outer['cleanup']!='CLOSED' or outer['exit_code']!=0 or outer['limit_hit'] is not None or not output.is_file() or output.stat().st_size>512*1024:
            raise Denied('SOURCE_OR_CLEANUP_UNCERTAIN_NO_REPLAY')
        source=json.loads(output.read_bytes());outer['observed_at']=datetime.now(timezone.utc).isoformat()
        if row['council']=='manchester':
            metrics=dict(requests=source['requests'],source_bytes=source['decoded_bytes']+source['encoded_bytes']+source['outbound_payload_bytes'],
                         source_seconds=source['supervisor_seconds'],supervised_seconds=outer['elapsed_seconds'])
        else:
            r=source['resource'];metrics=dict(requests=r['requests_attempted'],source_bytes=r['received_bytes'],source_seconds=r['elapsed_seconds'],supervised_seconds=outer['elapsed_seconds'])
        self.run.source(metrics)
        self.emit('source_closed',dict(council=row['council'],sha256=digest(source),metrics=metrics,outer=outer))
        return source,outer

    def execute(self):
        result=dict(status='STOP_RECONCILE_NO_RETRY',scopes=[],coverage_advance=False,admission_connected=False,extraction_connected=False)
        rule=ScreeningRule(RULE_V3,unit_threshold=10,link_related=False)
        try:
            with self.connection() as (c,_):self.policy=self.policy_read(c)
            if self.policy['screening_config']!=digest(rule.config()):raise Denied('INTAKE_RULE_BINDING')
            require_source_context(self.policy['councils'],disposable=self.test)
            rows=current_windows(datetime.now(timezone.utc),sorted(self.policy['councils'],key=lambda c:(binding_for(c).family=='arcus',c)))
            for row in rows:
                self.run.before_scope(binding_for(row['council']).family)
                if self.policy['expires_at']-time.time()<LIMITS['wall_seconds']-self.run.totals()['elapsed_seconds']:
                    raise Denied('INTAKE_PERIOD_TOO_SHORT_FOR_RUN')
                # SQL derives/checks the same London dates, rather than trusting
                # this Python selection or permitting arbitrary historical work.
                contract=self.contract(row);sb=binding_for(row['council'])
                from .limit_reconciliation import BROWSER_SOURCE_V2_ITEM_LIMITS
                from app.ingestion.ledger import DEFAULT_LIMITS
                limits=BROWSER_SOURCE_V2_ITEM_LIMITS if sb.execution_budget else DEFAULT_LIMITS
                owner=Owner(None,self.emit,self.run.check,expiry=datetime.fromtimestamp(min(self.policy['expires_at'],time.time()+1500),timezone.utc),bindings=self.binding)
                revision=self.args.period+'-'+row['end']+'-'+row['council']
                reg=capture_registration(owner,sb,contract,row['start'],row['end'],revision=revision,item_limits=limits)
                consumed=self.issue(reg)
                if consumed:
                    result['scopes'].append(dict(council=row['council'],status='ALREADY_RETAINED' if consumed['state']=='COMPLETE' else 'INCOMPLETE',records=0,failure=None,already_consumed=True))
                    continue
                caller=ChainCaller(sb,contract,rule,self.urls,revision=revision,bindings=dict(reg.bindings),capture_authority=reg.authority,
                                   chain_authority=reg.authority,stop_file=self.root/'STOP',allow_test_evidence=self.test,engine_options=self.options,intake_only=True,intake_run=self.run)
                caller.contained_failure=contained_idox_failure
                def before_archive(ledger):
                    with ledger.worker_engine.begin() as connection:self.policy_read(connection)
                caller.before_archive=before_archive
                def prepare(receipt):
                    root=caller.read_intake_items([reg.root_key])[0]
                    screen=screening_registration(owner,sb,contract,root,receipt,rule,revision=revision,item_limits=limits,allow_test_evidence=self.test,capture_bound=True)
                    self.issue(screen);caller.bindings.update(screen.bindings);return screen
                outcome=intake_slot(caller,reg.root_key,lambda _:self.collect(row),self.archive,prepare,check=self.run.check)
                result['scopes'].append(dict(council=row['council'],status=outcome.get('status','RETAINED_AND_SCREENED'),records=len(outcome['records']),failure=outcome.get('failure')))
            with self.connection() as (c,budget):
                # Existing worker SELECT access; no unknown historical key list.
                engine=budget.engines[0]
                ledger=ControllerLedger(engine,budget=budget,owner=WORKER,authority='',bindings={})
                result['backlog']=backlog_page(ledger,sorted(self.policy['councils']),[v['contract'] for v in self.policy['councils'].values()],rule,connection=c)
            result['status']='INCOMPLETE' if any(s['status']=='INCOMPLETE' for s in result['scopes']) else 'RETAINED_AND_SCREENED'
        except BaseException as error:
            # Never continue another council after shared/unclassified failure.
            self.run.closing=True
            result['failure']=type(error).__name__
            if isinstance(error,Denied):result['reason']=str(error)[:120]
            original=getattr(error,'orig',None)
            if original is not None and getattr(original,'sqlstate',None)=='P0001':
                import re
                message=original.diag.message_primary
                if re.fullmatch('[A-Z0-9_:]+',message):result['reason']=message
            try:
                if self.authorities:
                    self.stop_run('DAILY_INTAKE_SHARED_FAILURE')
            except BaseException:result['stop_readback']='UNCERTAIN'
        finally:
            self.run.closing=True
            try:
                if self.authorities:
                    payload=dict(operation='intake_close',period=self.args.period,execution_binding=self.binding,authorities=self.authorities)
                    with self.connection() as (c,_):
                        closed=c.execute(text('SELECT public.ingestion_register_bolton_exception(CAST(:p AS jsonb))'),dict(p=json.dumps(payload))).scalar_one()
                    if closed.get('authorities_invalidated') is not True:raise Denied('INTAKE_AUTHORITY_CLOSURE')
                    with self.connection() as (c,_):
                        actual=c.execute(text("SELECT outcome::jsonb->'grants' FROM public.ingestion_work_items WHERE key=repeat('0',64)")).scalar_one()
                    if any(actual.get(a,{}).get('expires_at')!=0 for a in self.authorities):raise Denied('INTAKE_AUTHORITY_COMMITTED_READBACK')
                result['authority_closure']='INVALIDATED' if self.authorities else 'NOT_ISSUED'
            except BaseException:result.update(status='STOP_RECONCILE_NO_RETRY',authority_closure='UNCERTAIN')
            result['usage']=self.run.totals();result['limits']=LIMITS
            result['cleanup']='CLOSED' if result['usage']['all_connections_closed'] and result['authority_closure']!='UNCERTAIN' else 'UNCERTAIN'
            if result['cleanup']!='CLOSED':result['status']='STOP_RECONCILE_NO_RETRY'
            result['effect_reconciliation_required']=result['status']=='STOP_RECONCILE_NO_RETRY'
            result['test_evidence']=self.test;result['execution_binding']=self.binding
            raw=canonical(result);events=canonical(self.events)
            try:
                if self.authorities:self.run.publication(len(raw)+len(events),10)
                if self.authorities and not self.test:
                    if self.github is None:
                        self.run.publication(0,1)
                        self.github=GitHub(self.emit,self.run.check,bound=LIMITS['github_calls']);self.head=self.github.call('GET',REPO+'/git/ref/heads/'+BRANCH)['object']['sha']
                    self.head=self.github.publish({'result-before-publication.json':raw,'events-before-publication.json':events},directory='docs/design/ingestion-operational-execution-daily-intake/'+self.args.period+'/'+self.root.name+'/final',expected_head=self.head)
                result['publication']='NOT_REQUIRED_NO_NEW_WORK' if not self.authorities else 'TEST_LOCAL_ARCHIVE' if self.test else 'VERIFIED'
            except BaseException:
                result.update(status='STOP_RECONCILE_NO_RETRY',publication='UNCERTAIN')
                try:
                    self.stop_run('DAILY_INTAKE_REQUIRED_PUBLICATION_FAILURE')
                except BaseException:result['stop_readback']='UNCERTAIN'
            result['usage']=self.run.totals()
            result['usage']['github_actual_calls']=self.github.requests if self.github is not None else 0
            result['usage']['github_calls_are_reserved']=True
            if not result['usage']['all_connections_closed']:result.update(status='STOP_RECONCILE_NO_RETRY',cleanup='UNCERTAIN')
            result['effect_reconciliation_required']=result['status']=='STOP_RECONCILE_NO_RETRY'
            # Preserve local originals even if required publication failed.
            for name,data in [('final-result.json',canonical(result)),('events.json',canonical(self.events))]:
                with (self.root/name).open('xb') as f:os.fchmod(f.fileno(),0o600);f.write(data)
        return result

    def read_backlog(self):
        """Read only: expiry stops collection, not inspection of retained work."""
        with self.connection() as (c,budget):
            c.execute(text('BEGIN READ ONLY'))
            try:
                p=self.policy_read(c,read_only=True)
                ledger=ControllerLedger(budget.engines[0],budget=budget,owner=WORKER,authority='',bindings={})
                page=backlog_page(ledger,sorted(p['councils']),[v['contract'] for v in p['councils'].values()],
                                  ScreeningRule(RULE_V3,unit_threshold=10,link_related=False),after=self.args.after,limit=self.args.page_size,connection=c)
            finally:c.execute(text('ROLLBACK'))
        page.update(status='BACKLOG_READ',usage=self.run.totals(),source_calls=0,registrations=0)
        with (self.root/'backlog.json').open('xb') as f:os.fchmod(f.fileno(),0o600);f.write(canonical(page))
        return page


def source_worker(args):
    if os.environ.get('INGESTION_SOURCE_PRIVATE')!='ONCE' or any('DATABASE' in k or k.endswith(('_KEY','_TOKEN','_PASSWORD')) for k in os.environ):raise Denied('PRIVATE_CREDENTIAL_FREE_SOURCE')
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024,512*1024))
    plan=json.loads(Path(args.plan).read_bytes());row=plan['row']
    seconds=75 if row['council']=='manchester' else 45;resource.setrlimit(resource.RLIMIT_CPU,(seconds,seconds))
    if plan['fixture'] is not None:
        raw=Path(plan['fixture']).read_bytes()
        fixture=json.loads(raw);delay=fixture.pop('_test_delay_seconds',0)
        if type(delay) not in (int,float) or not 0<=delay<=4:raise Denied('DISPOSABLE_DELAY_BOUND')
        if delay:time.sleep(delay)
        raw=canonical(fixture)
    else:
        from verification.discovery.source_profiles import profile
        from verification.discovery.finite_acceptance import read
        p=profile(row,'SCREENING_METADATA')
        audit=read(row,no_transport_retry=True,retain_proof=True,fixed_four_rows=True,execution_budget=p['execution_budget'],
                   execution_mode='four-council-owner-local' if p['family']=='ARCUS_UI' else None,campaign_scope=row,collection_profile=p)
        raw=canonical(audit)
    if len(raw)>512*1024:raise Denied('SOURCE_EXPORT_BOUND')
    with Path(args.output).open('xb') as f:f.write(raw)


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--period',required=True);p.add_argument('--output',required=True)
    p.add_argument('--disposable-sources');p.add_argument('--disposable-archive')
    p.add_argument('--hostaddr')
    p.add_argument('--backlog',action='store_true');p.add_argument('--after');p.add_argument('--page-size',type=int,default=3)
    args=p.parse_args(argv)
    runtime=Runtime(args)
    if args.backlog:
        result=runtime.read_backlog();print(json.dumps(dict(status=result['status'],records=len(result['records']),more=result['more'],next_cursor=result['next_cursor'])));return 0
    result=runtime.execute();print(json.dumps({k:result[k] for k in ('status','cleanup','authority_closure','publication')}))
    return 0 if result['status']=='RETAINED_AND_SCREENED' else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-worker',action='store_true',required=True);p.add_argument('--plan',required=True);p.add_argument('--output',required=True)
    source_worker(p.parse_args())
