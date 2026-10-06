"""Specification 023: synthetic adversarial evidence, never production facts."""
import datetime as dt
from types import SimpleNamespace

import pandas as pd
import pytest

from app.db.models import Application, Site, LocalPlan, LocalPlanCouncil, LocalPlanSite, VisualEvidence
from app.enrichment import epc_lookup
from app.pipeline.lapse_tracking import compute_lapse_status, classify_build_status
from app.pipeline.phase_tracking import compute_phase_progress
from app.reporting.dashboard import _approaching_lapse_cards, _undeveloped_phase_cards, build_ai_summary_carousel_items
from app.reporting.opportunity_feed import _reshape_signal_card, PLANNING_DELIVERY
from app.reporting.profile_destination import limited_profile, origin_evidence
from app.reporting.allocation_discovery import build_allocation_discovery, apply_filters
from app.visuals.site_view import build_allocation_image_status, build_allocation_visual_summaries
from app.search.query_parser import numeric_unit_mask, availability_mask


def site_and_grant(session, *, age=30, phase=False):
    site = Site(council_code="testcouncil", canonical_address="synthetic", display_address="Synthetic lead")
    session.add(site); session.flush()
    app = Application(council_code="testcouncil", site_id=site.id, reference="SYN/FULL",
        proposal="Erection of 40 dwellings" + (" in Phase 1" if phase else ""),
        decision="Granted", application_category="full_planning",
        decision_issued_date=(dt.date.today()-dt.timedelta(days=age)).isoformat(),
        summary_url="https://example.invalid/planning/SYN-FULL")
    session.add(app); session.commit()
    return site, app


@pytest.mark.parametrize("rows,grant,count,reasons", [
    ([{"registrationDate":"2020-01-01"}], dt.date(2026,1,1), 0, ["pre_grant"]),
    ([{"registrationDate":"2026-02-01","address":"Unrelated road"}], dt.date(2026,1,1), 1, ["post_grant_scheme_match_unverified"]),
    ([{"registrationDate":"2026-02-01","lmk-key":"x"}]*2, dt.date(2026,1,1), 1, ["post_grant_scheme_match_unverified","duplicate_certificate"]),
    ([{"registrationDate":"2020-01-01"},{"registrationDate":"2026-02-01","address":"Same postcode, different dwelling"}], dt.date(2026,1,1), 1, ["pre_grant","post_grant_scheme_match_unverified"]),
    ([{}], dt.date(2026,1,1), 0, ["date_scope_unknown"]),
    ([{"registrationDate":"invalid"}], dt.date(2026,1,1), 0, ["date_scope_unknown"]),
    ([{"registrationDate":None}], dt.date(2026,1,1), 0, ["date_scope_unknown"]),
    ([{"registrationDate":"2026-02-01"}], None, 0, ["date_scope_unknown"]),
    ([{"registrationDate":"2026-02-01"}], "invalid", 0, ["date_scope_unknown"]),
    ([], dt.date(2026,1,1), 0, []),
    ([None], dt.date(2026,1,1), 0, ["invalid_record"]),
])
def test_epcs_never_establish_unscoped_completion(monkeypatch, rows, grant, count, reasons):
    monkeypatch.setattr(epc_lookup,"search_epcs",lambda *_: rows)
    result=epc_lookup.check_build_status("offline","TEST",1,grant)
    assert result.status == "unknown"
    assert result.epc_count == count
    assert [e["reason"] for e in result.evidence] == reasons
    assert [e["record"] for e in result.evidence] == rows  # unmatched source evidence retained


@pytest.mark.parametrize("raw", [None,"unknown","complete","partially_complete","underway","no_completions_yet"])
@pytest.mark.parametrize("category", ["condition_discharge_or_details","variation_or_amendment"])
def test_admin_activity_never_promotes_or_overwrites_raw_status(session,raw,category):
    site,grant=site_and_grant(session)
    site.build_status=raw
    admin=Application(council_code="testcouncil",site_id=site.id,reference="SYN/ADMIN",application_category=category,
        application_received=dt.date.today().isoformat())
    for apps in ([grant,admin],[admin,grant]):
        assert classify_build_status(apps,site,dt.date.today()) == "unknown"
        result=compute_lapse_status(apps,site)
        assert result["build_status"] == "unknown"
        assert result["raw_build_status"] == raw
        assert result["availability"] == "unknown"
        assert result["granted_app"] is grant
        assert compute_phase_progress(apps)["status"] == "planning_activity"
    assert site.build_status == raw


