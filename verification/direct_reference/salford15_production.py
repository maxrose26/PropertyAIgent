"""One closed Salford15 invocation; existing Arcus/B2 worker and stop semantics."""
import argparse
import json
import os
from pathlib import Path
import sys

from . import batch, arcus_production
from .batch_supervisor import isolated
from .salford15_manifest import CONTEXTS

WORKFLOW = '.github/workflows/stage4-salford15-production-once.yml'
AUTHORITY = 'AUTHORISE_STAGE4_SALFORD15_QUARANTINE266_ONCE'
LIMITS = dict(requests=80, bytes=20*1024*1024, seconds=45, worker_seconds=75)


def execute(sha, phase, output, previous):
    spec = CONTEXTS[phase]
    rows = batch.manifest(spec)
    if output.exists(): raise ValueError('OUTPUT_EXISTS')
    if phase == 'salford15_a':
        if previous is not None: raise ValueError('NO_RESUME')
    else:
        if previous is None or previous.stat().st_size > batch.MAX_BATCH:
            raise ValueError('PREVIOUS_REQUIRED')
        proof = json.loads(previous.read_bytes())
        batch.validate(proof, spec=CONTEXTS['salford15_a'])
        if (proof['repository_sha'] != sha
            or proof['invocation'] != os.environ['GITHUB_RUN_ID']+'-salford15_a'
            or proof['assessment'] != 'ACCOUNTED' or proof['carried_ids']
            or proof['parent_audit_sha256'] is not None):
            raise ValueError('PREVIOUS_NOT_ACCOUNTED')
    environment = {k:os.environ[k] for k in arcus_production.ENV_KEYS if k in os.environ}
    environment['BATCH_DATABASE_URL'] = os.environ.pop('BATCH_DATABASE_URL','')
    if not environment['BATCH_DATABASE_URL']: raise ValueError('CREDENTIAL_MISSING')
    indices = {r['identity']['application_id']:i for i,r in enumerate(rows)}
    def record(row, limits):
        def command(r, allowance, path):
            return [sys.executable, '-m', 'verification.direct_reference.salford15_production',
                    '--sha',sha,'--authority',AUTHORITY,'--phase',phase,'--output',str(path),
                    '--worker-index',str(indices[r['application_id']]),'--limits',json.dumps(allowance)]
        return isolated(row, limits, command, environment)
    try:
        audit = batch.run(sha, os.environ['GITHUB_RUN_ID']+'-'+phase, record, spec=spec)
        with output.open('xb') as f: f.write(batch.encode(audit))
        return 0 if audit['assessment'] == 'ACCOUNTED' else 1
    finally:
        environment.pop('BATCH_DATABASE_URL',None)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sha', required=True); p.add_argument('--authority', required=True)
    p.add_argument('--phase', choices=tuple(CONTEXTS), required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--previous', type=Path)
    p.add_argument('--worker-index', type=int); p.add_argument('--limits')
    a = p.parse_args()
    try:
        if a.authority != AUTHORITY: raise ValueError('AUTHORITY')
        arcus_production.admit(a.sha, workflow=WORKFLOW)
        if a.worker_index is not None:
            rows = batch.manifest(CONTEXTS[a.phase])
            if (a.previous is not None or not 0 <= a.worker_index < len(rows)
                or a.limits is None or json.loads(a.limits) != LIMITS):
                raise ValueError('WORKER_SCOPE')
            arcus_production.worker(rows[a.worker_index]['identity'], LIMITS, a.output)
            return 0
        if a.limits is not None: raise ValueError('LIMITS')
        return execute(a.sha, a.phase, a.output, a.previous)
    except Exception:
        print('Salford15 stopped; inspect bounded audit. No rerun or automatic resume.', file=sys.stderr)
        return 2


if __name__ == '__main__': raise SystemExit(main())
