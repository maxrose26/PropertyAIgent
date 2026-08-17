"""Stage 4B persistence + entity-resolution + dry-run report tests -
app.enrichment.control_entities. Every test runs against the shared
in-memory SQLite `session` fixture (tests/conftest.py) - never the real
production database.
"""
from __future__ import annotations

import datetime as dt
import inspect

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
from app.enrichment import control_entities as ce
from app.enrichment.control_entities import (
    build_ownership_control_dry_run_report,
    create_control_relationship_if_absent,
    resolve_existing_company,
)


def _make_council(session, code: str) -> None:
    if session.get(Council, code) is None:
        session.add(Council(code=code, name=code.title(), base_url="https://example.invalid",
                             date_field_mode="received", doc_system="idox"))


def _make_site(session, council_code: str, address: str) -> Site:
    site = Site(council_code=council_code, canonical_address=address, display_address=address)
    session.add(site)
    session.flush()
    return site


def _make_application(session, council_code: str, reference: str, site_id: int | None = None) -> Application:
    app = Application(council_code=council_code, reference=reference, site_id=site_id)
    session.add(app)
    session.flush()
    return app


def _make_document(session, application_id: int, doc_type: str, text: str) -> Document:
    doc = Document(application_id=application_id, doc_type=doc_type, extracted_text=text, text_extracted=True)
    session.add(doc)
    session.flush()
    return doc


def _make_company(session, name_raw: str, ch_company_number: str | None = None) -> Company:
    company = Company(name_raw=name_raw, name_normalized=name_raw.lower(), ch_company_number=ch_company_number)
    session.add(company)
    session.flush()
    return company


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
        allocation_id=allocation_id, site_id=site_id, evidence_basis="document_confirmed_site",
        review_status="auto_applied",
    )
    session.add(rel)
    session.flush()
    return rel


# ---------------------------------------------------------------------------
# create_control_relationship_if_absent - basic creation, idempotency,
# contradiction handling
# ---------------------------------------------------------------------------


