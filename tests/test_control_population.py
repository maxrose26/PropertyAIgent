"""Stage 4B.1 tests - app.enrichment.control_population +
scripts.populate_control_relationships. Every test runs against the
shared in-memory SQLite `session` fixture (tests/conftest.py) - never the
real production database.
"""
from __future__ import annotations

import inspect

import pytest
from sqlalchemy import select

from app.db.models import (
    AllocationSiteRelationship,
    Application,
    Company,
    Council,
    ControlRelationship,
    Document,
    LocalPlanSite,
    Site,
)
from app.enrichment import control_population as cp
from app.enrichment.control_entities import create_control_relationship_if_absent
from app.enrichment.control_population import run_control_relationship_population


def _make_council(session, code: str) -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))


def _make_site(session, council_code: str, address: str) -> Site:
    site = Site(council_code=council_code, canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_application(session, council_code: str, reference: str, *, site_id=None, applicant_name_raw=None) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id, applicant_name_raw=applicant_name_raw)
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


def _make_allocation(session, council_code: str, site_name: str, policy_reference: str, min_dwellings: int) -> LocalPlanSite:
    allocation = LocalPlanSite(
        council_code=council_code, policy_reference=policy_reference, site_name=site_name,
        minimum_dwellings=min_dwellings, plan_name="Test Local Plan", plan_status="adopted",
    )
    session.add(allocation)
    session.flush()
    return allocation


def _make_allocation_site_relationship(session, allocation_id: int, site_id: int) -> AllocationSiteRelationship:
    rel = AllocationSiteRelationship(
        allocation_id=allocation_id, site_id=site_id, evidence_basis="document_confirmed_site", review_status="auto_applied",
    )
    session.add(rel)
    session.flush()
    return rel


_CERT_SECTION = (
    "Ownership Certificates and Agricultural Land Declaration\n"
    "Please answer the following questions to determine which Certificate of Ownership you need to complete: A, B, C or D.\n"
    "Certificate of ownership - Certificate {letter}\n"
    "I certify that the requirements of Certificate {letter} have been met in respect of this application.\n"
)


def _form_with_applicant(company_name: str | None = None, *, certificate_letter: str = "A", include_applicant_details: bool = True) -> str:
    """Builds a realistic 1APP-style form body: an Applicant Details
    section (mirroring real production field ordering - Title/First
    name/Surname/Care of Agent/Company Name/Address), an Agent Details
    section, then the ownership-certificate declaration."""
    body = ""
    if include_applicant_details:
        body += "Applicant Details\nName/Company\nTitle\nFirst name\nSurname\nCare of Agent\nCompany Name\n"
        if company_name:
            body += f"{company_name}\n"
        body += "Address\nAddress line 1\nSome Street\n"
    body += "Agent Details\nName/Company\nTitle\nFirst name\nSurname\nCompany Name\nSome Agent LLP\nAddress\n"
    body += _CERT_SECTION.format(letter=certificate_letter)
    return body


_CERT_A_BODY = _form_with_applicant("ABC Developments Limited")
_CERT_B_BODY = _form_with_applicant("ABC Developments Limited", certificate_letter="B")


# ---------------------------------------------------------------------------
# Dry-run zero writes / execute confirmation
# ---------------------------------------------------------------------------


def test_dry_run_makes_zero_writes(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw="ABC Developments Limited")
    _make_form(session, app.id, _CERT_A_BODY)
    session.commit()

    report = run_control_relationship_population(session, dry_run=True)

    assert report.relationships_would_create == 1
    assert len(session.new) == 0
    assert len(session.dirty) == 0
    assert session.execute(select(ControlRelationship)).scalars().all() == []


