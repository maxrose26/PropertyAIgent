"""Deployment-safety CLI: reports whether a release-candidate commit range
touches a schema-defining file (see app.deployment.schema_release_detection
for the exact file set and why each one is included).

    python -m scripts.detect_schema_change --base <ref> --head <ref>

READ-ONLY - runs `git diff --name-only <base>..<head>`, nothing else.
Never mutates the repository, never touches Render, never migrates or
deploys anything itself; this is a REPORTING command a deployment workflow
reads, exactly like scripts/verify_schema.py's own role for schema state.

Exit code 0: no migration required (matches verify_schema.py's own
"0 = current/safe" convention). Exit code 1: migration required - a
release built from this commit range must not be deployed until a
controlled production migration (python -m scripts.migrate_schema) has
been run and verified.

Also writes `migration_required=true|false` to $GITHUB_OUTPUT when that
environment variable is set (GitHub Actions' own step-output mechanism),
so a future CI/deployment job can branch on the result directly - a no-op
outside GitHub Actions.

IMPORTANT - choosing --base (CI/CD Phase 1 pre-merge amendment, Part 8,
"Base Commit / Diff Semantics"): --base should be the last commit ACTUALLY
DEPLOYED to production, not simply the previous master push. A schema
change introduced in an earlier, still-undeployed commit must keep gating
every later commit until it is migrated and deployed - even a later
commit that itself makes no further schema change would otherwise slip
through if compared only against the immediately-preceding push. This
script does not itself decide or track what "last deployed" means (no
such tracking mechanism exists yet in this repository - see this
project's CI/CD Phase 1 report for the recommended design, a moving git
tag updated only by the not-yet-built Phase 2 deploy workflow); wiring a
durable "last deployed" reference into an actual CI job is explicitly
Phase 2 scope, not this script's own concern.
"""
from __future__ import annotations

import argparse
import os

from app.deployment.schema_release_detection import detect_schema_change


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.detect_schema_change")
    parser.add_argument(
        "--base", required=True,
        help="Base ref/commit - should be the last commit actually deployed to production (see this script's own module docstring).",
    )
    parser.add_argument("--head", required=True, help="Release-candidate ref/commit.")
    args = parser.parse_args(argv)

    migration_required, matched = detect_schema_change(args.base, args.head)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"migration_required={'true' if migration_required else 'false'}\n")

    if migration_required:
        print(f"[detect-schema-change] migration_required=true changed_schema_files={sorted(matched)}")
        return 1

    print("[detect-schema-change] migration_required=false - no schema-defining file changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
