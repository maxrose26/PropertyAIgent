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

import app.reporting.buyer_family_feed as bff
import app.reporting.family_presentation as fp
from app.db.models import Application
from app.policy.buyer_matching import BUYER_MATCHING_POLICY_VERSION, NOT_SUITABLE
from app.reporting.opportunity_families import OVERLAP_WARNING
from tests.test_buyer_family_feed import BUYER, LAPSE_AGE, World, portal

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def world(session, monkeypatch):
    return World(session, monkeypatch)


def view_of(world, limit=6):
    return fp.build_buyer_family_dashboard_view(world.session, BUYER, limit)


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


def test_b_parent_not_suitable_with_a_possible_phase_remains_visible_headed_by_the_phase(world):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="N", phase="P", units_out=500, units_rm=140)
    view = view_of(world)
    assert len(view.families) == 1
    family = view.families[0]
    assert family.best.fit_label == "Possible fit" and family.phasing_context == fp.PHASING_CONTEXT
    assert "Not suitable" in [r.fit_label for r in family.related]


def test_c_parent_strong_and_phase_strong_one_family_one_headline_other_shown_as_also_strong(world):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="S", phase="S", units_out=120, units_rm=100)
    view = view_of(world)
    assert len(view.families) == 1
    family = view.families[0]
    assert family.best.fit_label == "Strong fit" and any(r.fit_label == "Strong fit" for r in family.related)
    assert family.phasing_context == fp.PHASING_CONTEXT


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
    assert not any("whole" in label.lower() or "unphased" in label.lower() for label in labels)


# --- negative / compact cases ---------------------------------------------------------------------------------------------------------

def test_large_site_with_no_phasing_evidence_is_a_compact_single_subject_family_with_no_phasing_claim(world):
    world.site(outline_age=LAPSE_AGE, parent="I", units_out=500)
    view = view_of(world)
    family = view.families[0]
    assert not family.related and family.phasing_context is None and family.overlap_warning is None and family.relationship_note is None
    assert family.best.fit_label == "Insufficient evidence"                      # the existing v6 result, unchanged


def test_one_genuine_phase_subject_alone_shows_the_phasing_label_without_fabricating_a_parent(world):
    world.site(rm_age=300, rm_phase="Phase 1", phase="S", units_rm=80)
    family = view_of(world).families[0]
    assert family.phasing_context == fp.PHASING_CONTEXT                      # one genuine phase is sufficient on its own
    assert len(family.related) == 0 and family.overlap_warning is None       # no synthetic parent / second subject, no overlap note
    assert family.best.label.startswith("Phase") and "wider" not in family.best.label.lower()


def test_wider_permission_label_has_no_unphased_wording_and_lifecycle_only_has_no_label(world):
    world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S")
    family = view_of(world).families[0]
    labels = [family.best.label] + [r.label for r in family.related]
    assert "Wider permission" in labels and not any("unphased" in label.lower() for label in labels)
    assert fp.PHASING_CONTEXT not in labels
    world.site(outline_age=LAPSE_AGE, parent="I", units_out=500)                 # lifecycle/whole only: no label
    lifecycle_only = [f for f in view_of(world).families if f.best.label.startswith("Permission approaching")]
    assert lifecycle_only and all(f.phasing_context is None for f in lifecycle_only)


