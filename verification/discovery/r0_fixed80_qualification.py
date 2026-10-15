"""Unregistered fixed80 qualification proposal; no DB, admission or live authority.

Only worker entry exists. Parent caller requires an explicitly injected reader;
registration/review must wire that reader under the proposed outer supervision.
"""
import hashlib
import json
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'docs/design/stage4-r0-execution/page-cap-correction/fixed80-qualification-manifest.json'
MANIFEST_SHA='1c4cb696cfd352532a0c19fe9e919e86059908cc3cf21ed37f8be2ec8ab23b12'
LIMITS=dict(calls=80,requests=160,bytes=160_000_000,seconds=4400,output_bytes=8_000_000,
            record_requests=2,record_bytes=2_000_000,record_seconds=55,record_output_bytes=65536,
            worker_rss=1024**3)
HARD=frozenset({'CLEANUP_FAILURE','ACCOUNTING_FAILURE','INVALID_ARTIFACT','UNSUPPORTED_ROUTE',
                'SCOPE_ESCAPE','AMBIGUOUS_SOURCE_RESULT','PARTIAL_RETRIEVAL','PARSER_FAILURE'})
LOCAL=frozenset({'TIMEOUT','SOURCE_UNAVAILABLE','RATE_LIMITED'})


def credential_free(env):
    if any('DATABASE' in k or k.startswith(('SUPABASE_','OPENAI_','ANTHROPIC_')) for k in env):
        raise ValueError('CREDENTIAL_CONTEXT_REJECTED') from None


def targets():
    raw=MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('FIXED80_MANIFEST_REJECTED')
    rows=json.loads(raw)['rows']
    if (len(rows)!=80 or len({(x['council'],x['reference']) for x in rows})!=80
        or sum(x['council']=='bolton' for x in rows)!=54 or sum(x['council']=='bury' for x in rows)!=26):
        raise ValueError('FIXED80_MANIFEST_REJECTED')
    from verification.direct_reference.refresh import validate_destination
    for i,row in enumerate(rows):
        if row['case']!=f'r0_fixed80_{i:02d}' or row['application_id'] is not None:
            raise ValueError('FIXED80_ROW_REJECTED')
        validate_destination(row)
    return rows


def worker(index):
    # Existing exact displayed-reference parser, request/byte/deadline bounds,
    # session/response closure and process resource limits, no factual writer.
    from .material_qualification import idox_worker
    credential_free(os.environ)
    if type(index) is not int or not 0<=index<80:raise ValueError('FIXED80_INDEX_REJECTED')
    return idox_worker(targets()[index])


def case_definitions():
    return {r['case']:(None,r['reference'],r['source_url']) for r in targets()}


def read(index,row):
    """Proposed binding to the existing owned-process supervisor/worker schema."""
    import contextlib
    import tempfile
    from verification.direct_reference.instrumented_probe import supervised
    credential_free(os.environ)
    if type(index) is not int or not 0<=index<80 or row!=targets()[index]:
        raise ValueError('FIXED80_ROW_REJECTED')
    with tempfile.TemporaryDirectory(prefix='r0-fixed80-qualification-') as directory:
        out=Path(directory)/'audit.json'
        with open(os.devnull,'w') as sink,contextlib.redirect_stdout(sink):
            supervised(row['case'],out)
        if not out.is_file() or out.stat().st_size>=LIMITS['record_output_bytes']:
            raise ValueError('INVALID_ARTIFACT')
        return json.loads(out.read_bytes())


def project(row,source):
    from .material_qualification import project_idox
    return project_idox(row,source)


def durable_checkpoint(path,result):
    """Create-only bounded JSON checkpoint; fsync before any subsequent call."""
    raw=json.dumps(result,sort_keys=True).encode()+b'\n'
    if len(raw)>=LIMITS['record_output_bytes']:raise ValueError('CHECKPOINT_BOUND')
    with Path(path).open('xb') as out:
        out.write(raw);out.flush();os.fsync(out.fileno())


