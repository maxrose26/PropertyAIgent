"""Gate 2A final pre-merge hardening - tests for the two Product Owner-
identified fixes:

1. External evidence -> role linkage (prompt-only fix; the deterministic
   evidence-sufficiency ceiling itself is UNCHANGED - these tests prove the
   ceiling mechanism still behaves correctly in exactly the three scenarios
   the fix targets: correctly-linked strong evidence survives at HIGH,
   evidence found but cited via the wrong ref stays capped, and a bare name
   alone can never establish a strong role).
2. Person vs organisation eligibility hardening (classify_identity_shape's
   new three-way ORGANISATION/PERSON/UNCERTAIN semantics, evidence-first).

OpenAI is ALWAYS mocked here - no real network call is ever made by this
file (the real controlled revalidation is a separate, explicit script run
outside the test suite - see this task's own final report).
"""
from __future__ import annotations

import datetime as dt

from app.db.models import Application, Company, ControlRelationship, SchemeIntelligence, Site
from app.reporting.applicant_identity import has_individual_title_prefix, is_likely_individual_name
from app.reporting.applicant_intelligence import (
    CONFIDENCE_HIGH, CONFIDENCE_LOW, CONFIDENCE_MEDIUM,
    IDENTITY_SHAPE_ORGANISATION, IDENTITY_SHAPE_PERSON, IDENTITY_SHAPE_UNCERTAIN,
    ROLE_HOUSEBUILDER, SOURCE_OFFICIAL_COMPANY_WEBSITE,
    apply_evidence_sufficiency_ceiling, build_applicant_identity_contexts, classify_identity_shape,
    evidence_supported_confidence_ceiling, is_person_shaped_identity,
)
from app.reporting.opportunity_universe import LONG_PENDING_APPLICATION_WINDOW_MONTHS, add_calendar_months


