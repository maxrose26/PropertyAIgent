"""Fixed owner-local App mint/seal. No activation, renewal or automatic revocation.
Actual App IDs/key fingerprint must be independently reviewed before any live use.
"""
import argparse
import base64
import copy
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time
import warnings
from contextlib import contextmanager

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from . import intake_owner as owner
from .intake_owner_io import Vault
from .intake_owner_operations import installation_token_allowed, token_arm, token_load
from .operational_publication import canonical

ROOT = Path('/home/maxrose26/.local/share/propertyaigent/b-publication-app')
REPOSITORY = 'maxrose26/PropertyAIgent'
REPOSITORY_ID = 1317423499
PERMISSIONS = {'contents': 'write', 'metadata': 'read'}
SLUG = 'propertyaigent-b-maxrose26'
ATTEMPT = 'ONE_B_PUBLICATION_TOKEN_MINT_V1'
BODY = {'repository_ids': [REPOSITORY_ID], 'permissions': PERMISSIONS}
API = 'https://api.github.com'
AUTH_KEYS = {'version','attempt','app_id','client_id','installation_id','app_slug',
             'repository','repository_id','permissions','key_fingerprint','application'}
REASONS = frozenset(('AUTHORITY','PRIVATE_PATH','PRIVATE_FILE','FILE_BOUND','FILE_HASH','JSON',
    'EXISTING_ATTEMPT','KEY','KEY_FINGERPRINT','INSTALLATION','RESPONSE_BOUND','HTTP',
    'SCOPE','TOKEN','EXPIRY','CLOCK','DEADLINE','JOURNAL','RECEIPT','BINDING','WINDOW',
    'EXISTING_SEAL','SEAL','UNKNOWN','ARGUMENTS','TTY','APPROVAL','SECRET','CLEANUP',
    'TRANSPORT_TIMEOUT','TRANSPORT_ERROR'))

class Refusal(Exception):
    pass

def need(value, reason):
    if not value:
        raise Refusal(reason)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def parse(raw):
    def pairs(values):
        d = {}
        for k,v in values:
            need(k not in d, 'JSON'); d[k] = v
        return d
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refusal('JSON')))
    except Refusal:
        raise
    except BaseException:
        raise Refusal('JSON') from None

def directory():
    need(ROOT.is_absolute() and ROOT.resolve()==ROOT and '..' not in ROOT.parts,'PRIVATE_PATH')
    need(not any(p.is_symlink() for p in (ROOT,*ROOT.parents)),'PRIVATE_PATH')
    s=ROOT.stat()
    need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'PRIVATE_PATH')

def private_read(path, limit):
    path=Path(path)
    need(path.is_absolute() and path.resolve()==path and not any(p.is_symlink() for p in path.parents),'PRIVATE_PATH')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1,'PRIVATE_FILE')
        need(s.st_size<=limit,'FILE_BOUND')
        with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read(limit+1)
        need(len(raw)<=limit,'FILE_BOUND');return raw
    finally:os.close(fd)

def load_file(path, sha):
    raw=private_read(path,32768)
    need(type(sha) is str and re.fullmatch('[a-f0-9]{64}',sha) and digest(raw)==sha,'FILE_HASH')
    return parse(raw)

def validate_authority(a):
    need(type(a) is dict and set(a)==AUTH_KEYS,'AUTHORITY')
    need(a['version']=='FIXED_B_PUBLICATION_APP_V1' and a['attempt']==ATTEMPT,'AUTHORITY')
    need(type(a['app_id']) is int and 0<a['app_id']<2**63 and type(a['installation_id']) is int and 0<a['installation_id']<2**63,'AUTHORITY')
    need(type(a['client_id']) is str and re.fullmatch('[A-Za-z0-9_.-]{1,80}',a['client_id']),'AUTHORITY')
    need(a['app_slug']==SLUG and a['repository']==REPOSITORY and type(a['repository_id']) is int and a['repository_id']==REPOSITORY_ID and a['permissions']==PERMISSIONS and a['application']==owner.APPLICATION_BINDING,'AUTHORITY')
    need(type(a['key_fingerprint']) is str and re.fullmatch('[A-Za-z0-9+/]{43}=',a['key_fingerprint']),'AUTHORITY')

