"""Specification 027 - audited correction of the STORED Nesten mandate to the approved canonical brief (NOT reseeding, NOT re-onboarding).

    python -m scripts.sync_nesten_mandate                                                   # DRY RUN (default): prints the field-level plan, writes nothing
    python -m scripts.sync_nesten_mandate --audit-out <dir>                                  # also saves the plan JSON (create-only, no secrets)
    python -m scripts.sync_nesten_mandate --apply --confirm "<phrase>" --expect-digest <plan_digest from the reviewed dry run>

Only Nesten Homes is authorised. Apply refuses unless the stored mandate is exactly the expected pre-correction state, the confirm phrase and the REVIEWED plan digest match and the Stage 1
operator checks pass; it updates only the approved columns in one transaction and leaves the onboarding baseline untouched (the mandate becomes STALE by computation; re-onboarding is a
separate command). No monitoring, reseed, model call, scraping or alert. Operator-authorised launch only (`launch:sync_nesten_mandate` plus the `buyer.write` action).
Production execution needs separate Product Owner authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.db.session import get_session
from app.policy.mandate_sync import CONFIRM_PHRASE, apply_mandate_sync, plan_mandate_sync
from app.security.cli import authorised_cli

BUYER_KEY = "nesten_homes"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the reviewed plan (requires --confirm and --expect-digest); default is a dry run")
    parser.add_argument("--confirm", default="", help=f"must equal {CONFIRM_PHRASE!r}")
    parser.add_argument("--expect-digest", default="", help="plan_digest of the reviewed dry run")
    parser.add_argument("--audit-out", type=Path, default=None, help="directory for a create-only JSON audit copy of the plan/result")
    return parser.parse_args(argv)


@authorised_cli('sync_nesten_mandate')
def main(argv=None) -> int:
    args = parse_args(argv)
    handle = None
    if args.audit_out is not None:                                                    # create the audit file BEFORE any write, so a bad path can never follow a committed apply
        args.audit_out.mkdir(parents=True, exist_ok=True)
        mode = "applied" if args.apply else "dry_run"
        target = args.audit_out / f"nesten_mandate_sync_{mode}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        handle = open(target, "x", encoding="utf-8", newline="\n")                   # never overwrite an audit file
    session = get_session()
    try:
        if args.apply:
            report = apply_mandate_sync(session, buyer_key=BUYER_KEY, confirm=args.confirm, expected_plan_digest=args.expect_digest)
        else:
            report = plan_mandate_sync(session, buyer_key=BUYER_KEY)
    finally:
        session.close()
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(text)
    if handle is not None:
        with handle:
            handle.write(text + "\n")
        print(target, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
