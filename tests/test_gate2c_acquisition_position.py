"""Gate 2C V1 ("Acquisition Position Intelligence") - focused tests for
app.reporting.acquisition_position.build_acquisition_position_facts.

Uses the same in-memory-SQLite `session` fixture as the rest of this suite
(tests/conftest.py). No live production database, no network, no AI.
"""
from __future__ import annotations

import inspect

import pytest
from sqlalchemy import select

from app.db.models import (
    Application,
    ApplicantIntelligence,
    Company,
    ControlRelationship,
    Document,
    Site,
    SchemeIntelligence,
)
from app.reporting import acquisition_position as ap
from app.reporting.acquisition_position import (
    COVERAGE_INDICATION_FOUND,
    COVERAGE_INSUFFICIENT,
    COVERAGE_SEARCHED_NO_INDICATION_FOUND,
    OWNERSHIP_APPLICANT_DECLARED_SOLE_OWNER,
    OWNERSHIP_NOT_FULLY_KNOWN,
    OWNERSHIP_OTHER_OWNER_INTEREST_DECLARED,
    OWNERSHIP_PARTIAL_IDENTIFICATION,
    build_acquisition_position_facts,
)

_CERT_SECTION = (
    "Ownership Certificates and Agricultural Land Declaration\n"
    "Please answer the following questions to determine which Certificate of Ownership you need to complete: A, B, C or D.\n"
    "Certificate of ownership - Certificate {letter}\n"
    "I certify that the requirements of Certificate {letter} have been met in respect of this application.\n"
)


def _form_body(company_name: str | None = None, *, letter: str = "A", include_applicant_details: bool = True) -> str:
    body = ""
    if include_applicant_details:
        body += "Applicant Details\nName/Company\nTitle\nFirst name\nSurname\nCare of Agent\nCompany Name\n"
        if company_name:
            body += f"{company_name}\n"
        body += "Address\nAddress line 1\nSome Street\n"
    body += "Agent Details\nName/Company\nTitle\nFirst name\nSurname\nCompany Name\nSome Agent LLP\nAddress\n"
    body += _CERT_SECTION.format(letter=letter)
    return body


