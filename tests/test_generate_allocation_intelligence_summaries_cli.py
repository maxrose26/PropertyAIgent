"""AI Allocation Intelligence Summary CLI (scripts.generate_allocation_
intelligence_summaries) - dry-run/execute eligibility parity tests.

V7 Quality Hardening Amendment - real production symptom: a controlled
`--allocation-ids 51,32,66,196` dry-run reported "fresh: 1, would generate:
3" immediately before an execute run against the identical target list that
attempted all FOUR allocations and regenerated allocation 51. Root-caused to
two compounding issues, both fixed here:

1. `_run_execute` hand-wrote its own separate freshness/skip check
   (`if only_stale and already_fresh: skip`) that had drifted from
   `_classify` (dry-run's own classifier) - when `only_stale` is False (an
   explicit `--allocation-id`/`--allocation-ids`/`--all-eligible` target),
   that check is a no-op (attempts every target regardless of freshness),
   but `_classify` used to report an already-fresh target as "fresh"
   (not "would generate") REGARDLESS of `only_stale`. Fixed by making
   `_classify` itself the single source of truth both functions call.

2. `is_allocation_summary_stale` (the function both the old and new
   `_classify` rely on) only ever compared the context fingerprint, never
   `prompt_version`, even though the SAME function generation actually uses
   internally (`should_regenerate_allocation_summary`) has always checked
   both - so a summary generated under an old prompt version, with an
   unchanged fingerprint, was reported "fresh" by the CLI right up until
   the real generation call regenerated it anyway. Fixed in
   app.reporting.allocation_intelligence_summary directly (see that
   module's own test file for the dedicated regression); this file proves
   the CLI layer built on top of it is now internally consistent.

No real OpenAI call anywhere - `_classify` is pure/read-only, and these
tests call it directly rather than invoking main()/argparse."""
from __future__ import annotations

import datetime as dt

from app.db.models import AllocationIntelligenceSummary, Council, LocalPlan, LocalPlanSite
from app.reporting.allocation_intelligence_summary import (
    PROMPT_VERSION, build_allocation_context, compute_context_fingerprint, get_allocation_summary,
)
from scripts.generate_allocation_intelligence_summaries import _classify


def _make_allocation(session, *, council_code="testcouncil", policy_reference="REF-1",
                      site_name="Test Allocation", minimum_dwellings=300) -> LocalPlanSite:
    if session.get(Council, council_code) is None:
        session.add(Council(code=council_code, name=council_code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))
        session.commit()
    plan = LocalPlan(council_code=council_code, plan_name="Test Local Plan", status="adopted", raw_status="adopted")
    session.add(plan)
    session.commit()
    allocation = LocalPlanSite(
        council_code=council_code, local_plan_id=plan.id, policy_reference=policy_reference, site_name=site_name,
        plan_name="Test Local Plan", plan_status="adopted", minimum_dwellings=minimum_dwellings, intended_use="residential",
    )
    session.add(allocation)
    session.commit()
    return allocation


def _persist_summary(session, allocation, *, prompt_version: str, fingerprint: str | None = None) -> None:
    context = build_allocation_context(session, allocation)
    fp = fingerprint if fingerprint is not None else compute_context_fingerprint(context)
    summary = get_allocation_summary(session, allocation.id)
    if summary is None:
        summary = AllocationIntelligenceSummary(allocation_id=allocation.id)
        session.add(summary)
    summary.headline = "Existing summary"
    summary.overview = "Existing overview."
    summary.context_fingerprint = fp
    summary.prompt_version = prompt_version
    summary.status = "ok"
    summary.generated_at = dt.datetime.now(dt.timezone.utc)
    session.commit()


def test_m_dry_run_and_execute_use_the_same_classification_fresh(session):
    """Test M - a genuinely fresh allocation, targeted by --stale (the
    default), classifies "fresh" - both dry-run's report and execute's
    skip decision are driven by this exact same call."""
    allocation = _make_allocation(session)
    _persist_summary(session, allocation, prompt_version=PROMPT_VERSION)
    assert _classify(session, allocation, only_stale=True) == "fresh"


def test_m_explicit_target_always_would_generate_regardless_of_freshness(session):
    """Test M (the exact real bug) - an allocation targeted EXPLICITLY
    (only_stale=False, matching --allocation-id/--allocation-ids/
    --all-eligible) must be "would_generate" even when genuinely fresh,
    because that is what execute actually does for an explicit target."""
    allocation = _make_allocation(session)
    _persist_summary(session, allocation, prompt_version=PROMPT_VERSION)
    assert _classify(session, allocation, only_stale=False) == "would_generate"


def test_n_fresh_summary_not_unexpectedly_regenerated_under_identical_state(session):
    """Test N - under --stale (only_stale=True), an unchanged, current-
    prompt-version summary stays "fresh", never "would_generate"/"stale"."""
    allocation = _make_allocation(session)
    _persist_summary(session, allocation, prompt_version=PROMPT_VERSION)
    for _ in range(3):
        assert _classify(session, allocation, only_stale=True) == "fresh"


def test_o_missing_summary_classified_missing_under_stale(session):
    allocation = _make_allocation(session)
    assert get_allocation_summary(session, allocation.id) is None
    assert _classify(session, allocation, only_stale=True) == "missing"


def test_o_error_status_with_no_headline_classified_missing(session):
    """A row with status="error"/headline=None (a rejected or failed prior
    attempt) is classified exactly like "no summary at all" - missing,
    not fresh - so --stale correctly retries it."""
    allocation = _make_allocation(session)
    summary = AllocationIntelligenceSummary(
        allocation_id=allocation.id, headline=None, status="error",
        generation_error="unsupported numbers: 83",
    )
    session.add(summary)
    session.commit()
    assert _classify(session, allocation, only_stale=True) == "missing"


def test_o_stale_via_fingerprint_change_classified_stale(session):
    allocation = _make_allocation(session)
    _persist_summary(session, allocation, prompt_version=PROMPT_VERSION, fingerprint="deliberately-stale-fingerprint")
    assert _classify(session, allocation, only_stale=True) == "stale"


def test_o_stale_via_prompt_version_drift_classified_stale(session):
    """Direct regression for the real parity bug's root cause - an
    unchanged fingerprint but an old prompt_version must classify stale."""
    allocation = _make_allocation(session)
    _persist_summary(session, allocation, prompt_version="allocation-intelligence-summary-v1-old")
    assert _classify(session, allocation, only_stale=True) == "stale"


def test_insufficient_context_classified_regardless_of_only_stale(session):
    allocation = _make_allocation(session, minimum_dwellings=0)
    # No related Site and no stated capacity - genuinely insufficient context.
    allocation.minimum_dwellings = None
    session.commit()
    assert _classify(session, allocation, only_stale=True) == "insufficient_context"
    assert _classify(session, allocation, only_stale=False) == "insufficient_context"
