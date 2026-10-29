"""Closed Oldham standing selection/public projection; no authority or expiry rendering."""
from datetime import datetime,timezone,timedelta,date
from types import SimpleNamespace
from app.ingestion.ledger import Denied,digest,DEFAULT_LIMITS
from app.ingestion.listing_screening import ScreeningRule,RULE_V3
from app.ingestion import owner_acceptance
from . import oldham_owner_package as pkg
from .standing_access import GITHUB
from .oldham_authority import derive,registration_value
from .scope_binding import binding_for
from .operational_owner import Owner
from .operational_runner import IdoxListingContract
from verification.discovery.idox_window import WindowConfig
from verification.discovery.outer_evidence import outer_from_slot_receipt
from .operational_publication import canonical

VERSION='OLDHAM_STANDING_CAPTURE_SCREENING_V1'
PREVIOUS='oldham-owner-installed-capture-screening-20261029'
PREVIOUS_COMMIT='4700f6276203e6ba043897e1f914816e6713e6a6'
PREVIOUS_RESULT='568cd64dcb254544bc166c3228585a679f4323dfecffb5153174c7c8965cc35a'
PREVIOUS_AUDIT='75053fb59c792797cf7aca7703ef9e2e643d460bd3b2ce5b31cbf68823737174'
FIELDS={'version','package','github','standing','prior_attempt','runtime_admission'}


class GrantDescription:
    """Pure accepted grant builder; no connector/register/issue/revoke capability."""
    build_grant=Owner.build_grant
    standing_capture_screening=True
    capture_screening_only=True
    grant_expiry=None
    def __init__(self,p,seal):
        self.expiry=datetime.fromisoformat(p['expires_at'])
        self.bindings=dict(revision=p['revision'],workflow_sha256=p['dependencies']['verification/ingestion_storage/oldham_standing_owner.py'],manifest_sha256=seal)


def manifest(p,*,standing=None,runtime_admission=None):
    return dict(version=VERSION,package=p,github=GITHUB,standing=standing,
                runtime_admission=runtime_admission,prior_attempt=dict(release_id=PREVIOUS,commit=PREVIOUS_COMMIT,result_sha256=PREVIOUS_RESULT,audit_prefix_sha256=PREVIOUS_AUDIT,disposition='CONSUMED_NO_REPLAY_RECONCILE_BEFORE_EFFECTS'))


def validate_selection(value,*,inactive=False):
    if not isinstance(value,dict) or set(value)!=FIELDS or value['version']!=VERSION or value['github']!=GITHUB:raise Denied('OLDHAM_STANDING_SELECTION')
    p=value['package']
    if set(p)!=pkg.FIELDS_INSTALLED or p['version']!=pkg.VERSION_INSTALLED or p['operation']!='CAPTURE_SCREENING_ONLY':raise Denied('OLDHAM_STANDING_OPERATION')
    if p['scope']!=dict(kind='DISCOVERY_SCOPE',council='oldham',semantics='RECEIVED',start='2026-10-15',end='2026-10-21'):raise Denied('OLDHAM_STANDING_SCOPE')
    if value['prior_attempt']!=manifest(p)['prior_attempt']:raise Denied('OLDHAM_STANDING_CONSUMED_BINDING')
    if inactive:
        if p['expires_at'] is not None:raise Denied('OLDHAM_STANDING_INACTIVE')
    else:
        expiry=datetime.fromisoformat(p['expires_at']);now=datetime.now(timezone.utc)
        if expiry.tzinfo is None or not now+timedelta(seconds=480)<expiry<=now+timedelta(hours=24):raise Denied('OLDHAM_STANDING_EXPIRY')
        admission=value['runtime_admission']
        if not isinstance(admission,dict) or set(admission)!={'run_number'} or type(admission['run_number']) is not int or admission['run_number']<1:raise Denied('OLDHAM_STANDING_RUNTIME_IDENTITY')
        state=value['standing']
        if not isinstance(state,dict) or set(state)!={'valid_until','state_sha256','qualification_sha256','credential_preparation_github_calls'}:raise Denied('OLDHAM_STANDING_QUALIFICATION_REQUIRED')
        if type(state['credential_preparation_github_calls']) is not int or not 0<=state['credential_preparation_github_calls']<=11:raise Denied('OLDHAM_STANDING_PREPARATION_ACCOUNTING')
        from .standing_access import valid_credential_lifetime
        valid_credential_lifetime(state['valid_until'],expiry)
        for k in ('state_sha256','qualification_sha256'):
            if not isinstance(state[k],str) or len(state[k])!=64 or any(c not in '0123456789abcdef' for c in state[k]):raise Denied('OLDHAM_STANDING_QUALIFICATION_REQUIRED')
    return p


