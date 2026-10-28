"""One fixed, inactive-until-approved READ ONLY adapter for the existing inspection runner.
No Owner construction, GRANT/SET ROLE, activation, secret client or source reader.
"""
import hashlib,json,os,re,stat,subprocess,sys,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from verification.ingestion_storage import oldham_inspection as old
from verification.ingestion_storage.admin_connection_probe import ProbeDenied
from verification.ingestion_storage.operational_publication import canonical

ROOT=Path(__file__).resolve().parent
REVISION='fa0064aa111c55bf4f8be1e4d4216aa2fe2b529e'
TREE='03751b14fa23d260baad2d39de2ad7bf604e563a'
STATE='oldham-activation-reconciliation-once-20261028'
AUTHORITY='AUTHORISE_OLDHAM_ACTIVATION_READONLY_RECONCILIATION_ONCE_20261028'
MODE='OLDHAM_ACTIVATION_READONLY_RECONCILIATION'
STATUS='OWNER_APPROVED_OLDHAM_ACTIVATION_READONLY_RECONCILIATION_ONCE'
Q=json.loads((ROOT/'queries.json').read_bytes())
EXPECTED_QUERY_SHA='4dc1b5947ea9f26187d66663d4a00a84dbd6d96dd1ab0e224baf26ceefd76366'
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((ROOT/'queries.json').read_bytes())==EXPECTED_QUERY_SHA
PRIMARY=['begin','identity','roles','memberships','sessions','functions','gate_predicates','gate_offenders','control','ledger','barriers','rollback']
KNOWN_ROLES=set(old.KNOWN_ROLE_NAMES)|{'postgres','ingestion_authority_issuer','pg_read_all_stats','pg_signal_backend'}


def originals():
    root=Path.home()/'.local/state/propertyaigent/oldham-owner-capture-screening-once-20261028'
    out=[]
    for name in ('final-result.json','events.jsonl','publication-events.jsonl'):
        p=root/name
        if not p.exists():out.append(dict(file=name,exists=False));continue
        s=p.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_size>2*1024**2:raise ProbeDenied('RESPONSE_BOUND')
        raw=p.read_bytes();t=p.lstat()
        if (s.st_ino,s.st_size,s.st_mtime_ns)!=(t.st_ino,t.st_size,t.st_mtime_ns):raise ProbeDenied('RESPONSE_SHAPE')
        out.append(dict(file=name,exists=True,sha256=sha(raw),bytes=len(raw),mode=stat.S_IMODE(s.st_mode),mode_is_private=stat.S_IMODE(s.st_mode)&0o077==0))
    return out


BASE_SESSION=old.session
BASE_JOURNAL=old.Journal

class BoundedJournal(BASE_JOURNAL):
    def emit(self,event,payload):
        record=dict(sequence=self.sequence,event=event,payload=payload,previous_sha256=self.head)
        raw=canonical(dict(record,sha256=sha(canonical(record))))+b'\n'
        current=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        if current+len(raw)>32768:raise ProbeDenied('RESPONSE_BOUND')
        return super().emit(event,payload)
    def save(self,name,value):
        raw=canonical(value)
        current=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        if len(raw)>32768 or current+len(raw)>65536:raise ProbeDenied('RESPONSE_BOUND')
        return super().save(name,value)

def bounded_session(*args,**kwargs):
    target=kwargs.pop('output',print)
    def output(line,**options):
        if len(line.encode())+1>32768:raise ProbeDenied('RESPONSE_BOUND')
        return target(line,**options)
    kwargs['output']=output
    return BASE_SESSION(*args,**kwargs)