def exclusive(name, value):
    fd=os.open(ROOT/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(canonical(value));f.flush();os.fsync(f.fileno())
    fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def exists(name):
    p=ROOT/name
    return p.exists() or p.is_symlink()

@contextmanager
def envelope():
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'DEADLINE')
    previous=signal.getsignal(signal.SIGALRM)
    def expired(*_):raise Refusal('DEADLINE')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,60)
    try:yield
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

def sign(a, password, now):
    raw=private_read(ROOT/'signing-key.pem',65536)
    try:key=serialization.load_pem_private_key(raw,password=password.encode())
    except BaseException:raise Refusal('KEY') from None
    need(isinstance(key,rsa.RSAPrivateKey) and 2048<=key.key_size<=4096,'KEY')
    public=key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    need(base64.b64encode(hashlib.sha256(public).digest()).decode()==a['key_fingerprint'],'KEY_FINGERPRINT')
    enc=lambda v:base64.urlsafe_b64encode(v).rstrip(b'=')
    header=enc(canonical({'alg':'RS256','typ':'JWT'}))
    claims=enc(canonical({'iat':int(now)-60,'exp':int(now)+300,'iss':a['client_id']}))
    message=header+b'.'+claims
    return (message+b'.'+enc(key.sign(message,padding.PKCS1v15(),hashes.SHA256()))).decode()