def qualify(*,reader,checkpoint,clock=time.monotonic):
    """No default/live reader: proposed finite caller, not a dispatch capability.

    reader must return existing supervised idox worker schema. Checkpoint each
    bounded result before another call; checkpoint failure stops, never replay.
    """
    from .rejection_audit import observation_audit
    credential_free(os.environ);rows=targets();start=clock();used_requests=used_bytes=0;results=[];stop=None;attempted=0
    def preserve(value):
        results.append(value)
        try:checkpoint(value);return True
        except Exception:return False
    for i,row in enumerate(rows):
        if (clock()-start+LIMITS['record_seconds']>LIMITS['seconds']
            or used_requests+2>LIMITS['requests'] or used_bytes+2_000_000>LIMITS['bytes']):
            stop='AGGREGATE_RESERVATION';break
        attempted+=1
        try:source=reader(i,row)
        except Exception:
            preserve(dict(council=row['council'],reference=row['reference'],
                admission_readiness='UNKNOWN_SOURCE_OR_SUPERVISOR_EXCEPTION',admission_authorised=False))
            stop='SOURCE_OR_SUPERVISOR_EXCEPTION_ACCOUNTING_UNKNOWN';break
        try:resource=project(row,source)
        except Exception:
            preserve(dict(council=row['council'],reference=row['reference'],
                admission_readiness='UNKNOWN_INVALID_ARTIFACT',admission_authorised=False))
            stop='SOURCE_OR_SUPERVISOR_EXCEPTION_ACCOUNTING_UNKNOWN';break
        audit=resource['audit'];failure=resource['failure']
        if (audit.get('cleanup_state')!='CLOSED' or audit.get('budget_state')!='WITHIN_LIMITS'):
            preserve(dict(council=row['council'],reference=row['reference'],source_audit=audit,
                failure=failure,admission_readiness='WITHHELD_RESOURCE_OR_CLEANUP',admission_authorised=False))
            stop='RESOURCE_OR_CLEANUP';break
        # project_idox verifies finite nonnegative counters and hard limits.
        used_requests+=audit['requests'];used_bytes+=audit['received_body_bytes']
        evidence=observation_audit(row,resource)
        identity=evidence['identity_qualification']=='EXACT_DISPLAYED_REFERENCE'
        eligible=identity and evidence['b2_eligible'] is True and failure is None
        result=dict(council=row['council'],reference=row['reference'],source_url=row['source_url'],
            retrieved_at=evidence['retrieved_at'],identity_qualification=evidence['identity_qualification'],
            observation_evidence=evidence,source_audit=audit,failure=failure,
            conservative_materiality=row['retained_materiality'],site_relationship='UNKNOWN',application_role='UNKNOWN',
            admission_readiness='ELIGIBLE_FOR_REVIEW_ONLY' if eligible else 'WITHHELD_PENDING_EVIDENCE',
            admission_authorised=False,production_writes=0)
        if not preserve(result):stop='CHECKPOINT_FAILURE_NO_NEXT_CALL';break
        if (failure is not None and failure not in LOCAL) or failure in HARD:
            stop='HARD_OR_UNCLASSIFIED_FAILURE';break
        if len(json.dumps(results,sort_keys=True).encode())>LIMITS['output_bytes']:
            stop='OUTPUT_LIMIT';break
    return dict(manifest_sha256=MANIFEST_SHA,results=results,stop_reason=stop,
        attempted=attempted,not_attempted=[dict(council=x['council'],reference=x['reference']) for x in rows[attempted:]],
        requests=used_requests,received_bytes=used_bytes,elapsed_seconds=clock()-start,
        accounting_complete=stop not in {'SOURCE_OR_SUPERVISOR_EXCEPTION_ACCOUNTING_UNKNOWN','RESOURCE_OR_CLEANUP'},
        persistence=False,admission_authorised=False)


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true',required=True)
    p.add_argument('--case',choices=case_definitions(),required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();credential_free(os.environ)
    if a.output.exists():raise ValueError('EXISTING_OUTPUT')
    # Worker only. No CLI parent, authority or arbitrary destination/reference.
    index=next(i for i,r in enumerate(targets()) if r['case']==a.case)
    result=worker(index);raw=json.dumps(result,sort_keys=True)
    if len(raw.encode())>=LIMITS['record_output_bytes']:raise ValueError('RECORD_OUTPUT_LIMIT')
    with a.output.open('x') as out:out.write(raw+'\n')

if __name__=='__main__':main()