@pytest.mark.parametrize("value,expected", [(40,True),(0,True),(51,False),(None,False),(float("nan"),False),
    ("bad",False),("40",True),(-1,False),(1.5,False),(float("inf"),False),(True,False),("40 / 80 conflicting",False)])
def test_explicit_maximum_does_not_turn_unknown_into_zero(value,expected):
    assert bool(numeric_unit_mask(pd.Series([value],dtype=object),maximum=50).iloc[0]) is expected


def test_bounds_and_unfiltered_discovery_are_distinct():
    values=pd.Series([None,10,50,100],dtype=object)
    assert numeric_unit_mask(values,minimum=20,maximum=80).tolist()==[False,False,True,False]
    assert numeric_unit_mask(values).tolist()==[True]*4
    assert numeric_unit_mask(values,minimum=80,maximum=20).tolist()==[False]*4


@pytest.mark.parametrize("state", [None,"unknown","complete","no_completions_yet","not_complete","available"])
def test_availability_requires_evidence(state):
    assert not availability_mask(pd.Series([state])).iloc[0]


def test_explicit_evidenced_availability_contract():
    assert availability_mask(pd.Series(["evidenced_available"])).iloc[0]


@pytest.mark.parametrize("date", [None,"bad","2026-02-30"])
def test_missing_or_invalid_decision_dates_do_not_make_deadlines(session,date):
    site,grant=site_and_grant(session)
    grant.decision_issued_date=date
    result=compute_lapse_status([grant],site)
    assert result["deadline"] is None
    assert result["deadline_basis"] == "unknown"
    assert result["build_status"] == "unknown"


def test_granted_phase_lead_survives_admin_activity(session):
    site,grant=site_and_grant(session,phase=True)
    other=Application(council_code="testcouncil",site_id=site.id,reference="SYN/OTHER",proposal="Erection of 20 dwellings in Phase 2")
    session.add(other);session.commit()
    before=_undeveloped_phase_cards(session,20)
    admin=Application(council_code="testcouncil",site_id=site.id,reference="SYN/ADMIN",proposal="Discharge of conditions Phase 1",
        application_category="condition_discharge_or_details",application_received=dt.date.today().isoformat())
    session.add(admin);session.commit()
    after=_undeveloped_phase_cards(session,20)
    assert len(before)==len(after)==1
    assert before[0]["id"]==after[0]["id"]
    assert after[0]["application_reference"]==grant.reference
    assert "unverified" in after[0]["reason"]
    grant.decision=None; session.commit()
    assert _undeveloped_phase_cards(session,20)==[]  # admin-only is not a permission


def test_assumed_date_opportunity_opens_same_scoped_evidence(session):
    site,grant=site_and_grant(session,age=3*365-25)
    cards=_approaching_lapse_cards(session,20)
    card=_reshape_signal_card(cards[0],opportunity_type=PLANNING_DELIVERY,extra_tags=[])
    assert card["params"]=={"site_id":str(site.id),"origin":"opportunities","application_reference":grant.reference}
    profile=limited_profile(site,[grant])
    assert profile["site_id"]==site.id
    assert profile["reference"]==grant.reference
    assert profile["source_url"]==grant.summary_url
    assert profile["lapse"]["deadline_basis"]=="assumed"
    assert "Assumed" in card["headline_reason"]
    origin=origin_evidence(site.id,[grant],grant.reference,"1")
    assert origin["reference"]==grant.reference and origin["requested_phase"]=="1"
    assert "wider site" in origin["limitation"]
    wrong=origin_evidence(site.id+1,[grant],grant.reference,"1")
    assert wrong["reference"] is None and wrong["source_url"] is None
    assert "no substitute subject" in wrong["limitation"]