def test_create_control_relationship_basic(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    app = _make_application(session, "testcouncil", "APP/1", site_id=site.id)
    doc = _make_document(session, app.id, "s106", "some text")
    session.commit()

    rel = create_control_relationship_if_absent(
        session, application_id=app.id, site_id=site.id, entity_name_raw="ABC Developments Limited",
        entity_type="company", role="OWNER", evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
        extraction_method="deterministic_regex", confidence="high", evidence_document_id=doc.id,
        evidence_snippet="the Owner is ABC Developments Limited", title_number="GM123456",
    )
    session.commit()

    assert rel is not None
    assert rel.id is not None
    assert rel.application_id == app.id
    assert rel.site_id == site.id
    assert rel.entity_name_raw == "ABC Developments Limited"
    assert rel.role == "OWNER"
    assert rel.review_status == "auto_applied"
    assert rel.title_number == "GM123456"


def test_create_control_relationship_idempotent_same_claim(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    session.commit()

    first = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    session.commit()
    second = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="abc developments limited", role="OWNER",  # case-insensitive match
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    session.commit()

    assert first is not None
    assert second is None
    rows = session.execute(select(ControlRelationship)).scalars().all()
    assert len(rows) == 1


def test_create_control_relationship_contradiction_preserves_both(session):
    """Two DIFFERENT entities claiming the SAME role on the SAME
    application - neither is deleted or silently preferred; both are
    preserved and both are flagged needs_confirmation."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    session.commit()

    first = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    session.commit()
    second = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="XYZ Holdings Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    session.commit()

    assert first is not None
    assert second is not None
    rows = session.execute(select(ControlRelationship)).scalars().all()
    assert len(rows) == 2
    assert {r.entity_name_raw for r in rows} == {"ABC Developments Limited", "XYZ Holdings Limited"}
    assert all(r.review_status == "needs_confirmation" for r in rows)


def test_create_control_relationship_rejected_row_not_counted_as_contradiction(session):
    """A pre-existing row a human has already REJECTED must not trigger
    contradiction-flagging for a new claim - it is deliberately excluded
    from the existing-rows comparison."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    rejected = ControlRelationship(
        application_id=app.id, entity_name_raw="Wrong Company Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
        extraction_method="deterministic_regex", review_status="rejected",
    )
    session.add(rejected)
    session.commit()

    result = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    session.commit()

    assert result is not None
    assert result.review_status == "auto_applied"  # not needs_confirmation - the rejected row doesn't count
    session.refresh(rejected)
    assert rejected.review_status == "rejected"  # untouched


def test_different_roles_never_treated_as_a_contradiction(session):
    """OWNER and DEVELOPER are different claims entirely, even for the
    same application - one must never flag the other for review."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    session.commit()

    owner = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    developer = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="XYZ Homes Limited", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER", extraction_method="deterministic_regex",
    )
    session.commit()

    assert owner.review_status == "auto_applied"
    assert developer.review_status == "auto_applied"


# ---------------------------------------------------------------------------
# resolve_existing_company - conservative, no external calls
# ---------------------------------------------------------------------------


def test_resolve_existing_company_exact_match(session):
    company = _make_company(session, "ABC Developments Limited")
    session.commit()
    resolved = resolve_existing_company(session, "ABC Developments Limited")
    assert resolved is not None
    assert resolved.id == company.id


def test_resolve_existing_company_fuzzy_high_confidence_match(session):
    company = _make_company(session, "ABC Developments Limited")
    session.commit()
    resolved = resolve_existing_company(session, "ABC Developments Ltd")  # legal-suffix variant
    assert resolved is not None
    assert resolved.id == company.id


def test_resolve_existing_company_no_match_returns_none(session):
    _make_company(session, "ABC Developments Limited")
    session.commit()
    resolved = resolve_existing_company(session, "Completely Unrelated Enterprises Limited")
    assert resolved is None


def test_resolve_existing_company_no_companies_at_all_returns_none(session):
    resolved = resolve_existing_company(session, "ABC Developments Limited")
    assert resolved is None


def test_resolve_existing_company_never_creates_a_company_row(session):
    before = session.execute(select(Company)).scalars().all()
    resolve_existing_company(session, "Some Brand New Name Limited")
    after = session.execute(select(Company)).scalars().all()
    assert len(before) == len(after) == 0


def test_no_companies_house_api_call():
    source = inspect.getsource(ce)
    assert "requests.get" not in source
    assert "get_active_officers" not in source
    assert "get_persons_with_significant_control" not in source
    assert "best_match(" not in source  # the CH search-API function - never called here


# ---------------------------------------------------------------------------
# Structural safety
# ---------------------------------------------------------------------------


def test_module_creates_relationships_only_through_the_shared_helper():
    """Exactly one place in this module ever constructs ControlRelationship(...)
    - inside create_control_relationship_if_absent itself - confirming
    this codebase's own 'one persistence path' precedent is followed."""
    source = inspect.getsource(ce)
    assert source.count("= ControlRelationship(") == 1
    assert "rel = ControlRelationship(" in source


def test_relationship_model_has_no_allocation_id_column():
    """Structural proof that allocation-wide control can never be stored
    directly - only Application/Site scope exists on this table."""
    assert "allocation_id" not in ControlRelationship.__table__.columns


def test_evidence_vocabulary_never_uses_current_owner_label():
    """No evidence_category/role CONSTANT anywhere is a bare 'CURRENT_
    OWNER'-style value - the point-in-time honesty lives in the category
    label itself (S106_DEFINED_OWNER etc), never a claim of present-day
    registered ownership."""
    from app.extraction import ownership_control_evidence as oce
    source = inspect.getsource(oce) + inspect.getsource(ce)
    assert "CURRENT_OWNER" not in source
    assert '"CURRENT' not in source


def test_no_openai_in_control_entities_module():
    source = inspect.getsource(ce)
    assert "import openai" not in source.lower()
    assert "OpenAI(" not in source


# ---------------------------------------------------------------------------
# Dry-run report - zero writes, deterministic only
# ---------------------------------------------------------------------------


def test_dry_run_report_certificate_and_s106_counts(session):
    _make_council(session, "testcouncil")
    app1 = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app1.id, "application_form", (
        "Ownership Certificates and Agricultural Land Declaration\n"
        "Please answer the following questions to determine which Certificate of Ownership you need to complete: A, B, C or D.\n"
        "Certificate of ownership - Certificate A\n"
        "I certify that the requirements of Certificate A have been met in respect of this application.\n"
    ))
    app2 = _make_application(session, "testcouncil", "APP/2")
    _make_document(session, app2.id, "s106", (
        'AND (2) ABC Developments Limited (company number 01234567) whose registered office is at '
        '1 High Street (the "Owner"). Title number GM781194.'
    ))
    session.commit()

    report = build_ownership_control_dry_run_report(session)

    assert report["application_forms_evaluated"] == 1
    assert report["certificate_a_count"] == 1
    assert report["s106_documents_evaluated"] == 1
    assert report["s106_explicit_owner_count"] == 1
    assert report["s106_title_numbers_extracted"] == 1
    assert report["applications_with_deterministic_control_evidence"] == 2


