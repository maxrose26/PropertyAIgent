"""Pure/local sealed-input checks. No credential lookup, database or source client."""
from datetime import datetime,timezone,timedelta,date
import hashlib,importlib.metadata,json,re,subprocess
from pathlib import Path
from app.ingestion.ledger import Denied,DEFAULT_LIMITS,digest
from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion import owner_acceptance
from .scope_binding import binding_for,scope_for
from .oldham_allocation import capacity
from .operational_publication import canonical
from verification.discovery.idox_window import WindowConfig

VERSION='OLDHAM_OWNER_WRAPPER_V1'
VERSION_ACCEPTED='OLDHAM_OWNER_WRAPPER_V2'      # V1 plus an explicit, sealed `owner_acceptance` key (specification 037); V1 packages are validated exactly as before
VERSION_CAPTURE_SCREENING='OLDHAM_CAPTURE_SCREENING_V1'
RISK='ACCEPT_POSSIBLE_PROVIDER_SCRAM_RETENTION_WORKER_EFFECT_APPLICATION_ONCE'
QUALIFICATION=Path('docs/design/stage4-discovery/evidence/idox-family1-oldham.json')
PACKAGES=('psycopg','SQLAlchemy','cryptography','requests','beautifulsoup4','psutil','PyYAML')
FIELDS={'version','mode','release_id','revision','tree','dependencies','packages','scope','source','outer','qualification','qualification_binding','control_sha256','evidence_head','origin','expires_at','risk_acceptance'}
FIELDS_ACCEPTED=FIELDS|{'owner_acceptance'}
FIELDS_CAPTURE_SCREENING=(FIELDS_ACCEPTED-{'control_sha256'})|{'operation','transition','control_stop_sha256'}

def sha(raw):return hashlib.sha256(raw).hexdigest()

def git(*args):
    return subprocess.run(['git',*args],check=True,capture_output=True,text=True,timeout=5).stdout.strip()

def dependencies():
    names=git('ls-files','app','config','verification').splitlines()
    names=[n for n in names if Path(n).suffix in {'.py','.sql','.yaml','.yml','.pem','.lock'}]
    return {n:sha(Path(n).read_bytes()) for n in names}

def packages():return {p:importlib.metadata.version(p) for p in PACKAGES}

def read_file(base,description,bound):
    if not isinstance(description,dict) or set(description)!={'name','sha256'}:raise Denied('OLDHAM_INPUT_DESCRIPTOR')
    name=description['name']
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',name) or name in {'.','..'}:raise Denied('OLDHAM_INPUT_PATH')
    path=base/name
    if path.is_symlink() or not path.is_file() or path.stat().st_size>bound:raise Denied('OLDHAM_INPUT_FILE')
    raw=path.read_bytes()
    if sha(raw)!=description['sha256']:raise Denied('OLDHAM_INPUT_HASH')
    value=json.loads(raw)
    if raw!=canonical(value):raise Denied('OLDHAM_CANONICAL_INPUT_REQUIRED')
    return value,raw