def test_joint_plan_does_not_establish_allocation_geography(session):
    plan=LocalPlan(council_code="testcouncil",plan_name="Synthetic joint plan",status="adopted")
    session.add(plan);session.flush()
    session.add_all([LocalPlanCouncil(local_plan_id=plan.id,council_code=c,role="participating_authority") for c in ("testcouncil","othercouncil")])
    allocation=LocalPlanSite(council_code="testcouncil",local_plan_id=plan.id,site_name="Synthetic allocation",plan_name=plan.plan_name,plan_status="adopted")
    session.add(allocation);session.commit()
    result=build_allocation_discovery(session)
    card=next(c for c in result["cards"] if c["id"]==allocation.id)
    assert card["is_multi_authority"] is True
    assert card["joint_plan_councils"]==["othercouncil"]
    assert card["allocation_cross_boundary"] is None
    assert apply_filters([card],{"cross_boundary_only":True})==[]
    assert apply_filters([card],{"joint_plan_only":True})==[card]


def test_visual_machine_selection_is_not_confirmation(session):
    plan=LocalPlan(council_code="testcouncil",plan_name="Synthetic",status="adopted")
    session.add(plan);session.flush()
    alloc=LocalPlanSite(council_code="testcouncil",local_plan_id=plan.id,site_name="Synthetic",plan_name="Synthetic",plan_status="adopted")
    session.add(alloc);session.flush()
    pending=VisualEvidence(allocation_id=alloc.id,source_page=1,image_type="allocation_map",review_status="needs_review",status="current",is_primary=True,extraction_confidence=.9)
    session.add(pending);session.commit()
    assert build_allocation_image_status(session,[alloc.id])[alloc.id]=="needs_review"
    summary=build_allocation_visual_summaries(session,[alloc.id])[alloc.id]
    assert summary["status"]=="needs_review" and summary["primary"] is pending
    confirmed=VisualEvidence(allocation_id=alloc.id,source_page=2,image_type="allocation_map",review_status="confirmed",status="current",is_primary=False)
    session.add(confirmed);session.commit()
    summary=build_allocation_visual_summaries(session,[alloc.id])[alloc.id]
    assert summary["status"]==build_allocation_image_status(session,[alloc.id])[alloc.id]=="confirmed"
    assert summary["primary"] is confirmed and summary["others"]==[pending]
    assert pending.review_status=="needs_review" and pending.is_primary is True  # no write to paper over disagreement


def test_legacy_narrative_is_not_republished_by_dashboard(session):
    site,grant=site_and_grant(session)
    site.status_summary="Complete and available; seller must sell now."
    site.status_summary_updated_at=dt.datetime.now(dt.timezone.utc);session.commit()
    item=next(i for i in build_ai_summary_carousel_items(session) if i["id"]==f"carousel-site-{site.id}")
    assert site.status_summary not in item["excerpt"]
    assert "unverified" in item["excerpt"]


def test_conflicting_approved_counts_do_not_fall_back_to_active_proposal(session):
    from app.db.models import SchemeIntelligence
    from app.reporting.scheme_reconciliation import build_operative_planning_facts, resolve_operative_filter_facts, FACT_CONFLICT
    from app.policy.buyer_matching import build_planning_delivery_matching_facts_from_operative
    site,grant=site_and_grant(session)
    second=Application(council_code="testcouncil",site_id=site.id,reference="SYN/CONFLICT",proposal="Erection of 80 dwellings",decision="Granted",decision_issued_date=grant.decision_issued_date)
    active=Application(council_code="testcouncil",site_id=site.id,reference="SYN/ACTIVE",proposal="Erection of 30 dwellings",application_received=dt.date.today().isoformat())
    session.add_all([second,active]);session.flush()
    for app,total in ((grant,40),(second,80),(active,30)):
        app.scheme_intelligence=SchemeIntelligence(application_id=app.id,total_units_final=total,core_intelligence_complete=True)
    session.commit()
    for apps in ([grant,second,active],[active,second,grant]):
        facts=build_operative_planning_facts(apps)
        assert facts.consented_position.approved_units.state == FACT_CONFLICT
        filters=resolve_operative_filter_facts(facts)
        matching=build_planning_delivery_matching_facts_from_operative(facts,apps)
        assert filters.units is None and filters.active_units==30
        assert matching.unit_count is None
        assert not numeric_unit_mask(pd.Series([filters.units]),maximum=50).iloc[0]


