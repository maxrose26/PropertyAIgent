"""Explicit single-batch executable candidate. Never activated by import.

Production use requires the separate operational decision and a matching
installed/registered policy. This wrapper cannot install SQL or clear a STOP.
"""
import argparse
from contextlib import contextmanager
import json
import hashlib
import base64
import os
import time
from pathlib import Path

from . import daily_intake_runtime as runtime
from .release_candidate import BATCH

EXPIRY = 1795032000.0  # 2026-11-18 20:00:00 UTC; no rolling extension


@contextmanager
def enabled(policy):
    if (type(policy) is not dict or policy.get('campaign_batch') != BATCH
            or policy.get('mode') != 'CAMPAIGN_FINITE_HISTORICAL_V1'
            or policy.get('max_runs') != 1
            or set(policy.get('councils', {})) != {'tameside'}
            or type(policy.get('expires_at')) not in (int,float)
            or not time.time() < policy['expires_at'] <= EXPIRY
            or policy.get('execution_binding') != runtime.execution_binding()
            or not __import__('re').fullmatch('[0-9a-f]{64}', policy.get('release_manifest_sha256',''))):
        raise ValueError('TAMESIDE_EXACT_CANDIDATE_REQUIRED')
    before=(runtime.LIVE_PRIVATE_EVIDENCE_RELEASE,runtime.LIVE_HISTORICAL_CAMPAIGN_RELEASE)
    if before != (False,False):
        raise ValueError('TAMESIDE_CANDIDATE_ALREADY_ENABLED')
    runtime.LIVE_PRIVATE_EVIDENCE_RELEASE=True
    runtime.LIVE_HISTORICAL_CAMPAIGN_RELEASE=True
    try: yield
    finally:
        runtime.LIVE_PRIVATE_EVIDENCE_RELEASE,runtime.LIVE_HISTORICAL_CAMPAIGN_RELEASE=before


def validate_job(policy, *, hostaddr, access_deadline, now=None, environ=None):
    """No connection: exact restricted Render target and finite closure reserve."""
    import math
    now=time.time() if now is None else now
    env=os.environ if environ is None else environ
    if (env.get('RENDER_SERVICE_ID')!='crn-d9sv93vavr4c73f98rb0'
            or env.get('RENDER_GIT_COMMIT')!=policy.get('execution_binding',{}).get('revision')
            or hostaddr!=policy.get('hostaddr') or policy.get('route')!='POOLER'
            or type(access_deadline) not in (int,float) or not math.isfinite(access_deadline)
            or not 1145 < access_deadline-now <= 2100
            or access_deadline>EXPIRY
            or not now+960 < policy.get('expires_at',0) <= access_deadline-185):
        raise ValueError('TAMESIDE_RUNTIME_TARGET_OR_DEADLINE')
    forbidden=('DATABASE_URL','INGESTION_ADMIN_DATABASE_URL','INGESTION_APPLICATION_DATABASE_URL',
               'SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY',
               'PROPERTYAIGENT_INTAKE_RENDER_API_KEY','GH_TOKEN','GITHUB_TOKEN')
    if any(env.get(key) for key in forbidden):
        raise ValueError('TAMESIDE_PRIVILEGED_ENVIRONMENT')
    if not all(env.get(key) for key in ('INGESTION_WORKER_DATABASE_URL','INGESTION_EFFECT_DATABASE_URL')):
        raise ValueError('TAMESIDE_RESTRICTED_CREDENTIALS_REQUIRED')
    return True


def main(argv=None):
    parser=argparse.ArgumentParser()
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--policy')
    source.add_argument('--policy-base64')
    parser.add_argument('--period',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--hostaddr',required=True)
    parser.add_argument('--policy-sha256',required=True)
    parser.add_argument('--access-deadline',required=True,type=float)
    args=parser.parse_args(argv)
    if args.policy_base64 is not None:
        if len(args.policy_base64)>8192:raise ValueError('TAMESIDE_POLICY_SIZE')
        raw=base64.b64decode(args.policy_base64,validate=True)
    else:
        if Path(args.policy).stat().st_size>6144:raise ValueError('TAMESIDE_POLICY_SIZE')
        raw=Path(args.policy).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.policy_sha256:
        raise ValueError('TAMESIDE_POLICY_FILE_DRIFT')
    policy=json.loads(raw)
    validate_job(policy,hostaddr=args.hostaddr,access_deadline=args.access_deadline)
    # Source planner binds the actual execution day and refuses a changed
    # period/window; the SQL issuer/runtime independently bind the full policy.
    from datetime import datetime,timezone
    runtime.selected_historical_campaign_rows(policy,args.period,as_of=datetime.now(timezone.utc))
    command=['--period',args.period,'--output',args.output]
    if args.hostaddr: command += ['--hostaddr',args.hostaddr]
    with enabled(policy): return runtime.main(command)


if __name__=='__main__': raise SystemExit(main())
