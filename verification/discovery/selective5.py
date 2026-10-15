"""Fixed selected cohort orchestration; shared primary identity and B2 sole writers."""
import hashlib,json,time
from pathlib import Path
from . import bolton53_admission as shared
ROOT=shared.ROOT
PACK=ROOT/'docs/design/stage4-r0-execution/autonomous-recovery-20261015'
COHORT_SHA='b540e74c6ccabe64636adf00f723c6a2bcfcbc499a39079f098e51d21185191f'
PRIMARY_SHA=shared.PRIMARY_SHA
PHASES=shared.PHASES
LIMITS=dict(shared.LIMITS,calls=5,requests=10,bytes=10_000_000,source_seconds=275,seconds=1020,setup_seconds=280,job_seconds=1500)

def rows():
    raw=(PACK/'selective5.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=COHORT_SHA:raise ValueError('COHORT_REJECTED')
    source={r['reference']:r for r in shared.rows()}
    for r in json.loads(raw)['rows']:
        yield source[r['reference']] if r['council']=='bolton' else r

def run(*,engine_factory,reader=shared.fresh,checkpoint,journal,clock=time.monotonic):
    start=clock();results=[];requests=size=0
    for i,row in enumerate(rows()):
        if clock()-start+180>1020:return dict(results=results,stop='AGGREGATE_DEADLINE')
        at=clock();journal(i,'RECORD_STARTED');engine=None
        if row['council']=='stockport':
            audit=dict(council='stockport',reference=row['reference'],identity='WITHHELD',facts='WITHHELD_FIXED_EXACT_SOURCE_CONTRACT_UNQUALIFIED',transaction='NOT_STARTED',site_relationship='UNKNOWN',application_role='UNKNOWN')
        else:
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
        if audit.get('stop') or 'UNCERTAIN' in audit.get('transaction','') or clock()-at>180 or requests>10 or size>10_000_000:
            return dict(results=results,stop='UNCERTAIN_OR_BOUND_NO_NEXT_RECORD',requests=None,received_bytes=None,known_partial_requests=requests,known_partial_received_bytes=size)
    return dict(results=results,stop=None,requests=requests,received_bytes=size)