@pytest.mark.parametrize("extracted", [False, True])
def test_conflicting_phase_counts_are_order_independent_unknown(session,extracted):
    from app.db.models import SchemeIntelligence
    from app.pipeline.phase_tracking import _phase_unit_count
    site,grant=site_and_grant(session,phase=True)
    second=Application(council_code="testcouncil",site_id=site.id,reference="SYN/PHASE-CONFLICT",proposal="Erection of 80 dwellings in Phase 1",decision="Granted",decision_issued_date=grant.decision_issued_date)
    session.add(second);session.flush()
    if extracted:
        for app,total in ((grant,40),(second,80)):
            app.scheme_intelligence=SchemeIntelligence(application_id=app.id,total_units_final=total,core_intelligence_complete=True)
    session.commit()
    for apps in ([grant,second],[second,grant]):
        assert _phase_unit_count(apps)["unit_count"] is None


@pytest.mark.parametrize("value", [None,"malformed",-2,1.5,float("inf"),True])
def test_buyer_numeric_requirement_rejects_invalid_total_as_unknown(value):
    from app.policy.buyer_matching import MatchingFacts, assess_buyer_fit, INSUFFICIENT_EVIDENCE, PERMISSION_GRANTED
    from app.policy.buyer_profiles import NESTEN_HOMES
    facts=MatchingFacts(opportunity_type=PLANNING_DELIVERY,unit_count=value,development_type_raw="houses",is_specialist_development=False,
        affordable_percentage=25,affordable_percentage_trusted=True,affordable_unit_count=20,planning_state=PERMISSION_GRANTED,
        has_identified_planning_activity=True,has_phasing_evidence=False,matched_to_site=True)
    result=assess_buyer_fit(NESTEN_HOMES,facts)
    assert result.classification==INSUFFICIENT_EVIDENCE
    assert any("No trusted unit count" in reason for reason in result.unknown)


def test_report_and_prompt_preserve_unknowns_and_assumed_dates():
    from app.reporting.pdf_report import compute_aggregate_stats, build_narrative_prompt, render_pdf
    row={"Address":"Synthetic", "Total Units":None,"Affordable Units":None,"decision_status":"granted","lapse_status":"approaching","Council":"testcouncil","Developer":None}
    stats=compute_aggregate_stats(pd.DataFrame([row]))
    assert stats.total_units is None and stats.unknown_total_schemes==1
    prompt=build_narrative_prompt(stats,None)
    assert "Sum of known unit counts: unknown" in prompt
    assert "not an evidenced statutory deadline" in prompt
    assert "landowner may need to sell" not in prompt
    pdf=render_pdf([row],stats,{"executive_summary":"Synthetic offline report.","buying_opportunities_and_risks":"Conditions and availability unverified."})
    import io
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf)) as document:
        text=" ".join(" ".join(page.extract_text().split()) for page in document.pages)
    assert "Known units" in text and "Unknown" in text
    assert "legal lapse and availability unverified" in text


def test_phase_unknown_count_does_not_inherit_whole_site_in_feed(session):
    from app.reporting.opportunity_feed import _attach_planning_delivery_matching_facts
    from app.db.models import SchemeIntelligence
    site,grant=site_and_grant(session)
    grant.scheme_intelligence=SchemeIntelligence(application_id=grant.id,total_units_final=80,core_intelligence_complete=True)
    session.commit()
    card={"params":{"site_id":str(site.id)},"phase_code":"1","application_reference":grant.reference,"phase_unit_count":None}
    _attach_planning_delivery_matching_facts(session,[card])
    assert card["matching_facts"].unit_count is None


# --- Gate 5B: evidence-aware completion filtering -------------------------
# Only verified completion may be hidden; unknown physical status is never read as
# incomplete, uncommenced or available, and always stays visible.

import ast
from pathlib import Path

from app.search import query_parser
from app.search.query_parser import (
    COMPLETION_EXCLUSION_NOTICE, COMPLETION_FILTER_CAPTION, COMPLETION_FILTER_LABEL,
    filters_from_result, verified_completion_exclusion_mask,
)

_EXPLORE = Path(__file__).resolve().parents[1] / "app" / "ui" / "pages" / "0_Explore.py"


def _explore_calls(attr):
    tree = ast.parse(_EXPLORE.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "st" and n.func.attr == attr]


