"""Frozen Oldham2 source worker only; no database or admission interface."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import tempfile
from . import r0_fixed80_qualification as shared

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'docs/design/stage4-r0-execution/narrow-continuation-20261016/oldham-two.json'
MANIFEST_SHA='808eb9a77c85e07da331cf6ca4f3a94f73d1a6e2fe74d8c1e0e6d1c0f695759b'
LIMITS=dict(calls=2,requests=4,bytes=4_000_000,seconds=110,output_bytes=8_000_000,
    record_requests=2,record_bytes=2_000_000,record_seconds=55,record_output_bytes=65536,
    worker_rss=1024**3)


def targets():
    raw=MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('OLDHAM_TWO_MANIFEST')
    rows=json.loads(raw)['rows']
    if [(r['council'],r['reference']) for r in rows]!=[('oldham','NMA/356901/26'),('oldham','VAR/356938/26')]:raise ValueError('OLDHAM_TWO_IDENTITY')
    from verification.direct_reference.refresh import validate_destination
    for row in rows:validate_destination(row)
    return rows


def case_definitions():
    return {r['case']:(None,r['reference'],r['source_url']) for r in targets()}


def worker(index):
    from .material_qualification import idox_worker
    shared.credential_free(os.environ)
    if type(index) is not int or not 0<=index<2:raise ValueError('OLDHAM2_INDEX_REJECTED')
    return idox_worker(targets()[index])


def read(index,row):
    from verification.direct_reference.instrumented_probe import supervised
    shared.credential_free(os.environ)
    if type(index) is not int or not 0<=index<2 or row!=targets()[index]:raise ValueError('OLDHAM2_ROW_REJECTED')
    with tempfile.TemporaryDirectory(prefix='narrow-oldham2-') as directory:
        out=Path(directory)/'audit.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):supervised(row['case'],out)
        if not out.is_file() or out.stat().st_size>=LIMITS['record_output_bytes']:raise ValueError('INVALID_ARTIFACT')
        return json.loads(out.read_bytes())


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