def test_dry_run_report_makes_no_writes(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    _make_document(session, app.id, "s106", 'AND (2) ABC Developments Limited (the "Owner").')
    session.commit()

    build_ownership_control_dry_run_report(session)

    assert len(session.new) == 0
    assert len(session.dirty) == 0
    assert len(session.deleted) == 0
    assert session.execute(select(ControlRelationship)).scalars().all() == []


def test_dry_run_report_no_openai_dependency():
    source = inspect.getsource(build_ownership_control_dry_run_report)
    assert "import openai" not in source.lower()
    assert "OpenAI(" not in source


# ---------------------------------------------------------------------------
# North of Mosley Common regression (Stage 4B Section 11)
# ---------------------------------------------------------------------------


def test_north_of_mosley_common_regression(session):
    """Mirrors the real production case: allocation JPA 32 (North of
    Mosley Common, capacity 1,100) related to TWO Sites via
    AllocationSiteRelationship - the Southern Parcel (244 units,
    Taylor Wimpey evidence) and a second Site representing the rest of
    the allocation with ZERO applications/documents at all. A
    ControlRelationship created for the Southern Parcel's application
    must NEVER surface as evidence for the other Site, and there is no
    mechanism anywhere in this task's shipped code that aggregates
    Application/Site-scoped control evidence up to allocation level."""
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "North of Mosley Common", "JPA 32", 1100)

    southern_parcel = _make_site(session, "wigan", "Land North Of Mosley Common South Of The Guided Busway")
    _make_allocation_site_relationship(session, allocation.id, southern_parcel.id)
    southern_app = _make_application(session, "wigan", "A/25/099409/RMMAJ", site_id=southern_parcel.id)
    southern_doc = _make_document(session, southern_app.id, "s106", (
        'AND (2) Taylor Wimpey Manchester Limited (the "Developer"). '
        'The Section 106 Agreement dated 16 September 2024 secures affordable housing.'
    ))
    session.commit()

    rel = create_control_relationship_if_absent(
        session, application_id=southern_app.id, site_id=southern_parcel.id,
        entity_name_raw="Taylor Wimpey Manchester Limited", entity_type="company", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
        extraction_method="deterministic_regex", evidence_document_id=southern_doc.id,
    )
    session.commit()
    assert rel is not None

    # A second Site representing the allocation's residual capacity, with
    # genuinely no applications/documents - the honest UNKNOWN case.
    residual_site = _make_site(session, "wigan", "Remainder of North of Mosley Common allocation")
    _make_allocation_site_relationship(session, allocation.id, residual_site.id)
    session.commit()

    evidence_for_residual_site = session.execute(
        select(ControlRelationship).where(ControlRelationship.site_id == residual_site.id)
    ).scalars().all()
    assert evidence_for_residual_site == []  # no evidence inherited from the other phase

    evidence_for_southern_parcel = session.execute(
        select(ControlRelationship).where(ControlRelationship.site_id == southern_parcel.id)
    ).scalars().all()
    assert len(evidence_for_southern_parcel) == 1
    assert evidence_for_southern_parcel[0].entity_name_raw == "Taylor Wimpey Manchester Limited"

    # Structural guard: no allocation-level aggregation function exists
    # anywhere in the shipped Stage 4B persistence module that would let a
    # caller accidentally read Site-scoped evidence as if it were
    # allocation-wide - it never even imports/joins to LocalPlanSite or
    # AllocationSiteRelationship at all.
    source = inspect.getsource(ce)
    assert "LocalPlanSite" not in source
    assert "AllocationSiteRelationship" not in source


def test_landowner_never_inherited_from_a_different_applications_developer(session):
    """A second, unrelated application on the SAME Site must not
    silently inherit the first application's control evidence - each
    row is scoped to its OWN application."""
    _make_council(session, "wigan")
    site = _make_site(session, "wigan", "some site")
    app1 = _make_application(session, "wigan", "APP/1", site_id=site.id)
    app2 = _make_application(session, "wigan", "APP/2", site_id=site.id)
    session.commit()

    create_control_relationship_if_absent(
        session, application_id=app1.id, site_id=site.id, entity_name_raw="Taylor Wimpey Manchester Limited",
        role="DEVELOPER", evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
        extraction_method="deterministic_regex",
    )
    session.commit()

    app2_evidence = session.execute(
        select(ControlRelationship).where(ControlRelationship.application_id == app2.id)
    ).scalars().all()
    assert app2_evidence == []


