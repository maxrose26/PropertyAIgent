"""Registers monitored Policy Intelligence sources for a council from
config/policy_sources.yaml (see app.policy.sources). The council's Local
Plan must already be ingested (python ingest_local_plan.py --council ...)
before its sources can be registered - this only attaches watch targets to
an existing plan.

    python -m scripts.register_policy_sources --council stockport

Safe to re-run - already-registered sources are found, not duplicated.
"""
from __future__ import annotations

import argparse

from app.db.session import get_session, init_db
from app.policy.sources import register_sources_for_council


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--council", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    session = get_session()
    sources = register_sources_for_council(session, args.council)
    if not sources:
        print(f"[register-policy-sources] {args.council}: no sources registered - either no config entry in "
              f"config/policy_sources.yaml, or its Local Plan hasn't been ingested yet")
        return
    print(f"[register-policy-sources] {args.council}: {len(sources)} source(s) registered/confirmed")
    for source in sources:
        print(f"  - {source.source_type}: {source.url}")


if __name__ == "__main__":
    main()
