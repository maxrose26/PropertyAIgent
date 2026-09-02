"""LPDI V1 Gate 3J ("Normal Authority Cohort Activation") - focused tests
proving the config-only changes made this gate (Bolton's adopted_plan
source, Oldham's adopted_plan source, Rochdale's emerging_plan source plus
its own-plan onboarding) resolve correctly through the EXISTING, unmodified
app.policy.sources/app.policy.joint_plans/app.policy.plan_attribution
mechanisms - no attribution/lifecycle code is touched by this gate.

Reads the REAL config/policy_sources.yaml (so a future accidental edit to
these entries is caught by this test), against a hand-built isolated
in-memory database whose LocalPlan rows mirror production's real identity
strings for Bolton (id 15), Oldham (id 11) and Rochdale's new own plan -
exactly the (council_code, plan_name, plan_version) triple
app.policy.sources._resolve_local_plan_id matches on."""
from __future__ import annotations

from app.db.models import Council, LocalPlan, LocalPlanCouncil, MonitoredReport, MonitoredSource
from app.policy.joint_plans import plans_for_council
from app.policy.plan_attribution import attribute_report
from app.policy.sources import load_source_config, register_sources_for_council

# The real, on-disk config - loaded once, reused read-only by every test in
# this file. Asserting against the actual file (not a hand-copied fixture)
# is deliberate: it fails loudly if a future edit to config/policy_sources.
# yaml silently changes these entries' shape.
REAL_CONFIG = load_source_config()


def _add_council(session, code, name):
    session.add(Council(code=code, name=name, base_url="https://example.invalid",
                         date_field_mode="received", doc_system="idox"))
    session.commit()


def _add_bolton_pfe_fixture(session):
    _add_council(session, "bolton", "Bolton Council")
    plan = LocalPlan(
        id=15, council_code="bolton", plan_name="Bolton's Allocations Plan",
        plan_version="Adopted (3 December 2014, unrevised)", status="adopted", raw_status="Adopted (3 December 2014, unrevised)",
    )
    session.add(plan)
    session.commit()
    return plan


def _add_oldham_fixture(session):
    _add_council(session, "oldham", "Oldham Council")
    plan = LocalPlan(
        id=11, council_code="oldham", plan_name="Oldham Saved Unitary Development Plan (Policy H1, saved allocations)",
        plan_version="Adopted (saved UDP)", status="adopted", raw_status="Adopted (saved UDP)",
    )
    session.add(plan)
    session.commit()
    return plan


def _add_pfe_fixture(session, participating_council_code):
    """Mirrors real production: PfE (council_code="bury") linked to a
    participant via LocalPlanCouncil - exactly Rochdale's real pre-Gate-3J
    shape (PfE as the sole plans_for_council candidate)."""
    pfe = LocalPlan(
        id=2, council_code="bury", plan_name="Places for Everyone Joint Development Plan (Bury allocations)",
        plan_version="2022-2039", status="adopted", raw_status="Adopted (with effect from 21 March 2024)",
    )
    session.add(pfe)
    session.commit()
    session.add(LocalPlanCouncil(local_plan_id=pfe.id, council_code=participating_council_code, role="participating_authority"))
    session.commit()
    return pfe


# --- Bolton ---

def test_bolton_config_only_has_the_expected_source_types(session):
    sources = REAL_CONFIG["councils"]["bolton"]["sources"]
    types = {s["source_type"] for s in sources}
    assert "adopted_plan" in types
    adopted = next(s for s in sources if s["source_type"] == "adopted_plan")
    assert adopted["url"] == "https://www.bolton.gov.uk/downloads/file/671/allocations-plan-written-statement"
    assert adopted["plan_name"] == "Bolton's Allocations Plan"
    assert adopted["plan_version"] == "Adopted (3 December 2014, unrevised)"