def public_claim(value,data,started_at):
    p=validate_selection(value);seal=digest(value);description=GrantDescription(p,seal)
    capture=derive(description,data['binding'],data['contract'],revision=p['revision'],item_limits=DEFAULT_LIMITS,phase='CAPTURE')
    return dict(version=VERSION,manifest=value,manifest_sha256=seal,inputs=dict(source=data['source'],slot=__import__('json').loads(data['slot_raw']),qualification=data['qualification']),
                capture_registration=registration_value(capture),package_started_at=started_at)


def runtime_inputs(claim,*,disposable=False):
    if not isinstance(claim,dict) or set(claim)!={'version','manifest','manifest_sha256','inputs','capture_registration','package_started_at'} or claim['version']!=VERSION:raise Denied('OLDHAM_STANDING_CLAIM')
    value=claim['manifest'];p=validate_selection(value);seal=digest(value)
    if claim['manifest_sha256']!=seal or p['revision']!=pkg.git('rev-parse','HEAD') or p['tree']!=pkg.git('rev-parse','HEAD^{tree}') or pkg.git('status','--porcelain'):raise Denied('OLDHAM_STANDING_CHECKOUT')
    if p['dependencies']!=pkg.dependencies() or p['packages']!=pkg.packages():raise Denied('OLDHAM_STANDING_DEPENDENCIES')
    if p['mode']!=('DISPOSABLE_TEST' if disposable else 'LIVE'):raise Denied('OLDHAM_STANDING_TEST_BOUNDARY')
    inputs=claim['inputs']
    if not isinstance(inputs,dict) or set(inputs)!={'source','slot','qualification'}:raise Denied('OLDHAM_STANDING_INPUTS')
    source,slot,q=[inputs[k] for k in ('source','slot','qualification')]
    for k,obj,bound in [('source',source,512*1024),('outer',slot,16*1024),('qualification',q,64*1024)]:
        raw=canonical(obj)
        if len(raw)>bound or pkg.sha(raw)!=p[k]['sha256']:raise Denied('OLDHAM_STANDING_INPUT_HASH')
    outer=slot['outer_supervisor'] if disposable else outer_from_slot_receipt(slot,source)
    if slot.get('source_sha256')!=digest(source) or slot.get('scope')!={k:p['scope'][k] for k in ('council','semantics','start','end')}:raise Denied('OLDHAM_STANDING_SUPERVISOR')
    if not disposable and canonical(q)!=canonical(__import__('json').loads(pkg.QUALIFICATION.read_bytes())):raise Denied('OLDHAM_ACCEPTED_QUALIFICATION_REQUIRED')
    if disposable:
        if q!=dict(kind='DISPOSABLE_TEST_QUALIFICATION',council='oldham',live_authority=False):raise Denied('OLDHAM_TEST_QUALIFICATION')
    elif any(k in source or k in outer for k in ('test_only','evidence_label','test_evidence')):raise Denied('OLDHAM_SYNTHETIC_NOT_LIVE')
    accepted=owner_acceptance.require(p['owner_acceptance'])
    expected=dict(qualification_sha256=pkg.sha(canonical(q)),source_sha256=digest(source),outer_sha256=digest(outer),scope=p['scope'],dependencies_sha256=digest(p['dependencies']),owner_acceptance_sha256=accepted.sha256)
    if p['qualification_binding']!=expected:raise Denied('OLDHAM_QUALIFICATION_CARRY_FORWARD_BINDING')
    contract=IdoxListingContract('oldham-owner-complete-v1',WindowConfig('oldham','RECEIVED',date(2026,10,15),date(2026,10,21),max_transport_retries=0),pkg.sha(canonical(q)),owner_acceptance=p['owner_acceptance'])
    projection=contract.project(source,outer,DEFAULT_LIMITS,source_bytes_limit=512*1024)
    if len(projection['records'])!=5:raise Denied('OLDHAM_STANDING_FIVE_RECORDS')
    description=GrantDescription(p,seal);binding=binding_for('oldham');capture=derive(description,binding,contract,revision=p['revision'],item_limits=DEFAULT_LIMITS,phase='CAPTURE')
    if registration_value(capture)!=claim['capture_registration']:raise Denied('OLDHAM_STANDING_CAPTURE_REGISTRATION')
    start=datetime.fromisoformat(claim['package_started_at']);now=datetime.now(timezone.utc)
    if start.tzinfo is None or start>now or (now-start).total_seconds()>=450:raise Denied('OLDHAM_STANDING_ORIGINAL_CLOCK')
    return dict(package=p,manifest=value,seal=seal,description=description,binding=binding,contract=contract,capture=capture,source=source,outer=outer,source_raw=canonical(source),started=start,rule=ScreeningRule(RULE_V3,unit_threshold=10,link_related=False))