def validate(path,expected_sha,*,disposable=False,now=None):
    path=Path(path);now=now or datetime.now(timezone.utc)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>128*1024:raise Denied('OLDHAM_PACKAGE_FILE')
    raw=path.read_bytes()
    if sha(raw)!=expected_sha:raise Denied('OLDHAM_PACKAGE_HASH')
    p=json.loads(raw)
    shapes={VERSION:FIELDS,VERSION_ACCEPTED:FIELDS_ACCEPTED,VERSION_CAPTURE_SCREENING:FIELDS_CAPTURE_SCREENING}
    if not isinstance(p,dict) or p.get('version') not in shapes or set(p)!=shapes[p['version']]:raise Denied('OLDHAM_PACKAGE_FIELDS')
    capture_screening_only=p['version']==VERSION_CAPTURE_SCREENING
    if p['mode']!=('DISPOSABLE_TEST' if disposable else 'LIVE'):raise Denied('OLDHAM_TEST_MODE_BOUNDARY')
    if not isinstance(p['release_id'],str) or not re.fullmatch(r'oldham-owner-[a-z0-9-]{1,60}',p['release_id']):raise Denied('OLDHAM_RELEASE_ID')
    if p['revision']!=git('rev-parse','HEAD') or p['tree']!=git('rev-parse','HEAD^{tree}') or git('status','--porcelain'):raise Denied('OLDHAM_CHECKOUT_BINDING')
    if p['dependencies']!=dependencies() or p['packages']!=packages():raise Denied('OLDHAM_DEPENDENCY_BINDING')
    from . import oldham_transition as transition
    if p['risk_acceptance']!=(transition.RISK if capture_screening_only else RISK):raise Denied('OLDHAM_THREE_LOGIN_RISK_ACCEPTANCE')
    if capture_screening_only:
        t=p['transition']
        if p['operation']!=transition.OPERATION or not isinstance(t,dict) or set(t)!={'inspection','predecessor','retire_standing','external_consumers_confirmed','installation_sha256','rollback_sha256'}:raise Denied('OLDHAM_TRANSITION_BINDING')
        if t['retire_standing'] is not True or t['external_consumers_confirmed'] is not True:raise Denied('OLDHAM_RETIREMENT_CONFIRMATION_REQUIRED')
        inspection,_=read_file(path.parent,t['inspection'],64*1024)
        if not disposable and any(k in inspection for k in ('evidence_label','test_evidence','test_only')):raise Denied('OLDHAM_SYNTHETIC_INSPECTION_NOT_LIVE')
        transition.validate_inspection(inspection,t['predecessor'])
        install,rollback=transition.texts(t['predecessor'])
        if t['installation_sha256']!=sha(install.encode()) or t['rollback_sha256']!=sha(rollback.encode()):raise Denied('OLDHAM_INSTALLATION_BINDING')
    expiry=datetime.fromisoformat(p['expires_at'])
    if expiry.tzinfo is None or not now+timedelta(seconds=480)<expiry<=now+timedelta(hours=24):raise Denied('OLDHAM_PACKAGE_EXPIRY')
    control_key='control_stop_sha256' if capture_screening_only else 'control_sha256'
    if any(not isinstance(p[k],str) or not re.fullmatch('[a-f0-9]{'+str(n)+'}',p[k]) for k,n in [(control_key,64),('evidence_head',40)]):raise Denied('OLDHAM_PACKAGE_IDENTITIES')
    if capture_screening_only:
        from .oldham_authority import STOP_STATE
        if p['control_stop_sha256']!=digest(STOP_STATE):raise Denied('OLDHAM_TRANSITION_STOP_BINDING')
    origin=p['origin']
    if not isinstance(origin,dict) or set(origin)!={'commit','source_path','slot_path'} or not re.fullmatch('[a-f0-9]{40}',origin['commit']):raise Denied('OLDHAM_ORIGIN_BINDING')
    if not re.fullmatch(r'docs/design/ingestion-operational-execution-[a-z0-9-]+/slot-[0-9]+/source.json',origin['source_path']) or origin['slot_path']!=origin['source_path'].rsplit('/',1)[0]+'/receipt.json':raise Denied('OLDHAM_ORIGIN_PATH')
    binding=binding_for('oldham');scope=p['scope']
    if scope!=scope_for(binding,scope.get('start'),scope.get('end')):raise Denied('OLDHAM_PACKAGE_SCOPE')
    source,source_raw=read_file(path.parent,p['source'],512*1024)
    slot,outer_raw=read_file(path.parent,p['outer'],16*1024)
    if disposable:
        outer=slot.get('outer_supervisor')
        if slot.get('source_sha256')!=digest(source):raise Denied('OLDHAM_SUPERVISOR_SOURCE_BINDING')
    else:
        from verification.discovery.outer_evidence import outer_from_slot_receipt
        outer=outer_from_slot_receipt(slot,source)
    if slot.get('scope')!={k:scope[k] for k in ('council','semantics','start','end')}:raise Denied('OLDHAM_SUPERVISOR_SCOPE_BINDING')
    qualification,qraw=read_file(path.parent,p['qualification'],64*1024)
    if disposable:
        if qualification!=dict(kind='DISPOSABLE_TEST_QUALIFICATION',council='oldham',live_authority=False):raise Denied('OLDHAM_TEST_QUALIFICATION')
    else:
        if qraw!=canonical(json.loads(QUALIFICATION.read_bytes())):raise Denied('OLDHAM_ACCEPTED_QUALIFICATION_REQUIRED')
        if any(k in source or k in outer for k in ('evidence_label','test_evidence','test_only')):raise Denied('OLDHAM_SYNTHETIC_NOT_LIVE')
    accepted_key=None;expected=dict(qualification_sha256=sha(qraw),source_sha256=digest(source),outer_sha256=digest(outer),scope=scope,dependencies_sha256=digest(p['dependencies']))
    if p['version'] in (VERSION_ACCEPTED,VERSION_CAPTURE_SCREENING):
        accepted_key=p['owner_acceptance'];acc=owner_acceptance.require(accepted_key);d=acc.data      # a KEY STRING of the closed in-code registry; null, an object or an unknown key is refused
        if (d['council'],d['semantics'],d['start'],d['end'])!=(scope['council'],scope['semantics'],scope['start'],scope['end']):raise Denied('OLDHAM_OWNER_ACCEPTANCE_SCOPE')
        expected=dict(expected,owner_acceptance_sha256=acc.sha256)      # the owner-approved package seals the exact acceptance, beside the code hashes that already cover the registry module
    if p['qualification_binding']!=expected:raise Denied('OLDHAM_QUALIFICATION_CARRY_FORWARD_BINDING')
    contract=IdoxListingContract('oldham-owner-complete-v1',WindowConfig('oldham','RECEIVED',date.fromisoformat(scope['start']),date.fromisoformat(scope['end']),max_transport_retries=0),sha(qraw),owner_acceptance=accepted_key)
    projected=contract.project(source,outer,DEFAULT_LIMITS,source_bytes_limit=512*1024)
    capacity(len(projected['records']),0)
    # Known input/publication costs must leave the unchanged reporting reserve.
    if len(raw)+len(source_raw)+len(qraw)+len(outer_raw)>2*1024**2-128*1024:raise Denied('OLDHAM_INITIAL_EXPORT_CAPACITY')
    return dict(package=p,raw=raw,source=source,source_raw=source_raw,outer=outer,slot_raw=outer_raw,qualification=qualification,qraw=qraw,contract=contract,binding=binding,expiry=expiry,sha256=expected_sha)
