"""Offline registration renderer for the screening-v3 installation ceremony and the screening-v3 retained-window run (PR #175). No network call, releases nothing, writes nothing.

    python docs/design/ingestion-screening-v3-activation-20261030/render_registration.py --mode policy|screening --evidence-head <40 hex> [--minutes N] [--policy-events-sha256 H --policy-final-sha256 H --control-sha256 H]

Prints the registration JSON to stdout and its SHA-256 to stderr. The runner's validator independently re-checks every binding. The screening registration additionally binds the audit of the installation ceremony and the
control digest that ceremony left. Rendering a registration starts its (short) expiry clock: render only when the owner is present.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'ingestion-window-demonstration-20261023' / 'base_constants.json'      # the carried non-secret constants (unchanged)


def render(mode, root=None, minutes=25, evidence_head=None, policy_audit=None, control_sha256=None):
    root = Path(root or HERE.parents[2])
    sys.path.insert(0, str(root))
    from verification.ingestion_storage import operational_runner as runner
    from verification.ingestion_storage.tls_trust import PEM_SHA256
    if mode not in ('policy', 'screening'):
        raise ValueError('MODE')
    if not re.fullmatch(r'[0-9a-f]{40}', evidence_head or ''):
        raise ValueError('EVIDENCE_HEAD_REQUIRED')
    manifest_file = root / runner.SV3_MANIFEST_PATH
    manifest = json.loads(manifest_file.read_text())
    carried = json.loads((root / BASE.relative_to(HERE.parents[2])).read_text())
    git = lambda *a: subprocess.check_output(['git', *a], cwd=root, text=True).strip()
    hashes = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in manifest['bound_paths']}
    expires = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
    r = {k: v for k, v in carried.items() if not k.startswith('_')}
    r.pop('limits', None)
    common = dict(expires_at=expires, revision=git('rev-parse', 'HEAD'), tree=git('rev-parse', 'HEAD^{tree}'), hashes=hashes,
                  controller_sha256=hashlib.sha256((root / 'verification/ingestion_storage/operational_runner.py').read_bytes()).hexdigest(), ca_sha256=PEM_SHA256,
                  manifest_sha256=hashlib.sha256(manifest_file.read_bytes()).hexdigest(), evidence_head=evidence_head)
    if mode == 'policy':
        r.update(common, mode=runner.SV3_POLICY_MODE, authority=runner.SV3_POLICY_AUTHORITY, evidence_directory=runner.SV3_EVIDENCE_DIRECTORY, predecessor=runner.SV3_POLICY_PREDECESSOR,
                 state_directory=runner.SV3_POLICY_STATE, execution_authority='NONE', risk_application='THIS_FINITE_SCREENING_V3_POLICY_AND_FUNCTION_INSTALLATION_ONLY',
                 owner_limits=dict(connections=list(runner.SV3_POLICY_OWNER_LIMITS['connections']), commands=list(runner.SV3_POLICY_OWNER_LIMITS['commands'])),
                 policy=dict(file=str(runner.GENERATION3_SCREENING_V3_POLICY), worker_function=str(runner.SV3_WORKER_INSTALL), rollback_function=str(runner.SV3_WORKER_ROLLBACK),
                             rollback_policy=str(runner.GENERATION3_WINDOW_POLICY), named_allowance=runner.SV3_NAME, baseline=runner.GENERATION3_STOP, scope=runner.WINDOW_SCOPE,
                             cap='UNCHANGED_EXCEPT_FOR_THE_ONE_NAMED_ALLOWANCE'),
                 execution=dict(attempt=1, kind='OWNER_LOCAL', maximum_attempts=1, retry=False, state_directory=runner.SV3_POLICY_STATE), approval='OWNER_SCREENING_V3_INSTALLATION_20261030')
    else:
        if not isinstance(policy_audit, dict) or set(policy_audit) != {'events_sha256', 'final_result_sha256'} or not all(re.fullmatch(r'[0-9a-f]{64}', v or '') for v in policy_audit.values()):
            raise ValueError('POLICY_CEREMONY_AUDIT_REQUIRED')
        if not re.fullmatch(r'[0-9a-f]{64}', control_sha256 or ''):
            raise ValueError('CONTROL_SHA256_REQUIRED')
        r.update(common, mode=runner.SV3_MODE, authority=runner.SV3_AUTHORITY, evidence_directory=runner.SV3_EVIDENCE_DIRECTORY, predecessor=runner.SV3_PREDECESSOR, state_directory=runner.SV3_STATE,
                 execution_authority='OWNER_GRANT_AND_EXCEPTION_FOR_THE_HOSTED_RESTRICTED_JOB', risk_application='THIS_FINITE_SCREENING_V3_RETAINED_ASSESSMENT_ONCE', screening_v3=runner.SV3_BINDING,
                 owner_limits=dict(connections=list(runner.SV3_OWNER_LIMITS['connections']), commands=list(runner.SV3_OWNER_LIMITS['commands'])), policy_ceremony_audit=policy_audit,
                 control_sha256=control_sha256, execution=dict(attempt=1, kind='OWNER_LOCAL', maximum_attempts=1, retry=False, state_directory=runner.SV3_STATE),
                 approval='OWNER_SCREENING_V3_RETAINED_RUN_20261030')
    return r


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True, choices=['policy', 'screening'])
    parser.add_argument('--minutes', type=int, default=25)
    parser.add_argument('--evidence-head', required=True)
    parser.add_argument('--policy-events-sha256')
    parser.add_argument('--policy-final-sha256')
    parser.add_argument('--control-sha256')
    args = parser.parse_args()
    if not 1 <= args.minutes <= (30 if args.mode == 'policy' else 120):
        raise SystemExit('EXPIRY_MINUTES_OUT_OF_RANGE')
    audit = dict(events_sha256=args.policy_events_sha256, final_result_sha256=args.policy_final_sha256) if args.mode == 'screening' else None
    body = json.dumps(render(args.mode, minutes=args.minutes, evidence_head=args.evidence_head, policy_audit=audit, control_sha256=args.control_sha256), sort_keys=True, indent=1) + '\n'
    sys.stdout.write(body)
    sys.stderr.write(hashlib.sha256(body.encode()).hexdigest() + '\n')
