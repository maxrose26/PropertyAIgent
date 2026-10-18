"""Offline registration renderer for the matrix cleanup. No network call, releases nothing, writes nothing.

    python docs/design/ingestion-matrix-cleanup-20261018/render_registration.py [--minutes N] [--state-root DIR]

The target session pid and the predecessor hashes are READ from the retained matrix audit (never typed). Prints the registration JSON to stdout and its SHA-256 to stderr.
"""
import argparse,hashlib,json,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent


def render(root=None,minutes=90,state_root=None):
    root=Path(root or HERE.parents[2]);sys.path.insert(0,str(root))
    from verification.ingestion_storage import matrix_cleanup as mc
    from verification.ingestion_storage.tls_trust import PEM_SHA256
    base=Path(state_root or Path.home()/'.local/state/propertyaigent')/mc.MATRIX_STATE
    events=(base/'events.jsonl').read_bytes();final=(base/'final-result.json').read_bytes();recorded=json.loads(final)
    sessions=recorded['diagnostics']['sessions']
    if len(sessions)!=1 or sessions[0][1]!='ingestion_worker_login':raise SystemExit('EXACTLY_ONE_RECORDED_WORKER_SESSION_REQUIRED')
    manifest=json.loads((HERE/'MANIFEST.json').read_text());git=lambda *a:subprocess.check_output(['git',*a],cwd=root,text=True).strip()
    expires=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    return dict(mode=mc.MODE,authority=mc.AUTHORITY,status=mc.STATUS,expires_at=expires,revision=git('rev-parse','HEAD'),tree=git('rev-parse','HEAD^{tree}'),
                hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in manifest['bound_paths']},
                controller_sha256=hashlib.sha256((root/'verification/ingestion_storage/matrix_cleanup.py').read_bytes()).hexdigest(),ca_sha256=PEM_SHA256,evidence_directory=mc.EVIDENCE_DIRECTORY,
                limits=mc.LIMITS,absent_capabilities=list(mc.ABSENT_CAPABILITIES),statements_sha256=mc.statements_digest(),target=dict(pid=sessions[0][0],role=sessions[0][1]),
                secrets=list(mc.SECRETS),preserved_secret=mc.PRESERVED,state_directory=mc.STATE,
                predecessor=dict(state_directory=mc.MATRIX_STATE,events_sha256=hashlib.sha256(events).hexdigest(),final_result_sha256=hashlib.sha256(final).hexdigest()))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--minutes',type=int,default=90);parser.add_argument('--state-root',default=None);args=parser.parse_args()
    if not 1<=args.minutes<=120:raise SystemExit('EXPIRY_MINUTES_1_TO_120')
    body=json.dumps(render(minutes=args.minutes,state_root=args.state_root),sort_keys=True,indent=1)+'\n'
    sys.stdout.write(body);sys.stderr.write(hashlib.sha256(body.encode()).hexdigest()+'\n')
