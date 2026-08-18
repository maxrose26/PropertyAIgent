"""Stage 4B deterministic extraction tests - app.extraction.ownership_
control_evidence. Every function under test is pure (no Session, no I/O),
so these tests construct lightweight fake Document-shaped objects rather
than touching the database at all.
"""
from __future__ import annotations

import inspect

from app.extraction import ownership_control_evidence as oce
from app.extraction.ownership_control_evidence import (
    CERTIFICATE_UNKNOWN,
    NO_CERTIFICATE_EVIDENCE,
    detect_ownership_certificate,
    extract_s106_defined_parties,
    extract_s106_title_numbers,
    resolve_certificate_a_applicant_identity,
)


class FakeDocument:
    def __init__(self, id: int, application_id: int, extracted_text: str | None):
        self.id = id
        self.application_id = application_id
        self.extracted_text = extracted_text


_CERT_BOILERPLATE = (
    "Ownership Certificates and Agricultural Land Declaration\n"
    "Certificates under Article 14 - Town and Country Planning (Development Management Procedure)\n"
    "(England) Order 2015 (as amended)\n"
    "Please answer the following questions to determine which Certificate of Ownership you need to complete: A, B, C or D.\n"
    "Is the applicant the sole owner of all the land to which this application relates; and has the applicant "
    "been the sole owner for more than 21 days?\nYes\nNo\n"
)


def _cert_document(letter: str) -> FakeDocument:
    body = _CERT_BOILERPLATE + (
        f"\n\nSome further unrelated form content here to add realistic spacing between sections of the document.\n\n"
        f"Certificate of ownership - Certificate {letter}\n"
        f"Town and Country Planning (Development Management Procedure) (England) Order 2015 (as amended)\n"
        f"I certify that the requirements of Certificate {letter} have been met in respect of this application.\n"
    )
    return FakeDocument(1, 100, body)


# ---------------------------------------------------------------------------
# Certificate detection
# ---------------------------------------------------------------------------


def test_certificate_boilerplate_alone_does_not_classify():
    doc = FakeDocument(1, 100, _CERT_BOILERPLATE)
    result = detect_ownership_certificate(doc)
    assert result.certificate_type == CERTIFICATE_UNKNOWN
    assert result.certificate_type not in ("CERTIFICATE_A", "CERTIFICATE_B", "CERTIFICATE_C", "CERTIFICATE_D")


def test_certificate_a_positive_detection():
    result = detect_ownership_certificate(_cert_document("A"))
    assert result.certificate_type == "CERTIFICATE_A"
    assert result.confidence == "high"
    assert result.snippet


def test_certificate_b_positive_detection():
    result = detect_ownership_certificate(_cert_document("B"))
    assert result.certificate_type == "CERTIFICATE_B"


def test_certificate_c_positive_detection():
    result = detect_ownership_certificate(_cert_document("C"))
    assert result.certificate_type == "CERTIFICATE_C"


def test_certificate_d_positive_detection():
    result = detect_ownership_certificate(_cert_document("D"))
    assert result.certificate_type == "CERTIFICATE_D"


def test_ambiguous_multiple_confident_letters_fails_closed():
    body = _CERT_BOILERPLATE + (
        "\n\nCertificate of ownership - Certificate A\n"
        "I certify that the requirements of Certificate A have been met.\n\n"
        "Certificate of ownership - Certificate B\n"
        "I certify that the requirements of Certificate B have also been met due to a scanning duplication error.\n"
    )
    result = detect_ownership_certificate(FakeDocument(1, 100, body))
    assert result.certificate_type == CERTIFICATE_UNKNOWN
    assert result.confidence is None


def test_no_certificate_section_at_all():
    doc = FakeDocument(1, 100, "This is a design and access statement with no certificate content whatsoever.")
    result = detect_ownership_certificate(doc)
    assert result.certificate_type == NO_CERTIFICATE_EVIDENCE


def test_empty_document_text_returns_none():
    assert detect_ownership_certificate(FakeDocument(1, 100, None)) is None
    assert detect_ownership_certificate(FakeDocument(1, 100, "   ")) is None


# ---------------------------------------------------------------------------
# S106 title number extraction
# ---------------------------------------------------------------------------