def _make_long_pending_opportunity(session, *, address, applicant_company, ref, council="testcouncil"):
    submitted = add_calendar_months(dt.date.today(), -(LONG_PENDING_APPLICATION_WINDOW_MONTHS + 2))
    site = Site(council_code=council, canonical_address=f"{address}-canon", display_address=address)
    session.add(site)
    session.flush()
    app = Application(
        council_code=council, reference=ref, site_id=site.id, status="Under consideration",
        application_category="primary_residential", application_received=submitted.strftime("%a %d %b %Y"),
        first_seen_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(app)
    session.flush()
    if applicant_company:
        session.add(SchemeIntelligence(application_id=app.id, applicant_company=applicant_company))
    session.commit()
    return site, app


# --- Fix 1: external evidence -> role linkage (ceiling mechanism proofs) ----

def test_official_evidence_found_and_correctly_linked_survives_at_high():
    """The fix's own success criterion: when the model DOES link its role
    to the matching evidence:<index>, HIGH is preserved."""
    evidence = [{
        "source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "Example Homes - Official Site",
        "url": "https://example-homes.co.uk", "publisher": "Example Homes Ltd",
        "claim": "Example Homes Ltd builds and sells residential homes across the North West.",
        "accessed_date": "2026-09-08",
    }]
    structured = {
        "roles": [{"role": ROLE_HOUSEBUILDER, "confidence": CONFIDENCE_HIGH, "evidence_refs": ["evidence:0"]}],
        "is_spv": "UNKNOWN", "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": evidence,
    }
    adjusted, notes = apply_evidence_sufficiency_ceiling(structured)
    assert adjusted["roles"][0]["confidence"] == CONFIDENCE_HIGH
    assert notes == []


def test_official_evidence_found_but_not_linked_stays_capped():
    """The exact failure mode the amendment brief itself reported (Bloor
    Homes/Onward Homes/Hollins Strategic Land): strong evidence genuinely
    EXISTS in the evidence array, but the role cites only an internal
    raw_name ref instead of evidence:0 - the ceiling correctly cannot
    'read the model's mind' and stays capped at LOW. This is the exact,
    intentionally-unchanged behaviour the prompt fix (Rule 11) targets -
    proving the ceiling logic itself was never the bug."""
    evidence = [{
        "source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "Example Homes - Official Site",
        "url": "https://example-homes.co.uk", "publisher": "Example Homes Ltd",
        "claim": "Example Homes Ltd builds and sells residential homes across the North West.",
        "accessed_date": "2026-09-08",
    }]
    structured = {
        "roles": [{"role": ROLE_HOUSEBUILDER, "confidence": CONFIDENCE_HIGH, "evidence_refs": ["raw_name:Example Homes Ltd"]}],
        "is_spv": "UNKNOWN", "parent_group": None, "summary": "x", "unresolved_questions": [], "evidence": evidence,
    }
    adjusted, notes = apply_evidence_sufficiency_ceiling(structured)
    assert adjusted["roles"][0]["confidence"] == CONFIDENCE_LOW
    assert len(notes) == 1


def test_raw_name_alone_can_never_establish_a_strong_role():
    ceiling = evidence_supported_confidence_ceiling(["raw_name:Example Homes Ltd"], [])
    assert ceiling == CONFIDENCE_LOW


def test_mixed_internal_and_correctly_linked_external_ref_reaches_high():
    """Rule 11's own explicit allowance: a role may cite BOTH an internal
    ref (context) and an evidence:<index> ref (role support) together -
    the presence of the STRONG evidence:0 ref alone is enough to reach
    HIGH, regardless of the co-cited internal ref."""
    evidence = [{
        "source_type": SOURCE_OFFICIAL_COMPANY_WEBSITE, "title": "x", "url": "https://example.com",
        "publisher": "x", "claim": "x", "accessed_date": "",
    }]
    ceiling = evidence_supported_confidence_ceiling(["raw_name:Example Homes Ltd", "evidence:0"], evidence)
    assert ceiling == CONFIDENCE_HIGH


# --- Fix 2: person vs organisation eligibility hardening --------------------

def test_title_prefixed_name_is_confidently_person(session):
    site, app = _make_long_pending_opportunity(session, address="Jackson Site", applicant_company=None, ref="REF-JACKSON")
    app.applicant_name_raw = "Ms Annie Jackson"
    session.commit()
    contexts = build_applicant_identity_contexts(session)
    # A bare title-prefixed individual is filtered out by clean_organisation_name
    # before it ever becomes an identity at all - confirm it produces none.
    assert all(c.display_name != "Ms Annie Jackson" for c in contexts.values())
    assert has_individual_title_prefix("Ms Annie Jackson") is True


def test_bare_name_with_no_structural_evidence_is_confidently_person(session):
    """'Annabel Baker' - Gate 2A amendment's own real production case,
    unchanged outcome: with no Company resolution, no ControlRelationship,
    and every raw variant matching the bare person-name shape, this
    remains a confident PERSON determination."""
    _make_long_pending_opportunity(session, address="Baker Site", applicant_company="Annabel Baker", ref="REF-BAKER")
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Annabel Baker")
    assert classify_identity_shape(ctx) == IDENTITY_SHAPE_PERSON
    assert is_person_shaped_identity(ctx) is True


def test_company_resolved_bare_name_is_not_incorrectly_treated_as_person(session):
    """The exact 'Bankfoot APAM' bug: a real, Companies-House-resolved
    organisation whose name happens to be two bare capitalised words with
    no organisational keyword must NOT be routed to the not_researched
    privacy path - structural evidence (an existing Company row) now
    overrides the bare name-shape heuristic entirely."""
    company = Company(name_raw="Bankfoot APAM", name_normalized="bankfoot apam", ch_company_number="12345678", ch_status="active")
    session.add(company)
    session.commit()
    assert is_likely_individual_name("Bankfoot APAM") is True  # the bare heuristic alone still reads this as person-shaped...

    _make_long_pending_opportunity(session, address="Bankfoot Site", applicant_company="Bankfoot APAM", ref="REF-BANKFOOT")
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Bankfoot APAM")
    assert ctx.identity_type == "company"  # ...but it resolved to the existing Company row
    assert classify_identity_shape(ctx) == IDENTITY_SHAPE_ORGANISATION
    assert is_person_shaped_identity(ctx) is False


def test_control_evidence_alone_also_overrides_bare_name_shape(session):
    """A second, independent structural-evidence override: even without a
    resolved Company row, a real, evidenced ControlRelationship for this
    identity is itself proof of organisational-grade activity, not a bare
    application-form name - must also route to ORGANISATION."""
    site, app = _make_long_pending_opportunity(session, address="Control Evidence Site", applicant_company="Rowan Fields", ref="REF-ROWAN")
    session.add(ControlRelationship(
        application_id=app.id, site_id=site.id, entity_name_raw="Rowan Fields", entity_type="company",
        role="OWNER", evidence_basis="certificate_a_declaration", evidence_category="CERTIFICATE_A_APPLICANT_OWNER_DECLARATION",
        extraction_method="deterministic_regex", confidence="medium",
    ))
    session.commit()
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Rowan Fields")
    assert classify_identity_shape(ctx) == IDENTITY_SHAPE_ORGANISATION
    assert is_person_shaped_identity(ctx) is False


def test_ordinary_company_without_ltd_suffix_remains_research_eligible(session):
    """An organisation-shaped name with an organisational keyword but no
    legal suffix at all - must resolve to ORGANISATION via name-shape
    alone, no structural evidence needed."""
    _make_long_pending_opportunity(session, address="Meridian Site", applicant_company="Meridian Group", ref="REF-MERIDIAN")
    contexts = build_applicant_identity_contexts(session)
    ctx = next(c for c in contexts.values() if c.display_name == "Meridian Group")
    assert classify_identity_shape(ctx) == IDENTITY_SHAPE_ORGANISATION
    assert is_person_shaped_identity(ctx) is False


def test_genuinely_ambiguous_identity_is_uncertain_not_silently_person():
    """A pure unit test of classify_identity_shape's own disagreement
    branch: one raw name variant reads as organisation-shaped ('Green
    Fields Estates' - the 'estates' keyword), another as a bare personal
    name ('Green Fields' alone), with NO structural evidence either way -
    a genuinely ambiguous case. Product Owner's own explicit instruction:
    this must NOT be silently treated as a person merely because one
    variant consists of 2-3 capitalised words - it is UNCERTAIN, a
    distinct, honestly-labelled state, and remains ELIGIBLE for research
    (only a confident PERSON skips it). Constructed directly against the
    dataclass (rather than via the full DB pipeline) since real production
    disagreement across variants of the exact same normalised identity_key
    is not something this fixture can force without also changing
    identity-merge behaviour, which is a separate concern from this test's
    own point - classify_identity_shape's decision logic itself."""
    from app.reporting.applicant_intelligence import ApplicantIdentityContext

    ctx = ApplicantIdentityContext(
        identity_ref="name:green fields", identity_type="name", display_name="Green Fields",
        raw_name_variants=["Green Fields Estates", "Green Fields"],
    )
    assert classify_identity_shape(ctx) == IDENTITY_SHAPE_UNCERTAIN
    assert is_person_shaped_identity(ctx) is False  # UNCERTAIN remains eligible for research
