"""v8 production transition - controlled monitoring rebaseline of the INTENTIONAL strategic capacity-semantics fingerprint change (see app.reporting.v8_monitoring_rebaseline).

    python -m scripts.v8_monitoring_rebaseline --audit-out <dir>                                  # DRY RUN (default): READ-ONLY plan + digest, writes nothing to the database
    python -m scripts.v8_monitoring_rebaseline --apply --confirm "<phrase>" --expect-digest <plan_digest of the reviewed dry run> --audit-out <dir>

Uses the existing Category C transition engine; touches only strategic allocations whose sole fingerprint change is the added non-exact ``capacity_semantics``. A coinciding genuine change blocks
the apply. No ordinary monitoring sync, no reseed, no buyer/mandate write, no model call, no schema change. Operator-authorised launch only (`launch:v8_monitoring_rebaseline`).
Production execution needs separate REVIEW authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import get_session
from app.reporting.v8_monitoring_rebaseline import CONFIRM_PHRASE, RebaselineRefused, apply_rebaseline, build_rebaseline_plan
from app.security.cli import authorised_cli


def _write_audit(directory: str | None, name: str, payload: dict) -> str | None:
    if not directory:
        return None
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    with open(path, "x", encoding="utf-8") as handle:             # never overwrites an existing artifact
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
    return str(path)


@authorised_cli('v8_monitoring_rebaseline')
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the reviewed plan (requires --confirm and --expect-digest); default is a read-only dry run")
    parser.add_argument("--confirm", default="", help=f"must equal {CONFIRM_PHRASE!r}")
    parser.add_argument("--expect-digest", default="", help="plan_digest of the reviewed dry run")
    parser.add_argument("--audit-out", default=None, help="directory for the plan / result JSON artifacts (created, never overwritten)")
    args = parser.parse_args(argv)
    session = get_session()
    try:
        plan = build_rebaseline_plan(session)
        digest = plan["plan_digest"]
        if not args.apply:
            plan_path = _write_audit(args.audit_out, f"v8_rebaseline_plan_{digest[:12]}.json", plan)
            print(json.dumps({**plan, "audit_file": plan_path, "mode": "dry_run"}, indent=2, sort_keys=True, default=str))
            return 0
        _write_audit(args.audit_out, f"v8_rebaseline_apply_plan_{digest[:12]}.json", plan)       # the audit record exists BEFORE any write
        try:
            result = apply_rebaseline(session, confirm=args.confirm, expected_plan_digest=args.expect_digest)
        except RebaselineRefused as refusal:
            print(json.dumps({"mode": "refused", "reason": str(refusal), "live_plan_digest": digest}, indent=2, sort_keys=True))
            return 1
        _write_audit(args.audit_out, f"v8_rebaseline_result_{digest[:12]}.json", result)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
