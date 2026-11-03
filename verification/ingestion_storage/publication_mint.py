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
    'TRANSPORT_TIMEOUT','TRANSPORT_ERROR','LOCAL_REPLACEMENT','CORRECTED_REPLACEMENT','EXECUTION_DAY','MINT_DAY_MARGIN','SUCCESSOR_PRECONDITION','PREDECESSOR_NOT_EXPIRED','BINDING_MISSING_RUN_FREEZE','FROZEN_PROOF_REQUIRED','FROZEN_BINDING_MISMATCH','FROZEN_OBSERVATION_EXPIRED','FREEZE_INCOMPLETE','RELEASE_WINDOW_CLOSED','BINDING_ARGUMENT_MISMATCH','PREPARATION_UNKNOWN','MINT_RESULT_REQUIRED','RELEASE_CLOSED_EXPLICIT_REBIND_REQUIRED','TIMING_RELEASE_UNBOUND'))

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

# Fixed extension of the same single-successful-mint authority, only after the
# exact acknowledged pre-POST refusal and corrected authentication proof.
CORRECTED_AUTHORITY=Path('/home/maxrose26/stage4-owner/b-github-get-readonly-20261103/authority-client-id-corrected.json')
CORRECTED_RAW_SHA='28a039e7dae4358055113fd830ad3ca2e3d742c6060d43c5b46f1c394e079096'
CORRECTED_A_SHA='ed07a6fb15ff6b0c8308f0ef28bf1b2e3eedc98159a538b87d7b1891d45bbe74'
CORRECTED_MARKER='mint-corrected-client-id-01-consumed.json'
CORRECTED_JOURNAL='mint-corrected-client-id-01.vault'
CORRECTED_OUTPUT='mint-evidence-corrected-client-id-01'
CORRECTED_DIAGNOSTIC=Path('/home/maxrose26/stage4-owner/b-github-installation-get-corrected-authority-evidence-01/result.json')
CORRECTED_PROOFS={
 'authority.json':'a10aa38ed9465c79ae4631f89435d2997113ca18acdfca5df2031a0016b0b05e',
 'mint-01-consumed.json':'691860d90f9e5b0eb4ea357ce86f5b63469e5f00d83508cf14ed1d0a353f4350',
 'mint-01.vault':'147b832cc4b15690ae4125e6160932dec177ef56d7e0e26c7f2929dcaf353e89',
 'mint-evidence-01/result.json':'233a2cc3682039be4ed7db54c69d20ca515c56d5a05d5243e4e6134acc21ea2c',
 'mint-evidence-local-correction-01/result.json':'ccbff66a02145d5eeeb9f79224eaf5698b42a010c478ae61fe31f3c8ca70f469',
}
CORRECTED_EXTERNAL_PROOFS={
 CORRECTED_DIAGNOSTIC:'f9b43000948ff16882cab29e4c92536fe1816b77797c8fafab6098df5c04b233',
 Path('/home/maxrose26/stage4-owner/b-github-installation-get-corrected-authority-evidence-01/reservation.json'):'8014feec3a9fbe3e4730243b28b840cda4e3f337e2c3c5bd4e1bb045324e430f',
 Path('/home/maxrose26/stage4-owner/b-github-installation-get-evidence-01/result.json'):'de82a0d2af19f574062cd6e17bab5f61872ce7d3d789786d9dd50c3a05d2c32d',
}


