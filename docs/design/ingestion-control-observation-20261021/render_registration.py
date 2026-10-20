"""Offline registration renderer for the CONTROL OBSERVATION owner mode. No network call, releases nothing, writes nothing.

    python docs/design/ingestion-control-observation-20261021/render_registration.py --evidence-head <40 hex> [--minutes N]

Prints the registration JSON to stdout and its SHA-256 to stderr. The runner's validator independently re-checks every binding (mode, authority, predecessor, limits, clean reviewed checkout, file
hashes, controller and CA hashes, expiry ceiling of 30 minutes). The mode issues no authority, makes no source request and commits nothing.
"""
import argparse,hashlib,json,re,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent


def render(root=None,minutes=25,evidence_head=None):
    root=Path(root or HERE.parents[2])
    sys.path.insert(0,str(root))
    from verification.ingestion_storage import operational_runner as runner
    from verification.ingestion_storage.tls_trust import PEM_SHA256
    if not re.fullmatch(r'[0-9a-f]{40}',evidence_head or ''):raise ValueError('EVIDENCE_HEAD_REQUIRED')
    manifest=json.loads((HERE/'MANIFEST.json').read_text());carried=json.loads((HERE/'base_constants.json').read_text())
    git=lambda *a:subprocess.check_output(['git',*a],cwd=root,text=True).strip()
    hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in manifest['bound_paths']}
    expires=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    r={k:v for k,v in carried.items() if not k.startswith('_')}
    r.update(mode=runner.OBSERVER_MODE,authority=runner.OBSERVER_AUTHORITY,expires_at=expires,revision=git('rev-parse','HEAD'),tree=git('rev-parse','HEAD^{tree}'),hashes=hashes,
             controller_sha256=hashlib.sha256((root/'verification/ingestion_storage/operational_runner.py').read_bytes()).hexdigest(),ca_sha256=PEM_SHA256,
             manifest_sha256=hashlib.sha256((HERE/'MANIFEST.json').read_bytes()).hexdigest(),evidence_head=evidence_head,
             evidence_directory='docs/design/ingestion-operational-execution-control-observation-20261021',predecessor=runner.OBSERVER_PREDECESSOR,state_directory=runner.OBSERVER_STATE,
             execution_authority='NONE',risk_application='THIS_FINITE_CONTROL_OBSERVATION_ONLY',
             owner_limits=dict(connections=list(runner.OBSERVER_OWNER_LIMITS['connections']),commands=list(runner.OBSERVER_OWNER_LIMITS['commands'])),
             observation=dict(statements=12,database_active_seconds=20,supervised_active_seconds=30,connections=1),
             execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=runner.OBSERVER_STATE),
             approval='OWNER_CONTROL_OBSERVATION_20261021')
    return r


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--minutes',type=int,default=25);parser.add_argument('--evidence-head',required=True);args=parser.parse_args()
    if not 1<=args.minutes<=30:raise SystemExit('EXPIRY_MINUTES_1_TO_30')
    body=json.dumps(render(minutes=args.minutes,evidence_head=args.evidence_head),sort_keys=True,indent=1)+'\n'
    sys.stdout.write(body);sys.stderr.write(hashlib.sha256(body.encode()).hexdigest()+'\n')
