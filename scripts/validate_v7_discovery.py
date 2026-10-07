"""Gate B - READ-ONLY v7 discovery validation (specification 026). Writes ONE non-secret artifact (JSON + compact CSV) and nothing else.

    python -m scripts.validate_v7_discovery --out-dir <dir>                                   # synthetic/local SQLite only (refuses a PostgreSQL route)
    python -m scripts.validate_v7_discovery --mode real --confirm "<phrase>" --out-dir <dir> # PRODUCTION READ: needs separate Product Owner authority

Real mode enforces: PostgreSQL + the application database route, a verified READ ONLY transaction, a statement timeout, a statement allow-list, an ORM write guard, a network guard,
a model-import block and rollback. It makes no model, scraping, document or external API call and performs no database, monitoring or mandate write. Operator-authorised launch only
(explicit command identity and scope `launch:validate_v7_discovery`).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.db.session import get_session
from app.security.cli import authorised_cli

CONFIRM_PHRASE = "RUN READ-ONLY V7 DISCOVERY VALIDATION"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--mode", choices=("synthetic", "real"), default="synthetic")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--shortlist", type=int, default=20)
    parser.add_argument("--statement-timeout-ms", type=int, default=60000)
    parser.add_argument("--max-queries", type=int, default=None, help="optional safety circuit-breaker (not a performance threshold)")
    parser.add_argument("--code-sha", default=None)
    return parser.parse_args(argv)


@authorised_cli('validate_v7_discovery')
def main(argv=None) -> int:
    args = parse_args(argv)
    real = args.mode == "real"
    if real and args.confirm != CONFIRM_PHRASE:
        print("Refused: real mode requires --confirm with the exact confirmation phrase.", file=sys.stderr)
        return 2
    from verification.gate_b.runner import artifact_json, resolve_code_sha, run_validation, shortlist_csv
    session = get_session()
    try:
        artifact = run_validation(session, real=real, code_sha=args.code_sha, shortlist_size=args.shortlist, statement_timeout_ms=args.statement_timeout_ms, max_queries=args.max_queries)
    finally:
        session.close()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"gate_b_validation_{resolve_code_sha(args.code_sha)[:8]}_{stamp}"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for suffix, content in ((".json", artifact_json(artifact)), (".csv", shortlist_csv(artifact))):
        target = args.out_dir / (stem + suffix)
        with open(target, "x", encoding="utf-8", newline="\n") as handle:            # never overwrite an existing artifact
            handle.write(content)
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