def corrected_replacement_preconditions(a,a_sha,vault_password=None,*,now=None):
    from zoneinfo import ZoneInfo
    directory()
    for name,h in CORRECTED_PROOFS.items():
        need(digest(private_read(ROOT/name,32768))==h,'CORRECTED_REPLACEMENT')
    for path,h in CORRECTED_EXTERNAL_PROOFS.items():
        need(digest(private_read(path,4096))==h,'CORRECTED_REPLACEMENT')
    original=parse(private_read(ROOT/'authority.json',32768))
    corrected=load_file(CORRECTED_AUTHORITY,CORRECTED_RAW_SHA)
    need(a==corrected==dict(original,client_id='Iv23liHaM7meqJPpdD8x') and
         original['client_id']=='Iv23IiHaM7meqJPpdD8x' and a_sha==CORRECTED_A_SHA==digest(canonical(a)), 'CORRECTED_REPLACEMENT')
    validate_authority(a)
    refused=parse(private_read(ROOT/'mint-evidence-local-correction-01/result.json',2048))
    need(refused==dict(failure('HTTP','DEFINITELY_NOT_SENT'),owner_process=dict(client_closed=True,exit_code=2,output_bytes=120,reason=None)),'CORRECTED_REPLACEMENT')
    diag=parse(private_read(CORRECTED_DIAGNOSTIC,2048))
    need(diag.get('authority_sha256')==CORRECTED_RAW_SHA and diag.get('http_status')==200 and diag.get('binding_check')=='MATCH' and
         diag.get('requests_started')==diag.get('responses_completed')==1 and diag.get('post_requests')==diag.get('provider_mutations')==0 and
         diag.get('retry') is False and diag.get('transport_closed') is True and diag.get('body_complete') is True and
         diag.get('owner_process',{}).get('client_closed') is True and diag['owner_process'].get('exit_code')==0 and diag['owner_process'].get('reason') is None,'CORRECTED_REPLACEMENT')
    need(not any(exists(n) for n in (CORRECTED_MARKER,CORRECTED_JOURNAL,CORRECTED_JOURNAL+'.next',
        'seal-01-consumed.json','seal-evidence-01','publication-01.vault','publication-01.vault.next','publication-01.vault.revoke-consumed')),'EXISTING_ATTEMPT')
    local=datetime.fromtimestamp(time.time() if now is None else now,ZoneInfo('Europe/London'))
    need(local.date().isoformat()=='2026-11-03','EXECUTION_DAY')
    midnight=datetime(2026,11,4,tzinfo=ZoneInfo('Europe/London'))
    need((midnight-local).total_seconds()>3065,'MINT_DAY_MARGIN')
    if vault_password is not None:
        # Read-only predecessor verification; the original journal is never saved.
        state=Vault(ROOT/'mint-01.vault',vault_password).load()
        need(set(state)=={'version','authority','authority_sha256','state','post_started'} and
             state['version']=='ONE_B_MINT_V1' and state['authority']==original and
             state['authority_sha256']==digest(canonical(original)) and state['state']=='REFUSED_POST_NOT_SENT' and
             state['post_started'] is False,'CORRECTED_REPLACEMENT')


SUCCESSOR_MARKER='mint-expired-unused-successor-01-consumed.json'
SUCCESSOR_JOURNAL='mint-expired-unused-successor-01.vault'
SUCCESSOR_OUTPUT='mint-evidence-expired-unused-successor-01'
SUCCESSOR_CLOSURE=Path('/home/maxrose26/stage4-owner/b-finite-release-20261103/EXPIRED-UNUSED-CLOSURE.json')
SUCCESSOR_CLOSURE_SHA='1b1ec660f8b88d67df43faaaf9e77bec958cd8886c75b059f78200696d7a0103'
PREDECESSOR_EXPIRY=1793703384
PREDECESSOR_RECEIPT='2e4ec5466a21474f21de40f30103305d172b4442e331fbd2264557be3955ddea'
SUCCESSOR_PREDECESSOR_PROOFS={
 'mint-evidence-corrected-client-id-01/result.json':'9e204657fcceb5e75152ef49614f103bd1056e5ffcbfc0b7dfa513a6608de3d3',
 CORRECTED_MARKER:'3823b52bf23e281e9ea8ce2bb742e2f67b68f30e42aa44930e83d20cfc90f485',
 CORRECTED_JOURNAL:'9bd3bdf320ad6ddc1a617abb2df6f50bf4a0fd5a549f8140db5776abba53a78e',
}
SUCCESSOR_PREDECESSOR_JOURNAL=CORRECTED_JOURNAL
SUCCESSOR_ATTEMPT='ONE_B_EXPIRED_UNUSED_SUCCESSOR_V1'
SUCCESSOR_UNUSED_RELEASE=Path('/home/maxrose26/stage4-owner/b-finite-release-20261103')
SUCCESSOR_UNUSED_PHASES=('seal-evidence','period-evidence','activate-evidence','qualify-evidence','handoff-evidence',
    'close-evidence','publication-revoke-evidence','handoff-restore-evidence','readback-evidence','submission.intent.json',
    'terminal-expected.json','final-expected.json')



