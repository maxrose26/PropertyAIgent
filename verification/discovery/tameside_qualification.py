"""Exactly one inactive listing-only qualification; existing reader/supervisor.

This does not register authority, create capture work, screen, publish or issue B.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import date, datetime, timezone

from app.ingestion.idox_adapter import IdoxListingContract
from app.ingestion.ledger import DEFAULT_LIMITS, Denied
from verification.discovery.idox_window import WindowConfig
from verification.ingestion_storage.operational_publication import canonical
from verification.ingestion_storage.operational_supervisor import supervise

ROW = dict(council='tameside', semantics='RECEIVED', start='2026-10-24', end='2026-10-30')
AUTHORITY = 'ONE_TAMESIDE_LISTING_METADATA_QUALIFICATION_20261024_30'
CONSUMPTION = Path('/home/maxrose26/stage4-owner/tameside-qualification-20261024-30-consumed.json')
SECOND_AUTHORITY = 'ONE_TAMESIDE_LISTING_METADATA_QUALIFICATION_20261024_30_ATTEMPT_02'
SECOND_OUTPUT = Path('/home/maxrose26/stage4-owner/tameside-listing-qualification-evidence-02')
SECOND_CONSUMPTION = Path('/home/maxrose26/stage4-owner/tameside-qualification-20261024-30-attempt-02-consumed.json')
PREDECESSOR_SHA256 = '0f6acecb8d134c0e107fb3b4069a7c314d6db1838d186f57691a7423cad0fd2b'
THIRD_AUTHORITY = 'ONE_TAMESIDE_LISTING_METADATA_QUALIFICATION_20261024_30_ATTEMPT_03'
THIRD_OUTPUT = Path('/home/maxrose26/stage4-owner/tameside-listing-qualification-evidence-03')
THIRD_CONSUMPTION = Path('/home/maxrose26/stage4-owner/tameside-qualification-20261024-30-attempt-03-consumed.json')
SECOND_CONSUMPTION_SHA256 = 'f23fcc2b5994df608690ce24971b1c25aa5f34164c6d3e4915ba776bab01d21d'
CALIBRATION_AUTHORITY='ONE_TAMESIDE_PAGINATION_CALIBRATION_20261024_30_V1'
CALIBRATION_OUTPUT=Path('/home/maxrose26/stage4-owner/tameside-pagination-calibration-evidence-01')
CALIBRATION_CONSUMPTION=Path('/home/maxrose26/stage4-owner/tameside-pagination-calibration-20261024-30-consumed.json')
THIRD_CONSUMPTION_SHA256='0d35e23218894e476dea5b5b37b53408ce8891acd91469932f0a4b4ea7c91d97'

QUALIFICATION_REASONS=frozenset("""
CALIBRATION_SCOPE
CALIBRATION_RETENTION_INCOMPLETE
CALIBRATION_PAGE_SIZE_IGNORED
CALIBRATION_SORT_CHANGED
CALIBRATION_PAGE_IDENTITY
CALIBRATION_NAVIGATION_AMBIGUOUS
CALIBRATION_NAVIGATION_UNSUPPORTED
CALIBRATION_NAVIGATION_CONFLICT
CALIBRATION_REPEATED_PAGE
CALIBRATION_DUPLICATE_IDENTITY
CALIBRATION_CONTRADICTORY_COUNTS
CALIBRATION_ERROR_RESPONSE
CALIBRATION_SESSION_EXPIRED
CALIBRATION_UNEXPECTED_MESSAGE
CALIBRATION_ROW_LAYOUT_REFUSED
CALIBRATION_SEARCH_BINDING
CALIBRATION_PAGE_CAP
CALIBRATION_ROW_CAP
CALIBRATION_REQUEST_CAP
CALIBRATION_BYTE_CAP
CALIBRATION_DEADLINE
CALIBRATION_TRACE_BOUND
CALIBRATION_TRACE_IO
CALIBRATION_UNKNOWN
OUTER_SAFETY
SCREENING_COLLECTION_MODE_REQUIRED
COLLECTION_PROFILE
PAYLOAD_BOUND
EXACT_IDOX_QUALIFICATION_AND_ZERO_RETRY_REQUIRED
IDOX_ACCOUNTING
IDOX_CLOCK
IDOX_COUNTS
IDOX_CRITERIA_BINDING
IDOX_CRITERIA_HASH
IDOX_OBSERVATION_PAGE_SHAPE
IDOX_OBSERVATION_REQUIRES_UNKNOWN_TOTAL
IDOX_OBSERVATION_ROWS_BELOW_PAGE_SIZE
IDOX_OBSERVATION_SINGLE_PAGE_ONLY
IDOX_QUALIFIED_WINDOW_REQUIRED
IDOX_RESOURCE_BOUND
IDOX_RESPONSE_ACCOUNTING
IDOX_RESPONSE_PROVENANCE
IDOX_ROW_DATE
IDOX_ROW_IDENTITY
IDOX_SEGMENT
IDOX_TERMINAL
IDOX_WINDOW_BINDING_OR_COMPLETENESS
IDOX_ZERO
OBSERVATION_TIMESTAMP_UTC_REQUIRED
OWNER_ACCEPTANCE_RECEIPT_BINDING
OWNER_ACCEPTANCE_SCOPE
OWNER_STOP
PARTIAL_OBSERVATION_NOT_ENABLED
PRIVATE_RESPONSE_NEW_DIRECTORY_REQUIRED
PRIVATE_RESPONSE_PROOF_BINDING
PRIVATE_RESPONSE_RETENTION_INCOMPLETE
PRIVATE_RESPONSE_SCOPE
PRIVATE_RESPONSE_UNSAFE_PATH
QUALIFICATION_CONTROL_BOUND
QUALIFICATION_PARENT_RSS
QUALIFICATION_SOURCE_EXPORT
QUALIFICATION_SOURCE_OR_CLOSURE_UNCERTAIN_NO_RETRY
SOURCE_AUDIT_BOUND
UNKNOWN
""".split())
QUALIFICATION_STAGES=frozenset({'PREPARE','SOURCE','SOURCE_SAFETY','SOURCE_EXPORT','PRIVATE_RETENTION','PROJECTION','ASSESSMENT','CALIBRATION','UNKNOWN'})


def qualification_outcome(root, stage, exc=None):
    from verification.discovery.four_council_proof import ProofError
    reason='UNKNOWN'
    if type(exc) in (Denied,ProofError,ValueError) and len(exc.args)==1 and type(exc.args[0]) is str and exc.args[0] in QUALIFICATION_REASONS:
        reason=exc.args[0]
    value=dict(status='REFUSED' if exc is not None else 'OBSERVATIONS_RECORDED' if stage=='CALIBRATION' else 'PROJECTION_ACCEPTED_ASSESSMENT_REQUIRED',
               stage=stage if stage in QUALIFICATION_STAGES else 'UNKNOWN',reason=reason if exc is not None else 'NONE',retry=False)
    raw=canonical(value)
    if len(raw)>2048:raise Denied('QUALIFICATION_CONTROL_BOUND')
    control_bound(root,reserve=len(raw))
    temporary=Path(root)/'qualification-outcome.next'
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temporary,Path(root)/'qualification-outcome.json')
    return value


def control_bound(root, *, reserve=0):
    # Existing owned scratch is independently bounded by the unchanged supervisor.
    files=[f for f in Path(root).rglob('*') if 'owned' not in f.relative_to(root).parts]
    if len(files)>64 or any(f.is_symlink() for f in files):raise Denied('QUALIFICATION_CONTROL_BOUND')
    controls=[f for f in files if f.is_file() and f.name!='source.json' and not f.name.endswith('.body')]
    if sum(f.stat().st_size for f in controls)+reserve>65536:raise Denied('QUALIFICATION_CONTROL_BOUND')


def qualify(root, *, supervisor=supervise, authority=AUTHORITY, private_pages=False, pagination_calibration=False):
    root = Path(root)
    if root.exists() or root.is_symlink(): raise Denied('NEW_QUALIFICATION_OUTPUT_REQUIRED')
    root.mkdir(mode=0o700)
    (root/'CONSUMED').write_text(authority + '\n')
    stage='PREPARE'
    try:
        plan = root/'plan.json'; output = root/'source.json'
        plan_value=dict(row=ROW, fixture=None)
        if private_pages:
            if authority not in (THIRD_AUTHORITY,CALIBRATION_AUTHORITY):raise Denied('PRIVATE_RESPONSE_SCOPE')
            (root/'raw-bodies').mkdir(mode=0o700)
            plan_value['private_response_bodies']=str((root/'raw-bodies').resolve())
        if pagination_calibration:
            if authority!=CALIBRATION_AUTHORITY or not private_pages:raise Denied('CALIBRATION_SCOPE')
            plan_value['pagination_calibration']='TAMESIDE_FIVE_PER_PAGE_V1'
        plan.write_bytes(canonical(plan_value))
        def check():
            import psutil
            if private_pages:control_bound(root)
            if psutil.Process().memory_info().rss > 256*1024**2: raise Denied('QUALIFICATION_PARENT_RSS')
            if (root/'STOP').exists(): raise Denied('OWNER_STOP')
        stage='SOURCE'
        outer = supervisor([sys.executable, '-B', '-m', 'verification.ingestion_storage.daily_intake_runtime',
                            '--source-worker', '--plan', str(plan.resolve()), '--output', str(output.resolve())],
                           environment={'INGESTION_SOURCE_PRIVATE': 'ONCE'}, root=root/'owned',
                           source=True, seconds=45, stop_file=root/'STOP', check=check)
        outer['observed_at'] = datetime.now(timezone.utc).isoformat()
        stage='SOURCE_SAFETY'
        if private_pages and len(canonical(outer))>4096:raise Denied('QUALIFICATION_CONTROL_BOUND')
        (root/'outer.json').write_bytes(canonical(outer))
        if outer.get('cleanup') != 'CLOSED' or outer.get('exit_code') != 0 or outer.get('limit_hit') is not None:
            raise Denied('QUALIFICATION_SOURCE_OR_CLOSURE_UNCERTAIN_NO_RETRY')
        stage='SOURCE_EXPORT'
        if not output.is_file() or output.is_symlink() or output.stat().st_size > 524288:
            raise Denied('QUALIFICATION_SOURCE_EXPORT')
        raw = output.read_bytes(); source = json.loads(raw)
        if private_pages:
            stage='PRIVATE_RETENTION'
            from verification.discovery.four_council_proof import validate_private_responses
            validate_private_responses(root/'raw-bodies',source)
            control_bound(root,reserve=2048+16384)
        if pagination_calibration:
            stage='CALIBRATION'
            from verification.discovery.pagination_calibration import MODE,CODES
            observation=source.get('calibration',{})
            if observation.get('mode')!=MODE or observation.get('acceptance_enabled') is not False:raise Denied('CALIBRATION_SCOPE')
            code=observation.get('failure')
            if code is None and (observation.get('criteria_verified') is not True or observation.get('state')!='OBSERVATIONS_REQUIRE_REVIEW'):code='CALIBRATION_UNKNOWN'
            summary=dict(status='CALIBRATION_OBSERVATIONS_REQUIRE_REVIEW' if code is None and observation.get('criteria_verified') is True else 'CALIBRATION_STOP_REQUIRES_REVIEW',mode=MODE,acceptance_enabled=False,completeness='UNKNOWN',reason=code if code in CODES else 'NONE' if code is None else 'UNKNOWN',observed_pages=len(observation.get('pages',[])),observed_records=len(source.get('records',[])),source_sha256=hashlib.sha256(raw).hexdigest(),criteria_verified=observation.get('criteria_verified') is True,product_decision_required=True,retry=False)
            if len(canonical(summary))>4096:raise Denied('QUALIFICATION_CONTROL_BOUND')
            control_bound(root,reserve=4096+2048)
            fd=os.open(root/'calibration-summary.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as f:f.write(canonical(summary));f.flush();os.fsync(f.fileno())
            if code is not None:raise Denied(code if code in CODES else 'UNKNOWN')
            qualification_outcome(root,stage)
            return summary
        stage='PROJECTION'
        c = WindowConfig('tameside', 'RECEIVED', date(2026,10,24), date(2026,10,30), 0, 60)
        # The assessment uses the exact source SHA as a provisional evidence identity;
        # REVIEW of the resulting qualification manifest is still required for B.
        contract = IdoxListingContract('tameside-screening-metadata-v1', c, hashlib.sha256(raw).hexdigest())
        receipt = contract.project(source, outer, DEFAULT_LIMITS, source_bytes_limit=524288)
        counts = {}
        for record in receipt['records']:
            for field, literal in record['fields'].items():
                bucket = counts.setdefault(field, {}); bucket[literal['state']] = bucket.get(literal['state'], 0) + 1
        result = dict(status='QUALIFICATION_EVIDENCE_REQUIRES_REVIEW', authority=authority, row=ROW,
                      source_sha256=hashlib.sha256(raw).hexdigest(), outer_sha256=hashlib.sha256(canonical(outer)).hexdigest(),
                      record_count=len(receipt['records']), pages=len(receipt['segments']), fields=counts,
                      source_calls=1, source_attempts=1, database_connections=0, persistence=False,
                      explicit_zero=not receipt['records'], replay=False,
                      limits=dict(requests=10, received_bytes=3000000, source_seconds=45,
                                  supervised_reservation_seconds=60, rows=60, pages=6, source_export_bytes=524288))
        stage='ASSESSMENT'
        if private_pages:
            if len(canonical(result))>16384:raise Denied('QUALIFICATION_CONTROL_BOUND')
            qualification_outcome(root,stage)
        if private_pages:
            fd=os.open(root/'assessment.next',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as f:f.write(canonical(result));f.flush();os.fsync(f.fileno())
            if (root/'assessment.json').exists() or (root/'assessment.json').is_symlink():raise Denied('QUALIFICATION_CONTROL_BOUND')
            os.replace(root/'assessment.next',root/'assessment.json')
        else:(root/'assessment.json').write_bytes(canonical(result))
        return result
    except BaseException as exc:
        if private_pages:
            try:qualification_outcome(root,stage,exc)
            except Exception:pass  # missing/nonfinal outcome remains uncertainty
        raise


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', required=True); p.add_argument('--authority', required=True)
    a = p.parse_args()
    consumption=CONSUMPTION
    if a.authority == CALIBRATION_AUTHORITY:
        if a.output!=str(CALIBRATION_OUTPUT):raise SystemExit('EXACT_CALIBRATION_OUTPUT_REQUIRED')
        for path,expected in ((CONSUMPTION,PREDECESSOR_SHA256),(SECOND_CONSUMPTION,SECOND_CONSUMPTION_SHA256),(THIRD_CONSUMPTION,THIRD_CONSUMPTION_SHA256)):
            if path.is_symlink() or not path.is_file() or path.stat().st_size>4096 or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise SystemExit('ALL_THREE_CONSUMPTIONS_REQUIRED')
        consumption=CALIBRATION_CONSUMPTION
    elif a.authority == THIRD_AUTHORITY:
        if a.output!=str(THIRD_OUTPUT):raise SystemExit('EXACT_THIRD_ATTEMPT_OUTPUT_REQUIRED')
        for path,expected in ((CONSUMPTION,PREDECESSOR_SHA256),(SECOND_CONSUMPTION,SECOND_CONSUMPTION_SHA256)):
            if path.is_symlink() or not path.is_file() or path.stat().st_size>4096 or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise SystemExit('BOTH_ORIGINAL_CONSUMPTIONS_REQUIRED')
        consumption=THIRD_CONSUMPTION
    elif a.authority == SECOND_AUTHORITY:
        if a.output != str(SECOND_OUTPUT):raise SystemExit('EXACT_SECOND_ATTEMPT_OUTPUT_REQUIRED')
        if (CONSUMPTION.is_symlink() or not CONSUMPTION.is_file() or CONSUMPTION.stat().st_size>4096
            or hashlib.sha256(CONSUMPTION.read_bytes()).hexdigest()!=PREDECESSOR_SHA256):
            raise SystemExit('ORIGINAL_CONSUMPTION_BINDING_REQUIRED')
        consumption=SECOND_CONSUMPTION
    elif a.authority != AUTHORITY:raise SystemExit('SOURCE_APPROVAL_BINDING_REQUIRED')
    if any('DATABASE' in k or k.endswith(('_KEY', '_TOKEN', '_PASSWORD')) for k in os.environ):
        raise SystemExit('CREDENTIAL_FREE_OWNER_PARENT_REQUIRED')
    os.umask(0o077)
    try:
        with consumption.open('x') as record:
            json.dump(dict(authority=a.authority,row=ROW,state='CONSUMED_BEFORE_SOURCE',
                           output=str(Path(a.output).resolve())),record,sort_keys=True)
            record.flush();os.fsync(record.fileno())
        if a.authority in (SECOND_AUTHORITY,THIRD_AUTHORITY,CALIBRATION_AUTHORITY):
            fd=os.open(consumption.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
    except OSError:
        raise SystemExit('QUALIFICATION_CONSUMED_OR_RECORD_UNAVAILABLE_RECONCILE_NO_RETRY') from None
    try:
        result = qualify(a.output,authority=a.authority,private_pages=True,pagination_calibration=True) if a.authority==CALIBRATION_AUTHORITY else qualify(a.output,authority=a.authority,private_pages=True) if a.authority==THIRD_AUTHORITY else qualify(a.output) if a.authority==AUTHORITY else qualify(a.output,authority=a.authority)
        print(json.dumps({k:result[k] for k in (('status','observed_pages','observed_records','source_sha256') if a.authority==CALIBRATION_AUTHORITY else ('status','record_count','pages','source_sha256'))}))
    except BaseException:
        print('STOP_QUALIFICATION_REQUIRES_REVIEW_NO_RETRY'); return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
