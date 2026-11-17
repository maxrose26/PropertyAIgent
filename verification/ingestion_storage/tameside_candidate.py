"""Explicit single-batch executable candidate. Never activated by import.

Production use requires the separate operational decision and a matching
installed/registered policy. This wrapper cannot install SQL or clear a STOP.
"""
import argparse
from contextlib import contextmanager
import json
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


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--policy',required=True)
    parser.add_argument('--period',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--hostaddr')
    args=parser.parse_args(argv)
    policy=json.loads(Path(args.policy).read_text())
    # Source planner binds the actual execution day and refuses a changed
    # period/window; the SQL issuer/runtime independently bind the full policy.
    from datetime import datetime,timezone
    runtime.selected_historical_campaign_rows(policy,args.period,as_of=datetime.now(timezone.utc))
    command=['--period',args.period,'--output',args.output]
    if args.hostaddr: command += ['--hostaddr',args.hostaddr]
    with enabled(policy): return runtime.main(command)


if __name__=='__main__': raise SystemExit(main())