# One fixed extension after the exact accepted, expired-unused successor. No
# arbitrary journal/path input and no erasure or reset of predecessor authority.
def select_reserve_successor():
    global SUCCESSOR_MARKER,SUCCESSOR_JOURNAL,SUCCESSOR_OUTPUT,SUCCESSOR_CLOSURE,SUCCESSOR_CLOSURE_SHA
    global PREDECESSOR_EXPIRY,PREDECESSOR_RECEIPT,SUCCESSOR_PREDECESSOR_PROOFS
    global SUCCESSOR_UNUSED_RELEASE,SUCCESSOR_PREDECESSOR_JOURNAL,SUCCESSOR_ATTEMPT
    SUCCESSOR_MARKER='mint-reserve-v2-20261103-01-consumed.json'
    SUCCESSOR_JOURNAL='mint-reserve-v2-20261103-01.vault'
    SUCCESSOR_OUTPUT='mint-evidence-reserve-v2-20261103-01'
    SUCCESSOR_ATTEMPT='ONE_B_PUBLICATION_MINT_RESERVE_V2_20261103_01'
    SUCCESSOR_CLOSURE=Path('/home/maxrose26/stage4-owner/b-successor-release-20261103/EXPIRED-UNUSED-SUCCESSOR-CLOSURE.json')
    SUCCESSOR_CLOSURE_SHA='e681654cd008cfca30a6c63dba522bb92a4412edcf7cb2430446b4779e09e522'
    PREDECESSOR_EXPIRY=1793708738
    PREDECESSOR_RECEIPT='352342cda2dd05a03848be80faf31830748bf55e0c5e841a86c0d3476db829a1'
    SUCCESSOR_PREDECESSOR_JOURNAL='mint-expired-unused-successor-01.vault'
    SUCCESSOR_PREDECESSOR_PROOFS={
        **SUCCESSOR_PREDECESSOR_PROOFS,
        'mint-evidence-expired-unused-successor-01/result.json':'8f175f5ae06a6f020d3f020f7ff41c3de6cf32523ec28a7c1268ca4cff9b0508',
        'mint-expired-unused-successor-01-consumed.json':'49b63877fd41cf60e132702e8963845a55715a4e97c21519db098f7456835e82',
        'mint-expired-unused-successor-01.vault':'64862226d0f9d0681afa357dfbf2c2ab09c1c13ccfe024994350d6f9385ce1d5',
    }
    SUCCESSOR_UNUSED_RELEASE=Path('/home/maxrose26/stage4-owner/b-successor-release-20261103')

