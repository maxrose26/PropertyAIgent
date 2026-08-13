"""Operator CLI: targeted normal B3 intelligence refresh for exactly ONE
existing Application (Render Shell / manual reprocessing use case).

    python -m scripts.refresh_intelligence_application --application-id 721
    python -m scripts.refresh_intelligence_application --reference A/20/88859/RMMAJ --council wigan

Calls app.extraction.intelligence_refresh.refresh_intelligence_for_application
directly and UNCHANGED - the exact same B3 atomic-replacement entry point
normal scheduled processing itself calls, never a parallel refresh path.
Deliberately NEVER passes extra_fields, so intelligence_rebuild_version/
intelligence_rebuilt_at (the historical-rebuild-only completion markers -
see app.extraction.historical_rebuild) are always left exactly as they
were. This is NOT the historical rebuild runner (scripts.rebuild_
intelligence, a separate tool) - it never sets B1/B2 trigger state
(evidence_refresh_required/material_evidence_changed_at), never calls B2
targeted evidence acquisition, never triggers Daily Discovery or batch
Intelligence Processing. It operates purely on whatever evidence is
ALREADY stored for the one named Application, using the family-aware
evidence selection refresh_intelligence_for_application itself already
performs internally.

Exactly one Application per invocation, by design - no batches, no comma-
separated IDs, no wildcard references. Target resolution happens BEFORE
any OpenAI client call is made, so an unresolvable/ambiguous target never
costs an API call.

Environment: same standard path as every other operator script in this
repository (app.db.session.get_session() for the DB session - reads
DATABASE_URL, calling load_dotenv() internally; OPENAI_API_KEY read
directly from the process environment, exactly as scripts.rebuild_
intelligence and app.pipeline.run_weekly already do). No secret value is
ever printed by this script.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import select

from app.db.models import Application
from app.extraction.intelligence_refresh import (
    refresh_depth_for_reasons,
    refresh_intelligence_for_application,
    select_refresh_evidence_documents,
)
from app.extraction.run_extraction import (
    OUTCOME_AI_ERROR,
    OUTCOME_ERROR,
    OUTCOME_INVALID_OUTPUT,
    OUTCOME_NO_USABLE_TEXT,
    OUTCOME_SUCCESS,
)
from app.pipeline.evidence_refresh import resolve_application_family

# Distinct exit codes per RefreshOutcome value (audited from app.extraction.
# run_extraction's own OUTCOME_* taxonomy - exactly 5 values, all mapped
# explicitly below; nothing defaults to "success"). EXIT_TARGET_ERROR is
# this script's own concern (target resolution failed before any OpenAI
# call was ever made).
EXIT_SUCCESS = 0
EXIT_TARGET_ERROR = 1
EXIT_NO_USABLE_TEXT = 2
EXIT_AI_ERROR = 3
EXIT_INVALID_OUTPUT = 4
EXIT_ERROR = 5

_EXIT_CODE_BY_OUTCOME = {
    OUTCOME_SUCCESS: EXIT_SUCCESS,
    OUTCOME_NO_USABLE_TEXT: EXIT_NO_USABLE_TEXT,
    OUTCOME_AI_ERROR: EXIT_AI_ERROR,
    OUTCOME_INVALID_OUTPUT: EXIT_INVALID_OUTPUT,
    OUTCOME_ERROR: EXIT_ERROR,
}


class TargetResolutionError(Exception):
    """Raised when the requested Application cannot be unambiguously
    resolved - always raised (and always exits non-zero) before any
    OpenAI client call is made."""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.refresh_intelligence_application",
        description=(
            "Targeted normal B3 intelligence refresh for exactly ONE existing Application. "
            "Not a batch tool, not the historical rebuild runner - see this module's own docstring."
        ),
    )
    parser.add_argument("--application-id", type=int, default=None, help="Exact Application primary key.")
    parser.add_argument("--reference", type=str, default=None, help="Exact Application.reference (requires --council too).")
    parser.add_argument("--council", type=str, default=None, help="Exact Application.council_code (requires --reference too).")
    parser.add_argument(
        "--inspect", action="store_true",
        help="Resolve the target and show selected family/evidence metadata only - zero OpenAI calls, zero writes.",
    )
    return parser


def resolve_target(session, *, application_id: int | None, reference: str | None, council: str | None) -> Application:
    """Section 3 of the task's own preferred semantics: (A) --application-id
    alone resolves by primary key; (B) --reference + --council together
    resolve by that exact pair (Application.reference/council_code carry a
    UniqueConstraint, so at most one row can genuinely match - the "multiple
    matches" branch below is defensive, not expected to be reachable); (C)
    if both are supplied, they must resolve to the SAME Application id or
    this refuses to guess."""
    if application_id is None and (reference is None or council is None):
        raise TargetResolutionError("Provide either --application-id, or both --reference and --council.")

    by_id: Application | None = None
    if application_id is not None:
        by_id = session.get(Application, application_id)
        if by_id is None:
            raise TargetResolutionError(f"No application found with id={application_id}.")

    by_ref: Application | None = None
    if reference is not None and council is not None:
        matches = session.execute(
            select(Application).where(Application.council_code == council, Application.reference == reference)
        ).scalars().all()
        if len(matches) == 0:
            raise TargetResolutionError(f"No application found for council={council!r} reference={reference!r}.")
        if len(matches) > 1:
            raise TargetResolutionError(
                f"Multiple applications ({len(matches)}) matched council={council!r} reference={reference!r} - refusing to guess."
            )
        by_ref = matches[0]

    if by_id is not None and by_ref is not None and by_id.id != by_ref.id:
        raise TargetResolutionError(
            f"--application-id={application_id} does not match --reference/--council "
            f"(that pair resolved to application id={by_ref.id}) - refusing to guess which one you meant."
        )

    return by_id if by_id is not None else by_ref


def _print_target(app: Application) -> None:
    print("=== TARGET ===")
    print(
        f"application_id={app.id} reference={app.reference!r} council={app.council_code!r} "
        f"site_id={app.site_id} status={app.status!r} decision={app.decision!r}"
    )


def _print_inspect(session, app: Application) -> None:
    family = resolve_application_family(session, app)
    reasons = tuple(part for part in (app.evidence_refresh_reason or "").split(",") if part)
    depth = refresh_depth_for_reasons(reasons)
    documents = select_refresh_evidence_documents(family, depth)
    print("=== INSPECT (read-only - zero OpenAI calls, zero writes) ===")
    print(f"depth={depth} family={[m.reference for m in family]}")
    for document in documents:
        print(f"  doc_id={document.id} doc_type={document.doc_type} name={document.document_name!r}")


def _print_result(app: Application, outcome) -> None:
    print("=== REFRESH ===")
    print(f"outcome={outcome.outcome} depth={outcome.depth} affordable_housing_changes={outcome.affordable_housing_changes}")

    intel = app.scheme_intelligence
    print("=== INTELLIGENCE ===")
    if intel is None:
        print("(no SchemeIntelligence row exists for this application)")
    else:
        print(f"latest_material_event={intel.latest_material_event!r}")
        print(f"recommendation_direction={intel.recommendation_direction!r}")
        print(f"formal_decision_outstanding={intel.formal_decision_outstanding!r}")
        print(f"refusal_reasons={intel.refusal_reasons!r}")
        print(f"withdrawal_reason={intel.withdrawal_reason!r}")
        print(f"affordable_percentage_final={intel.affordable_percentage_final!r}")
        print(f"affordable_units_final={intel.affordable_units_final!r}")
        print(f"affordable_tenure_split_final={intel.affordable_tenure_split_final!r}")
        print(f"affordable_housing_status={intel.affordable_housing_status!r}")
        print(f"affordable_housing_notes={intel.affordable_housing_notes!r}")
        print("=== HISTORICAL MARKERS (must be unchanged by this CLI) ===")
        print(f"intelligence_rebuild_version={intel.intelligence_rebuild_version!r}")
        print(f"intelligence_rebuilt_at={intel.intelligence_rebuilt_at!r}")

    site = app.site
    print("=== SITE SUMMARY ===")
    print(site.status_summary if site is not None else "(no linked Site)")


def run(
    session, client: OpenAI | None, *,
    application_id: int | None, reference: str | None, council: str | None, inspect: bool,
) -> int:
    """The testable core (mockable client, in-memory session) - main()
    below is a thin wrapper constructing the real session/client. Target
    resolution ALWAYS happens first; refresh_intelligence_for_application
    is only ever reached once a single unambiguous target is confirmed."""
    try:
        app = resolve_target(session, application_id=application_id, reference=reference, council=council)
    except TargetResolutionError as exc:
        print(f"[refresh-intelligence-application] {exc}", file=sys.stderr)
        return EXIT_TARGET_ERROR

    _print_target(app)

    if inspect:
        _print_inspect(session, app)
        return EXIT_SUCCESS

    outcome = refresh_intelligence_for_application(session, client, app)
    _print_result(app, outcome)
    return _EXIT_CODE_BY_OUTCOME.get(outcome.outcome, EXIT_ERROR)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    from app.db.session import get_session

    session = get_session()
    try:
        client = None
        if not args.inspect:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                print("[refresh-intelligence-application] OPENAI_API_KEY is not set.", file=sys.stderr)
                return EXIT_TARGET_ERROR
            client = OpenAI(api_key=api_key)

        return run(
            session, client,
            application_id=args.application_id, reference=args.reference, council=args.council,
            inspect=args.inspect,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
