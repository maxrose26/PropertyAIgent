"""One explicit installed-policy successor. No installation/retirement or new policy."""
from copy import deepcopy
from pathlib import Path
import json,stat,time
from psycopg import sql
from app.ingestion.ledger import Denied,digest
from .operational_publication import canonical,Uncertain
from .oldham_lifecycle import verify_inventory
from .oldham_authority import stop_identity
from .oldham_inspection import ROLE_SETTINGS
from .oldham_transition import Transition

FAILED_RELEASE='oldham-owner-capture-screening-once-20261028'
AUTHORITY='INGESTION_CHAIN_OLDHAM_STAGED_CAPTURE_E9D12874CFB5'
REGISTRATION='9c9100f8257fc92f40f5c76e8167d110f30971e229b4e9198307e51ede3023b6'
FAILED_PACKAGE='386b7c64d53f20af4a185f91b095d622f3c78260e895dfaec3ac97d4db4a006b'
SETTINGS=['idle_in_transaction_session_timeout=20s','lock_timeout=3s','statement_timeout=10s']
FILES={'failed_claim':128*1024,'original_result':64*1024,'original_audit':1024**2,'reconciliation':64*1024}



def expected_historical(o,c):
    """Re-derive the reviewed immutable registration, not a replacement grant."""
    from datetime import datetime,date
    from .operational_owner import Owner
    from .oldham_authority import derive,registration_value,STOP_STATE
    from .scope_binding import binding_for
    from app.ingestion.idox_adapter import IdoxListingContract
    from app.ingestion.ledger import DEFAULT_LIMITS
    from verification.discovery.idox_window import WindowConfig
    revision='fa0064aa111c55bf4f8be1e4d4216aa2fe2b529e'
    bindings=dict(revision=revision,workflow_sha256='06c50c29acf645a5f79cd5f4eb712af0d0346467a0ded829db4dfa33c66e282b',manifest_sha256=FAILED_PACKAGE)
    old=Owner(None,None,lambda:None,expiry=datetime.fromisoformat('2026-10-28T23:08:10+00:00'),bindings=bindings)
    contract=IdoxListingContract('oldham-owner-complete-v1',WindowConfig('oldham','RECEIVED',date(2026,10,15),date(2026,10,21),max_transport_retries=0),'3d519c158bb35d50ad7d1472e842e40eb850dcde6ee7a6e01eda36e91589a003',owner_acceptance='OLDHAM_RECEIVED_20261015_20261021_V1')
    reg=derive(old,binding_for('oldham'),contract,revision=revision,item_limits=DEFAULT_LIMITS,phase='CAPTURE')
    value=registration_value(reg)
    if digest(value)!=REGISTRATION or reg.authority!=AUTHORITY:raise Denied('OLDHAM_REUSE_HISTORICAL_DERIVATION')
    evidence=dict(source_sha256='97a3fe071da69a7fde32ee7bc663a19d8543c0e49fca5a127415c7e8c7ebc671',qualification_sha256=contract.qualification_sha256,outer_sha256='b8e38edeaddf6609833b07354563092183c832f8aa6a21f62228716ecb5cbba3',registration_sha256=REGISTRATION)
    package=dict(authority=AUTHORITY,registration=value,scope=contract.scope(),stop=STOP_STATE,evidence=evidence,targets={})
    package_sha=o.q(c,"SELECT encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(json.dumps(package),))[0][0]
    grant=deepcopy(reg.grant);grant['oldham_package_sha256']=package_sha
    allowance=dict(grant_binding={k:v for k,v in grant.items() if k not in ('source_calls','writes')},source_cap=0,write_cap=0,revoked=False,expires_at=grant['expires_at'],stop_sha256=digest(STOP_STATE),scope=contract.scope(),evidence=evidence,targets={},package=package,package_sha256=package_sha)
    return grant,allowance


def original_files(p,base):
    from .oldham_owner_package import sha
    out={}
    for key,bound in FILES.items():
        d=p['reuse'][key]
        if not isinstance(d,dict) or set(d)!={'name','sha256'}:raise Denied('OLDHAM_REUSE_INPUT_DESCRIPTOR')
        import re
        if not isinstance(d['name'],str) or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}',d['name']):raise Denied('OLDHAM_REUSE_INPUT_PATH')
        f=Path(base)/d['name'];a=f.lstat()
        if not stat.S_ISREG(a.st_mode) or f.is_symlink() or a.st_size>bound:raise Denied('OLDHAM_REUSE_INPUT_FILE')
        raw=f.read_bytes();b=f.lstat()
        if (a.st_ino,a.st_size,a.st_mtime_ns)!=(b.st_ino,b.st_size,b.st_mtime_ns) or sha(raw)!=d['sha256']:raise Denied('OLDHAM_REUSE_INPUT_HASH')
        out[key]=dict(raw=raw,mode=stat.S_IMODE(a.st_mode),sha256=sha(raw),bytes=len(raw))
    return out