def successor_preconditions(a,a_sha,vault_password=None,*,now=None):
    from zoneinfo import ZoneInfo
    stamp=time.time() if now is None else now
    need(stamp>PREDECESSOR_EXPIRY,'PREDECESSOR_NOT_EXPIRED')
    directory()
    for name,h in {**CORRECTED_PROOFS,**SUCCESSOR_PREDECESSOR_PROOFS}.items():
        need(digest(private_read(ROOT/name,32768))==h,'SUCCESSOR_PRECONDITION')
    for path,h in CORRECTED_EXTERNAL_PROOFS.items():
        need(digest(private_read(path,4096))==h,'SUCCESSOR_PRECONDITION')
    original=load_file(ROOT/'authority.json',CORRECTED_PROOFS['authority.json'])
    need(a==load_file(CORRECTED_AUTHORITY,CORRECTED_RAW_SHA)==dict(original,client_id='Iv23liHaM7meqJPpdD8x') and
         a_sha==CORRECTED_A_SHA==digest(canonical(a)),'SUCCESSOR_PRECONDITION')
    validate_authority(a)
    closure=load_file(SUCCESSOR_CLOSURE,SUCCESSOR_CLOSURE_SHA)
    need(closure.get('status')=='EXPIRED_UNUSED' and closure.get('recorded_expiry_epoch')==PREDECESSOR_EXPIRY and
         type(closure.get('observed_epoch')) in (int,float) and PREDECESSOR_EXPIRY<closure['observed_epoch']<=stamp and
         closure.get('token_specific_revocation')=='NOT_PERFORMED' and closure.get('installation_removal')=='NOT_PERFORMED' and
         closure.get('later_phases_evidenced') is False,'SUCCESSOR_PRECONDITION')
    for name in SUCCESSOR_UNUSED_PHASES:
        p=SUCCESSOR_UNUSED_RELEASE/name
        need(not p.exists() and not p.is_symlink(),'SUCCESSOR_PRECONDITION')
    need(not any(exists(n) for n in (SUCCESSOR_MARKER,SUCCESSOR_JOURNAL,SUCCESSOR_JOURNAL+'.next',
        'seal-01-consumed.json','seal-evidence-01','publication-01.vault','publication-01.vault.next','publication-01.vault.revoke-consumed',
        'b-20261103-tm-2e4ec5466a21-period.vault','b-20261103-tm-2e4ec5466a21-access.vault')),'EXISTING_ATTEMPT')
    local=datetime.fromtimestamp(stamp,ZoneInfo('Europe/London'))
    need(local.date().isoformat()=='2026-11-03','EXECUTION_DAY')
    need((datetime(2026,11,4,tzinfo=ZoneInfo('Europe/London'))-local).total_seconds()>3065,'MINT_DAY_MARGIN')
    if SUCCESSOR_ATTEMPT=='ONE_B_PUBLICATION_MINT_RESERVE_V2_20261103_01':
        from . import finite_release_binding as flow
        flow.use_timing_release();static=flow.static()
        need(static.get('execution_day')=='2026-11-03' and static.get('window')==dict(start='2026-10-27',end='2026-11-02',inclusive=True,tameside='RECEIVED',manchester='VALIDATED'),'EXECUTION_DAY')
        need(static.get('mint_authority')==dict(attempt=SUCCESSOR_ATTEMPT,predecessor_closure_sha256=SUCCESSOR_CLOSURE_SHA,predecessor_receipt_sha256=PREDECESSOR_RECEIPT,max_mint_posts=1,approved_for_execution=False) and
             static.get('mint_journal_path')==str(ROOT/SUCCESSOR_JOURNAL) and static.get('mint_result_path')==str(ROOT/SUCCESSOR_OUTPUT/'result.json'),'SUCCESSOR_PRECONDITION')
        for name in (*SUCCESSOR_UNUSED_PHASES,'owner-binding.json','period-policy.json','FROZEN.json','ACTUAL-MINT-REVIEW.json','handoff-observation.json','submission-observation.json','submission-check-evidence'):
            path=flow.ROOT/name;need(not path.exists() and not path.is_symlink(),'EXISTING_ATTEMPT')
        for value in (static['access_vault'],static['binding_fields']['period_vault_path']):
            path=Path(value);need(not path.exists() and not path.is_symlink() and not Path(str(path)+'.next').exists() and not Path(str(path)+'.next').is_symlink(),'EXISTING_ATTEMPT')
    if vault_password is not None:
        state=Vault(ROOT/SUCCESSOR_PREDECESSOR_JOURNAL,vault_password).load()
        need(state.get('version')=='ONE_B_MINT_V1' and state.get('post_started') is True and
             state.get('state')=='RECEIPT_VALIDATED_NOT_ARMED' and state.get('authority')==a and
             state.get('authority_sha256')==a_sha and state.get('receipt_sha256')==PREDECESSOR_RECEIPT and
             digest(canonical(state.get('receipt')))==PREDECESSOR_RECEIPT and
             state['receipt'].get('expiry')==PREDECESSOR_EXPIRY and state['receipt'].get('http_status')==201 and
             'binding' not in state and installation_token_allowed(state.get('token_candidate')),'SUCCESSOR_PRECONDITION')


def mint_journal(a_sha,*,successor=False):
    return SUCCESSOR_JOURNAL if successor else CORRECTED_JOURNAL if a_sha==CORRECTED_A_SHA else 'mint-01.vault'