def test_cli_execute_requires_exact_confirm_phrase(monkeypatch):
    """Structural/behavioural check of the CLI's own fail-closed gate -
    mirrors every other Stage 2/3/4 script's established convention."""
    import sys

    import scripts.populate_control_relationships as cli

    monkeypatch.setattr(sys, "argv", ["populate_control_relationships.py", "--execute", "--confirm", "WRONG-PHRASE"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_cli_execute_without_confirm_at_all_fails_closed(monkeypatch):
    import sys

    import scripts.populate_control_relationships as cli

    monkeypatch.setattr(sys, "argv", ["populate_control_relationships.py", "--execute"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Certificate semantics
# ---------------------------------------------------------------------------


def test_certificate_a_same_form_applicant_eligible(session):
    """Certificate A + a company name independently extracted from the
    SAME form's own Applicant Details section (no raw name needed at
    all) -> OWNER eligible."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw=None)
    _make_form(session, app.id, _form_with_applicant("ABC Developments Limited"))
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.certificate_a_identity_confirmed_from_form == 1
    assert report.certificate_a_relationships_eligible == 1
    assert report.relationships_created == 1
    rows = session.execute(select(ControlRelationship)).scalars().all()
    assert len(rows) == 1
    assert rows[0].role == "OWNER"
    assert rows[0].entity_name_raw == "ABC Developments Limited"
    assert rows[0].evidence_category == "CERTIFICATE_A_APPLICANT_OWNER_DECLARATION"
    assert rows[0].confidence == "medium"  # a self-declaration, not S106-grade legal evidence


def test_certificate_a_applicant_name_raw_absent_from_form_creates_nothing(session):
    """applicant_name_raw is present but does NOT appear anywhere in the
    form's Applicant Details section at all - and the form itself names
    a DIFFERENT applicant - so this must resolve as a conflict/absence,
    never silently trust the portal-scraped field alone."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw="Nowhere Near Limited")
    _make_form(session, app.id, _form_with_applicant("ABC Developments Limited"))
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.certificate_a_identity_unresolved == 1
    assert report.relationships_created == 0
    assert session.execute(select(ControlRelationship)).scalars().all() == []


def test_certificate_a_conservatively_matching_raw_and_form_applicant_eligible(session):
    """Both sources present AND agree (after conservative normalisation)
    -> eligible, using the form's own extraction as the confirmed name."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw="ABC Developments Limited")
    _make_form(session, app.id, _form_with_applicant("ABC Developments Limited"))
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.certificate_a_identity_confirmed_from_form == 1
    rows = session.execute(select(ControlRelationship)).scalars().all()
    assert len(rows) == 1
    assert rows[0].entity_name_raw == "ABC Developments Limited"


def test_certificate_a_conflicting_raw_and_form_applicant_creates_nothing(session):
    """Both sources present but they DISAGREE - a genuine conflict, never
    resolved by preferring one source over the other."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw="XYZ Holdings Limited")
    _make_form(session, app.id, _form_with_applicant("ABC Developments Limited"))
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.certificate_a_identity_unresolved == 1
    assert report.relationships_created == 0
    assert session.execute(select(ControlRelationship)).scalars().all() == []


def test_certificate_a_unresolved_applicant_creates_nothing(session):
    """No Applicant Details section at all, and no applicant_name_raw -
    genuinely nothing to tie an identity to."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw=None)
    _make_form(session, app.id, _form_with_applicant(None, include_applicant_details=False))
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.certificate_a_identity_unresolved == 1
    assert report.relationships_created == 0
    assert session.execute(select(ControlRelationship)).scalars().all() == []


def test_certificate_a_applicant_name_raw_fallback_confirmed_in_form(session):
    """No extractable Company Name/individual name in the Applicant
    Details section itself (e.g. genuinely blank fields), but
    applicant_name_raw IS conservatively confirmed present within that
    same section's own text -> eligible via the fallback method."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw="Fallback Developments Limited")
    form_text = (
        "Applicant Details\nName/Company\nTitle\nFirst name\nSurname\nCare of Agent\nCompany Name\n"
        "Address\nAddress line 1\nc/o Fallback Developments Limited registered office\n"
        "Agent Details\nCompany Name\nSome Agent LLP\nAddress\n"
    ) + _CERT_SECTION.format(letter="A")
    _make_form(session, app.id, form_text)
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.certificate_a_identity_confirmed_via_raw_fallback == 1
    rows = session.execute(select(ControlRelationship)).scalars().all()
    assert len(rows) == 1
    assert rows[0].entity_name_raw == "Fallback Developments Limited"


def test_certificate_a_individual_applicant_surname_duplicated_into_company_name_field(session):
    """Real production edge case: an individual applicant's OWN surname
    is duplicated into the form's 'Company Name' field by the portal
    generator - this must resolve to the individual's full name, entity_
    type='individual', never a bare surname treated as a company."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw=None)
    form_text = (
        "Applicant Details\nName/Company\nTitle\nMr\nFirst name\nRob\nSurname\nWatson\n"
        "Care of Agent\nCompany Name\nWatson\nAddress\nAddress line 1\nc/o agent\n"
        "Agent Details\nCompany Name\nFocus Town Planning Limited\nAddress\n"
    ) + _CERT_SECTION.format(letter="A")
    _make_form(session, app.id, form_text)
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.certificate_a_identity_confirmed_from_form == 1
    rows = session.execute(select(ControlRelationship)).scalars().all()
    assert len(rows) == 1
    assert rows[0].entity_name_raw == "Rob Watson"
    assert rows[0].entity_type == "individual"
    assert rows[0].company_id is None


def test_certificate_boilerplate_alone_still_insufficient_for_identity(session):
    """Even with a real applicant_name_raw present, boilerplate-only
    certificate text (no genuine A/B/C/D selection at all) must still
    create nothing - the underlying Stage 4B certificate-detection
    safety is unchanged by this amendment."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw="ABC Developments Limited")
    boilerplate_only = (
        "Applicant Details\nCompany Name\nABC Developments Limited\nAddress\n"
        "Ownership Certificates and Agricultural Land Declaration\n"
        "Please answer the following questions to determine which Certificate of Ownership you need to complete: A, B, C or D.\n"
    )
    _make_form(session, app.id, boilerplate_only)
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.certificate_ambiguous_count == 1
    assert report.relationships_created == 0
    assert session.execute(select(ControlRelationship)).scalars().all() == []


def test_no_scheme_intelligence_used_for_certificate_a_identity():
    """Structural guard: this module must never IMPORT/read
    SchemeIntelligence for Certificate A identity resolution - that is a
    different, AI-derived evidence path reserved for a future Stage 4C
    reconciliation, never this deterministic one. (The module docstring
    legitimately DISCUSSES SchemeIntelligence.applicant_company while
    explaining why it is deliberately NOT used - only the import
    statement, the actual usage signal, is checked here.)"""
    import app.enrichment.control_population as cp_module

    source_lines = inspect.getsource(cp_module).splitlines()
    import_lines = [ln for ln in source_lines if ln.strip().startswith(("import ", "from "))]
    assert not any("SchemeIntelligence" in ln for ln in import_lines)
    assert not hasattr(cp_module, "SchemeIntelligence")


def test_certificate_b_without_named_owner_creates_no_fake_owner(session):
    """Certificate B/C/D are ALWAYS report-only - no B/C/D named-owner
    extractor exists, so this must never invent an entity."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1", applicant_name_raw="Should Not Be Used Ltd")
    _make_form(session, app.id, _CERT_B_BODY)
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.certificate_b_count == 1
    assert report.certificate_bcd_reported_no_entity == 1
    assert report.relationships_created == 0
    assert session.execute(select(ControlRelationship)).scalars().all() == []


# ---------------------------------------------------------------------------
# S106 semantics
# ---------------------------------------------------------------------------


def test_s106_owner_persistence(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, 'AND (2) ABC Developments Limited (the "Owner").')
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.s106_owner_hits == 1
    rows = session.execute(select(ControlRelationship)).scalars().all()
    assert len(rows) == 1
    assert rows[0].role == "OWNER"
    assert rows[0].entity_name_raw == "ABC Developments Limited"
    assert rows[0].confidence == "high"


def test_s106_mortgagee_persistence(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, 'AND (4) Big Bank PLC (the "Mortgagee").')
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.s106_mortgagee_hits == 1
    rows = session.execute(select(ControlRelationship)).scalars().all()
    assert len(rows) == 1
    assert rows[0].role == "MORTGAGEE"


def test_mortgagee_never_treated_as_owner(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, 'AND (4) Big Bank PLC (the "Mortgagee").')
    session.commit()

    run_control_relationship_population(session, dry_run=False)
    session.commit()

    owner_rows = session.execute(
        select(ControlRelationship).where(ControlRelationship.role == "OWNER")
    ).scalars().all()
    assert owner_rows == []


def test_title_number_alone_creates_no_fake_relationship(session):
    """A title number with no accompanying Owner/Developer/Mortgagee hit
    in the same document must never invent a party just to hold it."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, "Registered with the Land Registry under title number GM781194 - no defined party named here.")
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.s106_title_numbers_found == 1
    assert report.s106_title_numbers_without_party == 1
    assert report.relationships_created == 0
    assert session.execute(select(ControlRelationship)).scalars().all() == []


def test_title_number_attached_only_to_owner_role(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, (
        'AND (2) ABC Developments Limited (the "Owner") AND (3) Big Bank PLC (the "Mortgagee"). '
        "Title number GM781194."
    ))
    session.commit()

    run_control_relationship_population(session, dry_run=False)
    session.commit()

    rows = {r.role: r for r in session.execute(select(ControlRelationship)).scalars().all()}
    assert rows["OWNER"].title_number == "GM781194"
    assert rows["MORTGAGEE"].title_number is None


# ---------------------------------------------------------------------------
# evidence_date
# ---------------------------------------------------------------------------


def test_evidence_date_not_derived_from_downloaded_at(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    import datetime as dt
    doc = Document(
        application_id=app.id, doc_type="s106", extracted_text='AND (2) ABC Developments Limited (the "Owner").',
        text_extracted=True, downloaded_at=dt.datetime(2024, 9, 16, tzinfo=dt.timezone.utc),
    )
    session.add(doc)
    session.commit()

    run_control_relationship_population(session, dry_run=False)
    session.commit()

    rel = session.execute(select(ControlRelationship)).scalars().one()
    assert rel.evidence_date is None


def test_run_control_relationship_population_never_reads_downloaded_at():
    source = inspect.getsource(cp)
    assert ".downloaded_at" not in source


# ---------------------------------------------------------------------------
# Entity type / resolution
# ---------------------------------------------------------------------------


def test_private_individual_style_name_never_extracted_by_s106(session):
    """This module never invents individual owners either - reuses Stage
    4B's own conservative org-suffix-only extraction unchanged."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, 'AND (2) John Smith of 4 Acacia Avenue (the "Owner").')
    session.commit()

    run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert session.execute(select(ControlRelationship)).scalars().all() == []


def test_company_resolution_reuses_existing_company_row(session):
    _make_council(session, "testcouncil")
    company = Company(name_raw="ABC Developments Limited", name_normalized="abc developments")
    session.add(company)
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, 'AND (2) ABC Developments Limited (the "Owner").')
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.company_resolved_count == 1
    rel = session.execute(select(ControlRelationship)).scalars().one()
    assert rel.company_id == company.id
    assert rel.entity_type == "company"


def test_unresolved_entity_remains_raw_with_no_company_id(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, 'AND (2) Completely Unknown Enterprises Limited (the "Owner").')
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.unresolved_entity_count == 1
    rel = session.execute(select(ControlRelationship)).scalars().one()
    assert rel.company_id is None
    assert rel.entity_type == "unknown"
    assert rel.entity_name_raw == "Completely Unknown Enterprises Limited"  # never dropped for lack of a Company match


# ---------------------------------------------------------------------------
# Idempotency / human-confirmed evidence preservation
# ---------------------------------------------------------------------------


def test_duplicate_run_is_idempotent(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, 'AND (2) ABC Developments Limited (the "Owner").')
    session.commit()

    run_control_relationship_population(session, dry_run=False)
    session.commit()
    first_count = len(session.execute(select(ControlRelationship)).scalars().all())

    report2 = run_control_relationship_population(session, dry_run=False)
    session.commit()
    second_count = len(session.execute(select(ControlRelationship)).scalars().all())

    assert first_count == 1
    assert second_count == 1
    assert report2.relationships_created == 0
    assert report2.relationships_already_present == 1


def test_human_confirmed_evidence_preserved_across_reruns(session):
    """A row a human has already confirmed must never be downgraded by a
    later run finding a genuinely different competing claim."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    confirmed = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="Human Confirmed Owner Ltd", role="OWNER",
        evidence_basis="manual", evidence_category="MANUAL_CONFIRMATION", extraction_method="manual",
        review_status="confirmed",
    )
    _make_s106(session, app.id, 'AND (2) A Different Company Limited (the "Owner").')
    session.commit()

    run_control_relationship_population(session, dry_run=False)
    session.commit()

    session.refresh(confirmed)
    assert confirmed.review_status == "confirmed"  # never downgraded
    rows = session.execute(select(ControlRelationship).where(ControlRelationship.application_id == app.id)).scalars().all()
    assert len(rows) == 2
    new_row = next(r for r in rows if r.id != confirmed.id)
    assert new_row.review_status == "needs_confirmation"  # the competing claim is still visible


# ---------------------------------------------------------------------------
# Scope / allocation-propagation safety, including North of Mosley Common
# ---------------------------------------------------------------------------


def test_no_allocation_wide_propagation(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "Test Allocation", "H3", 500)
    site_a = _make_site(session, "wigan", "Parcel A")
    site_b = _make_site(session, "wigan", "Parcel B")
    _make_allocation_site_relationship(session, allocation.id, site_a.id)
    _make_allocation_site_relationship(session, allocation.id, site_b.id)
    app_a = _make_application(session, "wigan", "APP/A", site_id=site_a.id)
    _make_s106(session, app_a.id, 'AND (2) Bellway Homes Limited (the "Developer").')
    session.commit()

    run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert session.execute(select(ControlRelationship).where(ControlRelationship.site_id == site_b.id)).scalars().all() == []
    assert len(session.execute(select(ControlRelationship).where(ControlRelationship.site_id == site_a.id)).scalars().all()) == 1


def test_north_of_mosley_common_regression(session):
    """Mirrors the real production case exactly: allocation JPA 32
    related to TWO Sites - the Southern Parcel (with real S106 evidence
    naming Taylor Wimpey as Developer) and a residual Site with zero
    documents. The production runner must never infer Taylor Wimpey
    controls the whole allocation/residual, and must never invent Turley
    (the planning agent, mentioned nowhere in S106/certificate text) as a
    Developer - this module never reads SchemeIntelligence.planning_agent
    at all."""
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North of Mosley Common", "JPA 32", 1100)

    southern_parcel = _make_site(session, "wigan", "Land North Of Mosley Common South Of The Guided Busway")
    _make_allocation_site_relationship(session, allocation.id, southern_parcel.id)
    southern_app = _make_application(session, "wigan", "A/25/099409/RMMAJ", site_id=southern_parcel.id)
    _make_s106(session, southern_app.id, (
        'AND (2) Taylor Wimpey Manchester Limited (the "Developer"). '
        "The Section 106 Agreement dated 16 September 2024 secures affordable housing."
    ))

    residual_site = _make_site(session, "wigan", "Remainder of North of Mosley Common allocation")
    _make_allocation_site_relationship(session, allocation.id, residual_site.id)
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.s106_developer_hits == 1

    residual_evidence = session.execute(
        select(ControlRelationship).where(ControlRelationship.site_id == residual_site.id)
    ).scalars().all()
    assert residual_evidence == []  # no evidence inherited from the other phase

    southern_evidence = session.execute(
        select(ControlRelationship).where(ControlRelationship.site_id == southern_parcel.id)
    ).scalars().all()
    assert len(southern_evidence) == 1
    assert southern_evidence[0].role == "DEVELOPER"
    assert southern_evidence[0].entity_name_raw == "Taylor Wimpey Manchester Limited"

    # Turley (the real planning agent on this application) is never
    # created as anything - this module has no basis to name it at all.
    all_names = {r.entity_name_raw for r in session.execute(select(ControlRelationship)).scalars().all()}
    assert "Turley" not in all_names
    assert not any("turley" in name.lower() for name in all_names)


# ---------------------------------------------------------------------------
# Semantic-review exclusion / failure isolation / schema fail-closed
# ---------------------------------------------------------------------------


def test_semantic_review_cases_excluded_from_persistence(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_s106(session, app.id, (
        "The Owner's obligations under this Deed are set out in Schedule 2, and the Developer "
        "shall comply with the phasing plan referred to therein."
    ))
    session.commit()

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.semantic_review_excluded_count == 1
    assert session.execute(select(ControlRelationship)).scalars().all() == []


def test_one_document_failure_does_not_corrupt_prior_successful_relationships(session, monkeypatch):
    _make_council(session, "testcouncil")
    good_app = _make_application(session, "testcouncil", "APP/GOOD")
    _make_s106(session, good_app.id, 'AND (2) Reliable Developments Limited (the "Owner").')
    bad_app = _make_application(session, "testcouncil", "APP/BAD")
    _make_s106(session, bad_app.id, 'AND (2) Broken Developments Limited (the "Owner").')
    session.commit()

    original = cp.create_control_relationship_if_absent

    def _boom(session, **kwargs):
        if kwargs.get("entity_name_raw") == "Broken Developments Limited":
            raise RuntimeError("simulated failure")
        return original(session, **kwargs)

    monkeypatch.setattr(cp, "create_control_relationship_if_absent", _boom)

    report = run_control_relationship_population(session, dry_run=False)
    session.commit()

    assert report.documents_failed == 1
    assert len(report.errors) == 1

    good_rows = session.execute(
        select(ControlRelationship).where(ControlRelationship.application_id == good_app.id)
    ).scalars().all()
    assert len(good_rows) == 1  # the prior successful document's write survives

    bad_rows = session.execute(
        select(ControlRelationship).where(ControlRelationship.application_id == bad_app.id)
    ).scalars().all()
    assert bad_rows == []  # the failed document's own partial write was rolled back


def test_missing_schema_fails_closed_in_execute_mode(session, monkeypatch):
    """Structural/behavioural check of the CLI's own Section 12 gate."""
    import sys

    import scripts.populate_control_relationships as cli

    class _FakeInspector:
        def has_table(self, name):
            return False

    monkeypatch.setattr(cli, "inspect", lambda engine: _FakeInspector())
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "get_session", lambda: session)
    monkeypatch.setattr(cli, "get_engine", lambda: object())
    monkeypatch.setattr(sys, "argv", ["populate_control_relationships.py", "--execute", "--confirm", cli.CONFIRM_PHRASE])

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# No AI / no external calls
# ---------------------------------------------------------------------------


def test_no_openai_dependency():
    source = inspect.getsource(cp)
    assert "import openai" not in source.lower()
    assert "OpenAI(" not in source


def test_no_companies_house_api_call():
    source = inspect.getsource(cp)
    assert "companies_house" not in source.lower()
    assert "requests.get" not in source
    assert "requests.post" not in source


def test_no_land_registry_or_network_calls():
    source = inspect.getsource(cp)
    assert "land_registry" not in source.lower()
    assert "urllib" not in source
    assert "httpx" not in source.lower()


def test_cli_no_openai_or_external_api_dependency():
    import scripts.populate_control_relationships as cli
    source = inspect.getsource(cli)
    assert "import openai" not in source.lower()
    assert "OpenAI(" not in source
    assert "companies_house" not in source.lower()


def test_orchestrator_creates_relationships_only_through_the_shared_helper():
    source = inspect.getsource(cp)
    assert "ControlRelationship(" not in source  # never constructs the model directly
    assert "create_control_relationship_if_absent(" in source
