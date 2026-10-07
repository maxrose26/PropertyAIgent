"""v8 production transition - ROLLBACK of the strategic monitoring rebaseline (see app.reporting.v8_monitoring_rollback).

    python -m scripts.v8_monitoring_rollback --plan-file <forward plan.json> --result-file <forward result.json> --audit-out <dir>        # DRY RUN (default): read-only restore plan + digest
    python -m scripts.v8_monitoring_rollback --plan-file ... --result-file ... --apply --confirm "<phrase>" --expect-digest <restore_plan_digest> --audit-out <dir>

Restores only `fingerprint` and `fingerprint_fields` of only the rebaselined rows, to the exact recorded previous values; refuses if any row is no longer in the expected post-transition state.
No ordinary monitoring sync, no reseed, no model call. Operator-authorised launch only (`launch:v8_monitoring_rollback`). Production execution needs separate REVIEW authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import get_session
from app.reporting.v8_monitoring_rollback import CONFIRM_PHRASE, RollbackRefused, apply_restore, build_restore_plan, load_forward_artifacts
from app.security.cli import authorised_cli


def _audit(directory, name, payload):
    if not directory:
        return None
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    with open(path, "x", encoding="utf-8") as handle:             # never overwrites an artifact
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
    return str(path)


@authorised_cli('v8_monitoring_rollback')
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan-file", required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="", help=f"must equal {CONFIRM_PHRASE!r}")
    parser.add_argument("--expect-digest", default="", help="restore_plan_digest of the reviewed dry run")
    parser.add_argument("--audit-out", default=None)
    args = parser.parse_args(argv)
    try:
        forward = load_forward_artifacts(json.loads(Path(args.plan_file).read_text(encoding="utf-8")), json.loads(Path(args.result_file).read_text(encoding="utf-8")))
    except (RollbackRefused, OSError, ValueError) as error:
        print(json.dumps({"mode": "refused", "reason": str(error)}, indent=2))
        return 1
    session = get_session()
    try:
        plan = build_restore_plan(session, forward)
        digest = plan["restore_plan_digest"]
        if not args.apply:
            path = _audit(args.audit_out, f"v8_monitoring_rollback_plan_{digest[:12]}.json", plan)
            print(json.dumps({**plan, "audit_file": path, "mode": "dry_run"}, indent=2, sort_keys=True, default=str))
            return 0
        _audit(args.audit_out, f"v8_monitoring_rollback_apply_plan_{digest[:12]}.json", plan)       # recorded BEFORE any write
        try:
            result = apply_restore(session, forward, confirm=args.confirm, expected_restore_digest=args.expect_digest)
        except RollbackRefused as refusal:
            print(json.dumps({"mode": "refused", "reason": str(refusal), "live_restore_plan_digest": digest}, indent=2, sort_keys=True))
            return 1
        _audit(args.audit_out, f"v8_monitoring_rollback_result_{digest[:12]}.json", result)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
