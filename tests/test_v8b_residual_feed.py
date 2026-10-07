"""Stage 2.5B V8-B: the residual ladder through the REAL family feed (real Application/Site rows, the real detectors, real G2 containment; the buyer-fit evaluator is the
deterministic fake used by the family-feed tests). Production evidence => R2 at best (R1 dormant by evidence); a synthetic qualified provider => an R1 derived subject."""
from __future__ import annotations

import pytest

import app.reporting.buyer_family_feed as bff
import app.reporting.opportunity_families as fam
import app.reporting.residual_opportunity as ro
from tests.test_buyer_family_feed import LAPSE_AGE, World, family_of

BUYER = "housing_association"


@pytest.fixture
def world(session, monkeypatch):
    return World(session, monkeypatch)


def _build(world, **kw):
    return bff.build_buyer_opportunity_families(world.session, BUYER, 6, **kw)


def _site(world, **kw):
    from app.db.models import Application, SchemeIntelligence
    site = world.site(outline_age=LAPSE_AGE, rm_age=LAPSE_AGE, units_out=500, units_rm=300, parent="I", phase="I", **kw)
    for application in world.session.query(Application).filter(Application.site_id == site.id):      # EXACT extracted totals (a portal estimate alone is only APPROXIMATE)
        world.session.add(SchemeIntelligence(application_id=application.id, total_units_final=500 if application.reference.startswith("OUT") else 300, core_intelligence_complete=True))
    world.session.commit()
    return site


def _qualified_provider(site_ids=None):
    def provider(site_id, parent, children):
        if site_ids is not None and site_id not in site_ids:
            return None
        return ro.ResidualEvidence(non_overlap=tuple((a.subject_id, b.subject_id, "synthetic S106 plan: distinct") for i, a in enumerate(children) for b in children[i + 1:]),
                                   child_set=((parent.subject_id, tuple(sorted(c.subject_id for c in children)), "synthetic decision notice: phases named in full"),))
    return provider


def test_production_feed_yields_r2_context_at_best_and_never_a_residual_subject(world):
    site = _site(world)
    inputs = bff.load_buyer_family_inputs(world.session)
    q = inputs.residuals[site.id]
    assert q.level == ro.LEVEL_R2 and q.residual_value is None and q.subject_id is None            # containment from the real RM citation; completeness / non-overlap unknown
    assert q.predicate(ro.CHILD_RELATIONSHIP_QUALIFIED).state == ro.TRUE and q.predicate(ro.CHILD_SET_COMPLETE).state == ro.UNKNOWN
    result = bff.evaluate_buyer_families(world.session, BUYER, inputs, 6)
    family = family_of(result, site)
    assert all(m.slot != fam.SLOT_RESIDUAL for m in family.members)
    assert result["counts"]["derived_subjects_r1"] == 0 and result["counts"]["investigation_contexts_r2"] == 1
    assert any((m.source or {}).get("potential_residual") == ro.PLANNING_R2_TEXT for m in family.members)


def test_r2_context_changes_no_family_fit_membership_or_representative(world):
    site = _site(world)
    with_context = bff.evaluate_buyer_families(world.session, BUYER, bff.load_buyer_family_inputs(world.session), 6)
    no_residuals = bff.FamilyInputs(*(getattr(bff.load_buyer_family_inputs(world.session), f) for f in ("strategic", "lapse_raw", "undeveloped_raw", "recent_permission_raw",
                                                                                                        "long_pending_raw", "delivery")))
    without = bff.evaluate_buyer_families(world.session, BUYER, no_residuals, 6)
    a, b = family_of(with_context, site), family_of(without, site)
    assert (a.fit, a.investigative, a.representative.subject_key) == (b.fit, b.investigative, b.representative.subject_key)
    assert [m.subject_key for m in a.members] == [m.subject_key for m in b.members]


def test_a_synthetic_qualified_provider_activates_r1_through_the_defined_interface(world):
    site = _site(world)
    result = _build(world, residual_evidence_provider=_qualified_provider())
    family = family_of(result, site)
    residual = [m for m in family.members if m.slot == fam.SLOT_RESIDUAL]
    assert len(residual) == 1 and result["counts"]["derived_subjects_r1"] == 1
    card = residual[0].source
    assert card["residual"].residual_value == 200 and card["count_assessment"].exact_value == 200 and card["residual_subject_id"].startswith(f"planning_delivery:residual:{site.id}:")
    assert residual[0].fit != fam.STRONG_FIT                                                       # capped at POSSIBLE_FIT
    from app.reporting.opportunity_route import RESIDUAL_OPPORTUNITY, derive_opportunity_route
    assert derive_opportunity_route(card).route == RESIDUAL_OPPORTUNITY
    from app.reporting.family_presentation import present_family_result
    view = present_family_result(result, {site.id: world.session.get(__import__("app.db.models", fromlist=["Site"]).Site, site.id)})
    labels = [view.families[0].best.label] + [r.label for r in view.families[0].related]
    assert "Derived residual capacity" in labels
    assert result["route_counts"][RESIDUAL_OPPORTUNITY] in (0, 1)


def test_r1_does_not_alter_the_other_subjects_of_the_family_and_is_stable_across_builds(world):
    site = _site(world)
    base = family_of(_build(world), site)
    first = family_of(_build(world, residual_evidence_provider=_qualified_provider()), site)
    second = family_of(_build(world, residual_evidence_provider=_qualified_provider()), site)
    others = lambda f: sorted((m.subject_key, m.fit, m.investigative) for m in f.members if m.slot != fam.SLOT_RESIDUAL)   # noqa: E731
    assert others(first) == others(base)
    ids = lambda f: [m.subject_key for m in f.members if m.slot == fam.SLOT_RESIDUAL]                                       # noqa: E731
    assert ids(first) == ids(second) and len(ids(first)) == 1


def test_provider_evidence_for_another_site_does_not_activate_r1_here(world):
    site = _site(world)
    result = _build(world, residual_evidence_provider=_qualified_provider(site_ids={site.id + 999}))
    assert result["counts"]["derived_subjects_r1"] == 0