def _make_site(session, address="1 Test St") -> Site:
    site = Site(council_code="testcouncil", canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_application(session, *, reference: str, site_id: int | None = None, **kwargs) -> Application:
    app = Application(council_code="testcouncil", reference=reference, site_id=site_id, **kwargs)
    session.add(app)
    session.flush()
    return app


def _make_form(session, application_id: int, text: str) -> Document:
    doc = Document(application_id=application_id, doc_type="application_form", extracted_text=text, text_extracted=True)
    session.add(doc)
    session.flush()
    return doc


def _make_s106(session, application_id: int, text: str) -> Document:
    doc = Document(application_id=application_id, doc_type="s106", extracted_text=text, text_extracted=True)
    session.add(doc)
    session.flush()
    return doc


# --- Certificate A/B/C/D semantics, live-computed -----------------------------


def test_certificate_a_produces_sole_owner_fact(session):
    app = _make_application(session, reference="APP/1")
    _make_form(session, app.id, _form_body("ABC Developments Limited", letter="A"))
    session.commit()

    facts = build_acquisition_position_facts(session, [app])
    assert len(facts.ownership_evidence) == 1
    fact = facts.ownership_evidence[0]
    assert fact.state == OWNERSHIP_APPLICANT_DECLARED_SOLE_OWNER
    assert fact.entity_name == "ABC Developments Limited"
    assert fact.confidence == "medium"
    assert fact.evidence_document_id is not None
    assert facts.ownership_coverage == COVERAGE_INDICATION_FOUND


def test_certificate_b_produces_other_owner_interest_fact_not_owner(session):
    app = _make_application(session, reference="APP/1")
    _make_form(session, app.id, _form_body("ABC Developments Limited", letter="B"))
    session.commit()

    facts = build_acquisition_position_facts(session, [app])
    assert len(facts.ownership_evidence) == 1
    assert facts.ownership_evidence[0].state == OWNERSHIP_OTHER_OWNER_INTEREST_DECLARED
    assert facts.ownership_evidence[0].entity_name == "ABC Developments Limited"


def test_certificate_c_produces_partial_identification_fact(session):
    app = _make_application(session, reference="APP/1")
    _make_form(session, app.id, _form_body("ABC Developments Limited", letter="C"))
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    assert facts.ownership_evidence[0].state == OWNERSHIP_PARTIAL_IDENTIFICATION


def test_certificate_d_produces_not_fully_known_fact(session):
    app = _make_application(session, reference="APP/1")
    _make_form(session, app.id, _form_body("ABC Developments Limited", letter="D"))
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    assert facts.ownership_evidence[0].state == OWNERSHIP_NOT_FULLY_KNOWN


def test_certificate_false_positive_boilerplate_rejected(session):
    """The boilerplate question sentence mentions every letter A-D but must
    never itself be treated as a genuine certificate selection."""
    app = _make_application(session, reference="APP/1")
    text = (
        "Applicant Details\nCompany Name\nABC Developments Limited\nAddress\n"
        "Ownership Certificates and Agricultural Land Declaration\n"
        "Please answer the following questions to determine which Certificate of Ownership you need to complete: A, B, C or D.\n"
    )
    _make_form(session, app.id, text)
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    assert facts.ownership_evidence == ()


def test_missing_text_document_produces_no_crash_no_fact(session):
    app = _make_application(session, reference="APP/1")
    doc = Document(application_id=app.id, doc_type="application_form", extracted_text=None, text_extracted=False)
    session.add(doc)
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    assert facts.ownership_evidence == ()
    assert facts.evidence_coverage.ownership_certificate_documents_present is False


def test_idempotent_computation(session):
    """Computed, non-persisted - calling twice gives byte-identical facts,
    and makes zero writes (no new/dirty session state)."""
    app = _make_application(session, reference="APP/1")
    _make_form(session, app.id, _form_body("ABC Developments Limited"))
    session.commit()

    facts1 = build_acquisition_position_facts(session, [app])
    assert len(session.new) == 0 and len(session.dirty) == 0
    facts2 = build_acquisition_position_facts(session, [app])
    assert facts1 == facts2


# --- Entity-type resolution ----------------------------------------------------


def test_corporate_shaped_name_resolves_company_without_existing_row(session):
    app = _make_application(session, reference="APP/1")
    _make_form(session, app.id, _form_body("Ropley Properties Limited"))
    session.commit()
    assert session.execute(select(Company)).scalars().all() == []

    facts = build_acquisition_position_facts(session, [app])
    fact = facts.ownership_evidence[0]
    assert fact.entity_type == "company"
    assert fact.company_id is None


def test_corporate_shaped_name_resolves_existing_company_id_when_matching(session):
    company = Company(name_raw="ABC Developments Limited", name_normalized="abc developments limited")
    session.add(company)
    session.flush()
    app = _make_application(session, reference="APP/1")
    _make_form(session, app.id, _form_body("ABC Developments Limited"))
    session.commit()

    facts = build_acquisition_position_facts(session, [app])
    fact = facts.ownership_evidence[0]
    assert fact.entity_type == "company"
    assert fact.company_id == company.id


def test_individual_applicant_never_resolves_company_id(session):
    app = _make_application(session, reference="APP/1")
    form_text = (
        "Applicant Details\nName/Company\nTitle\nMr\nFirst name\nRob\nSurname\nWatson\n"
        "Care of Agent\nCompany Name\nWatson\nAddress\nAddress line 1\nc/o agent\n"
        "Agent Details\nCompany Name\nSome Agent LLP\nAddress\n"
    ) + _CERT_SECTION.format(letter="A")
    _make_form(session, app.id, form_text)
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    fact = facts.ownership_evidence[0]
    assert fact.entity_type == "individual"
    assert fact.company_id is None
    assert fact.entity_name == "Rob Watson"


# --- Conflicting/multiple facts -------------------------------------------------


def test_conflicting_developer_evidence_surfaced_not_silently_resolved(session):
    site = _make_site(session)
    app1 = _make_application(session, reference="APP/1", site_id=site.id)
    session.add(SchemeIntelligence(application_id=app1.id, developer="Housebuilder X"))
    app2 = _make_application(session, reference="APP/2", site_id=site.id)
    session.add(SchemeIntelligence(application_id=app2.id, developer="Housebuilder Y"))
    session.commit()

    facts = build_acquisition_position_facts(session, [app1, app2])
    assert len(facts.conflicts) >= 1
    assert "Housebuilder X" in facts.conflicts[0] and "Housebuilder Y" in facts.conflicts[0]
    developer_names = {d.developer_name for d in facts.developer_indications}
    assert developer_names == {"Housebuilder X", "Housebuilder Y"}  # both preserved, neither dropped


def test_multiple_ownership_facts_preserved_not_collapsed(session):
    """Two applications on the same site, each with their own resolvable
    Certificate A owner - both facts kept, never collapsed to one."""
    site = _make_site(session)
    app1 = _make_application(session, reference="APP/1", site_id=site.id)
    _make_form(session, app1.id, _form_body("Owner One Limited"))
    app2 = _make_application(session, reference="APP/2", site_id=site.id)
    _make_form(session, app2.id, _form_body("Owner Two Limited"))
    session.commit()

    facts = build_acquisition_position_facts(session, [app1, app2])
    assert len(facts.ownership_evidence) == 2
    names = {f.entity_name for f in facts.ownership_evidence}
    assert names == {"Owner One Limited", "Owner Two Limited"}


def test_persisted_needs_confirmation_relationship_surfaced_as_conflict(session):
    site = _make_site(session)
    app = _make_application(session, reference="APP/1", site_id=site.id)
    session.add(ControlRelationship(
        application_id=app.id, site_id=site.id, entity_name_raw="Some Party Ltd", entity_type="unknown",
        role="OWNER", evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
        extraction_method="deterministic_regex", confidence="high", review_status="needs_confirmation",
    ))
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    assert any("needs_confirmation" in c for c in facts.conflicts)


# --- Site/application-family scope ----------------------------------------------


def test_narrow_application_scope_never_promoted_to_whole_site_without_evidence(session):
    """An application with no site_id must be scoped to itself only - never
    silently treated as if it spoke for a wider site it isn't linked to."""
    app = _make_application(session, reference="APP/1", site_id=None)
    _make_form(session, app.id, _form_body("Solo Owner Limited"))
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    assert facts.site_id is None
    assert facts.application_ids == (app.id,)
    assert facts.ownership_evidence[0].site_id is None


def test_multi_application_site_reconciliation_scopes_control_relationships_by_site(session):
    site = _make_site(session)
    app1 = _make_application(session, reference="APP/1", site_id=site.id)
    app2 = _make_application(session, reference="APP/2", site_id=site.id)
    session.add(ControlRelationship(
        site_id=site.id, entity_name_raw="Site Owner Ltd", entity_type="unknown",
        role="OWNER", evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
        extraction_method="deterministic_regex", confidence="high",
    ))
    session.commit()
    facts = build_acquisition_position_facts(session, [app1, app2])
    assert len(facts.control_relationships) == 1
    assert facts.control_relationships[0].entity_name == "Site Owner Ltd"


# --- Evidence coverage / negative evidence semantics ----------------------------


def test_coverage_insufficient_when_no_relevant_documents_at_all(session):
    app = _make_application(session, reference="APP/1")
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    assert facts.ownership_coverage == COVERAGE_INSUFFICIENT
    assert facts.evidence_coverage.ownership_certificate_documents_present is False
    assert facts.evidence_coverage.s106_documents_present is False


def test_coverage_searched_no_indication_found_distinct_from_insufficient(session):
    """A genuine application_form document exists and was examined, but no
    certificate evidence was found - this is NOT the same as insufficient
    coverage (Section 12/13 - absence of evidence != evidence of absence,
    but 'we looked' is still a stronger, different claim than 'we never
    looked')."""
    app = _make_application(session, reference="APP/1")
    _make_form(session, app.id, "Some other form content with no certificate section at all.")
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    assert facts.ownership_coverage == COVERAGE_SEARCHED_NO_INDICATION_FOUND
    assert facts.evidence_coverage.ownership_certificate_documents_present is True
    assert facts.ownership_coverage != COVERAGE_INSUFFICIENT


def test_strategic_land_no_application_case_does_not_crash(session):
    """A strategic-land allocation with no matched planning application at
    all must not crash or fabricate application-based facts."""
    facts = build_acquisition_position_facts(session, [])
    assert facts.site_id is None
    assert facts.application_ids == ()
    assert facts.ownership_evidence == ()
    assert facts.developer_indications == ()
    assert facts.control_relationships == ()
    assert facts.ownership_coverage == COVERAGE_INSUFFICIENT


# --- Developer/applicant indication ----------------------------------------------


def test_developer_applicant_indication_never_claims_ownership(session):
    app = _make_application(session, reference="APP/1")
    session.add(SchemeIntelligence(application_id=app.id, developer="Big Housebuilder Ltd"))
    session.commit()
    facts = build_acquisition_position_facts(session, [app])
    assert facts.ownership_evidence == ()  # a developer name is never itself an ownership claim
    assert any(d.developer_name == "Big Housebuilder Ltd" for d in facts.developer_indications)


# --- Structural guards: buyer-independence / no AVAILABLE / no new events ------


def test_control_position_field_and_constants_do_not_exist(session):
    """Gate 2C V1 amendment (Product Owner decision): the coarse
    control_position summary field was removed entirely, not replaced by
    another coarse field - ownership evidence, applicant position,
    developer indication and control/third-party relationships remain the
    only source of truth, read directly by any consumer."""
    app = _make_application(session, reference="APP/1")
    session.add(SchemeIntelligence(application_id=app.id, developer="Big Housebuilder Ltd"))
    session.commit()
    facts = build_acquisition_position_facts(session, [app])

    assert not hasattr(facts, "control_position")
    for banned in (
        "control_position", "CONTROL_UNKNOWN", "CONTROL_THIRD_PARTY_INTEREST_IDENTIFIED",
        "CONTROL_DEVELOPER_APPLICANT_INDICATED", "CONTROL_CONFLICTING_EVIDENCE",
        "acquisition_status", "control_status", "availability_status",
        "selling_position", "transaction_probability", "opportunity_status",
    ):
        assert not hasattr(ap, banned)


def test_module_never_imports_buyer_profile():
    """Checks actual import statements only - the module's own docstring
    legitimately DISCUSSES buyer-independence by name while explaining it,
    the same 'discusses vs imports' distinction test_control_population.py
    already establishes for SchemeIntelligence."""
    source_lines = inspect.getsource(ap).splitlines()
    import_lines = [ln for ln in source_lines if ln.strip().startswith(("import ", "from "))]
    assert not any("BuyerProfile" in ln or "buyer_matching" in ln or "buyer_profile" in ln for ln in import_lines)


def test_module_never_produces_available_classification():
    """No module-level constant's own STRING VALUE (i.e. an actual
    classification this module could emit as a fact) contains AVAILABLE -
    the word appears in prose comments/docstrings explaining what is
    deliberately NOT implemented, which is expected and fine; what must
    never exist is a real output value like that."""
    for name in dir(ap):
        if name.isupper():
            value = getattr(ap, name)
            if isinstance(value, str):
                assert "AVAILABLE" not in value.upper()


def test_module_never_writes_application_lifecycle_event():
    source = inspect.getsource(ap)
    assert "ApplicationLifecycleEvent" not in source
    assert "lifecycle_events" not in source


def test_module_makes_no_database_writes(session):
    """Structural safety net alongside the idempotency test above - build_
    acquisition_position_facts must never add/flush/commit anything."""
    app = _make_application(session, reference="APP/1")
    _make_form(session, app.id, _form_body("ABC Developments Limited"))
    session.commit()
    build_acquisition_position_facts(session, [app])
    assert len(session.new) == 0
    assert len(session.dirty) == 0


def test_no_pursue_verify_monitor_output_anywhere_in_module():
    """No module-level constant's own STRING VALUE is one of these buyer-
    recommendation tokens - the docstring legitimately names them in prose
    while explaining they belong to a future gate, which is expected.
    Recommendation Taxonomy V2: INVESTIGATE added (replaces VERIFY at the
    Agent Evaluation recommendation layer - app.reporting.acquisition_
    position is buyer-independent and must never produce ANY of these,
    old or new vocabulary)."""
    for name in dir(ap):
        if name.isupper():
            value = getattr(ap, name)
            if isinstance(value, str):
                assert value.upper() not in ("PURSUE", "VERIFY", "INVESTIGATE", "MONITOR", "NOT_RELEVANT")
