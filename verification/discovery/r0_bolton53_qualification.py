"""Fresh Bolton53 qualification only; no database or admission interface."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import tempfile
from . import r0_fixed80_qualification as shared

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'docs/design/stage4-r0-execution/bolton-initial-exact20/fresh-bolton53-proposal.json'
MANIFEST_SHA='0857e43999b43a810f0206c839861eb6b71ccd6b57a83b5409a4ae01f4c40473'
LIMITS=dict(calls=53,requests=106,bytes=106_000_000,seconds=2915,output_bytes=8_000_000,
    record_requests=2,record_bytes=2_000_000,record_seconds=55,record_output_bytes=65536,
    worker_rss=1024**3)


def targets():
    raw=MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('BOLTON53_MANIFEST_REJECTED')
    data=json.loads(raw);rows=data['rows']
    # Frozen bytes retain original case/origin provenance; execution names are
    # a closed deterministic namespace, not arbitrary case input.
    if (len(rows)!=53 or len({r['reference'] for r in rows})!=53
        or any(r['council']!='bolton' or r['reference']=='01842/26' or r['application_id'] is not None for r in rows)
        or sum(r['proposal_origin']=='HISTORICAL_42_REQUIRES_FRESH_CONTRACT_EVIDENCE' for r in rows)!=42
        or sum(r['proposal_origin']=='UNATTEMPTED_11' for r in rows)!=11):raise ValueError('BOLTON53_ROWS_REJECTED')
    from verification.direct_reference.refresh import validate_destination
    for row in rows:validate_destination(row)
    return [dict(row,case=f'r0_bolton53_{i:02d}') for i,row in enumerate(rows)]


def case_definitions():
    return {r['case']:(None,r['reference'],r['source_url']) for r in targets()}


def worker(index):
    from .material_qualification import idox_worker
    shared.credential_free(os.environ)
    if type(index) is not int or not 0<=index<53:raise ValueError('BOLTON53_INDEX_REJECTED')
    return idox_worker(targets()[index])


def read(index,row):
    from verification.direct_reference.instrumented_probe import supervised
    shared.credential_free(os.environ)
    if type(index) is not int or not 0<=index<53 or row!=targets()[index]:raise ValueError('BOLTON53_ROW_REJECTED')
    with tempfile.TemporaryDirectory(prefix='r0-bolton53-') as directory:
        out=Path(directory)/'audit.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):supervised(row['case'],out)
        if not out.is_file() or out.stat().st_size>=LIMITS['record_output_bytes']:raise ValueError('INVALID_ARTIFACT')
        return json.loads(out.read_bytes())


def qualify(*,reader,checkpoint):
    return shared._qualify_fixed(targets(),MANIFEST_SHA,LIMITS,reader=reader,checkpoint=checkpoint)


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true',required=True)
    p.add_argument('--case',choices=case_definitions(),required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();shared.credential_free(os.environ)
    if a.output.exists():raise ValueError('EXISTING_OUTPUT')
    index=next(i for i,r in enumerate(targets()) if r['case']==a.case)
    raw=json.dumps(worker(index),sort_keys=True).encode()+b'\n'
    if len(raw)>=LIMITS['record_output_bytes']:raise ValueError('RECORD_OUTPUT_LIMIT')
    with a.output.open('xb') as out:out.write(raw)

if __name__=='__main__':main()