def test_s106_title_number_extraction():
    text = "The Owner is the registered proprietor with absolute title of the Site under Land Registry title number GM781194."
    hits = extract_s106_title_numbers(FakeDocument(2, 100, text))
    assert len(hits) == 1
    assert hits[0].title_number == "GM781194"


def test_s106_multiple_distinct_title_numbers():
    text = (
        "registered proprietor with title absolute of freehold title number MAN108197 and by virtue of being the "
        "registered proprietor with good title of leasehold title number MAN108147."
    )
    hits = extract_s106_title_numbers(FakeDocument(2, 100, text))
    numbers = {h.title_number for h in hits}
    assert numbers == {"MAN108197", "MAN108147"}


# ---------------------------------------------------------------------------
# S106 defined-role party extraction
# ---------------------------------------------------------------------------


def test_s106_explicit_owner_defined_by_recital():
    text = (
        'THIS AGREEMENT is made BETWEEN (1) Example Council and (2) ABC Developments Limited '
        '(company number 01234567) whose registered office is at 1 High Street, Wigan (the "Owner").'
    )
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].role == "OWNER"
    assert hits[0].entity_name_raw == "ABC Developments Limited"
    assert hits[0].evidence_category == "S106_DEFINED_OWNER"


def test_s106_explicit_owner_defined_by_means_clause():
    text = '"the Owner" means ABC Developments Limited.'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].role == "OWNER"
    assert hits[0].entity_name_raw == "ABC Developments Limited"


def test_s106_explicit_developer_role():
    text = 'AND (3) XYZ Homes Limited whose registered office is at 2 Park Road (the "Developer").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].role == "DEVELOPER"
    assert hits[0].evidence_category == "S106_DEFINED_DEVELOPER"


def test_s106_mortgagee_never_classified_as_owner():
    text = 'AND (4) Big Bank PLC (the "Mortgagee").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].role == "MORTGAGEE"
    assert hits[0].role != "OWNER"
    assert hits[0].evidence_category == "S106_DEFINED_MORTGAGEE"


def test_s106_incidental_owner_mention_not_evidence():
    """'successors in title to the Owner' presupposes a definition
    established elsewhere - it must never itself create a NEW party
    attribution (Stage 4B Section 4's own explicit example)."""
    text = "The rights and obligations pass to successors in title to the Owner under this Deed."
    assert extract_s106_defined_parties(FakeDocument(3, 100, text)) == []


def test_s106_owner_shall_pay_clause_not_evidence():
    text = "The Owner shall pay to the Council the Monitoring Fee on or before completion."
    assert extract_s106_defined_parties(FakeDocument(3, 100, text)) == []


def test_s106_description_style_means_clause_rejected():
    """A definitions clause that defines the term as a DESCRIPTION rather
    than naming an organisation must never be reported as if the
    description text were itself a party's name."""
    text = '"the Owner" means the person(s) named in Schedule 1 hereto.'
    assert extract_s106_defined_parties(FakeDocument(3, 100, text)) == []


def test_s106_address_not_mistaken_for_party_name():
    """Regression for a real false positive found against production S106
    text during development: a registered-office ADDRESS following the
    real company name must never be picked over (or instead of) the
    actual company name."""
    text = (
        'AND (2) Example Developments Limited whose registered office is at Town Hall, '
        'Petersgate, Stockport, England, SK1 1AR (the "Developer").'
    )
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert "Petersgate" not in hits[0].entity_name_raw
    assert "SK1 1AR" not in hits[0].entity_name_raw
    assert hits[0].entity_name_raw == "Example Developments Limited"


def test_s106_company_number_phrase_not_mistaken_for_party_name():
    """Regression for a real false positive found against production S106
    text during development: the literal phrase 'Company number 12345678'
    must never be extracted as if it were the party's own name."""
    text = 'AND (2) BINGLEY UK DEVELOPMENTS LIMITED (Company number 12851676) (the "Owner").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "BINGLEY UK DEVELOPMENTS LIMITED"
    assert "Company number" not in hits[0].entity_name_raw