# ---------------------------------------------------------------------------
# Multi-Site / multi-party safety (Stage 4B Section 12)
# ---------------------------------------------------------------------------


def test_one_allocation_several_sites_independent_evidence(session):
    _make_council(session, "wigan")
    allocation = _make_allocation(session, "wigan", "Test Allocation", "H3", 500)
    site_a = _make_site(session, "wigan", "Parcel A")
    site_b = _make_site(session, "wigan", "Parcel B")
    _make_allocation_site_relationship(session, allocation.id, site_a.id)
    _make_allocation_site_relationship(session, allocation.id, site_b.id)
    app_a = _make_application(session, "wigan", "APP/A", site_id=site_a.id)
    session.commit()

    create_control_relationship_if_absent(
        session, application_id=app_a.id, site_id=site_a.id, entity_name_raw="Bellway Homes Limited",
        role="DEVELOPER", evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER",
        extraction_method="deterministic_regex",
    )
    session.commit()

    assert session.execute(select(ControlRelationship).where(ControlRelationship.site_id == site_b.id)).scalars().all() == []
    assert len(session.execute(select(ControlRelationship).where(ControlRelationship.site_id == site_a.id)).scalars().all()) == 1


def test_one_site_several_applications_independent_evidence(session):
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    outline_app = _make_application(session, "testcouncil", "OUT/1", site_id=site.id)
    rm_app = _make_application(session, "testcouncil", "RM/1", site_id=site.id)
    session.commit()

    create_control_relationship_if_absent(
        session, application_id=outline_app.id, site_id=site.id, entity_name_raw="ABC Developments Limited",
        role="OWNER", evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER",
        extraction_method="deterministic_regex",
    )
    session.commit()

    rm_app_evidence = session.execute(
        select(ControlRelationship).where(ControlRelationship.application_id == rm_app.id)
    ).scalars().all()
    assert rm_app_evidence == []  # the RM application has no owner evidence of its own - never inherited


def test_several_companies_different_roles_same_application(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    session.commit()

    create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="Big Bank PLC", role="MORTGAGEE",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_MORTGAGEE", extraction_method="deterministic_regex",
    )
    create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="XYZ Homes Limited", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER", extraction_method="deterministic_regex",
    )
    session.commit()

    rows = session.execute(select(ControlRelationship).where(ControlRelationship.application_id == app.id)).scalars().all()
    assert {r.role for r in rows} == {"OWNER", "MORTGAGEE", "DEVELOPER"}
    assert all(r.review_status == "auto_applied" for r in rows)  # no false contradiction across different roles


def test_same_entity_different_roles_coexist(session):
    """The same company can genuinely hold two different roles (e.g. a
    housebuilder is both the S106 Owner AND the Developer at outline
    stage) - both rows must coexist, neither is a 'duplicate'."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    session.commit()

    owner = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    developer = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="DEVELOPER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_DEVELOPER", extraction_method="deterministic_regex",
    )
    session.commit()

    assert owner is not None and developer is not None
    rows = session.execute(select(ControlRelationship).where(ControlRelationship.application_id == app.id)).scalars().all()
    assert len(rows) == 2


def test_private_individual_entity_type_not_forced_into_company(session):
    """A non-company party (entity_type='individual') must be
    representable without a company_id, and never mistakenly linked to
    an unrelated Company row."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    session.commit()

    rel = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="John Smith", entity_type="individual", role="OWNER",
        evidence_basis="manual", evidence_category="MANUAL_NOTE", extraction_method="manual", company_id=None,
    )
    session.commit()

    assert rel.entity_type == "individual"
    assert rel.company_id is None


def test_mortgagee_role_kept_structurally_distinct_from_owner(session):
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    session.commit()

    mortgagee = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="Big Bank PLC", role="MORTGAGEE",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_MORTGAGEE", extraction_method="deterministic_regex",
    )
    session.commit()

    assert mortgagee.role == "MORTGAGEE"
    owner_rows = session.execute(
        select(ControlRelationship).where(ControlRelationship.application_id == app.id, ControlRelationship.role == "OWNER")
    ).scalars().all()
    assert owner_rows == []  # the mortgagee row is never also counted as an owner row


