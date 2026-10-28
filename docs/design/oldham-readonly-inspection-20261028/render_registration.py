"""Offline registration renderer for the Oldham read-only inspection (NOT AUTHORISED FOR EXECUTION). Makes no network call, releases nothing and writes nothing.

    python docs/design/oldham-readonly-inspection-20261028/render_registration.py [--minutes N]

Prints the registration JSON to stdout and its SHA-256 to stderr. The controller independently re-checks every binding and rejects expiry beyond two hours.
"""
import argparse,hashlib,json,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent


def render(root=None,minutes=90):
    root=Path(root or HERE.parents[2])
    sys.path.insert(0,str(root))
    from verification.ingestion_storage import oldham_inspection as inspection
    from verification.ingestion_storage.tls_trust import PEM_SHA256
    manifest=json.loads((HERE/'MANIFEST.json').read_text())
    git=lambda *a:subprocess.check_output(['git',*a],cwd=root,text=True).strip()
    hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in manifest['bound_paths']}
    expires=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    return dict(mode=inspection.MODE,authority=inspection.AUTHORITY,status=inspection.STATUS,state_directory=inspection.STATE,expires_at=expires,revision=git('rev-parse','HEAD'),tree=git('rev-parse','HEAD^{tree}'),hashes=hashes,
                controller_sha256=hashlib.sha256((root/'verification/ingestion_storage/oldham_inspection.py').read_bytes()).hexdigest(),ca_sha256=PEM_SHA256,
                evidence_directory=inspection.EVIDENCE_DIRECTORY,limits=inspection.BOUND,absent_capabilities=list(inspection.ABSENT_CAPABILITIES),statements_sha256=inspection.statements_sha256())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--minutes',type=int,default=90);args=parser.parse_args()
    if not 1<=args.minutes<=120:raise SystemExit('EXPIRY_MINUTES_1_TO_120')
    body=json.dumps(render(minutes=args.minutes),sort_keys=True,indent=1)+'\n'
    sys.stdout.write(body);sys.stderr.write(hashlib.sha256(body.encode()).hexdigest()+'\n')
