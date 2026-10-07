"""V7C-2 - standalone stale-mandate re-onboarding (the approved v7 transition path; NOT scripts.bootstrap_acquisition_monitoring).

    python -m scripts.reonboard_stale_mandates                       # DRY RUN (default): prints the JSON audit report, writes nothing
    python -m scripts.reonboard_stale_mandates --buyer nesten_homes  # restrict to named buyers (repeatable)
    python -m scripts.reonboard_stale_mandates --apply --confirm "<phrase>" --expect-digest <plan_digest from the reviewed dry run>

No ordinary monitoring sync, no reseed, no scraping/ingestion, no model call. Apply refuses unless the confirm phrase and the REVIEWED plan digest match, the same-universe v6/v7 parity
check passes (no oracle is configured yet - REVIEW decision pending - so apply currently refuses by design), and the Stage 1 checks pass; it then commits once for all mandates.
Operator-authorised launch only (`launch:reonboard_stale_mandates`). Production execution needs separate REVIEW authority.
"""
from __future__ import annotations

import argparse
import json

from app.db.session import get_session
from app.policy.mandate_reonboarding import CONFIRM_PHRASE, apply_stale_mandate_reonboarding, plan_stale_mandate_reonboarding
from app.security.cli import authorised_cli

PARITY_ORACLE = None   # REVIEW decision pending: no independent same-universe v6 comparison exists yet, so apply cannot pass parity


@authorised_cli('reonboard_stale_mandates')
def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--buyer", action="append", dest="buyers", help="buyer_key to include (repeatable); default every active buyer")
    parser.add_argument("--apply", action="store_true", help="write the reviewed plan (requires --confirm and --expect-digest); default is a dry run")
    parser.add_argument("--confirm", default="", help=f"must equal {CONFIRM_PHRASE!r}")
    parser.add_argument("--expect-digest", default="", help="plan_digest of the reviewed dry run")
    args = parser.parse_args(argv)
    session = get_session()
    try:
        if args.apply:
            report = apply_stale_mandate_reonboarding(session, confirm=args.confirm, expected_plan_digest=args.expect_digest, buyer_keys=args.buyers, parity_oracle=PARITY_ORACLE)
        else:
            report = plan_stale_mandate_reonboarding(session, buyer_keys=args.buyers, parity_oracle=PARITY_ORACLE)
    finally:
        session.close()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