class Transport:
    """Exactly GET installation then at most one POST; no credential inheritance."""
    def __init__(self,a,jwt):
        import requests
        self.a=a;self.jwt=jwt;self.calls=0
        self.session=requests.Session();self.session.trust_env=False
        self.session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
    def call(self,method):
        need((self.calls,method) in ((0,'GET'),(1,'POST')),'HTTP')
        self.calls+=1
        path='/repos/'+REPOSITORY+'/installation' if method=='GET' else '/app/installations/'+str(self.a['installation_id'])+'/access_tokens'
        with self.session.request(method,API+path,
                headers={'Authorization':'Bearer '+self.jwt,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10'},
                json=copy.deepcopy(BODY) if method=='POST' else None,
                timeout=(5,5),allow_redirects=False,stream=True,verify=True) as r:
            raw=bytearray()
            for chunk in r.iter_content(4096):
                need(len(raw)+len(chunk)<=32768,'RESPONSE_BOUND');raw.extend(chunk)
            return r.status_code,bytes(raw)
    def close(self):
        self.jwt=None;self.session.close()

def installation(a,value):
    need(type(value) is dict and type(value.get('id')) is int and value['id']==a['installation_id'] and type(value.get('app_id')) is int and value['app_id']==a['app_id'],'INSTALLATION')
    need(value.get('app_slug')==SLUG and value.get('account',{}).get('login')=='maxrose26' and value.get('account',{}).get('type')=='User' and value.get('repository_selection')=='selected' and 'suspended_at' in value and value['suspended_at'] is None and value.get('permissions')==PERMISSIONS,'INSTALLATION')

def receipt(value,started,received,a_sha):
    need(type(value) is dict and installation_token_allowed(value.get('token')),'TOKEN')
    need(value.get('permissions')==PERMISSIONS and value.get('repository_selection')=='selected','SCOPE')
    rows=value.get('repositories')
    need(type(rows) is list and len(rows)==1 and type(rows[0]) is dict and type(rows[0].get('id')) is int and rows[0]['id']==REPOSITORY_ID and rows[0].get('full_name')==REPOSITORY,'SCOPE')
    raw=value.get('expires_at')
    need(type(raw) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',raw),'EXPIRY')
    try:expiry=datetime.strptime(raw,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
    except BaseException:raise Refusal('EXPIRY') from None
    # Provider lifetime is one hour; 60s clock tolerance is a local refusal bound.
    need(received+owner.MINT_START_MIN_SECONDS<expiry<=started+3660,'EXPIRY')
    return dict(version='VALIDATED_B_MINT_RECEIPT_V1',authority_sha256=a_sha,
                repository=REPOSITORY,repository_id=REPOSITORY_ID,permissions=PERMISSIONS,
                expires_at=raw,expiry=expiry,request_started=started,response_received=received,
                http_status=201,repository_selection='selected')

def failure(reason,outcome):
    return dict(status='STOP_MINT_SEAL_REQUIRES_REVIEW_NO_RETRY',reason=reason if type(reason) is str and reason in REASONS else 'UNKNOWN',mint_outcome=outcome,retry=False)

def mint(a,a_sha,password,vault_password,*,transport_factory=Transport,clock=time.time):
    """All errors return fixed diagnostics; POST entry is conservatively uncertain."""
    post=False;minted=False;journal=None;state=None;transport=None;prior=False
    try:
        directory();validate_authority(a);need(digest(canonical(a))==a_sha,'AUTHORITY')
        prior=any(exists(n) for n in ('mint-01-consumed.json','mint-01.vault','seal-01-consumed.json','publication-01.vault'))
        need(not prior,'EXISTING_ATTEMPT')
        exclusive('mint-01-consumed.json',dict(attempt=ATTEMPT,authority_sha256=a_sha,retry=False))
        journal=Vault(ROOT/'mint-01.vault',vault_password,create=True)
        state=dict(version='ONE_B_MINT_V1',authority=a,authority_sha256=a_sha,state='CONSUMED_POST_NOT_SENT',post_started=False)
        journal.save(state)
        start=clock();mono=time.monotonic();jwt=sign(a,password,start)
        transport=transport_factory(a,jwt)
        status,raw=transport.call('GET');need(status==200,'HTTP');need(len(raw)<=32768,'RESPONSE_BOUND')
        installation(a,parse(raw))
        need(abs((clock()-start)-(time.monotonic()-mono))<=5,'CLOCK')
        state['state']='POST_INTENT_NO_RETRY';journal.save(state)
        posted=clock();post=True
        status,raw=transport.call('POST')
        need(status==201,'HTTP');minted=True;need(len(raw)<=32768,'RESPONSE_BOUND')
        value=parse(raw)
        # Save recoverable token candidate before any scope/expiry validation.
        candidate=value.get('token') if type(value) is dict else None
        state.update(state='MINTED_UNVALIDATED_REQUIRES_CLOSURE',post_started=True)
        if type(candidate) is str and len(candidate)<=2048:state['token_candidate']=candidate
        journal.save(state)
        received=clock();need(abs((received-start)-(time.monotonic()-mono))<=5,'CLOCK')
        r=receipt(value,posted,received,a_sha)
        state.update(state='RECEIPT_VALIDATED_NOT_ARMED',receipt=r,receipt_sha256=digest(canonical(r)))
        journal.save(state)
        return dict(status='MINT_RECEIPT_VALIDATED_NOT_ARMED',mint_outcome='MINTED',authority_sha256=a_sha,receipt_sha256=state['receipt_sha256'],expires_at=r['expires_at'],expiry=r['expiry'],retry=False)
    except BaseException as error:
        outcome='PRIOR_ATTEMPT_RECONCILE' if prior else 'MINTED_REQUIRES_CLOSURE' if minted else 'UNCERTAIN' if post else 'DEFINITELY_NOT_SENT'
        # No exception text or provider data. Prior durable POST_INTENT alone is
        # uncertain after process loss; only this live path can assert unsent.
        if journal is not None and state is not None:
            state['state']='MINTED_REQUIRES_CLOSURE' if minted else 'MINT_OUTCOME_UNCERTAIN' if post else 'REFUSED_POST_NOT_SENT'
            state['post_started']=post
            try:journal.save(state)
            except BaseException:pass
        import requests
        reason=error.args[0] if type(error) is Refusal else 'TRANSPORT_TIMEOUT' if isinstance(error,(TimeoutError,requests.exceptions.Timeout)) else 'TRANSPORT_ERROR' if isinstance(error,requests.exceptions.RequestException) else 'UNKNOWN'
        return failure(reason,outcome)
    finally:
        if transport is not None:
            try:transport.close()
            except BaseException:
                if journal is not None and state is not None:
                    state['state']='TRANSPORT_CLEANUP_REQUIRES_CLOSURE'
                    try:journal.save(state)
                    except BaseException:pass
                return failure('CLEANUP','MINTED_REQUIRES_CLOSURE' if minted else 'UNCERTAIN' if post else 'DEFINITELY_NOT_SENT')

def seal(a,a_sha,b,vault_password,*,clock=time.time):
    """Local only. Consume seal intent before creating the existing token vault."""
    begun=False
    try:
        directory();validate_authority(a);need(digest(canonical(a))==a_sha,'AUTHORITY')
        journal=Vault(ROOT/'mint-01.vault',vault_password);state=journal.load()
        need(state.get('version')=='ONE_B_MINT_V1' and state.get('authority')==a and state.get('authority_sha256')==a_sha and state.get('state')=='RECEIPT_VALIDATED_NOT_ARMED','RECEIPT')
        r=state['receipt'];need(state.get('receipt_sha256')==digest(canonical(r)) and r.get('authority_sha256')==a_sha,'RECEIPT')
        meta=dict(authority_sha256=a_sha,receipt_sha256=state['receipt_sha256'],expires_at=r['expiry'])
        need(b.get('publication_mint')==meta and b.get('publication_valid_until')==r['expiry'] and b.get('valid_until')==r['expiry'] and b.get('publication_scope')==dict(repository=REPOSITORY,**PERMISSIONS) and b.get('publication_vault_path')==str(ROOT/'publication-01.vault'),'BINDING')
        owner.validate_binding(b,opening=True,now=clock())
        need(installation_token_allowed(state.get('token_candidate')),'TOKEN')
        need(not any(exists(n) for n in ('seal-01-consumed.json','publication-01.vault','publication-01.vault.revoke-consumed')),'EXISTING_SEAL')
        exclusive('seal-01-consumed.json',dict(attempt=ATTEMPT,authority_sha256=a_sha,binding_sha256=digest(canonical(b)),receipt_sha256=state['receipt_sha256'],retry=False));begun=True
        state['state']='SEAL_INTENT_NO_RETRY';journal.save(state)
        target=Vault(ROOT/'publication-01.vault',vault_password,create=True)
        token_arm(b,state['token_candidate'],target.save)
        need(token_load(b,target.load())==state['token_candidate'],'SEAL')
        state.update(state='SEALED_ACKNOWLEDGED',binding=b);state.pop('token_candidate',None);journal.save(state)
        return dict(status='PRIVATE_PUBLICATION_TOKEN_ARMED',mint_outcome='MINTED',receipt_sha256=state['receipt_sha256'],provider_calls=0,retry=False)
    except BaseException as error:
        reason=error.args[0] if type(error) is Refusal else 'WINDOW' if isinstance(error,owner.Denied) and not begun else 'UNKNOWN'
        return failure(reason,'SEAL_UNCERTAIN_RECONCILE' if begun else 'MINTED_NOT_ARMED')

def hidden(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning);value=getpass.getpass(prompt)
    need(type(value) is str and value and len(value)<=1024 and not any(c in value for c in '\r\n\0'),'SECRET')
    return value

def public_result(raw):
    need(len(raw)<=2048,'FILE_BOUND');r=parse(raw)
    need(type(r) is dict and set(r)<= {'status','reason','mint_outcome','retry','authority_sha256','receipt_sha256','expires_at','expiry','provider_calls'},'JSON')
    need(r.get('status') in ('STOP_MINT_SEAL_REQUIRES_REVIEW_NO_RETRY','MINT_RECEIPT_VALIDATED_NOT_ARMED','PRIVATE_PUBLICATION_TOKEN_ARMED') and r.get('retry') is False,'JSON')
    need(r.get('mint_outcome') in ('MINTED','MINTED_REQUIRES_CLOSURE','UNCERTAIN','DEFINITELY_NOT_SENT','PRIOR_ATTEMPT_RECONCILE','MINTED_NOT_ARMED','SEAL_UNCERTAIN_RECONCILE','NOT_INFERRED','NOT_INFERRED_RECONCILE'),'JSON')
    for k in ('authority_sha256','receipt_sha256'):
        if k in r:need(type(r[k]) is str and re.fullmatch('[a-f0-9]{64}',r[k]),'JSON')
    if 'reason' in r:need(type(r['reason']) is str and r['reason'] in REASONS,'JSON')
    if 'expires_at' in r:need(type(r['expires_at']) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ',r['expires_at']),'JSON')
    if 'expiry' in r:need(type(r['expiry']) in (int,float) and 0<r['expiry']<2**63,'JSON')
    if 'provider_calls' in r:need(type(r['provider_calls']) is int and r['provider_calls']==0,'JSON')
    return r


def main(argv=None):
    os.umask(0o077)
    result=failure('UNKNOWN','NOT_INFERRED');output=None;capture_record=None
    try:
        parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('mint','seal'),required=True)
        parser.add_argument('--authority',required=True);parser.add_argument('--authority-sha256',required=True)
        parser.add_argument('--binding');parser.add_argument('--binding-sha256')
        parser.add_argument('--child',action='store_true');parser.add_argument('--secrets-fd',type=int)
        parser.error=lambda _: (_ for _ in ()).throw(Refusal('ARGUMENTS'))
        args=parser.parse_args(argv)
        directory();a=load_file(args.authority,args.authority_sha256);validate_authority(a)
        a_sha=digest(canonical(a));b=None
        if args.phase=='seal':b=load_file(args.binding,args.binding_sha256)
        else:need(args.binding is None and args.binding_sha256 is None,'ARGUMENTS')
        if args.child:
            need(type(args.secrets_fd) is int and args.secrets_fd>2,'ARGUMENTS')
            try:secret=parse(os.read(args.secrets_fd,4096))
            finally:os.close(args.secrets_fd)
            need(type(secret) is dict and set(secret)=={'vault_password','key_password'},'SECRET')
            need(type(secret['vault_password']) is str and 24<=len(secret['vault_password'])<=1024,'SECRET')
            if args.phase=='mint':need(type(secret['key_password']) is str and 0<len(secret['key_password'])<=1024,'SECRET')
            else:need(secret['key_password'] is None,'SECRET')
            with envelope():
                result=mint(a,a_sha,secret['key_password'],secret['vault_password']) if args.phase=='mint' else seal(a,a_sha,b,secret['vault_password'])
        else:
            need(args.secrets_fd is None,'ARGUMENTS')
            need(sys.stdin.isatty() and sys.stderr.isatty(),'TTY')
            phrase='EXECUTE_ONE_B_PUBLICATION_TOKEN_MINT' if args.phase=='mint' else 'SEAL_EXACT_B_PUBLICATION_TOKEN_ONCE'
            need(input('Approved phrase ('+phrase+'): ').strip()==phrase,'APPROVAL')
            output=ROOT/(args.phase+'-evidence-01');output.mkdir(mode=0o700)
            password=hidden('Existing/new vault passphrase (hidden, >=24 characters): ')
            need(len(password)>=24,'SECRET')
            need(hidden('Confirm vault passphrase (hidden): ')==password,'SECRET')
            key_password=hidden('Encrypted owner-local PEM passphrase (hidden): ') if args.phase=='mint' else None
            secrets_raw=canonical(dict(vault_password=password,key_password=key_password))
            need(len(secrets_raw)<=4000,'SECRET')
            from .intake_owner_client import capture
            readfd,writefd=os.pipe()
            try:
                os.write(writefd,secrets_raw);os.close(writefd);writefd=None
                command=[sys.executable,'-B','-m','verification.ingestion_storage.publication_mint','--child','--secrets-fd',str(readfd),'--phase',args.phase,'--authority',str(Path(args.authority).absolute()),'--authority-sha256',args.authority_sha256]
                if b is not None:command+=['--binding',str(Path(args.binding).absolute()),'--binding-sha256',args.binding_sha256]
                data,c=capture(command,dict(HOME=str(Path.home()),PATH='/usr/bin:/bin',LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1'),seconds=60,ceiling=4096,pass_fds=(readfd,))
            finally:
                os.close(readfd)
                if writefd is not None:os.close(writefd)
            capture_record={k:c[k] for k in ('exit_code','reason','client_closed','output_bytes')}
            if c['reason'] is not None or not c['client_closed'] or c['exit_code'] not in (0,2):
                result=failure('DEADLINE' if c['reason']=='DEADLINE' else 'UNKNOWN','NOT_INFERRED_RECONCILE')
            else:
                result=public_result(data)
                need((c['exit_code']==0)==(result['status']!='STOP_MINT_SEAL_REQUIRES_REVIEW_NO_RETRY'),'JSON')
    except BaseException as error:
        result=failure(error.args[0] if type(error) is Refusal else 'UNKNOWN','NOT_INFERRED_RECONCILE')
    if capture_record is not None:result['owner_process']=capture_record
    raw=canonical(result);need(len(raw)<=2048,'FILE_BOUND')
    if output is not None:
        try:
            fd=os.open(output/'result.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            fd=os.open(output,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        except BaseException:
            raw=canonical(failure('JOURNAL','NOT_INFERRED_RECONCILE'));result=parse(raw)
    print(raw.decode().strip())
    return 0 if result['status'] in ('MINT_RECEIPT_VALIDATED_NOT_ARMED','PRIVATE_PUBLICATION_TOKEN_ARMED') else 2

if __name__=='__main__':
    raise SystemExit(main())