def test_gate5b_a_checkbox_uses_evidence_aware_completion_wording():
    assert COMPLETION_FILTER_LABEL == "Hide sites with verified completion evidence"
    source = _EXPLORE.read_text(encoding="utf-8")
    assert "Hide completed sites" not in source
    checkbox_labels = [c.args[0].id for c in _explore_calls("checkbox") if c.args and isinstance(c.args[0], ast.Name)]
    assert "COMPLETION_FILTER_LABEL" in checkbox_labels
    captions = [c.args[0].id for c in _explore_calls("caption") if c.args and isinstance(c.args[0], ast.Name)]
    assert "COMPLETION_FILTER_CAPTION" in captions


@pytest.mark.parametrize("state", ["unknown", None, "no_completions_yet", "underway", "partially_complete", ""])
def test_gate5b_b_exclude_completed_keeps_every_non_verified_completion_row(state):
    assert verified_completion_exclusion_mask(pd.Series([state])).tolist() == [True]


def test_gate5b_c_explicitly_complete_row_is_removed_under_existing_contract():
    frame = pd.DataFrame({"build_status": ["complete", "unknown", None, "complete"], "site": [1, 2, 3, 4]})
    kept = frame[verified_completion_exclusion_mask(frame["build_status"])]
    assert kept["site"].tolist() == [2, 3]


def test_gate5b_c_all_unknown_universe_is_left_intact():
    frame = pd.DataFrame({"build_status": ["unknown"] * 5})
    assert verified_completion_exclusion_mask(frame["build_status"]).all()


def test_gate5b_d_natural_language_intent_still_maps_to_exclude_completed():
    assert filters_from_result({"exclude_completed": True}).exclude_completed is True
    assert filters_from_result({}).exclude_completed is False
    prompt_source = Path(query_parser.__file__).read_text(encoding="utf-8")
    assert "\"haven't been completed\" -> exclude_completed = true" in prompt_source


def test_gate5b_e_natural_language_exclusion_shows_evidence_notice():
    tree = ast.parse(_EXPLORE.read_text(encoding="utf-8"))
    branches = [n for n in ast.walk(tree) if isinstance(n, ast.If) and isinstance(n.test, ast.Attribute)
                and n.test.attr == "exclude_completed" and isinstance(n.test.value, ast.Name) and n.test.value.id == "nl_filters"]
    assert len(branches) == 1
    body_calls = [n for stmt in branches[0].body for n in ast.walk(stmt) if isinstance(n, ast.Call)]
    assert any(isinstance(c.func, ast.Attribute) and c.func.attr == "info" and c.args
               and isinstance(c.args[0], ast.Name) and c.args[0].id == "COMPLETION_EXCLUSION_NOTICE" for c in body_calls)
    assert any(isinstance(c.func, ast.Name) and c.func.id == "verified_completion_exclusion_mask" for c in body_calls)
    assert "unknown physical status remain included" in COMPLETION_EXCLUSION_NOTICE


@pytest.mark.parametrize("text", [COMPLETION_FILTER_LABEL, COMPLETION_FILTER_CAPTION, COMPLETION_EXCLUSION_NOTICE])
def test_gate5b_f_wording_never_equates_unknown_with_incomplete(text):
    lowered = text.lower()
    assert "verified completion evidence" in lowered
    for claim in ("are incomplete", "not completed", "not complete", "uncommenced", "not started",
                  "available", "completion is not verified for any site"):
        assert claim not in lowered
    assert "incomplete" not in lowered or "does not prove" in lowered


def test_gate5b_g_unknown_physical_status_never_matches_or_hard_mismatches():
    from dataclasses import replace
    from app.policy.buyer_matching import B2MatchingContext, assess_buyer_fit
    from app.policy.buyer_profiles import (
        NESTEN_HOMES, STRATEGIC_LAND_BUYER, UNCOMMENCED_PREFERRED, UNDERWAY_ACCEPTABLE, UNDERWAY_PREFERRED,
    )
    from tests.test_buyer_mandate_v2_phase_b2 import _facts
    for base in (NESTEN_HOMES, STRATEGIC_LAND_BUYER):
        for appetite in (UNCOMMENCED_PREFERRED, UNDERWAY_ACCEPTABLE, UNDERWAY_PREFERRED):
            policy = replace(base, development_state_appetite=appetite)
            for state in ("unknown", None):
                result = assess_buyer_fit(policy, _facts(), context=B2MatchingContext(development_state=state,
                                                                                      development_state_scope_verified=True))
                assert not any("underway or further" in m for m in result.does_not_match + result.matches)
                assert not any("preference is not met" in u for u in result.unknown)