def mint(a,a_sha,password,vault_password,*,transport_factory=Transport,clock=time.time,corrected_replacement=False,successor=False):
    """All errors return fixed diagnostics; POST entry is conservatively uncertain."""
    post=False;minted=False;journal=None;state=None;transport=None;prior=False
    try:
        directory();validate_authority(a);need(digest(canonical(a))==a_sha,'AUTHORITY')
        need(not(corrected_replacement and successor),'ARGUMENTS')
        keys=(SUCCESSOR_MARKER,SUCCESSOR_JOURNAL,SUCCESSOR_JOURNAL+'.next','seal-01-consumed.json','publication-01.vault')
        if not successor:keys+=(CORRECTED_MARKER,CORRECTED_JOURNAL,CORRECTED_JOURNAL+'.next')
        if not corrected_replacement and not successor:keys+=('mint-01-consumed.json','mint-01.vault')
        prior=any(exists(n) for n in keys)
        need(not prior,'EXISTING_ATTEMPT')
        if successor:successor_preconditions(a,a_sha,vault_password,now=clock())
        elif corrected_replacement:corrected_replacement_preconditions(a,a_sha,vault_password,now=clock())
        else:need(a_sha!=CORRECTED_A_SHA,'CORRECTED_REPLACEMENT')
        marker=SUCCESSOR_MARKER if successor else CORRECTED_MARKER if corrected_replacement else 'mint-01-consumed.json'
        intent=dict(attempt=ATTEMPT,authority_sha256=a_sha,retry=False)
        if successor:intent.update(attempt=SUCCESSOR_ATTEMPT,predecessor_receipt_sha256=PREDECESSOR_RECEIPT,predecessor_closure_sha256=SUCCESSOR_CLOSURE_SHA)
        exclusive(marker,intent)
        journal=Vault(ROOT/mint_journal(a_sha,successor=successor),vault_password,create=True)
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

def seal(a,a_sha,b,vault_password,*,clock=time.time,successor=False):
    """Local only. Consume seal intent before creating the existing token vault."""
    begun=False
    try:
        directory();validate_authority(a);need(digest(canonical(a))==a_sha,'AUTHORITY')
        need(not successor or a_sha==CORRECTED_A_SHA,'AUTHORITY')
        journal_path=Path(b['publication_mint_journal_path']) if 'timing_policy' in b else ROOT/mint_journal(a_sha,successor=successor)
        need(journal_path.parent==ROOT and journal_path.suffix=='.vault' and journal_path!=ROOT/'publication-01.vault','BINDING')
        journal=Vault(journal_path,vault_password);state=journal.load()
        need(state.get('version')=='ONE_B_MINT_V1' and state.get('authority')==a and state.get('authority_sha256')==a_sha and state.get('state')=='RECEIPT_VALIDATED_NOT_ARMED','RECEIPT')
        r=state['receipt'];need(state.get('receipt_sha256')==digest(canonical(r)) and r.get('authority_sha256')==a_sha,'RECEIPT')
        meta=dict(authority_sha256=a_sha,receipt_sha256=state['receipt_sha256'],expires_at=r['expiry'])
        need(b.get('publication_mint')==meta and b.get('publication_valid_until')==r['expiry'] and (b.get('valid_until')<=r['expiry'] if 'timing_policy' in b else b.get('valid_until')==r['expiry']) and b.get('publication_scope')==dict(repository=REPOSITORY,**PERMISSIONS) and b.get('publication_vault_path')==str(ROOT/'publication-01.vault'),'BINDING')
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

LOCAL_REFUSAL_SHA256='233a2cc3682039be4ed7db54c69d20ca515c56d5a05d5243e4e6134acc21ea2c'
REPLACEMENT_OUTPUT='mint-evidence-local-correction-01'


