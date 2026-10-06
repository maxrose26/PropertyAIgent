"""Stage 2.5B G3b Slice 2 (spec 025): the REAL Streamlit renderer for buyer-dashboard families, under AppTest.

Runs in the UI offline job (verification/stage2_ui_offline_pytest.py permits asyncio's local socketpair); the presenter/view-model tests live in
tests/test_family_dashboard.py (offline Stage 2 job). Product assertions: phase headline, honest scale, phasing context only where qualified, overlap
warning, collapsed related subjects, and none of the forbidden claims (totals, remaining, availability, subdivision, relationships).
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

import app.reporting.family_presentation as fp
from app.db.models import Application
from app.reporting.opportunity_families import OVERLAP_WARNING
from tests.test_buyer_family_feed import BUYER, LAPSE_AGE, World, portal

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


def test_a_large_parent_with_a_strong_phase_renders_phase_headline_phasing_overlap_and_collapsed_related(world):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S", units_out=500, units_rm=140)
    family = view_of(world).families[0]
    text, at = render(family)
    assert "Phased delivery evidenced." in text and OVERLAP_WARNING in text and "Strong fit" in text and "140" in text
    assert len(at.expander) == 1 and at.expander[0].label.startswith("Related acquisition subjects (")
    assert not at.expander[0].proto.expanded                     # collapsed by default
    assert "640" not in text and "360" not in text               # no family total, no residual
    assert text.count("Best acquisition subject for this buyer") == 1
    assert_no_forbidden(text)


def test_b_parent_not_suitable_with_a_possible_phase_renders_cleanly(world):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="N", phase="P", units_out=500, units_rm=140)
    text, _ = render(view_of(world).families[0])
    assert "Possible fit" in text and "Phased delivery evidenced." in text
    assert_no_forbidden(text)


def test_d_phase_only_family_renders_no_whole_site_subject(world):
    s = world.site(rm_age=300, rm_phase="Phase 1", phase="S", units_rm=60)
    world.session.add(Application(council_code="testcouncil", reference=f"RM2/{s.id}", site_id=s.id, decision="Granted",
                                  decision_issued_date=portal(310), application_received=portal(400), estimated_unit_count=70,
                                  proposal=f"Reserved matters for Phase 2 of 70 dwellings pursuant to outline permission OUT/{s.id}"))
    world.session.commit()
    text, _ = render(view_of(world).families[0])
    assert "whole site" not in text.lower() and "unphased" not in text.lower() and "Phased delivery evidenced." in text
    assert_no_forbidden(text)


def test_single_subject_large_site_is_compact_with_no_phasing_overlap_or_expander(world):
    world.site(outline_age=LAPSE_AGE, parent="I", units_out=500)
    text, at = render(view_of(world).families[0])
    assert "Phased delivery evidenced" not in text and OVERLAP_WARNING not in text and len(at.expander) == 0
    assert "Insufficient evidence" in text
    assert_no_forbidden(text)


def test_strategic_family_renders_its_strategic_information_and_is_never_phased(world):
    world.site(outline_age=1000)
    world.allocation(capacity=8400, fit="S", name="Wharfside")
    family = next(f for f in view_of(world).families if f.is_strategic)
    text, at = render(family)
    assert "Wharfside" in text and "Phased delivery evidenced" not in text and len(at.expander) == 0
    assert_no_forbidden(text)