def test_s106_no_organisation_suffix_found_reports_nothing():
    """Fail closed: if no strong legal-entity-suffixed name is found near
    the defining term at all, this module reports nothing rather than
    guessing at a person's name or an unrelated phrase."""
    text = 'AND (2) John Smith of 4 Acacia Avenue (the "Owner").'
    assert extract_s106_defined_parties(FakeDocument(3, 100, text)) == []


# ---------------------------------------------------------------------------
# Final amendment: S106 entity-name cleanliness - a legal-entity suffix is
# always name-terminal in real UK naming, so anything following it within
# the same candidate (a registered-office/"of <address>" clause) is
# isolated away rather than persisted as part of the entity name.
# ---------------------------------------------------------------------------


def test_s106_limited_followed_by_address_is_cleaned():
    text = 'AND (2) Example Developments Limited of 5 High Street, Manchester, M1 1AA (the "Owner").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "Example Developments Limited"
    assert "High Street" not in hits[0].entity_name_raw
    assert "Manchester" not in hits[0].entity_name_raw


def test_s106_ltd_followed_by_address_is_cleaned():
    text = 'AND (2) Northern Homes Ltd of Unit 4 Business Park, Bolton (the "Developer").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "Northern Homes Ltd"
    assert "Business Park" not in hits[0].entity_name_raw


def test_s106_llp_followed_by_address_is_cleaned():
    text = 'AND (2) Riverside Partners LLP of Riverside House, Salford Quays (the "Owner").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "Riverside Partners LLP"
    assert "Salford Quays" not in hits[0].entity_name_raw


def test_s106_plc_followed_by_address_is_cleaned():
    text = 'AND (4) Lloyds Bank PLC of 25 Gresham Street, London (the "Mortgagee").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "Lloyds Bank PLC"
    assert "Gresham Street" not in hits[0].entity_name_raw


def test_s106_council_followed_by_address_is_cleaned():
    """The real production example found during Stage 4B development:
    'WIGAN BOROUGH COUNCIL of Town Hall Library Street Wigan WN1 1YN'."""
    text = 'AND (1) WIGAN BOROUGH COUNCIL of Town Hall Library Street Wigan WN1 1YN and (2) Example Developments Limited (the "Owner").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "Example Developments Limited"  # the actually-defined Owner, not the Council recital


def test_s106_council_itself_as_the_defined_party_is_cleaned():
    text = 'AND (2) WIGAN BOROUGH COUNCIL of Town Hall Library Street Wigan WN1 1YN (the "Owner").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "WIGAN BOROUGH COUNCIL"
    assert "Town Hall" not in hits[0].entity_name_raw
    assert "WN1" not in hits[0].entity_name_raw


def test_s106_means_clause_address_is_also_cleaned():
    text = '"the Developer" means XYZ Homes Limited of 2 Park Road, Manchester.'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "XYZ Homes Limited"
    assert "Park Road" not in hits[0].entity_name_raw


def test_s106_legitimate_multiword_name_with_no_address_is_unaffected():
    """A legitimate name with ordinary words and NO trailing address must
    never be truncated - the cleaning only ever fires on text that
    actually follows the suffix word within the same candidate."""
    text = 'AND (2) Trafford Housing Trust Limited (the "Owner").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "Trafford Housing Trust Limited"


def test_s106_legitimate_name_with_of_before_suffix_is_unaffected():
    """'of' appearing BEFORE the suffix word, as part of the entity's own
    name, must never be affected - only text AFTER the suffix is ever
    isolated away."""
    text = 'AND (2) Duchy of Lancaster Estates Limited (the "Owner").'
    hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
    assert len(hits) == 1
    assert hits[0].entity_name_raw == "Duchy of Lancaster Estates Limited"


def test_s106_entity_cleanliness_invariant_no_address_words_in_any_production_style_hit():
    """Structural invariant check across several realistic shapes at
    once: nothing persisted ever contains an address-shaped tail."""
    samples = [
        'AND (2) Alpha Construction Limited of 1 Foundation Way, Leeds (the "Owner").',
        'AND (3) Beta Estates LLP of Beta House, York Road (the "Developer").',
        'AND (4) Gamma Finance PLC of Gamma Tower, Leeds (the "Mortgagee").',
    ]
    for text in samples:
        hits = extract_s106_defined_parties(FakeDocument(3, 100, text))
        assert len(hits) == 1
        assert " of " not in hits[0].entity_name_raw
        assert "," not in hits[0].entity_name_raw


