"""Offline registration renderer for the policy-v5 ceremony and the Bolton window demonstration. No network call, releases nothing, writes nothing.

    python docs/design/ingestion-window-demonstration-20261023/render_registration.py --mode policy|window --evidence-head <40 hex> [--minutes N] [--policy-events-sha256 H --policy-final-sha256 H --control-sha256 H]

Prints the registration JSON to stdout and its SHA-256 to stderr. The runner's validator independently re-checks every binding. The window registration additionally binds the audit of the policy-v5 ceremony and the control digest that ceremony left.
"""
import argparse,hashlib,json,re,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent


def render(mode,root=None,minutes=25,evidence_head=None,policy_audit=None,control_sha256=None):
    root=Path(root or HERE.parents[2])
    sys.path.insert(0,str(root))
    from verification.ingestion_storage import operational_runner as runner
    from verification.ingestion_storage.tls_trust import PEM_SHA256
    if mode not in ('policy','window'):raise ValueError('MODE')
    if not re.fullmatch(r'[0-9a-f]{40}',evidence_head or ''):raise ValueError('EVIDENCE_HEAD_REQUIRED')
    manifest=json.loads((HERE/'MANIFEST.json').read_text());carried=json.loads((HERE/'base_constants.json').read_text())
    git=lambda *a:subprocess.check_output(['git',*a],cwd=root,text=True).strip()
    hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in manifest['bound_paths']}
    expires=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    r={k:v for k,v in carried.items() if not k.startswith('_')}
    r.pop('limits',None)
    common=dict(expires_at=expires,revision=git('rev-parse','HEAD'),tree=git('rev-parse','HEAD^{tree}'),hashes=hashes,
                controller_sha256=hashlib.sha256((root/'verification/ingestion_storage/operational_runner.py').read_bytes()).hexdigest(),ca_sha256=PEM_SHA256,
                manifest_sha256=hashlib.sha256((HERE/'MANIFEST.json').read_bytes()).hexdigest(),evidence_head=evidence_head)
    if mode=='policy':
        r.update(common,mode=runner.WINDOW_POLICY_MODE,authority=runner.WINDOW_POLICY_AUTHORITY,evidence_directory=runner.WINDOW_EVIDENCE_DIRECTORY,predecessor=runner.WINDOW_POLICY_PREDECESSOR,state_directory=runner.WINDOW_POLICY_STATE,
                 execution_authority='NONE',risk_application='THIS_FINITE_POLICY_WINDOW_ALLOWANCE_INSTALLATION_ONLY',
                 owner_limits=dict(connections=list(runner.WINDOW_POLICY_OWNER_LIMITS['connections']),commands=list(runner.WINDOW_POLICY_OWNER_LIMITS['commands'])),
                 policy=dict(file=str(runner.GENERATION3_WINDOW_POLICY),named_allowances=[runner.WINDOW_AUTHORITY+'_CAPTURE',runner.WINDOW_AUTHORITY+'_SCREEN'],baseline=runner.GENERATION3_STOP,scope=runner.WINDOW_SCOPE,cap='UNCHANGED_EXCEPT_FOR_THE_TWO_NAMED_ALLOWANCES'),
                 execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=runner.WINDOW_POLICY_STATE),approval='OWNER_POLICY_WINDOW_ALLOWANCE_20261023')
    else:
        if not policy_audit:raise ValueError('POLICY_CEREMONY_AUDIT_REQUIRED')
        if not re.fullmatch(r'[0-9a-f]{64}',control_sha256 or ''):raise ValueError('CONTROL_SHA256_REQUIRED')
        r.update(common,mode=runner.WINDOW_MODE,authority=runner.WINDOW_AUTHORITY,evidence_directory=runner.WINDOW_EVIDENCE_DIRECTORY,predecessor=runner.WINDOW_PREDECESSOR,state_directory=runner.WINDOW_STATE,
                 execution_authority='OWNER_GRANT_AND_EXCEPTION_FOR_THE_HOSTED_RESTRICTED_JOB',risk_application='THIS_FINITE_BOLTON_WINDOW_DEMONSTRATION_ONCE',window=runner.WINDOW_BINDING,
                 owner_limits=dict(connections=list(runner.PIPELINE_OWNER_LIMITS['connections']),commands=list(runner.PIPELINE_OWNER_LIMITS['commands'])),policy_ceremony_audit=policy_audit,control_sha256=control_sha256,
                 execution=dict(attempt=1,kind='OWNER_LOCAL',maximum_attempts=1,retry=False,state_directory=runner.WINDOW_STATE),approval='OWNER_BOLTON_WINDOW_DEMONSTRATION_20261023')
    return r


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',required=True,choices=['policy','window']);parser.add_argument('--minutes',type=int,default=25);parser.add_argument('--evidence-head',required=True)
    parser.add_argument('--policy-events-sha256');parser.add_argument('--policy-final-sha256');parser.add_argument('--control-sha256');args=parser.parse_args()
    if not 1<=args.minutes<=(30 if args.mode=='policy' else 120):raise SystemExit('EXPIRY_MINUTES_OUT_OF_RANGE')
    audit=dict(events_sha256=args.policy_events_sha256,final_result_sha256=args.policy_final_sha256) if args.mode=='window' else None
    body=json.dumps(render(args.mode,minutes=args.minutes,evidence_head=args.evidence_head,policy_audit=audit,control_sha256=args.control_sha256),sort_keys=True,indent=1)+'\n'
    sys.stdout.write(body);sys.stderr.write(hashlib.sha256(body.encode()).hexdigest()+'\n')
