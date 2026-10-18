"""Offline registration renderer for the restricted-connection matrix. No network call, releases nothing, writes nothing.

    python docs/design/ingestion-restricted-connection-matrix-20261018/render_registration.py [--minutes N]

Prints the registration JSON to stdout and its SHA-256 to stderr. The runner's validator independently re-checks every binding (exact matrix, exact numeric limits, owner
limits, no execution authority, risk acceptance applied to this finite test only, two-hour expiry ceiling).
"""
import argparse,hashlib,json,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent


def render(root=None,minutes=90):
    root=Path(root or HERE.parents[2])
    sys.path.insert(0,str(root))
    from verification.ingestion_storage import operational_runner as runner
    from verification.ingestion_storage import restricted_matrix as matrix
    from verification.ingestion_storage.tls_trust import PEM_SHA256
    manifest=json.loads((HERE/'MANIFEST.json').read_text());carried=json.loads((HERE/'base_constants.json').read_text())
    git=lambda *a:subprocess.check_output(['git',*a],cwd=root,text=True).strip()
    hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in manifest['bound_paths']}
    expires=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    r={k:v for k,v in carried.items() if not k.startswith('_')}
    r.update(mode=runner.MATRIX_MODE,authority=runner.MATRIX_AUTHORITY,expires_at=expires,revision=git('rev-parse','HEAD'),tree=git('rev-parse','HEAD^{tree}'),hashes=hashes,
             controller_sha256=hashlib.sha256((root/'verification/ingestion_storage/operational_runner.py').read_bytes()).hexdigest(),ca_sha256=PEM_SHA256,
             manifest_sha256=hashlib.sha256((HERE/'MANIFEST.json').read_bytes()).hexdigest(),
             matrix=[list(e) for e in matrix.ENTRIES],matrix_limits=matrix.LIMITS,
             owner_limits=dict(connections=list(runner.MATRIX_OWNER_LIMITS['connections']),commands=list(runner.MATRIX_OWNER_LIMITS['commands'])),
             execution_authority='NONE',risk_application='THIS_FINITE_RESTRICTED_CONNECTION_MATRIX_ONLY',state_directory=runner.MATRIX_STATE,
             execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=runner.MATRIX_STATE),
             approval='OWNER_RESTRICTED_CONNECTION_MATRIX_ONLY_20261018')
    return r


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--minutes',type=int,default=90);args=parser.parse_args()
    if not 1<=args.minutes<=120:raise SystemExit('EXPIRY_MINUTES_1_TO_120')
    body=json.dumps(render(minutes=args.minutes),sort_keys=True,indent=1)+'\n'
    sys.stdout.write(body);sys.stderr.write(hashlib.sha256(body.encode()).hexdigest()+'\n')