def replacement_preconditions():
    original=ROOT/'mint-evidence-01'
    need(original.is_dir() and not original.is_symlink() and
         {p.name for p in original.iterdir()}=={'result.json'},'LOCAL_REPLACEMENT')
    raw=private_read(original/'result.json',2048)
    need(digest(raw)==LOCAL_REFUSAL_SHA256 and parse(raw)==failure('SECRET','NOT_INFERRED_RECONCILE'),'LOCAL_REPLACEMENT')
    need(not any(exists(n) for n in ('mint-01-consumed.json','mint-01.vault','mint-01.vault.next',
        'seal-01-consumed.json','seal-evidence-01','publication-01.vault','publication-01.vault.next',
        'publication-01.vault.revoke-consumed')),'EXISTING_ATTEMPT')


def key_unlock(a, password):
    # Owner-terminal local validation only. No mint intent or provider request.
    # Only the known key-unlock refusal can be corrected here; fingerprint/path
    # drift and arbitrary exceptions remain terminal refusals.
    try: sign(a,password,time.time())
    except Refusal as exc:
        if exc.args==('KEY',): return False
        raise
    return True


def public_result(raw):
    need(len(raw)<=2048,'FILE_BOUND');r=parse(raw)
    need(type(r) is dict and set(r)<= {'status','reason','mint_outcome','retry','authority_sha256','receipt_sha256','expires_at','expiry','provider_calls'},'JSON')
    need(r.get('status') in ('STOP_MINT_SEAL_REQUIRES_REVIEW_NO_RETRY','MINT_RECEIPT_VALIDATED_NOT_ARMED','PRIVATE_PUBLICATION_TOKEN_ARMED') and r.get('retry') is False,'JSON')
    need(r.get('mint_outcome') in ('MINTED','MINTED_REQUIRES_CLOSURE','UNCERTAIN','DEFINITELY_NOT_SENT','PRIOR_ATTEMPT_RECONCILE','MINTED_NOT_ARMED','SEAL_UNCERTAIN_RECONCILE','NOT_INFERRED','NOT_INFERRED_RECONCILE'),'JSON')
    shapes={
        'STOP_MINT_SEAL_REQUIRES_REVIEW_NO_RETRY': {'status','reason','mint_outcome','retry'},
        'MINT_RECEIPT_VALIDATED_NOT_ARMED': {'status','mint_outcome','retry','authority_sha256','receipt_sha256','expires_at','expiry'},
        'PRIVATE_PUBLICATION_TOKEN_ARMED': {'status','mint_outcome','retry','receipt_sha256','provider_calls'}}
    need(set(r)==shapes[r['status']],'JSON')
    if r['status']!='STOP_MINT_SEAL_REQUIRES_REVIEW_NO_RETRY':need(r['mint_outcome']=='MINTED','JSON')
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
        parser.add_argument('--replace-local-refusal',action='store_true')
        parser.add_argument('--replace-issuer-refusal',action='store_true')
        parser.add_argument('--successor-expired-unused',action='store_true')
        parser.add_argument('--child',action='store_true');parser.add_argument('--secrets-fd',type=int)
        parser.add_argument('--reserve-v2',action='store_true');parser.add_argument('--launch',action='store_true');parser.add_argument('--continue-owner-session',action='store_true');parser.add_argument('--timing-v2',action='store_true')
        parser.error=lambda _: (_ for _ in ()).throw(Refusal('ARGUMENTS'))
        args=parser.parse_args(argv)
        if args.reserve_v2:
            need(args.successor_expired_unused and args.timing_v2,'ARGUMENTS');select_reserve_successor()
        if args.launch:
            need(not args.child and args.phase=='seal','ARGUMENTS')
            from . import finite_release_binding as flow
            import shlex
            try:flow.use_timing_release()
            except flow.PreparationError as exc:raise Refusal(exc.code) from None
            _,command=flow.next_command(expect='seal')
            raw=list(sys.argv[1:] if argv is None else argv)
            need(raw.count('--launch')==1 and [x for x in raw if x!='--launch']==shlex.split(command)[2:],'BINDING_ARGUMENT_MISMATCH')
        need(not args.continue_owner_session or (not args.child and args.phase=='mint'),'ARGUMENTS')
        if args.timing_v2:
            from .finite_release_binding import use_timing_release
            try:use_timing_release()
            except BaseException as exc:
                if getattr(exc,'code',None)=='TIMING_RELEASE_UNBOUND':raise Refusal('TIMING_RELEASE_UNBOUND') from None
                raise
        directory();a=load_file(args.authority,args.authority_sha256);validate_authority(a)
        a_sha=digest(canonical(a));b=None
        if args.phase=='seal':
            if args.successor_expired_unused:
                from .finite_release_binding import frozen_binding,PreparationError
                try:b,binding_path,binding_hash=frozen_binding()
                except PreparationError as exc:raise Refusal(exc.code) from None
                need((args.binding is None and args.binding_sha256 is None) or
                     (args.binding==str(binding_path) and args.binding_sha256==binding_hash),'BINDING_ARGUMENT_MISMATCH')
                args.binding=str(binding_path);args.binding_sha256=binding_hash
            else:
                need(args.binding is not None and Path(args.binding).is_file(),'BINDING_MISSING_RUN_FREEZE')
                b=load_file(args.binding,args.binding_sha256)
        else:need(args.binding is None and args.binding_sha256 is None,'ARGUMENTS')
        need(sum((args.replace_local_refusal,args.replace_issuer_refusal,args.successor_expired_unused))<=1,'ARGUMENTS')
        if args.replace_local_refusal:
            need(args.phase=='mint','ARGUMENTS');replacement_preconditions()
        if args.replace_issuer_refusal:
            need(args.phase=='mint','ARGUMENTS');corrected_replacement_preconditions(a,a_sha)
        if args.successor_expired_unused:
            need(a_sha==CORRECTED_A_SHA,'AUTHORITY')
            if args.phase=='mint':successor_preconditions(a,a_sha)
        if args.child:
            need(type(args.secrets_fd) is int and args.secrets_fd>2,'ARGUMENTS')
            try:secret=parse(os.read(args.secrets_fd,4096))
            finally:os.close(args.secrets_fd)
            need(type(secret) is dict and set(secret)=={'vault_password','key_password'},'SECRET')
            need(type(secret['vault_password']) is str and 24<=len(secret['vault_password'])<=1024,'SECRET')
            if args.phase=='mint':need(type(secret['key_password']) is str and 0<len(secret['key_password'])<=1024,'SECRET')
            else:need(secret['key_password'] is None,'SECRET')
            with envelope():
                result=mint(a,a_sha,secret['key_password'],secret['vault_password'],**({'successor':True} if args.successor_expired_unused else {'corrected_replacement':True} if args.replace_issuer_refusal else {})) if args.phase=='mint' else seal(a,a_sha,b,secret['vault_password'],**({'successor':True} if args.successor_expired_unused else {}))
        else:
            need(args.secrets_fd is None,'ARGUMENTS')
            need(sys.stdin.isatty() and sys.stderr.isatty(),'TTY')
            phrase='EXECUTE_ONE_RESERVE_V2_20261103_MINT' if args.reserve_v2 and args.phase=='mint' else 'EXECUTE_ONE_SUCCESSOR_AFTER_EXPIRED_UNUSED_MINT' if args.successor_expired_unused and args.phase=='mint' else 'EXECUTE_ONE_CORRECTED_ISSUER_B_PUBLICATION_TOKEN_MINT' if args.replace_issuer_refusal else 'EXECUTE_ONE_B_PUBLICATION_TOKEN_MINT' if args.phase=='mint' else 'SEAL_EXACT_B_PUBLICATION_TOKEN_ONCE'
            need(input('Approved phrase ('+phrase+'): ').strip()==phrase,'APPROVAL')
            from . import intake_owner_client as client
            destination=ROOT/(SUCCESSOR_OUTPUT if args.successor_expired_unused and args.phase=='mint' else CORRECTED_OUTPUT if args.replace_issuer_refusal else REPLACEMENT_OUTPUT if args.replace_local_refusal else args.phase+'-evidence-01')
            need(not destination.exists() and not destination.is_symlink(),'EXISTING_ATTEMPT')
            if args.phase=='mint' and args.successor_expired_unused:
                password=client.vault_input(ROOT/SUCCESSOR_PREDECESSOR_JOURNAL)
                successor_preconditions(a,a_sha,password)
                print('Retrieve PropertyAIgent — GitHub signing-key passphrase; same existing encrypted key.',file=sys.stderr)
                key_password=client.private_input('PropertyAIgent — GitHub signing-key passphrase (hidden): ',validator=lambda value:key_unlock(a,value),unlock_code='KEY')
            elif args.phase=='mint' and args.replace_issuer_refusal:
                password=client.vault_input(ROOT/'mint-01.vault')
                corrected_replacement_preconditions(a,a_sha,password)
                print('Retrieve PropertyAIgent — GitHub signing-key passphrase; same existing key, no rotation.',file=sys.stderr)
                key_password=client.private_input('PropertyAIgent — GitHub signing-key passphrase (hidden): ',validator=lambda value:key_unlock(a,value),unlock_code='KEY')
            elif args.phase=='mint':
                need(not any(exists(n) for n in ('mint-01-consumed.json','mint-01.vault',CORRECTED_MARKER,CORRECTED_JOURNAL,'seal-01-consumed.json','publication-01.vault')),'EXISTING_ATTEMPT')
                print('Choose/retain the B-state Vault passphrase for encrypted token, period and access state. This is distinct from the signing-key and PREBUILD baseline passphrases.',file=sys.stderr)
                password=client.private_input('B-state Vault passphrase (hidden, >=24 characters): ',minimum=24,confirm=True)
                print('Retrieve PropertyAIgent — GitHub signing-key passphrase to unlock the existing owner-local encrypted PEM; it never goes to Render.',file=sys.stderr)
                key_password=client.private_input('PropertyAIgent — GitHub signing-key passphrase (hidden): ',
                    validator=lambda value:key_unlock(a,value),unlock_code='KEY')
            else:
                password=client.vault_input(Path(b['publication_mint_journal_path']) if b is not None and 'timing_policy' in b else ROOT/mint_journal(a_sha,successor=args.successor_expired_unused))
                key_password=None
            # Recheck after unbounded owner input; authority is not consumed by
            # any recognised local correction above.
            if args.replace_local_refusal:replacement_preconditions()
            if args.replace_issuer_refusal:corrected_replacement_preconditions(a,a_sha,password)
            if args.successor_expired_unused and args.phase=='mint':successor_preconditions(a,a_sha,password)
            need(not destination.exists() and not destination.is_symlink(),'EXISTING_ATTEMPT')
            secrets_raw=canonical(dict(vault_password=password,key_password=key_password))
            need(len(secrets_raw)<=4000,'SECRET')
            destination.mkdir(mode=0o700);output=destination
            from .intake_owner_client import capture
            readfd,writefd=os.pipe()
            try:
                os.write(writefd,secrets_raw);os.close(writefd);writefd=None
                command=[sys.executable,'-B','-m','verification.ingestion_storage.publication_mint','--child','--secrets-fd',str(readfd),'--phase',args.phase,'--authority',str(Path(args.authority).absolute()),'--authority-sha256',args.authority_sha256]
                if args.replace_local_refusal:command+=['--replace-local-refusal']
                if args.replace_issuer_refusal:command+=['--replace-issuer-refusal']
                if args.successor_expired_unused:command+=['--successor-expired-unused']
                if args.timing_v2:command+=['--timing-v2']
                if args.reserve_v2:command+=['--reserve-v2']
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
    if result['status']=='MINT_RECEIPT_VALIDATED_NOT_ARMED' and args.continue_owner_session:
        key_password=None;secrets_raw=None  # Drop references; not guaranteed erasure.
        from .intake_owner_client import attended_session
        try:return attended_session(vault_password=password)
        except BaseException as exc:
            print(__import__(__package__+'.intake_owner_client',fromlist=['failure_output']).failure_output('UNKNOWN_PHASE',exc));return 2
        finally:password=None
    return 0 if result['status'] in ('MINT_RECEIPT_VALIDATED_NOT_ARMED','PRIVATE_PUBLICATION_TOKEN_ARMED') else 2

if __name__=='__main__':
    raise SystemExit(main())