class Reconciliation(old.InspectionRunner):
    def observe(self,c):
        s=lambda n,p=None:self.send(c,n,Q[n],p)
        s('begin');self.in_transaction=True
        ident=s('identity')[0]
        if len(ident)!=19 or ident[0]!='postgres' or ident[1]!='postgres' or ident[15] is not True or ident[16] is not True:raise ProbeDenied('RESPONSE_SHAPE')
        password_visible=ident[12] is True;visible=ident[10] is True
        self.inspection=dict(transaction_read_only=True,repeatable_read=True,observed_at=ident[17].isoformat(),identity_matches=True,
            storage_owner_usage=ident[6],storage_owner_set=ident[7],barrier_usage=ident[8],barrier_set=ident[9],password_presence_visible=password_visible,session_visibility=visible,
            ledger_access=ident[18],stored_authority={'status':'UNKNOWN_ACCESS_NOT_ESTABLISHED'},uncertainty_barriers={'status':'UNKNOWN_ACCESS_NOT_ESTABLISHED'})
        rows=s('roles' if password_visible else 'roles_without_password',[list(old.LOGINS)+['ingestion_recovery_login']])
        recovery=next((r for r in rows if r[0]=='ingestion_recovery_login'),None)
        self.inspection['recovery_dormancy']=dict(exists=recovery is not None,can_login=recovery[1] if recovery is not None else None)
        self.inspection['logins']=old.project_roles([tuple(r) for r in rows],[],[],password_visible)
        members=s('memberships',[['ingestion_worker_login','ingestion_effect_login','postgres']])
        self.inspection['memberships']=[dict(member=m if m in KNOWN_ROLES else 'OTHER_ROLE',role=r if r in KNOWN_ROLES else 'OTHER_ROLE',role_sha256=sha(r.encode()),admin=a,inherit=i,set=t) for m,r,a,i,t in members]
        if visible:self.inspection['sessions']=old.project_sessions([r[:3] for r in s('sessions',[list(old.LOGINS)])],True)
        else:self.inspection['sessions']={'visibility':'UNKNOWN','reason':'IDENTITY_LACKS_PG_READ_ALL_STATS'}
        funcs=s('functions',[old.function_names()])
        if len(funcs)>16:raise ProbeDenied('RESPONSE_BOUND')
        self.inspection['functions']=old.classify_functions([tuple(r[:6]) for r in funcs])
        self.inspection['function_identities']=[dict(name=r[0],body_sha256=r[1],owner_matches=r[2]=='ingestion_storage_owner',search_path_matches=r[3]==['search_path=pg_catalog'],security_definer=r[4],signature_sha256=sha(r[5].encode()),worker_execute=r[6],effect_execute=r[7]) for r in funcs]
        self.inspection['gate_predicates']=s('gate_predicates')[0][0]
        self.inspection['gate_offenders']=s('gate_offenders')[0][0]
        if len(canonical(self.inspection))>16000:raise ProbeDenied('RESPONSE_BOUND')
        expected=old.expected_states()['oldham'].get('ingestion_acceptance_control')
        safe=any(r[0]=='ingestion_acceptance_control' and r[1]==expected and r[2]=='ingestion_storage_owner' and r[3]==['search_path=pg_catalog'] for r in funcs)
        self.inspection['control']={'status':'UNKNOWN_FUNCTION_NOT_VERIFIED'}
        if safe and ident[13] is True:self.inspection['control']=old.project_control(s('control')[0][0])
        access=ident[18] or {}
        if access.get('control_columns') is True and access.get('rls_unfiltered') is True:
            data=s('ledger');self.inspection['stored_authority']=data[0][0] if data else {'status':'CONTROL_SENTINEL_NOT_OBSERVED'}
        else:self.inspection['stored_authority']={'status':'UNKNOWN_DIRECT_LEDGER_ACCESS_UNAVAILABLE','temporary_grant_required_for_additional_access':True,'grant_performed':False}
        if access.get('barrier_columns') is True and access.get('rls_unfiltered') is True:
            u,w=s('barriers')[0];self.inspection['uncertainty_barriers']=dict(status='OBSERVED',persistence_uncertain=u,write_intents=w)
        if len(canonical(self.inspection))>16000:raise ProbeDenied('RESPONSE_BOUND')
        s('rollback');self.in_transaction=False;self.rollbacks+=1
        return self.inspection

    def execute(self):
        self.original_before=originals();self.emit('historical_file_observation_separate',dict(files=self.original_before))
        # Reuse the existing native watchdog; no cancel connection or mutation.
        from verification.ingestion_storage.operational_cleanup import HardDeadline
        native_connect=self.connect;watch=[None]
        def bounded_connect():
            watch[0]=HardDeadline(time.monotonic()+old.BOUND['database_seconds'])
            return native_connect()
        self.connect=bounded_connect
        try:result=super().execute()
        finally:
            if watch[0] is not None:watch[0].close()
        result['historical_file_observation']=self.original_before
        after=originals();result['historical_files_unchanged']=after==self.original_before
        if after!=self.original_before:result['status']='STOP_RECONCILE_NO_RETRY';result['historical_file_status']='CHANGED_DURING_OBSERVATION'
        if len(canonical(result))>23000:raise ProbeDenied('RESPONSE_BOUND')
        return result

    def common(self,components):
        result=super().common(components)
        result['authority_invalidation']='NOT_PERFORMED_READ_ONLY_EXISTING_AUTHORITY_UNRECONCILED'
        result['access']='NO_ACCESS_CREATED_BY_DIAGNOSTIC_EXISTING_ACCESS_OBSERVED_SEPARATELY'
        result['closure_scope']='DIAGNOSTIC_CONNECTION_AND_OWNED_PROCESS_ONLY_NOT_PRIOR_RUN_ACCESS'
        return result

    def failed(self,exc):
        result=super().failed(exc)
        if self.inspection is not None and len(canonical(self.inspection))<=16000:result['partial_inspection']=self.inspection
        return result


