"""Offline registration renderer for the administrative connection probe. Makes no network call, releases nothing and writes nothing.

    python docs/design/ingestion-admin-connection-probe-20261018/render_registration.py [--minutes N]

Prints the registration JSON to stdout and its SHA-256 to stderr. The probe validator independently re-checks every binding and rejects expiry beyond two hours.
"""
import argparse,hashlib,json,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent


def render(root=None,minutes=90,attempt=1,state_root=None):
    root=Path(root or HERE.parents[2])
    sys.path.insert(0,str(root))
    from verification.ingestion_storage import admin_connection_probe as probe
    from verification.ingestion_storage.tls_trust import PEM_SHA256
    manifest=json.loads((HERE/'MANIFEST.json').read_text())
    git=lambda *a:subprocess.check_output(['git',*a],cwd=root,text=True).strip()
    hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in manifest['bound_paths']}
    expires=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    namespace=probe.probe_namespace(attempt);predecessor=None
    if namespace['predecessor'] is not None:
        previous=probe.probe_namespace(namespace['predecessor'])['state_directory'];base=Path(state_root or Path.home()/'.local/state/propertyaigent')/previous
        predecessor=dict(attempt=namespace['predecessor'],state_directory=previous,events_sha256=hashlib.sha256((base/'events.jsonl').read_bytes()).hexdigest(),
                         final_result_sha256=hashlib.sha256((base/'final-result.json').read_bytes()).hexdigest())
    return dict(mode=probe.MODE,authority=namespace['authority'],status=probe.STATUS,attempt=attempt,state_directory=namespace['state_directory'],predecessor=predecessor,expires_at=expires,revision=git('rev-parse','HEAD'),tree=git('rev-parse','HEAD^{tree}'),hashes=hashes,
                controller_sha256=hashlib.sha256((root/'verification/ingestion_storage/admin_connection_probe.py').read_bytes()).hexdigest(),ca_sha256=PEM_SHA256,
                evidence_directory='docs/design/ingestion-admin-connection-probe-20261018',limits=probe.LIMITS,absent_capabilities=list(probe.ABSENT_CAPABILITIES),
                statement_sha256=hashlib.sha256(probe.STATEMENT.encode()).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--minutes',type=int,default=90);parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args()
    if not 1<=args.minutes<=120:raise SystemExit('EXPIRY_MINUTES_1_TO_120')
    body=json.dumps(render(minutes=args.minutes,attempt=args.attempt),sort_keys=True,indent=1)+'\n'
    sys.stdout.write(body);sys.stderr.write(hashlib.sha256(body.encode()).hexdigest()+'\n')