def test_bolton_adopted_plan_source_resolves_to_localplan_id_15(session):
    _add_council(session, "othercouncil2", "placeholder")  # keep council_code namespace tidy across tests
    plan = _add_bolton_pfe_fixture(session)

    registered = register_sources_for_council(session, "bolton", config=REAL_CONFIG)
    adopted = next(s for s in registered if s.source_type == "adopted_plan")
    assert adopted.local_plan_id == plan.id == 15
    assert adopted.url == "https://www.bolton.gov.uk/downloads/file/671/allocations-plan-written-statement"

    # No Core Strategy source was added - explicitly out of this gate's scope.
    urls = {s.url for s in registered}
    assert not any("core-strategy" in u for u in urls)


# --- Oldham ---

def test_oldham_config_only_has_the_expected_source_types(session):
    sources = REAL_CONFIG["councils"]["oldham"]["sources"]
    adopted = next(s for s in sources if s["source_type"] == "adopted_plan")
    assert adopted["url"] == "https://www.oldham.gov.uk/download/downloads/id/6788/saved_udp_policies_document.pdf"
    assert adopted["plan_name"] == "Oldham Saved Unitary Development Plan (Policy H1, saved allocations)"
    assert adopted["plan_version"] == "Adopted (saved UDP)"
    # No speculative AMR/monitoring-report addition this gate.
    assert not any(s["source_type"] in ("authority_monitoring_report", "annual_monitoring_report") for s in sources)


def test_oldham_adopted_plan_source_resolves_to_localplan_id_11(session):
    plan = _add_oldham_fixture(session)

    registered = register_sources_for_council(session, "oldham", config=REAL_CONFIG)
    adopted = next(s for s in registered if s.source_type == "adopted_plan")
    assert adopted.local_plan_id == plan.id == 11


# --- Rochdale ---

def test_rochdale_config_declares_the_expected_emerging_plan_source(session):
    sources = REAL_CONFIG["councils"]["rochdale"]["sources"]
    emerging = next(s for s in sources if s["source_type"] == "emerging_plan")
    assert emerging["url"] == "https://www.rochdale.gov.uk/downloads/file/3280/publication-local-plan-document"
    assert emerging["plan_name"] == "Rochdale Local Plan"
    assert emerging["plan_version"] == "Regulation 19 Publication"
    # The pre-existing amr_page entry is genuinely untouched by this gate.
    amr = next(s for s in sources if s["source_type"] == "amr_page")
    assert amr.get("plan_name") is None
    assert amr["url"] == "https://www.rochdale.gov.uk/planning-policy/authority-monitoring-reports"


def test_rochdale_before_onboarding_pfe_is_the_sole_candidate_and_the_risk_is_real(session):
    """Documents the EXACT risk Gate 3I/3G identified, using the real,
    unmodified attribute_report - proves it before asserting the fix."""
    _add_council(session, "rochdale", "Rochdale Council")
    _add_pfe_fixture(session, "rochdale")

    candidates = plans_for_council(session, "rochdale")
    assert [p.id for p in candidates] == [2]  # PfE only - the documented risk shape

    report = MonitoredReport(
        council_code="rochdale", local_plan_id=None, source_type="local_plan",
        url="https://www.rochdale.gov.uk/downloads/file/3280/publication-local-plan-document",
        title="Rochdale Borough Local Plan - Publication Plan",
    )
    session.add(report)
    session.commit()

    result = attribute_report(session, report)
    # This is the documented risk itself: with only one candidate,
    # attribute_report's single-candidate shortcut returns PLAN_MATCH(PfE)
    # for a report that is NOT actually PfE content - exactly why Gate 3I
    # required own-plan onboarding BEFORE any Rochdale source is registered.
    assert result.status == "PLAN_MATCH"
    assert result.plan.id == 2


