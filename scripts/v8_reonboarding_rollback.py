"""v8 production transition - ROLLBACK of the stale-mandate re-onboarding (see app.policy.mandate_reonboarding_rollback).

    python -m scripts.v8_reonboarding_rollback --forward-report <forward APPLIED report.json> --audit-out <dir>                  # DRY RUN (default): read-only restore plan + digest
    python -m scripts.v8_reonboarding_rollback --forward-report ... --apply --confirm "<phrase>" --expect-digest <restore_plan_digest> --audit-out <dir>

Restores only `matching_fingerprint`, `onboarding_completed_at` and `onboarding_summary` of only the re-onboarded mandates, to the exact recorded previous values; refuses if any mandate is no longer in
the expected post-transition state. One transaction. No monitoring sync, no reseed, no model call. Operator-authorised launch only (`launch:v8_reonboarding_rollback`) plus buyer.write.
Production execution needs separate REVIEW authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import get_session
from app.policy.mandate_reonboarding_rollback import (
    CONFIRM_PHRASE, RollbackRefused, apply_mandate_reonboarding_rollback, load_forward_report, plan_mandate_reonboarding_rollback,
)
from app.security.cli import authorised_cli


def _audit(directory, name, payload):
    if not directory:
        return None
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    with open(path, "x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
    return str(path)


@authorised_cli('v8_reonboarding_rollback')
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--forward-report", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="", help=f"must equal {CONFIRM_PHRASE!r}")
    parser.add_argument("--expect-digest", default="")
    parser.add_argument("--audit-out", default=None)
    args = parser.parse_args(argv)
    try:
        forward = load_forward_report(json.loads(Path(args.forward_report).read_text(encoding="utf-8")))
    except (RollbackRefused, OSError, ValueError) as error:
        print(json.dumps({"mode": "refused", "reason": str(error)}, indent=2))
        return 1
    session = get_session()
    try:
        plan = plan_mandate_reonboarding_rollback(session, forward)
        digest = plan["restore_plan_digest"]
        if not args.apply:
            path = _audit(args.audit_out, f"v8_reonboarding_rollback_plan_{digest[:12]}.json", plan)
            print(json.dumps({**plan, "audit_file": path, "mode": "dry_run"}, indent=2, sort_keys=True, default=str))
            return 0
        _audit(args.audit_out, f"v8_reonboarding_rollback_apply_plan_{digest[:12]}.json", plan)
        try:
            result = apply_mandate_reonboarding_rollback(session, forward, confirm=args.confirm, expected_restore_digest=args.expect_digest)
        except RollbackRefused as refusal:
            print(json.dumps({"mode": "refused", "reason": str(refusal), "live_restore_plan_digest": digest}, indent=2, sort_keys=True))
            return 1
        _audit(args.audit_out, f"v8_reonboarding_rollback_result_{digest[:12]}.json", result)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