def test_historical_evidence_not_labelled_current_ownership(session):
    """The evidence_category itself must carry the point-in-time-honest
    label - never a bare 'CURRENT_OWNER'-style value."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    session.commit()

    rel = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    session.commit()

    assert rel.evidence_category == "S106_DEFINED_OWNER"
    assert "CURRENT" not in rel.evidence_category


# ---------------------------------------------------------------------------
# Final amendment: temporal evidence - evidence_date is distinct from
# created_at (when PropertyAIgent wrote the row) and is NEVER derived from
# Document.downloaded_at (when PropertyAIgent fetched the file).
# ---------------------------------------------------------------------------


def test_created_at_and_evidence_date_are_semantically_distinct(session):
    """created_at is always set (row-creation timestamp); evidence_date
    defaults to None and is a completely independent field - setting one
    must never imply or populate the other."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    session.commit()

    rel = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
    )
    session.commit()

    assert rel.created_at is not None
    assert rel.evidence_date is None
    assert rel.created_at != rel.evidence_date


def test_evidence_date_may_safely_be_null(session):
    """NULL is the normal, correct value for every row this task's own
    deterministic extractors create - it must never be treated as an
    error state or as 'no evidence exists' (review_status/evidence_
    snippet/evidence_document_id remain the source of truth for that)."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = _make_document(session, app.id, "s106", "some text")
    session.commit()

    rel = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
        evidence_document_id=doc.id, evidence_snippet="the Owner is ABC Developments Limited",
    )
    session.commit()

    assert rel.evidence_date is None
    assert rel.evidence_document_id == doc.id  # evidence itself is still fully present
    assert rel.evidence_snippet


def test_downloaded_at_never_substituted_for_evidence_date(session):
    """Stage 4B's own deterministic extractors/persistence helper must
    never derive evidence_date from Document.downloaded_at, even when a
    downloaded_at value is genuinely available on the source document."""
    _make_council(session, "testcouncil")
    app = _make_application(session, "testcouncil", "APP/1")
    doc = Document(
        application_id=app.id, doc_type="s106", extracted_text="some text", text_extracted=True,
        downloaded_at=dt.datetime(2024, 9, 16, tzinfo=dt.timezone.utc),
    )
    session.add(doc)
    session.commit()

    rel = create_control_relationship_if_absent(
        session, application_id=app.id, entity_name_raw="ABC Developments Limited", role="OWNER",
        evidence_basis="s106_defined_role", evidence_category="S106_DEFINED_OWNER", extraction_method="deterministic_regex",
        evidence_document_id=doc.id,
    )
    session.commit()

    assert doc.downloaded_at is not None  # the document genuinely has one
    assert rel.evidence_date is None  # never copied across


def test_create_control_relationship_if_absent_never_derives_evidence_date_from_downloaded_at():
    """Structural guard: the persistence helper's own CODE (not its
    docstring, which legitimately explains why it must never do this)
    never reads Document.downloaded_at at all."""
    source = inspect.getsource(ce.create_control_relationship_if_absent)
    # Strip the leading docstring (delimited by the first pair of `"""`)
    # before checking - only the executable body is checked below.
    parts = source.split('"""')
    body_only = parts[-1] if len(parts) >= 3 else source
    assert ".downloaded_at" not in body_only


def test_future_authoritative_evidence_can_carry_an_evidence_date(session):
    """Proves the field is usable by a FUTURE authoritative source (e.g.
    HM Land Registry) without any schema change - not executed/called in
    this task, only demonstrated as a direct persistence call."""
    _make_council(session, "testcouncil")
    site = _make_site(session, "testcouncil", "some site")
    session.commit()

    land_registry_date = dt.datetime(2026, 1, 15, tzinfo=dt.timezone.utc)
    rel = create_control_relationship_if_absent(
        session, application_id=None, site_id=site.id, entity_name_raw="ABC Land Ltd",
        entity_type="company", role="OWNER", evidence_basis="hm_land_registry",
        evidence_category="HM_LAND_REGISTRY_TITLE", extraction_method="manual",
        confidence="authoritative", evidence_document_id=None, title_number="GM123456",
        evidence_date=land_registry_date,
    )
    session.commit()

    assert rel.evidence_date == land_registry_date
    assert rel.evidence_document_id is None  # no Document row needed for this source
    assert rel.confidence == "authoritative"


def test_deterministic_extractors_never_populate_evidence_date():
    """Structural guard: this task's own extraction module never produces
    a date value at all (no datetime import, no date parsing) - matching
    the instruction that no speculative document-text date parsing is
    attempted in this amendment."""
    from app.extraction import ownership_control_evidence as oce
    source = inspect.getsource(oce)
    assert "evidence_date" not in source
    assert "import datetime" not in source and "from datetime" not in source