def test_rochdale_own_plan_onboarded_resolves_source_to_own_plan_not_pfe(session):
    _add_council(session, "rochdale", "Rochdale Council")
    pfe = _add_pfe_fixture(session, "rochdale")
    own_plan = LocalPlan(
        council_code="rochdale", plan_name="Rochdale Local Plan", plan_version="Regulation 19 Publication",
        status="proposed_submission", raw_status="Regulation 19 Publication",
    )
    session.add(own_plan)
    session.commit()

    # plans_for_council now returns exactly own plan + PfE.
    candidates = plans_for_council(session, "rochdale")
    assert {p.id for p in candidates} == {own_plan.id, pfe.id}
    assert len(candidates) == 2

    registered = register_sources_for_council(session, "rochdale", config=REAL_CONFIG)
    emerging = next(s for s in registered if s.source_type == "emerging_plan")
    assert emerging.local_plan_id == own_plan.id
    assert emerging.local_plan_id != pfe.id


def test_rochdale_report_from_the_explicitly_linked_source_attributes_to_own_plan_not_pfe(session):
    """The end-to-end proof: once onboarded, a report discovered via the
    explicitly-linked emerging_plan source attributes deterministically to
    Rochdale's own plan (Tier 1 of attribute_report) - never PfE."""
    _add_council(session, "rochdale", "Rochdale Council")
    pfe = _add_pfe_fixture(session, "rochdale")
    own_plan = LocalPlan(
        council_code="rochdale", plan_name="Rochdale Local Plan", plan_version="Regulation 19 Publication",
        status="proposed_submission", raw_status="Regulation 19 Publication",
    )
    session.add(own_plan)
    session.commit()

    registered = register_sources_for_council(session, "rochdale", config=REAL_CONFIG)
    source = next(s for s in registered if s.source_type == "emerging_plan")
    assert source.local_plan_id == own_plan.id

    report = MonitoredReport(
        council_code="rochdale", local_plan_id=source.local_plan_id, monitored_source_id=source.id,
        source_type="local_plan", url=source.url, title="Rochdale Borough Local Plan - Publication Plan",
    )
    session.add(report)
    session.commit()

    result = attribute_report(session, report)
    assert result.status == "PLAN_MATCH"
    assert result.plan.id == own_plan.id
    assert result.plan.id != pfe.id
    assert "trusted source configuration" in result.reason


def test_rochdale_unlinked_amr_page_report_is_never_silently_attributed_to_pfe_once_own_plan_exists(session):
    """The authority-wide-monitoring safety net: a report from the STILL-
    unlinked amr_page source (this gate deliberately does not force-link
    it) must not silently resolve to PfE either, now that there are 2
    genuine candidates and no explicit signal for this particular report."""
    _add_council(session, "rochdale", "Rochdale Council")
    _add_pfe_fixture(session, "rochdale")
    own_plan = LocalPlan(
        council_code="rochdale", plan_name="Rochdale Local Plan", plan_version="Regulation 19 Publication",
        status="proposed_submission", raw_status="Regulation 19 Publication",
    )
    session.add(own_plan)
    session.commit()

    unlinked_source = MonitoredSource(
        council_code="rochdale", local_plan_id=None, source_type="amr_page",
        url="https://www.rochdale.gov.uk/planning-policy/authority-monitoring-reports",
    )
    session.add(unlinked_source)
    session.commit()

    report = MonitoredReport(
        council_code="rochdale", local_plan_id=None, monitored_source_id=unlinked_source.id,
        source_type="authority_monitoring_report", url="https://www.rochdale.gov.uk/some-amr-2025.pdf",
        title="Rochdale Authority Monitoring Report 2024/25",
    )
    session.add(report)
    session.commit()

    result = attribute_report(session, report)
    # AUTHORITY_WIDE (not PLAN_MATCH(PfE)) - an AMR genuinely isn't plan-
    # specific content, and with 2 real candidates now present, the old
    # single-candidate shortcut can no longer fire at all.
    assert result.status == "AUTHORITY_WIDE"
    assert result.plan is None
