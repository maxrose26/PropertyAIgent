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

    # AI-narrated synthesis across every linked application (phases, progress
    # filings, lapse/build status, planning stage, expected decision date) -
    # see app.reporting.scheme_summary. Regenerated weekly by the pipeline,
    # not on every page view - see app.pipeline.run_weekly.
    # stage_generate_scheme_summaries.
    status_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_summary_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Manual review kill-switch - a human reviewing the AI status summary
    # confirms this isn't actually a genuine residential scheme (e.g. the
    # regex/AI qualification pipeline let through something that turns out
    # non-residential on closer reading). Excluded from search results by
    # default rather than deleted, so the decision and its reasoning are
    # kept - see app.ui.streamlit_app's "Show excluded sites" toggle.
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    excluded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    applications: Mapped[list["Application"]] = relationship(
        back_populates="site", foreign_keys="Application.site_id"
    )


class LocalPlan(Base):
    """One individual Local Plan or plan version for a council - the
    plan-level entity that sits above individual site Allocations
    (LocalPlanSite). Introduced in the Policy Intelligence Foundation sprint
    (specifications/004-core-domain-model.md's "Policy" domain object) to
    give a Local Plan an independent lifecycle - status, timetable, housing
    requirement - rather than the plan being just a name/status string
    repeated on every allocation row, as it was in the original single-
    council pilot. A council may have more than one LocalPlan row over time
    (a superseded plan and its adopted successor), and in principle more
    than one live at once during a transition between plan periods."""

    __tablename__ = "local_plans"
    __table_args__ = (UniqueConstraint("council_code", "plan_name", "plan_version", name="uq_council_plan_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    council_code: Mapped[str] = mapped_column(ForeignKey("councils.code"))
    # LPA code (e.g. ONS/PINS local authority code) where available - not
    # every source states one, so this stays optional rather than blocking
    # ingestion when it's unknown.
    authority_code: Mapped[str | None] = mapped_column(String(30), nullable=True)

    plan_name: Mapped[str] = mapped_column(String(300))
    # Free text ("Regulation 18", "Regulation 19", "Adopted 2024") - plan
    # versioning terminology isn't standardised across councils, so this is
    # kept as the council's own label rather than forced into an enum.
    plan_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # legacy (2004 Act development plan system) | new (Levelling-up and
    # Regeneration Act 2023 system, once councils start transitioning) -
    # affects which stages/terminology are expected to appear for this plan.
    planning_system: Mapped[str] = mapped_column(String(20), default="legacy")

    # Normalised against app.policy.status.PLAN_STATUSES (see
    # app.policy.status.normalise_plan_status) - raw_status is always kept
    # alongside it, since normalisation is best-effort keyword matching and
    # a council's own wording is the only ground truth when it disagrees.
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    raw_status: Mapped[str | None] = mapped_column(String(300), nullable=True)

    plan_period: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "2024-2042"
    adoption_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    publication_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # The plan's OWN stated housing number - distinct from a housing need
    # study's output and distinct from housing land supply (see
    # specifications/003-policy-intelligence-v1.md Sec.2).
    annual_housing_requirement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_housing_requirement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Kept as free text (e.g. "5.2 years") rather than a bare float - councils
    # state this in inconsistent units/bases, and the raw figure is more
    # trustworthy than a value we've silently reinterpreted.
    housing_land_supply: Mapped[str | None] = mapped_column(String(100), nullable=True)
    housing_land_supply_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    source_webpage: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # JSON-encoded list of {"title": ..., "url": ...} - a simple record of
    # which documents this plan's data was drawn from. Full monitoring
    # metadata (hash, last-checked, health) lives on MonitoredSource, not
    # here - this field is just "what documents exist", not "how they're
    # being watched".
    source_documents: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Status/lifecycle monitoring (Part 5) ---
    current_stage_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    next_milestone: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_milestone_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expected_adoption_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timetable_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_checked: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Distinct from updated_at (generic row-bookkeeping, bumped on ANY
    # field change) - this is specifically "when did the plan's real-world
    # content last change", the fact change-detection cares about.
    content_last_updated: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monitoring_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)  # high | medium | low
    monitoring_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    allocations: Mapped[list["LocalPlanSite"]] = relationship(back_populates="local_plan")
    status_history: Mapped[list["LocalPlanStatusHistory"]] = relationship(
        back_populates="local_plan", cascade="all, delete-orphan"
    )
    monitored_sources: Mapped[list["MonitoredSource"]] = relationship(
        back_populates="local_plan", cascade="all, delete-orphan"
    )


class LocalPlanStatusHistory(Base):
    """Append-only snapshot of a LocalPlan's status whenever it changes -
    never overwritten, never deleted (Part 10). Written by
    app.policy.change_detection whenever an ingest or a monitoring check
    finds a LocalPlan's status has moved on from what's currently stored."""

    __tablename__ = "local_plan_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_plan_id: Mapped[int] = mapped_column(ForeignKey("local_plans.id"))

    status: Mapped[str] = mapped_column(String(50))
    raw_status: Mapped[str | None] = mapped_column(String(300), nullable=True)
    plan_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    local_plan: Mapped["LocalPlan"] = relationship(back_populates="status_history")


class LocalPlanSite(Base):
    """One site allocated for housing in a council's Local Plan - a
    leading-indicator signal distinct from everything else in this database,
    since these are sites identified BEFORE any planning application exists
    for them at all (see app.extraction.local_plan). Sourced from whatever
    document the council actually publishes (usually a PDF site-allocations
    schedule) - there's no equivalent of the Idox/Arcus portal for this, so
    ingestion is necessarily semi-manual and per-council, unlike
    applications.

    This is the "Local Plan Allocation" domain object (specifications/
    004-core-domain-model.md) - kept under its original class name to avoid
    disturbing every existing reference to it (app.extraction.local_plan,
    ingest_local_plan.py, the Local Plan browse page), but conceptually and
    going forward it IS the Allocation entity, distinct from - never to be
    confused with - a Site or a Planning Application."""

    __tablename__ = "local_plan_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    council_code: Mapped[str] = mapped_column(ForeignKey("councils.code"))

    # Nullable for backwards compatibility with rows created before this
    # sprint - backfilled by scripts/migrate_policy_intelligence.py. New
    # ingestion always sets this.
    local_plan_id: Mapped[int | None] = mapped_column(ForeignKey("local_plans.id"), nullable=True)

    policy_reference: Mapped[str] = mapped_column(String(50))  # e.g. "HOM 2.30"
    site_name: Mapped[str] = mapped_column(String(300))
    # The plan's stated intended use for this allocation as printed - most
    # are residential, some are mixed use. Recording what the plan actually
    # says rather than assuming residential-only (see
    # specifications/003-policy-intelligence-v1.md Sec.2).
    intended_use: Mapped[str | None] = mapped_column(String(200), nullable=True, default="residential")

    # minimum_dwellings IS this allocation's minimum-capacity figure (the
    # plan's own stated dwelling count) - kept under its original name
    # rather than duplicated as a new "minimum_capacity" column, since it's
    # already exactly that field and every existing caller depends on this
    # name. indicative/maximum are new, genuinely additional figures some
    # plans state alongside (or instead of) a single minimum.
    minimum_dwellings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indicative_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Council-specific grouping as it appears in the source document (e.g.
    # "List 1: built-up area", "List 2: grey belt") - kept verbatim rather
    # than normalised into an enum, since this varies by council and the
    # exact wording is meaningful context in its own right.
    category: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Normalised against app.policy.status.ALLOCATION_STATUSES (Part 6) -
    # raw_allocation_status preserves the source wording alongside it, same
    # pattern as LocalPlan.status/raw_status. Nullable because allocations
    # ingested before this sprint don't have one yet until the migration
    # derives a best-effort value for them (flagged for review, never
    # guessed as "adopted").
    allocation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_allocation_status: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # DEPRECATED in favour of local_plan.plan_name/plan_status - kept
    # populated (not removed) so existing code reading these two fields
    # directly (the Local Plan browse page, the Site-page display before
    # this sprint) keeps working unchanged. New code should read
    # local_plan.plan_name / local_plan.status instead.
    plan_name: Mapped[str] = mapped_column(String(300))
    plan_status: Mapped[str] = mapped_column(String(50))

    source_document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Reserved for future GIS work (specifications/004 explicitly puts
    # polygon/boundary work out of scope for this sprint) - a place to hold
    # a raw geometry string (WKT/GeoJSON) once that's built, without another
    # schema change. Genuinely unused today.
    geometry_placeholder: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cross-reference to an already-scraped Site, where one has been matched
    # by address/name similarity (see app.extraction.local_plan.
    # match_to_existing_sites) - null means no planning application has been
    # submitted for this allocation yet, which is itself the useful signal:
    # a genuinely pre-application opportunity, not just an early one.
    matched_site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # auto_applied | needs_confirmation | confirmed | rejected - set
    # whenever a change is ambiguous enough to need a human look (Part 11's
    # review queue is PolicyChangeEvent rows with review_status=
    # needs_review; this field is the allocation's OWN current review state,
    # e.g. after a low-confidence Site match or an ambiguous status derived
    # by migration).
    review_status: Mapped[str] = mapped_column(String(30), default="auto_applied")

    # --- Progression signal (Part 7) - deterministic, never AI-derived.
    # See app.policy.progression.classify_progression. ---
    progression_signal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # JSON-encoded list of the deterministic reasons behind the signal -
    # always stored alongside it, since a bare label with no explanation is
    # exactly the kind of unexplainable decision CLAUDE.md's product
    # principles rule out.
    progression_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    progression_computed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Copied from matched_site when matched (already geocoded there) or
    # free-text geocoded directly from site_name otherwise (see
    # app.extraction.local_plan.geocode_local_plan_site) - a genuinely
    # unmatched allocation has no scraped application to inherit coordinates
    # from, so this is the only way to plot it on the map at all.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    extracted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    matched_site: Mapped["Site | None"] = relationship(foreign_keys=[matched_site_id])
    local_plan: Mapped["LocalPlan | None"] = relationship(back_populates="allocations")
    versions: Mapped[list["AllocationVersion"]] = relationship(
        back_populates="allocation", cascade="all, delete-orphan"
    )


class AllocationVersion(Base):
    """Append-only snapshot of a LocalPlanSite's fields, written whenever an
    ingest or migration finds it materially changed from what's stored
    (Part 10 - version history). Never updated or deleted once written -
    the current LocalPlanSite row is always the latest state; this table is
    purely the audit trail behind it."""

    __tablename__ = "allocation_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    allocation_id: Mapped[int] = mapped_column(ForeignKey("local_plan_sites.id"))
    local_plan_id: Mapped[int | None] = mapped_column(ForeignKey("local_plans.id"), nullable=True)

    policy_reference: Mapped[str] = mapped_column(String(50))
    site_name: Mapped[str] = mapped_column(String(300))
    minimum_dwellings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indicative_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(String(300), nullable=True)
    allocation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_allocation_status: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # initial_migration | new_allocation | capacity_changed | status_changed |
    # amended | removed - see app.policy.change_detection.
    change_reason: Mapped[str] = mapped_column(String(50))
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    allocation: Mapped["LocalPlanSite"] = relationship(back_populates="versions")


class MonitoredSource(Base):
    """A single URL/document being watched for change, belonging to a
    LocalPlan - the foundation for Part 8's continuous monitoring. Checking
    a source (fetching it, hashing its content, comparing to
    content_hash) is a separate concern (app.pipeline.policy_monitoring)
    from this table, which just holds the current watched state."""

    __tablename__ = "monitored_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_plan_id: Mapped[int] = mapped_column(ForeignKey("local_plans.id"))

    url: Mapped[str] = mapped_column(String(500))
    final_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # after redirects, when different
    # webpage | timetable | consultation_portal | examination_library |
    # adopted_plan | policies_map | pdf | other
    source_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)

    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # sha256 hex digest
    published_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    last_checked: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_check: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_changed: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ok | error | never_checked - a quick-glance signal for "is this source
    # still reachable", independent of whether its content has changed.
    monitoring_health: Mapped[str] = mapped_column(String(20), default="never_checked")

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    local_plan: Mapped["LocalPlan"] = relationship(back_populates="monitored_sources")


class PolicyChangeEvent(Base):
    """A single detected change in Policy Intelligence data - the log Part 9
    (change detection) writes to, and simultaneously the Part 11 review
    queue: a queue is just the rows here with review_status="needs_review",
    not a separate table duplicating the same shape. Deliberately never
    overwritten - each detected change is its own row, so the full change
    history is reconstructable from this table alone."""

    __tablename__ = "policy_change_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_plan_id: Mapped[int | None] = mapped_column(ForeignKey("local_plans.id"), nullable=True)
    allocation_id: Mapped[int | None] = mapped_column(ForeignKey("local_plan_sites.id"), nullable=True)
    monitored_source_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_sources.id"), nullable=True)

    # new_plan_version | stage_change | adoption | withdrawal | new_allocation |
    # allocation_removed | allocation_retained | allocation_amended |
    # capacity_changed - see app.policy.change_detection.EVENT_TYPES.
    event_type: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # High-confidence, unambiguous changes (a status that only ever moves
    # forward, e.g. draft -> adopted with a matching plan-level adoption) are
    # applied automatically; anything ambiguous (a PDF changed with no clear
    # status delta, an allocation vanishing, unusual wording that doesn't
    # match a known status) is left for a human - see
    # app.policy.change_detection.classify_confidence.
    auto_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(30), default="auto_applied")  # auto_applied | needs_review | confirmed | rejected
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    detected_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    # Real scraped value on Arcus councils ("Target decision date"/"Decision
    # Date Due" - label varies per council, see arcus_portal.py). Idox
    # portals don't expose an equivalent field publicly - for those, UI/
    # summary code falls back to lapse_tracking.estimate_statutory_decision_date,
    # a computed estimate from application_validated, not a scraped fact.
    expected_decision_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
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

    # Cooldown tracking for app.pipeline.run_weekly.stage_fetch_related_applications
    # - when this application was last searched for other applications
    # citing it, regardless of whether it's a citation-verified parent or
    # just a site's own granted application with no known children yet
    # (still worth periodic rechecking - a discharge/amendment filing can
    # appear months after the grant).
    related_search_checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