def require_retained_packet(p,old):
    if any(p[k]['sha256']!=old[k]['sha256'] for k in ('source','outer','qualification')) or any(p[k]!=old[k] for k in ('origin','owner_acceptance')):raise Denied('OLDHAM_REUSE_RETAINED_PACKET')


def validate_inputs(p,base,*,disposable=False):
    expected={'authority':AUTHORITY,'registration_sha256':REGISTRATION,'failed_package_sha256':FAILED_PACKAGE,'failed_release_id':FAILED_RELEASE,'role_settings':SETTINGS}
    if not isinstance(p['reuse'],dict) or set(p['reuse'])!=set(expected)|set(FILES) or any(p['reuse'].get(k)!=v for k,v in expected.items()):raise Denied('OLDHAM_REUSE_BINDING')
    if p['operation']!='CAPTURE_SCREENING_ONLY' or p['release_id']==FAILED_RELEASE:raise Denied('OLDHAM_REUSE_OPERATION')
    files=original_files(p,base);claim=json.loads(files['failed_claim']['raw']);result=json.loads(files['original_result']['raw']);recon=json.loads(files['reconciliation']['raw'])
    if not disposable:
        if claim.get('consumed') is not True or claim.get('package_sha256')!=FAILED_PACKAGE or digest(claim.get('package'))!=FAILED_PACKAGE:raise Denied('OLDHAM_REUSE_FAILED_CLAIM')
        if claim['package'].get('release_id')!=FAILED_RELEASE or claim['package'].get('scope')!=p['scope']:raise Denied('OLDHAM_REUSE_FAILED_SCOPE')
        old=claim['package']
        require_retained_packet(p,old)
        if result.get('status')!='STOP_RECONCILE_NO_RETRY' or result.get('failure',{}).get('stage')!='ACCESS_ACTIVATION' or result.get('transition',{}).get('installation')!='VERIFIED' or result['transition'].get('retirement')!='VERIFIED':raise Denied('OLDHAM_REUSE_ORIGINAL_RESULT')
        if recon.get('status')!='OLDHAM_READONLY_INSPECTION_COMPLETE' or recon.get('inspection',{}).get('functions',{}).get('state')!='OLDHAM_EXACT_INSTALLATION':raise Denied('OLDHAM_REUSE_RECONCILIATION')
        if any(k in v for v in (claim,result,recon) for k in ('test_only','test_evidence','evidence_label')):raise Denied('OLDHAM_REUSE_SYNTHETIC_NOT_LIVE')
    else:
        if any(json.loads(files[k]['raw']).get('evidence_label')!='DISPOSABLE_RECONCILED_STATE' for k in ('failed_claim','original_result','reconciliation')):raise Denied('OLDHAM_REUSE_DISPOSABLE_INPUT')
    previous='0'*64
    for i,line in enumerate(files['original_audit']['raw'].splitlines()):
        e=json.loads(line);h=e.pop('sha256')
        if e.get('sequence')!=i or e.get('previous_sha256')!=previous or digest(e)!=h:raise Denied('OLDHAM_REUSE_ORIGINAL_AUDIT')
        previous=h
    if not files['original_audit']['raw']:raise Denied('OLDHAM_REUSE_ORIGINAL_AUDIT')
    if result.get('audit_sha256') is not None and result['audit_sha256']!=files['original_audit']['sha256']:raise Denied('OLDHAM_REUSE_RESULT_AUDIT')
    return files


