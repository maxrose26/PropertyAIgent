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


def qualify(root, *, supervisor=supervise, authority=AUTHORITY):
    root = Path(root)
    if root.exists() or root.is_symlink(): raise Denied('NEW_QUALIFICATION_OUTPUT_REQUIRED')
    root.mkdir(mode=0o700)
    (root/'CONSUMED').write_text(authority + '\n')
    plan = root/'plan.json'; output = root/'source.json'
    plan.write_bytes(canonical(dict(row=ROW, fixture=None)))
    def check():
        import psutil
        if psutil.Process().memory_info().rss > 256*1024**2: raise Denied('QUALIFICATION_PARENT_RSS')
        if (root/'STOP').exists(): raise Denied('OWNER_STOP')
    outer = supervisor([sys.executable, '-B', '-m', 'verification.ingestion_storage.daily_intake_runtime',
                        '--source-worker', '--plan', str(plan.resolve()), '--output', str(output.resolve())],
                       environment={'INGESTION_SOURCE_PRIVATE': 'ONCE'}, root=root/'owned',
                       source=True, seconds=45, stop_file=root/'STOP', check=check)
    outer['observed_at'] = datetime.now(timezone.utc).isoformat()
    (root/'outer.json').write_bytes(canonical(outer))
    if outer.get('cleanup') != 'CLOSED' or outer.get('exit_code') != 0 or outer.get('limit_hit') is not None:
        raise Denied('QUALIFICATION_SOURCE_OR_CLOSURE_UNCERTAIN_NO_RETRY')
    if not output.is_file() or output.is_symlink() or output.stat().st_size > 524288:
        raise Denied('QUALIFICATION_SOURCE_EXPORT')
    raw = output.read_bytes(); source = json.loads(raw)
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
    (root/'assessment.json').write_bytes(canonical(result))
    return result


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', required=True); p.add_argument('--authority', required=True)
    a = p.parse_args()
    consumption=CONSUMPTION
    if a.authority == SECOND_AUTHORITY:
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
        if a.authority == SECOND_AUTHORITY:
            fd=os.open(consumption.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
    except OSError:
        raise SystemExit('QUALIFICATION_CONSUMED_OR_RECORD_UNAVAILABLE_RECONCILE_NO_RETRY') from None
    try:
        result = qualify(a.output,authority=a.authority)
        print(json.dumps({k:result[k] for k in ('status','record_count','pages','source_sha256')}))
    except BaseException:
        print('STOP_QUALIFICATION_REQUIRES_REVIEW_NO_RETRY'); return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
