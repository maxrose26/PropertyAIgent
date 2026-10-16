"""Fixed selected cohort orchestration; shared primary identity and B2 sole writers."""
import hashlib,json,time
from pathlib import Path
from . import narrow_oldham_record as shared
ROOT=shared.ROOT
PACK=ROOT/'docs/design/stage4-r0-execution/narrow-continuation-20261016'
COHORT_SHA='808eb9a77c85e07da331cf6ca4f3a94f73d1a6e2fe74d8c1e0e6d1c0f695759b'
PRIMARY_SHA=shared.PRIMARY_SHA
PHASES=shared.PHASES
LIMITS=dict(shared.LIMITS,calls=2,requests=4,bytes=4_000_000,source_seconds=110,seconds=480,setup_seconds=280,job_seconds=960)

def rows():
    return shared.rows()

def run(*,engine_factory,reader=shared.fresh,checkpoint,journal,clock=time.monotonic):
    start=clock();results=[];requests=size=0
    for i,row in enumerate(rows()):
        if clock()-start+180>480:return dict(results=results,stop='AGGREGATE_DEADLINE')
        at=clock();journal(i,'RECORD_STARTED');engine=None
        try:
            engine=engine_factory()
            audit=shared.record(engine,row,retrieve=reader,journal=lambda phase:journal(i,phase))
        except Exception:audit=dict(council=row['council'],reference=row['reference'],identity='UNKNOWN',facts='UNKNOWN',transaction='UNCERTAIN_STOP_NO_RETRY',stop=True)
        finally:
            if engine is not None:
                try:engine.dispose();journal(i,'ENGINE_DISPOSED')
                except Exception:audit=dict(council=row['council'],reference=row['reference'],transaction='CLEANUP_UNCERTAIN',stop=True)
        results.append(audit)
        try:checkpoint(audit);journal(i,'RECORD_CLOSED')
        except Exception:return dict(results=results,stop='CHECKPOINT_UNCERTAIN_NO_NEXT_RECORD',requests=None,received_bytes=None,known_partial_requests=requests,known_partial_received_bytes=size)
        a=audit.get('source',{});requests+=a.get('requests',0);size+=a.get('received_body_bytes',0)
        if audit.get('stop') or 'UNCERTAIN' in audit.get('transaction','') or clock()-at>180 or requests>4 or size>4_000_000:
            return dict(results=results,stop='UNCERTAIN_OR_BOUND_NO_NEXT_RECORD',requests=None,received_bytes=None,known_partial_requests=requests,known_partial_received_bytes=size)
    return dict(results=results,stop=None,requests=requests,received_bytes=size)