class InstalledReuse(Transition):
    """Reuse existing Owner accounting/capabilities and exact revoke/readback shape."""
    def __init__(self,op):
        self.op=op;self.o=op.owner;self.life=op.life;self.sealed=op.p['reuse'];self.before=None;self.cleaned=False

    def access(self,c,*,residual):
        value=self.life.observed(c)
        if len(value['roles'])!=2 or value['sessions'] or any(r[1] or not r[2] or any(r[4:9]) or r[9]!=1 for r in value['roles']):raise Denied('OLDHAM_REUSE_RETIRED_ACCESS')
        wanted=[(r,cap,False,True,False) for r,cap in sorted(self.life.roles.items())] if residual else []
        if value['memberships']!=wanted:raise Denied('OLDHAM_REUSE_MEMBERSHIPS')
        settings=self.o.q(c,ROLE_SETTINGS,[list(self.life.roles)])
        if len(settings)!=2 or any(sorted(cfg or [])!=SETTINGS or n!=0 for _,cfg,n in settings):raise Denied('OLDHAM_REUSE_ROLE_SETTINGS')
        self.o.emit('oldham_reuse_access',dict(residual_memberships=residual,logins_disabled=True,passwords_absent=True,sessions_absent=True,role_settings_sha256=digest(settings)))

    def inventory(self,c):
        verify_inventory(self.o,c,capture_screening_only=True)
        row=self.o.q(c,"SELECT prosecdef,provolatile,(SELECT lanname FROM pg_language WHERE oid=prolang),pg_get_function_identity_arguments(oid),(SELECT count(*)=1 AND bool_and(a.grantee=p.proowner AND a.privilege_type='EXECUTE') FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a) FROM pg_proc p WHERE oid='public.ingestion_oldham_allowed(jsonb,text,text,jsonb)'::regprocedure")[0]
        if row!=(True,'s','sql','ctl jsonb, authority text, work_key text, subject jsonb',True):raise Denied('OLDHAM_REUSE_POLICY_ATTRIBUTES')

    def historical(self,ctl,*,cleaned):
        g=ctl.get('grants',{}).get(AUTHORITY);a=ctl.get('oldham_allowances',{}).get(AUTHORITY)
        wanted_g,wanted_a=deepcopy(self.expected)
        if cleaned:wanted_g['expires_at']=0;wanted_a['revoked']=True
        if g!=wanted_g or a!=wanted_a:raise Denied('OLDHAM_REUSE_HISTORICAL_BINDING')
        if self.expected[0]['expires_at']>=time.time():raise Denied('OLDHAM_REUSE_AUTHORITY_NOT_EXPIRED')

    def run(self):
        o=self.o;self.op.stage='INSTALLED_POLICY_CLEANUP'
        self.op.result['historical_cleanup']=dict(authority=AUTHORITY,status='NOT_ATTEMPTED')
        files=original_files(self.op.p,self.op.data['base'])
        self.o.emit('oldham_supplied_original_copies', {k:{n:v[n] for n in ('sha256','bytes','mode')} for k,v in files.items()})
        names=self.op.github.names()
        if 'DATABASE_URL' not in names or any(n in names for n in (*self.life.secrets.values(),'INGESTION_STORAGE_DATABASE_URL','INGESTION_APPLICATION_DATABASE_URL')):raise Denied('OLDHAM_REUSE_SECRET_STATE')
        try:
            with o.connection() as c:
                identity=o.q(c,'SELECT current_user,session_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user')[0]
                if identity!=(o.identity,o.identity,False,True,True,True):raise Denied('OLDHAM_OWNER_IDENTITY')
                self.capabilities_absent(c);self.inventory(c);self.access(c,residual=True)
                owner_flags=o.q(c,"SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid='ingestion_storage_owner'::regrole AND member=current_user::regrole AND admin_option),EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid='ingestion_storage_owner'::regrole AND member=current_user::regrole AND grantor=current_user::regrole),(SELECT count(*)=2 AND bool_and(relowner='ingestion_storage_owner'::regrole AND relrowsecurity AND relforcerowsecurity) FROM pg_class WHERE oid IN ('public.ingestion_work_items'::regclass,'public.ingestion_work_attempts'::regclass))")[0]
                if owner_flags!=(True,False,True):raise Denied('OLDHAM_REUSE_OWNER_CAPABILITY')
                grantors=o.q(c,"SELECT m.member::regrole::text,m.roleid::regrole::text,pg_get_userbyid(m.grantor) FROM pg_auth_members m WHERE m.member=ANY(%s::regrole[]) ORDER BY 1,2",(list(self.life.roles),))
                if grantors!=[(r,cap,o.identity) for r,cap in sorted(self.life.roles.items())]:raise Denied('OLDHAM_REUSE_GRANTOR')
                o.q(c,'BEGIN',effect=True)
                o.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
                ctl=o.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64) FOR UPDATE")[0][0]
                self.expected=expected_historical(o,c)
                self.historical(ctl,cleaned=False);self.barriers(c)
                # Expected residual membership is still present: all effective
                # activation conditions are observed before cleanup or new authority.
                self.life.gate(c,inside_transaction=True)
                self.before=deepcopy(ctl)
                ctl['grants'][AUTHORITY]['expires_at']=0;ctl['oldham_allowances'][AUTHORITY]['revoked']=True
                o.q(c,"UPDATE public.ingestion_work_items SET outcome=%s::json WHERE key=repeat('0',64)",(json.dumps(ctl),),effect=True)
                for role,cap in self.life.roles.items():o.q(c,sql.SQL('REVOKE {} FROM {} GRANTED BY CURRENT_USER').format(sql.Identifier(cap),sql.Identifier(role)),effect=True)
                o.q(c,'REVOKE ingestion_storage_owner FROM CURRENT_USER GRANTED BY CURRENT_USER',effect=True)
                o.q(c,'COMMIT',effect=True)
                o.awaiting_verification=True
                self.op.result['historical_cleanup']=dict(authority=AUTHORITY,status='COMMIT_ACKNOWLEDGED_READBACK_REQUIRED')
            self.op.stage='INSTALLED_POLICY_CLEANUP_READBACK'
            with o.connection() as c:
                self.capabilities_absent(c);self.inventory(c);self.access(c,residual=False)
                o.q(c,'BEGIN',effect=True);o.q(c,'GRANT ingestion_storage_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE',effect=True)
                actual=o.q(c,"SELECT outcome FROM public.ingestion_work_items WHERE key=repeat('0',64)")[0][0]
                self.historical(actual,cleaned=True)
                if actual!=ctl:raise Uncertain('OLDHAM_REUSE_CONTROL_READBACK')
                o.require_control_sha256=digest(actual);self.barriers(c)
                # Validate the expected effective rights with memberships restored
                # transactionally. ROLLBACK leaves them absent before issuance.
                for role,cap in self.life.roles.items():o.q(c,sql.SQL('GRANT {} TO {} WITH ADMIN FALSE, INHERIT TRUE, SET FALSE').format(sql.Identifier(cap),sql.Identifier(role)),effect=True)
                self.life.gate(c,inside_transaction=True)
                o.q(c,'ROLLBACK',effect=True)
                self.capabilities_absent(c)
                o.original_control=actual;o.awaiting_verification=False
            after=self.op.github.names()
            if after!=names:raise Uncertain('OLDHAM_REUSE_SECRET_READBACK')
            current=original_files(self.op.p,self.op.data['base'])
            if {k:(v['sha256'],v['mode']) for k,v in current.items()}!={k:(v['sha256'],v['mode']) for k,v in files.items()}:raise Uncertain('OLDHAM_REUSE_ORIGINAL_CHANGED')
            self.cleaned=True
            self.op.result['historical_cleanup']=dict(authority=AUTHORITY,grant_expiry_before=self.before['grants'][AUTHORITY]['expires_at'],grant_expiry_after=0,allowance_revoked=True,memberships='ABSENT',readback='VERIFIED',history_preserved=True)
            self.op.result['transition']=dict(retirement='NOT_REPEATED',installation='REUSED_VERIFIED',rollback='NOT_EXECUTED')
            self.o.emit('oldham_reuse_cleanup_verified',self.op.result['historical_cleanup'])
        except BaseException:
            # Known committed cleanup and any uncertain mutation remain evidence,
            # never a trigger to compensate or start new work.
            self.life.state='UNCERTAIN'
            raise
