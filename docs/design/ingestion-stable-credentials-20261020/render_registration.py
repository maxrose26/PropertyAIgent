"""Offline registration renderer for the stable-credential OWNER modes (provisioning and revocation). No network call, releases nothing, writes nothing.

    python docs/design/ingestion-stable-credentials-20261020/render_registration.py --mode provisioning|revocation --evidence-head <40 hex> [--minutes N]

Prints the registration JSON to stdout and its SHA-256 to stderr. The runner's validator independently re-checks every binding (mode, authority, predecessors, limits, validity, clean reviewed
checkout, file hashes, controller and CA hashes, expiry ceiling). Neither mode carries any execution authority; qualification is a separate restricted-runtime step (no registration).
"""
import argparse,hashlib,json,re,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent
EVIDENCE_DIRECTORY='docs/design/ingestion-operational-execution-stable-credentials-20261020'


def render(mode='provisioning',root=None,minutes=60,evidence_head=None):
    root=Path(root or HERE.parents[2])
    sys.path.insert(0,str(root))
    from verification.ingestion_storage import operational_runner as runner
    from verification.ingestion_storage.tls_trust import PEM_SHA256
    if mode not in ('provisioning','revocation'):raise ValueError('MODE')
    if not re.fullmatch(r'[0-9a-f]{40}',evidence_head or ''):raise ValueError('EVIDENCE_HEAD_REQUIRED')
    runner_mode=runner.STABLE_PROVISION_MODE if mode=='provisioning' else runner.STABLE_REVOKE_MODE
    authority,state,risk=runner.STABLE_MODES[runner_mode]
    manifest=json.loads((HERE/'MANIFEST.json').read_text());carried=json.loads((HERE/'base_constants.json').read_text())
    git=lambda *a:subprocess.check_output(['git',*a],cwd=root,text=True).strip()
    hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in manifest['bound_paths']}
    expires=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    r={k:v for k,v in carried.items() if not k.startswith('_')}
    r.update(mode=runner_mode,authority=authority,expires_at=expires,revision=git('rev-parse','HEAD'),tree=git('rev-parse','HEAD^{tree}'),hashes=hashes,
             controller_sha256=hashlib.sha256((root/'verification/ingestion_storage/operational_runner.py').read_bytes()).hexdigest(),ca_sha256=PEM_SHA256,
             manifest_sha256=hashlib.sha256((HERE/'MANIFEST.json').read_bytes()).hexdigest(),evidence_head=evidence_head,evidence_directory=EVIDENCE_DIRECTORY,
             predecessor=runner.DIRECT_PREDECESSOR,state_directory=state,execution_authority='NONE',risk_application=risk,
             owner_limits=dict(connections=list(runner.STABLE_OWNER_LIMITS['connections']),commands=list(runner.STABLE_OWNER_LIMITS['commands'])),
             execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=state),
             approval='OWNER_STABLE_CREDENTIAL_%s_20261020'%mode.upper())
    if mode=='provisioning':r['validity_days']=runner.STABLE_VALIDITY_DAYS
    return r


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mode',required=True,choices=['provisioning','revocation']);parser.add_argument('--minutes',type=int,default=60);parser.add_argument('--evidence-head',required=True);args=parser.parse_args()
    if not 1<=args.minutes<=110:raise SystemExit('EXPIRY_MINUTES_1_TO_110')
    body=json.dumps(render(args.mode,minutes=args.minutes,evidence_head=args.evidence_head),sort_keys=True,indent=1)+'\n'
    sys.stdout.write(body);sys.stderr.write(hashlib.sha256(body.encode()).hexdigest()+'\n')