def test_the_label_follows_the_shared_phasing_fact_and_nothing_else():
    """V7A: the presentation consumes the ONE derived fact (attached to each card by the family feed). CURRENT only; historical-only, none, a missing fact, and every
    strategic family show no current-evidence label - whatever the cards' own phase codes or scopes look like."""
    from app.policy.buyer_matching import (
        AcquisitionPhasingEvidence, PHASING_CURRENT_EVIDENCED_PHASE, PHASING_CURRENTNESS_UNKNOWN, PHASING_DOCUMENTED, PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED,
    )
    from app.reporting.opportunity_families import FamilySubject, OpportunityFamily, RelatedSubject, SLOT_LIFECYCLE, SLOT_PHASE, ID_SYSTEM_FEED

    def subject(key, slot, state):
        card = {"phase_code": "2" if slot == SLOT_PHASE else None}
        if state is not None:
            card["acquisition_phasing"] = AcquisitionPhasingEvidence(state)
        return FamilySubject(domain="planning_delivery", anchor_id=1, subject_key=key, slot=slot, fit="INSUFFICIENT_EVIDENCE", source=card, id_system=ID_SYSTEM_FEED)

    def family(state):
        phase, lifecycle = subject("opp-phase-1-2", SLOT_PHASE, state), subject("opp-lapse-1", SLOT_LIFECYCLE, state)
        return OpportunityFamily(("planning_delivery", 1), phase, (RelatedSubject(lifecycle, "INSUFFICIENT"),))
    assert fp.phasing_evidenced(family(PHASING_CURRENT_EVIDENCED_PHASE)) is True
    assert fp.phasing_context(family(PHASING_CURRENT_EVIDENCED_PHASE)) == "Phased delivery evidenced."
    assert fp.phasing_context(family(PHASING_CURRENTNESS_UNKNOWN)) == "Phase evidence identified — current status unverified."   # the weaker label, same fact
    assert fp.phasing_evidenced(family(PHASING_CURRENTNESS_UNKNOWN)) is False                                                    # never the CURRENT label
    for not_current in (PHASING_HISTORICAL_ONLY, PHASING_NONE_IDENTIFIED, PHASING_DOCUMENTED, None):
        assert fp.phasing_evidenced(family(not_current)) is False, not_current       # historical / none / reserved documented / fact missing: no current label
        assert fp.phasing_context(family(not_current)) is None, not_current
    single = OpportunityFamily(("planning_delivery", 1), subject("opp-phase-1-2", SLOT_PHASE, PHASING_CURRENT_EVIDENCED_PHASE), ())
    assert fp.phasing_evidenced(single) is True                                          # one genuine phase subject is sufficient on its own
    lifecycle_only = OpportunityFamily(("planning_delivery", 1), subject("opp-lapse-1", SLOT_LIFECYCLE, PHASING_NONE_IDENTIFIED), ())
    assert fp.phasing_evidenced(lifecycle_only) is False
    strategic = FamilySubject(domain="strategic_land", anchor_id=1, subject_key="opp-feed-alloc-1", slot="ALLOCATION", fit="INSUFFICIENT_EVIDENCE",
                              source={"acquisition_phasing": AcquisitionPhasingEvidence(PHASING_CURRENT_EVIDENCED_PHASE)}, id_system=ID_SYSTEM_FEED)
    assert fp.phasing_evidenced(OpportunityFamily(("strategic_land", 1), strategic, ())) is False   # a strategic allocation is never labelled phased


def test_end_to_end_an_undated_phase_shows_the_weak_label_and_an_address_only_phase_shows_none(world):
    from app.db.models import Application
    undated = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S")
    world.session.query(Application).filter(Application.site_id == undated.id, Application.reference.like("RM/%")).update({"decision_issued_date": None})
    address_only = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, parent="I", phase="S")
    rm = world.session.query(Application).filter(Application.site_id == address_only.id, Application.reference.like("RM/%")).one()
    rm.proposal = "Reserved matters for 30 dwellings"
    rm.address = "Phase 2, Mill Lane, Anytown"
    world.session.commit()
    labels = {f.title: f.phasing_context for f in view_of(world, 10).families}
    assert labels[f"Site {undated.id}"] == "Phase evidence identified — current status unverified."
    assert labels.get(f"Site {address_only.id}") is None


# --- strategic ------------------------------------------------------------------------------------------------------------------------

def test_strategic_family_keeps_its_strategic_information_and_is_never_labelled_phased(world):
    site = world.site(outline_age=1000)
    a = world.allocation(capacity=8400, fit="S", name="Wharfside")
    family = next(f for f in view_of(world).families if f.is_strategic)
    assert family.title == "Wharfside" and family.best.signal_label and family.best.metrics and family.phasing_context is None
    assert family.overlap_warning is None and not family.related and a.id and site.id


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
    assert BUYER_MATCHING_POLICY_VERSION == 7


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
