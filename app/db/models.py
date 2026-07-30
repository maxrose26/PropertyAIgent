from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Council(Base):
    __tablename__ = "councils"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(300))
    date_field_mode: Mapped[str] = mapped_column(String(20))  # received | validated
    doc_system: Mapped[str] = mapped_column(String(20))  # idox | idox_anite
    anite_base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    unit_threshold: Mapped[int] = mapped_column(Integer, default=10)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    applications: Mapped[list["Application"]] = relationship(back_populates="council")


class Site(Base):
    """A physical site, consolidated from one or more planning `applications`
    that turn out to refer to the same place (e.g. an EIA screening opinion,
    a scoping opinion, and an ancillary certificate for the same scheme -
    see app.pipeline.site_linking)."""

    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    council_code: Mapped[str] = mapped_column(ForeignKey("councils.code"))
    canonical_address: Mapped[str] = mapped_column(String(500), index=True)
    display_address: Mapped[str] = mapped_column(Text)
    postcode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    build_status: Mapped[str | None] = mapped_column(String(30), nullable=True)  # not_started | partially_complete | complete | unknown
    build_status_checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    epc_dwellings_found: Mapped[int | None] = mapped_column(Integer, nullable=True)

    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    applications: Mapped[list["Application"]] = relationship(
        back_populates="site", foreign_keys="Application.site_id"
    )


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("council_code", "reference", name="uq_council_reference"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    council_code: Mapped[str] = mapped_column(ForeignKey("councils.code"))

    reference: Mapped[str] = mapped_column(String(100), index=True)
    alternative_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decision_issued_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    application_received: Mapped[str | None] = mapped_column(String(50), nullable=True)
    application_validated: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ward: Mapped[str | None] = mapped_column(String(200), nullable=True)
    case_officer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    applicant_name_raw: Mapped[str | None] = mapped_column(String(300), nullable=True)
    applicant_address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    summary_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    further_info_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    documents_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    keyval: Mapped[str | None] = mapped_column(String(200), nullable=True)

    estimated_unit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    application_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opportunity_classification: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Unit-count confirmation gate (see app.pipeline.run_weekly.stage_confirm_units).
    # Applications only reach here with estimated_unit_count already set (a
    # confident regex match on the portal proposal text) or None (only
    # qualified via a REVIEW_KEYWORDS guess - e.g. "residential development"
    # with no number stated anywhere). The latter get one cheap check
    # (application form, then planning statement) before the full
    # document-download + 3-LLM extraction pipeline is allowed to run at all.
    unit_confirmation_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # null (portal regex already confirmed it, or not checked yet) |
    # confirmed_qualifying | confirmed_disqualified | undetermined

    scrape_batch_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    site_link_method: Mapped[str | None] = mapped_column(String(30), nullable=True)  # exact_address | parent_reference | suggested_fuzzy | created
    site_link_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # only meaningful for suggested_fuzzy
    suggested_site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), nullable=True)  # candidate site awaiting Confirm/Reject when method=suggested_fuzzy

    council: Mapped["Council"] = relationship(back_populates="applications")
    site: Mapped["Site | None"] = relationship(back_populates="applications", foreign_keys=[site_id])
    suggested_site: Mapped["Site | None"] = relationship(foreign_keys=[suggested_site_id])
    documents: Mapped[list["Document"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    scheme_intelligence: Mapped["SchemeIntelligence | None"] = relationship(
        back_populates="application", cascade="all, delete-orphan", uselist=False
    )
    application_companies: Mapped[list["ApplicationCompany"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))

    doc_type: Mapped[str] = mapped_column(String(50), default="other")  # standardised type, see extraction.pdf_text
    document_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    text_extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    downloaded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    application: Mapped["Application"] = relationship(back_populates="documents")


class SchemeIntelligence(Base):
    """One row per qualifying (10+ unit) application - the reconciled output."""

    __tablename__ = "scheme_intelligence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)

    # Housing mix (regex pass)
    total_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    affordable_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    private_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    affordable_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    affordable_tenure_split: Mapped[str | None] = mapped_column(Text, nullable=True)
    housing_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Affordable evidence classifier (LLM pass) - these are the values that win reconciliation
    affordable_data_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    application_context_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    affordable_classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    affordable_classification_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    affordable_classification_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Site development intelligence (LLM pass)
    site_area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    density_dph: Mapped[float | None] = mapped_column(Float, nullable=True)
    development_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    housing_typology: Mapped[str | None] = mapped_column(String(200), nullable=True)
    specialist_housing_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    allocation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    existing_use: Mapped[str | None] = mapped_column(String(200), nullable=True)
    proposed_use: Mapped[str | None] = mapped_column(String(200), nullable=True)
    site_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Project entities (LLM pass)
    applicant_company: Mapped[str | None] = mapped_column(String(300), nullable=True)
    developer: Mapped[str | None] = mapped_column(String(300), nullable=True)
    landowner: Mapped[str | None] = mapped_column(String(300), nullable=True)
    site_owner: Mapped[str | None] = mapped_column(String(300), nullable=True)
    planning_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    architect: Mapped[str | None] = mapped_column(String(300), nullable=True)
    housing_association: Mapped[str | None] = mapped_column(String(300), nullable=True)
    registered_provider: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Distinguishes "documents don't mention an RP at all" from "an RP is
    # promised but not yet named" (common at outline/full stage before a
    # nominations agreement - e.g. "to be transferred to a Registered
    # Provider" with no company stated) from "a specific RP is named" - a
    # blank registered_provider field alone can't tell these apart, and a
    # user reading "RP: None" has no way to know whether that's worth
    # chasing (nomination pending) or a dead end (no RP involved at all).
    registered_provider_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # named | not_yet_confirmed | not_applicable | unknown
    contractor: Mapped[str | None] = mapped_column(String(300), nullable=True)
    entity_source_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The LLM's own reasoning about entity roles (e.g. why developer was
    # left null despite an applicant being named - agent vs developer
    # judgment calls) - the schema always asks for this, but it was
    # silently discarded here until now, so that reasoning never reached
    # the database or the UI even when the model had genuinely useful
    # context to explain an otherwise-unexplained blank field.
    entity_relationship_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Reconciled final values (priority: classified > regex > portal metadata)
    total_units_final: Mapped[int | None] = mapped_column(Integer, nullable=True)
    affordable_units_final: Mapped[int | None] = mapped_column(Integer, nullable=True)
    private_units_final: Mapped[int | None] = mapped_column(Integer, nullable=True)
    affordable_percentage_final: Mapped[float | None] = mapped_column(Float, nullable=True)
    affordable_tenure_split_final: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set only when application_category == "external_consultation" - our
    # copy of the application is just a neighbouring authority's consultation
    # notice, so the real scheme data lives on another council's portal
    # entirely. Holds "<council name> (ref <their reference>)".
    external_consultation_source: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Set when affordable_data_status resolved to "no affordable required"
    # (or "offsite/commuted sum") but the classifier's own affordable
    # percentage field was non-empty anyway - a self-contradiction confirmed
    # in a real case (PA/2026/0539) where the reason text described "a
    # minimum of 20% affordable housing... proposed, but no specific
    # number... stated". Rather than silently resolve that to a confident
    # 0%, the split is left unresolved and this note explains why - surfaced
    # in the UI and folded into needs_manual_review.
    affordable_status_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    unit_total_check: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_total_difference: Mapped[float | None] = mapped_column(Float, nullable=True)
    affordable_percentage_check: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_reconciliation_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    large_scheme_50_plus_units: Mapped[bool] = mapped_column(Boolean, default=False)
    major_scheme_25_plus_units: Mapped[bool] = mapped_column(Boolean, default=False)
    major_scheme_10_plus_units: Mapped[bool] = mapped_column(Boolean, default=False)
    affordable_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    developer_info_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    data_quality_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    core_intelligence_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    application: Mapped["Application"] = relationship(back_populates="scheme_intelligence")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ch_company_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)

    name_raw: Mapped[str] = mapped_column(String(300))
    name_normalized: Mapped[str] = mapped_column(String(300), index=True)
    ch_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ch_incorporation_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ch_registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    ch_match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    verified_domain: Mapped[str | None] = mapped_column(String(200), nullable=True)
    domain_verification_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Set when verified_domain was found via an active corporate PSC's name
    # rather than the company's own - common for SPV-style applicant/
    # developer companies with no web presence of their own (see
    # contact_pipeline.enrich_company). Holds the parent company's name so
    # the UI can show why the domain belongs to a different-looking company.
    domain_matched_via_parent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # openai | serpapi | serpapi_parent - which mechanism found verified_domain,
    # for transparency (see contact_pipeline.enrich_company's ordering).
    domain_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(300), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    officers: Mapped[list["Officer"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    persons_with_significant_control: Mapped[list["PersonWithSignificantControl"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    application_companies: Mapped[list["ApplicationCompany"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class ApplicationCompany(Base):
    """Link table: which company plays which role on which application."""

    __tablename__ = "application_companies"
    __table_args__ = (UniqueConstraint("application_id", "company_id", "role", name="uq_app_company_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    role: Mapped[str] = mapped_column(String(50))  # applicant | developer | agent | landowner | architect | housing_association

    application: Mapped["Application"] = relationship(back_populates="application_companies")
    company: Mapped["Company"] = relationship(back_populates="application_companies")


class Officer(Base):
    __tablename__ = "officers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    full_name: Mapped[str] = mapped_column(String(300))
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    appointed_on: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Other companies this person directs, fetched once at enrichment time
    # via Companies House's officer.appointments cross-reference - reveals
    # SPV networks a single company lookup can't show. Comma-joined company
    # names, e.g. "Front Holdings Ltd, Global Titans Organisers Limited".
    other_appointments: Mapped[str | None] = mapped_column(Text, nullable=True)
    resigned_on: Mapped[str | None] = mapped_column(String(50), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="officers")


class PersonWithSignificantControl(Base):
    """Companies House PSC data - who actually owns/controls a company,
    distinct from (and sometimes completely different to) its directors.
    Confirmed a real case: a company's only director owned 0% of it, while
    the actual PSC (75-100% shares/voting rights, right to appoint/remove
    directors) wasn't listed as a director at all."""

    __tablename__ = "persons_with_significant_control"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(50))  # individual | corporate-entity | legal-person | super-secure
    natures_of_control: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-joined
    ceased: Mapped[bool] = mapped_column(Boolean, default=False)
    # Only set when kind is corporate/legal-entity - the owner is itself a
    # company, which can be looked up in turn to trace the chain further.
    identification_company_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="persons_with_significant_control")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    full_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    email: Mapped[str | None] = mapped_column(String(300), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(300), nullable=True)

    source: Mapped[str] = mapped_column(String(30))  # apollo | hunter | generated | news_article
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # set for source=news_article
    # The quote/context an AI web search cited as evidence this person is
    # connected to the specific scheme - set for source=news_article, where
    # (unlike a direct Apollo/Hunter directory match) the evidence itself is
    # the whole basis for trusting the contact, not just a byproduct.
    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)  # opt-out / do-not-contact flag

    # deal-tracking (single-user CRM lite, used by the Streamlit viewer)
    outreach_status: Mapped[str | None] = mapped_column(String(30), nullable=True)  # contacted | interested | rejected

    company: Mapped["Company"] = relationship(back_populates="contacts")


class Settings(Base):
    """Single-row table for the personal spend-throttle credit counter. Not
    real billing - this is a single-user tool, just a way to see/limit your
    own Apollo/Hunter/OpenAI usage from the on-demand enrichment button."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    credits_remaining: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