def validate(body,expected_sha):
    if sha(body)!=expected_sha:raise ValueError('REGISTRATION_SHA256')
    r=json.loads(body);plan=json.loads((ROOT/'registration.INACTIVE.json').read_bytes())
    allowed={**plan,'status':STATUS,'expires_at':r.get('expires_at')}
    if r!=allowed or r['expires_at'] is None:raise ValueError('EXACT_ATTENDED_READONLY_APPROVAL_REQUIRED')
    now=datetime.now(timezone.utc);expiry=datetime.fromisoformat(r['expires_at'])
    if expiry.tzinfo is None or not now+timedelta(seconds=180)<expiry<=now+timedelta(hours=2):raise ValueError('RECONCILIATION_EXPIRY')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=REVISION or subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip()!=TREE or subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise ValueError('CLEAN_REVIEWED_CHECKOUT')
    for p,h in r['repository_hashes'].items():
        if sha(Path(p).read_bytes())!=h:raise ValueError('REPOSITORY_BINDING')
    for p,h in r['bundle_hashes'].items():
        if p not in ('diagnostic.py','queries.json','gate-mapping.json','owner-run.sh') or sha((ROOT/p).read_bytes())!=h:raise ValueError('DIAGNOSTIC_BINDING')
    if r['limits']!=old.BOUND or r['query_sha256']!=EXPECTED_QUERY_SHA:raise ValueError('LIMIT_OR_QUERY_BINDING')
    return r


def configure():
    old.MODE=MODE;old.AUTHORITY=AUTHORITY;old.STATUS=STATUS;old.STATE=STATE
    old.Journal=BoundedJournal;old.session=bounded_session
    old.ABSENT_CAPABILITIES=tuple(x for x in old.ABSENT_CAPABILITIES if x!='ledger_table_select')
    old.allowed=lambda:set(Q.values())
    old.planned=lambda *a:[(n,Q[n],None) for n in PRIMARY]
    old.InspectionRunner=Reconciliation
    old.validate_registration=validate

if __name__=='__main__':
    os.umask(0o077);configure();old.main()
