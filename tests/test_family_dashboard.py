"""Stage 2.5B G3b Slice 2 (spec 025): buyer-dashboard FAMILY presentation.

Real rows + the real family builder (fit driven by the deterministic fake table from tests/test_buyer_family_feed.py), then the presenter
(app.reporting.family_presentation) and the real Streamlit renderer (app.ui.shell.opportunity_family_card) under AppTest. Presentation only: these tests also
pin that nothing about buyer-fit policy, ranking, relationships, totals or availability is introduced.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import app.reporting.buyer_family_feed as bff
import app.reporting.family_presentation as fp
from app.db.models import Application
from app.policy.buyer_matching import BUYER_MATCHING_POLICY_VERSION, NOT_SUITABLE
from app.reporting.opportunity_families import OVERLAP_WARNING
from tests.test_buyer_family_feed import BUYER, LAPSE_AGE, World, portal

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORBIDDEN = ("remaining", "available", "subdivi", "other phases", "sold in phases", "contained in", "pursuant to", "total of")


@pytest.fixture
def world(session, monkeypatch):
    return World(session, monkeypatch)


def view_of(world, limit=6):
    return fp.build_buyer_family_dashboard_view(world.session, BUYER, limit)


def render(family_view):
    """The real renderer under AppTest; returns (all visible text, the AppTest)."""
    def script():
        import streamlit as st
        from app.ui.shell import opportunity_family_card
        # st.page_link needs a multipage app context; the full dashboard (and its links) is covered by the journey test.
        original = st.page_link
        st.page_link = lambda page, label=None, **kw: st.caption(f"[link] {page} {kw.get('query_params')}")
        try:
            opportunity_family_card(st.session_state["view"], key="test")
        finally:
            st.page_link = original   # never leak the stub into other tests (the journey test needs the real page_link)
    at = AppTest.from_function(script)
    at.session_state["view"] = family_view
    at.run(timeout=30)
    assert not at.exception, [(e.message, e.stack_trace) for e in at.exception]
    text = "\n".join(str(e.value) for kind in ("markdown", "caption", "info", "subheader", "write") for e in at.get(kind))
    text += "\n" + "\n".join(str(e.proto) for e in at.get("badge")) + "\n" + "\n".join(e.label for e in at.expander)
    return text, at


def assert_no_forbidden(text):
    lowered = text.lower()
    assert not [w for w in FORBIDDEN if w in lowered], text


# --- A-C. large parent + buyer-sized phase ----------------------------------------------------------------------------------------------

def test_a_large_parent_insufficient_with_a_strong_phase_is_one_family_headed_by_the_phase(world):
    s = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S", units_out=500, units_rm=140)
    view = view_of(world)
    assert view.error is None and len(view.families) == 1
    family = view.families[0]
    assert family.title == f"Site {s.id}" and family.best.fit_label == "Strong fit" and "140" in (family.best.scale or "")
    assert family.best.label.startswith("Phase") or "2" in family.best.label
    assert "Permission approaching its assumed review date" in [r.label for r in family.related]
    assert family.phasing_context == fp.PHASING_CONTEXT and family.overlap_warning == OVERLAP_WARNING
    assert family.relationship_note == fp.RELATIONSHIP_NOTE
    text, at = render(family)
    assert "Phased delivery evidenced." in text and OVERLAP_WARNING in text and "Strong fit" in text and "140" in text
    assert len(at.expander) == 1 and at.expander[0].label.startswith("Related acquisition subjects (")
    assert "640" not in text and "360" not in text            # no family total, no residual
    assert_no_forbidden(text)


def test_b_parent_not_suitable_with_a_possible_phase_remains_visible_headed_by_the_phase(world):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="N", phase="P", units_out=500, units_rm=140)
    view = view_of(world)
    assert len(view.families) == 1
    family = view.families[0]
    assert family.best.fit_label == "Possible fit" and family.phasing_context == fp.PHASING_CONTEXT
    assert "Not suitable" in [r.fit_label for r in family.related]
    assert_no_forbidden(render(family)[0])


def test_c_parent_strong_and_phase_strong_one_family_one_headline_other_shown_as_also_strong(world):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="S", units_out=120, units_rm=100)
    view = view_of(world)
    assert len(view.families) == 1
    family = view.families[0]
    assert family.best.fit_label == "Strong fit" and any(r.fit_label == "Strong fit" for r in family.related)
    assert family.phasing_context == fp.PHASING_CONTEXT
    text, _ = render(family)
    assert text.count("Best acquisition subject for this buyer") == 1


# --- D. phase-only family ------------------------------------------------------------------------------------------------------------

def test_d_phase_only_family_with_two_phases_has_no_fabricated_whole_site_subject(world):
    s = world.site(rm_age=300, rm_phase="Phase 1", phase="S", units_rm=60)
    world.session.add(Application(council_code="testcouncil", reference=f"RM2/{s.id}", site_id=s.id, decision="Granted",
                                  decision_issued_date=portal(310), application_received=portal(400), estimated_unit_count=70,
                                  proposal=f"Reserved matters for Phase 2 of 70 dwellings pursuant to outline permission OUT/{s.id}"))
    world.session.commit()
    view = view_of(world)
    assert len(view.families) == 1
    family = view.families[0]
    labels = [family.best.label] + [r.label for r in family.related]
    assert len(labels) == 2 and all(label.startswith("Phase") for label in labels)
    assert family.phasing_context == fp.PHASING_CONTEXT
    text, _ = render(family)
    assert "whole site" not in text.lower() and "unphased" not in text.lower()
    assert_no_forbidden(text)


# --- negative / compact cases ---------------------------------------------------------------------------------------------------------

def test_large_site_with_no_phasing_evidence_is_a_compact_single_subject_family_with_no_phasing_claim(world):
    world.site(outline_age=LAPSE_AGE, parent="I", units_out=500)
    view = view_of(world)
    family = view.families[0]
    assert not family.related and family.phasing_context is None and family.overlap_warning is None and family.relationship_note is None
    assert family.best.fit_label == "Insufficient evidence"                      # the existing v6 result, unchanged
    text, at = render(family)
    assert "Phased delivery evidenced" not in text and OVERLAP_WARNING not in text and len(at.expander) == 0
    assert_no_forbidden(text)


def test_single_phase_subject_family_shows_no_phasing_label(world):
    world.site(rm_age=300, rm_phase="Phase 1", phase="S", units_rm=80)
    family = view_of(world).families[0]
    assert len(family.related) == 0 and family.phasing_context is None


def test_unphased_bucket_alone_is_never_evidence_of_phasing(world):
    from app.pipeline.phase_tracking import UNPHASED_LABEL
    from app.reporting.opportunity_families import FamilySubject, OpportunityFamily, RelatedSubject, SLOT_LIFECYCLE, SLOT_PHASE, ID_SYSTEM_FEED
    from app.reporting.residential_count import CountAssessment

    def subject(key, slot, code, scope_type):
        card = {"phase_code": code, "count_assessment": CountAssessment(scope_type=scope_type, scope_label="x")}
        return FamilySubject(domain="planning_delivery", anchor_id=1, subject_key=key, slot=slot, fit="INSUFFICIENT_EVIDENCE", source=card, id_system=ID_SYSTEM_FEED)
    lifecycle, unphased = subject("opp-lapse-1", SLOT_LIFECYCLE, None, "whole_site"), subject(f"opp-phase-1-{UNPHASED_LABEL}", SLOT_PHASE, UNPHASED_LABEL, "whole_site")
    assert fp.phasing_evidenced(OpportunityFamily(("planning_delivery", 1), lifecycle, (RelatedSubject(unphased, "INSUFFICIENT"),))) is False
    real_phase = subject("opp-phase-1-2", SLOT_PHASE, "2", "phase")
    assert fp.phasing_evidenced(OpportunityFamily(("planning_delivery", 1), real_phase, (RelatedSubject(lifecycle, "INSUFFICIENT"),))) is True
    assert fp.phasing_evidenced(OpportunityFamily(("planning_delivery", 1), real_phase, ())) is False     # a single subject never shows the label


# --- strategic ------------------------------------------------------------------------------------------------------------------------

def test_strategic_family_keeps_its_strategic_information_and_is_never_labelled_phased(world):
    site = world.site(outline_age=1000)
    a = world.allocation(capacity=8400, fit="S", name="Wharfside")
    family = next(f for f in view_of(world).families if f.is_strategic)
    assert family.title == "Wharfside" and family.best.signal_label and family.best.metrics and family.phasing_context is None
    assert family.overlap_warning is None and not family.related and a.id and site.id
    text, at = render(family)
    assert "Wharfside" in text and "Phased delivery evidenced" not in text and len(at.expander) == 0
    assert_no_forbidden(text)


# --- terminal exclusion + counts --------------------------------------------------------------------------------------------------------

def test_terminal_exclusion_and_family_count_semantics(world):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="N", phase="N")      # every subject NOT_SUITABLE: excluded
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="N", phase="I")      # one non-NOT_SUITABLE: stays
    view = view_of(world)
    assert len(view.families) == 1 and view.families[0].best.fit_label == "Insufficient evidence"
    assert "1 of 2 development families shown" in view.caption and "1 excluded as not suitable for this buyer" in view.caption
    assert "acquisition subjects considered" in view.caption and view.subject_caption.startswith("Subject counts (not opportunities):")
    assert NOT_SUITABLE and "more not shown" not in view.caption


def test_more_families_not_shown_is_reported(world):
    for _ in range(3):
        world.site(outline_age=LAPSE_AGE, parent="S")
    view = fp.build_buyer_family_dashboard_view(world.session, BUYER, 2)
    assert len(view.families) == 2 and "2 of 3 development families shown" in view.caption and "1 more not shown" in view.caption


# --- fit language / no policy change ------------------------------------------------------------------------------------------------------

def test_fit_labels_use_the_existing_language_and_no_policy_is_changed():
    assert fp.fit_label("STRONG_FIT", False) == "Strong fit" and fp.fit_label("POSSIBLE_FIT", False) == "Possible fit"
    assert fp.fit_label("INSUFFICIENT_EVIDENCE", True) == "Investigate" and fp.fit_label("INSUFFICIENT_EVIDENCE", False) == "Insufficient evidence"
    assert fp.fit_label("NOT_SUITABLE", False) == "Not suitable"
    assert BUYER_MATCHING_POLICY_VERSION == 6


def test_presenter_does_not_import_policy_g2_or_do_arithmetic_on_units():
    tree = ast.parse(inspect.getsource(fp))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and ("subject_relationships" in m or "buyer_matching" in m) for m in imported)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult)) and "unit" in ast.dump(n).lower()]


# --- fail closed UI state ---------------------------------------------------------------------------------------------------------------

def test_construction_failure_shows_an_operator_safe_error_and_never_the_legacy_cards(world, monkeypatch, caplog):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE)
    import app.reporting.opportunity_feed as legacy

    def boom(*a, **k):
        raise bff.MissingFamilySubjectMatchingFacts("opp-lapse-9", "planning_delivery")
    monkeypatch.setattr(bff, "build_buyer_opportunity_families", boom)
    monkeypatch.setattr(legacy, "build_opportunity_feed", lambda *a, **k: pytest.fail("legacy feed must never be used as a fallback"))
    view = view_of(world)
    assert view.error == fp.FAMILY_ERROR_MESSAGE and view.families == () and view.caption == ""
    assert "opp-" not in view.error and "Traceback" not in view.error and "matching facts" not in view.error
    assert any("failed closed" in r.message for r in caplog.records)           # the detail is logged server-side only


def test_access_refusals_are_not_swallowed(world, monkeypatch):
    from app.security.access import AccessDenied
    monkeypatch.setattr(bff, "build_buyer_opportunity_families", lambda *a, **k: (_ for _ in ()).throw(AccessDenied("Access denied.")))
    with pytest.raises(AccessDenied):
        view_of(world)


# --- dashboard wiring + generic preservation -------------------------------------------------------------------------------------------

def test_dashboard_buyer_branch_uses_families_and_the_generic_branch_is_the_original_feed():
    source = (ROOT / "app/ui/pages/00_Dashboard.py").read_text(encoding="utf-8")
    assert "build_buyer_family_dashboard_view(session, buyer_key)" in source and "opportunity_family_card(family" in source
    assert "build_opportunity_feed(session, buyer_key=None)" in source and "buyer_key=buyer_key" not in source
    assert "excluded_not_suitable" not in source                                  # the card-count caption is gone from the buyer path


def test_generic_feed_is_unchanged_by_slice_2(session, monkeypatch):
    world = World(session, monkeypatch)
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="S")
    from app.reporting.opportunity_feed import build_opportunity_feed
    generic = build_opportunity_feed(session, limit=6)
    assert set(generic) == {"cards", "counts", "buyer_key"} and generic["buyer_key"] is None and all("buyer_fit" not in c for c in generic["cards"])