def test_s106_empty_document_text_returns_empty_lists():
    assert extract_s106_defined_parties(FakeDocument(3, 100, None)) == []
    assert extract_s106_title_numbers(FakeDocument(3, 100, "")) == []


# ---------------------------------------------------------------------------
# Structural safety: this module never conflates applicant/agent with
# ownership/developer roles, since it never even reads those fields.
# ---------------------------------------------------------------------------


def test_certificate_and_s106_functions_never_read_applicant_or_agent_fields():
    """The CERTIFICATE-TYPE and S106 extraction functions specifically
    (not the whole module - see the Stage 4B.1 note below) extract ONLY
    from Certificate/S106 document text - they structurally cannot
    conflate 'applicant' or 'planning agent' with 'developer'/'owner'."""
    for fn in (detect_ownership_certificate, extract_s106_defined_parties, extract_s106_title_numbers):
        source = inspect.getsource(fn)
        assert "applicant_name_raw" not in source
        assert "applicant_company" not in source
        assert "planning_agent" not in source
        assert "SchemeIntelligence" not in source


def test_module_never_reads_scheme_intelligence_ai_derived_fields():
    """Stage 4B.1 final amendment note: resolve_certificate_a_applicant_
    identity DOES now legitimately read Application.applicant_name_raw
    (the raw portal-scraped field, as a conservative same-form-confirmed
    fallback only - see that function's own docstring) - this is an
    intentional, narrowly-scoped exception introduced by this amendment,
    NOT a regression of the module's own 'never conflate applicant with
    developer' discipline. What must NEVER be true, before or after this
    amendment: the module never reads the AI-DERIVED SchemeIntelligence
    fields (applicant_company/planning_agent) at all - those remain a
    completely different evidence path, reserved for a future Stage 4C."""
    source = inspect.getsource(oce)
    assert "SchemeIntelligence" not in source
    assert "applicant_company" not in source
    assert "planning_agent" not in source
    # applicant_name_raw IS now read - deliberately, only within
    # resolve_certificate_a_applicant_identity, verified separately below.
    assert "applicant_name_raw" in inspect.getsource(resolve_certificate_a_applicant_identity)
    for fn in (detect_ownership_certificate, extract_s106_defined_parties, extract_s106_title_numbers):
        assert "applicant_name_raw" not in inspect.getsource(fn)


def test_no_openai_or_external_api_dependency():
    """Same 'discuss vs invoke' distinction this codebase's other no-
    OpenAI structural tests already draw (e.g. app.policy.allocation_
    evidence_scan's own tests) - this module's docstring legitimately
    DISCUSSES OpenAI/Companies House/Land Registry while explaining it
    never calls them; only actual invocation patterns are checked here."""
    source = inspect.getsource(oce)
    assert "import openai" not in source.lower()
    assert "OpenAI(" not in source
    assert "from openai" not in source.lower()
    assert "import requests" not in source.lower()
    import_lines = [ln for ln in source.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert not any("companies_house" in ln.lower() for ln in import_lines)


# ---------------------------------------------------------------------------
# Stage 4B.1 final amendment: Certificate-A applicant identity resolution
# ---------------------------------------------------------------------------


class FakeApplication:
    def __init__(self, id: int, applicant_name_raw: str | None):
        self.id = id
        self.applicant_name_raw = applicant_name_raw


def _form(applicant_block: str = "", *, include_agent: bool = True) -> str:
    text = applicant_block
    if include_agent:
        text += "\nAgent Details\nCompany Name\nSome Agent LLP\nAddress\n"
    return text


def test_resolve_identity_same_form_company_name():
    form = _form("Applicant Details\nName/Company\nTitle\nFirst name\nSurname\nCompany Name\nABC Developments Limited\nAddress\n")
    doc = FakeDocument(1, 100, form)
    app = FakeApplication(100, None)
    result = resolve_certificate_a_applicant_identity(doc, app)
    assert result.resolved_name == "ABC Developments Limited"
    assert result.entity_type == "company"
    assert result.method == "same_form_company_name"


def test_resolve_identity_no_applicant_details_section_is_unresolved():
    doc = FakeDocument(1, 100, "This document has no Applicant Details section at all.")
    app = FakeApplication(100, "ABC Developments Limited")
    result = resolve_certificate_a_applicant_identity(doc, app)
    assert result.method == "unresolved"
    assert result.resolved_name is None


def test_resolve_identity_agent_company_name_never_mistaken_for_applicants():
    """The Applicant Details section's own bound (ending at Agent
    Details) must prevent the AGENT's Company Name from ever being
    picked up as if it were the applicant's."""
    form = (
        "Applicant Details\nName/Company\nTitle\nFirst name\nSurname\nCompany Name\nAddress\n"
        "Agent Details\nName/Company\nTitle\nFirst name\nSurname\nCompany Name\nWrong Agent Limited\nAddress\n"
    )
    doc = FakeDocument(1, 100, form)
    app = FakeApplication(100, None)
    result = resolve_certificate_a_applicant_identity(doc, app)
    assert result.method == "unresolved"
    assert result.resolved_name != "Wrong Agent Limited"


def test_resolve_identity_individual_surname_duplicated_into_company_name_field():
    """Real production edge case confirmed against live data: an
    individual applicant's own Surname is duplicated into the form's
    'Company Name' field - must resolve to the full individual name,
    never a bare surname treated as a company."""
    form = _form(
        "Applicant Details\nName/Company\nTitle\nMr\nFirst name\nRob\nSurname\nWatson\n"
        "Care of Agent\nCompany Name\nWatson\nAddress\n"
    )
    doc = FakeDocument(1, 100, form)
    app = FakeApplication(100, None)
    result = resolve_certificate_a_applicant_identity(doc, app)
    assert result.resolved_name == "Rob Watson"
    assert result.entity_type == "individual"
    assert result.method == "same_form_individual_name"


def test_resolve_identity_form_and_raw_conflict_is_unresolved():
    form = _form("Applicant Details\nName/Company\nTitle\nFirst name\nSurname\nCompany Name\nABC Developments Limited\nAddress\n")
    doc = FakeDocument(1, 100, form)
    app = FakeApplication(100, "Completely Different Holdings Limited")
    result = resolve_certificate_a_applicant_identity(doc, app)
    assert result.method == "unresolved"
    assert result.resolved_name is None


def test_resolve_identity_form_and_raw_agree_confirms():
    form = _form("Applicant Details\nName/Company\nTitle\nFirst name\nSurname\nCompany Name\nABC Developments Limited\nAddress\n")
    doc = FakeDocument(1, 100, form)
    app = FakeApplication(100, "ABC Developments Limited")
    result = resolve_certificate_a_applicant_identity(doc, app)
    assert result.method == "same_form_company_name"
    assert result.resolved_name == "ABC Developments Limited"


def test_resolve_identity_raw_fallback_confirmed_within_applicant_section():
    """No genuine Company Name/individual name extractable from the
    form, but applicant_name_raw IS conservatively found present within
    the Applicant Details section's own text."""
    form = _form(
        "Applicant Details\nName/Company\nTitle\nFirst name\nSurname\nCompany Name\nAddress\n"
        "Address line 1\nc/o Fallback Developments Limited\n"
    )
    doc = FakeDocument(1, 100, form)
    app = FakeApplication(100, "Fallback Developments Limited")
    result = resolve_certificate_a_applicant_identity(doc, app)
    assert result.method == "applicant_name_raw_confirmed_in_form"
    assert result.resolved_name == "Fallback Developments Limited"


def test_resolve_identity_raw_present_but_not_in_form_is_unresolved():
    form = _form("Applicant Details\nName/Company\nTitle\nFirst name\nSurname\nCompany Name\nAddress\n")
    doc = FakeDocument(1, 100, form)
    app = FakeApplication(100, "Nowhere Near Limited")
    result = resolve_certificate_a_applicant_identity(doc, app)
    assert result.method == "unresolved"


def test_resolve_identity_empty_document_text_is_unresolved():
    doc = FakeDocument(1, 100, None)
    app = FakeApplication(100, "ABC Developments Limited")
    result = resolve_certificate_a_applicant_identity(doc, app)
    assert result.method == "unresolved"
    assert result.resolved_name is None
