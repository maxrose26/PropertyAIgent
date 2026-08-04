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
    """A planning authority - the parent object for both planning-
    application scraping (base_url/date_field_mode/doc_system, existing
    since this project's first version) AND Policy Intelligence
    (Sprint 2, "Greater Manchester Policy Intelligence Framework": GSS
    code/authority_type/website/monitoring_enabled below, plus the
    local_plans relationship).

    Deliberately the SAME row/table as the original scraping config, not a
    new parallel entity - a Council extended with more capabilities is
    exactly what specifications/004-core-domain-model.md's "extend existing
    domain objects wherever possible, avoid new core objects unless
    absolutely necessary" principle asks for, and LocalPlan.council_code
    already pointed at this table's primary key from Sprint 1 - there was
    never a second "Council" concept to reconcile."""

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

    # --- Policy Intelligence fields (Sprint 2, Part 2) ---
    # Government Statistical Service code (e.g. "E08000002" for Bury) -
    # nullable since not every source used to populate this table states
    # one; a genuine gap is left null, not guessed.
    gss_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # e.g. "Metropolitan Borough Council", "Unitary Authority", "District
    # Council" - free text, not an enum, since England/Wales genuinely mix
    # authority types and a new one showing up for council 11+ shouldn't
    # need a schema change.
    authority_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # The council's own general website - distinct from base_url, which is
    # specifically the PLANNING PORTAL base URL used for application
    # scraping. Two different things that happen to both be "a URL for this
    # council" - kept as two columns rather than overloading base_url's
    # existing, already-depended-upon meaning.
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # A real, independent per-council setting - whether Policy Intelligence
    # monitoring should run for this council at all - not a rollup of its
    # sources' own state. monitoring_health and "last monitored" are
    # deliberately NOT stored columns here (see
    # app.policy.council_dashboard.summarise_council) - they're always
    # computed live from this council's MonitoredSource rows, so there is
    # no cached rollup that can drift out of sync with the sources it's
    # supposedly summarising.
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    applications: Mapped[list["Application"]] = relationship(back_populates="council")
    local_plans: Mapped[list["LocalPlan"]] = relationship(back_populates="council")
    monitored_sources: Mapped[list["MonitoredSource"]] = relationship(back_populates="council")


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

    plan_period: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "2024-2042" - kept for backwards compatibility
    # Sprint 3B ("AI Local Plan Evidence Extraction") - structured start/end
    # years alongside the existing free-text plan_period, so date-range
    # validation (plan_period_end must not precede plan_period_start) is
    # possible without re-parsing a string every time.
    plan_period_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_period_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adoption_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    publication_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # --- Sprint 3B additions: plan identity/status fields Part 2 asks for
    # that didn't already exist. ---
    submission_date: Mapped[str | None] = mapped_column(String(50), nullable=True)  # submitted to the Secretary of State
    examination_status: Mapped[str | None] = mapped_column(String(200), nullable=True)  # e.g. "Hearings concluded", "Awaiting main modifications"
    inspector_report_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # free-text nuance a normalised status can't carry

    # The plan's OWN stated housing number - distinct from a housing need
    # study's output and distinct from housing land supply (see
    # specifications/003-policy-intelligence-v1.md Sec.2). annual_/total_
    # housing_requirement are the plan's OWN adopted/proposed figures;
    # housing_need_annual/total (Sprint 3B) are a housing need STUDY's
    # output - the two are frequently different numbers and must never be
    # collapsed into one field (Part 3: "housing need is not automatically
    # the adopted housing requirement").
    annual_housing_requirement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_housing_requirement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    housing_need_annual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    housing_need_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The council's own wording for how the requirement figure was reached
    # (e.g. "standard method", "standard method uplifted for affordability",
    # "locally-derived") - kept verbatim, never inferred.
    requirement_basis: Mapped[str | None] = mapped_column(String(300), nullable=True)
    unmet_need: Mapped[int | None] = mapped_column(Integer, nullable=True)  # dwellings the plan itself states it cannot accommodate
    neighbouring_authority_contribution: Mapped[str | None] = mapped_column(Text, nullable=True)  # e.g. "met via Places for Everyone redistribution"
    requirement_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Sprint 3B: Housing delivery (Part 2) - represents the LATEST
    # known reporting period's position, sourced from the most recent
    # Annual Monitoring Report / housing delivery statement / trajectory
    # found for this plan. A housing trajectory's forward projection is
    # NOT the same as an adopted requirement (Part 3) - trajectory_
    # remaining_requirement is kept as its own field, never folded into
    # annual_housing_requirement above. ---
    latest_reporting_period: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "2023/24"
    homes_delivered_latest_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cumulative_homes_delivered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_requirement_for_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_surplus_or_shortfall: Mapped[int | None] = mapped_column(Integer, nullable=True)  # signed - negative is a shortfall
    housing_delivery_test_result: Mapped[str | None] = mapped_column(String(100), nullable=True)  # the HDT's own published %/result, verbatim
    trajectory_remaining_requirement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Sprint 3B: Five-year housing land supply (Part 2) - a genuinely
    # new structured layer; housing_land_supply (below, pre-existing) stays
    # as the free-text fallback for whatever a source states in a form
    # these structured fields can't capture. five_year_supply_years must
    # never be inferred from unrelated dwelling figures (Part 3) - see
    # app.policy.evidence_validation's explicit-evidence requirement for it. ---
    five_year_supply_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    five_year_supply_base_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    five_year_supply_publication_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    deliverable_supply_dwellings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    five_year_requirement_dwellings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    five_year_shortfall_or_surplus_dwellings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buffer_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)  # e.g. 5/20% NPPF buffer, as the source states it
    calculation_method: Mapped[str | None] = mapped_column(String(300), nullable=True)  # e.g. "Sedgefield", "Liverpool" - verbatim
    supply_position_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Kept as free text (e.g. "5.2 years") rather than a bare float - councils
    # state this in inconsistent units/bases, and the raw figure is more
    # trustworthy than a value we've silently reinterpreted. Superseded in
    # practice by five_year_supply_years above where the source supports a
    # clean number, but retained for anything that doesn't fit that shape.
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

    # --- Sprint 3B.1 ("AI Local Plan Summary") - a concise AI-narrated
    # synthesis of this plan's own trusted/pending evidence, same
    # grounded-numbers-then-narrate discipline as app.reporting.
    # scheme_summary. Persisted (not regenerated on every page view) and
    # gated by ai_summary_evidence_fingerprint - see
    # app.reporting.local_plan_summary.should_regenerate. key_risks/
    # key_opportunities/evidence_gaps are JSON-encoded lists of strings,
    # not free text, so the UI can render them as distinct bullet lists
    # without re-parsing prose.
    ai_summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_key_risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_key_opportunities: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_evidence_gaps: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_generated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # sha256 over the narrative-relevant portion of the summary payload
    # (fact values/trust-state/staleness/conflicts, allocation and
    # progression counts) - deliberately NOT including last_checked or any
    # other pure-bookkeeping timestamp, so a routine monitoring pass that
    # finds nothing new never forces a regeneration/AI-cost event.
    ai_summary_evidence_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_summary_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_summary_prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    council: Mapped["Council"] = relationship(back_populates="local_plans")
    allocations: Mapped[list["LocalPlanSite"]] = relationship(back_populates="local_plan")
    status_history: Mapped[list["LocalPlanStatusHistory"]] = relationship(
        back_populates="local_plan", cascade="all, delete-orphan"
    )
    # Sources tied to THIS specific plan/version once one has been ingested
    # - a strict subset of Council.monitored_sources, which also includes
    # council-level sources (a Local Plan landing page, a consultation
    # portal) registered before any LocalPlan exists at all - see
    # MonitoredSource's docstring (Sprint 2, Part 3).
    monitored_sources: Mapped[list["MonitoredSource"]] = relationship(back_populates="local_plan")


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


class LocalPlanFieldHistory(Base):
    """Generic append-only snapshot of a single LocalPlan field's PRE-change
    value, for any of the Sprint 3B evidence fields (housing requirement/
    need, delivery, five-year supply, examination/status fields) -
    deliberately separate from LocalPlanStatusHistory (which stays exactly
    as Sprint 1 built it, still used for status/raw_status/plan_version
    only) rather than adding ~25 mostly-null columns to that table.

    Written by app.policy.review.approve_change immediately before it
    applies a proposed value from proposed_data - the full evidence trail
    behind why a value changed always remains recoverable from the
    PolicyChangeEvent that was approved (never deleted), so this table only
    needs to hold the bare old/new value, not re-duplicate the evidence."""

    __tablename__ = "local_plan_field_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_plan_id: Mapped[int] = mapped_column(ForeignKey("local_plans.id"))

    field_name: Mapped[str] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The PolicyChangeEvent.event_type that caused this change - "why", not
    # "what changed" (that's field_name/old_value/new_value already).
    change_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    local_plan: Mapped["LocalPlan"] = relationship()


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

    # Nullable (Sprint 2, onboarding Bury) - confirmed a real case where a
    # council's own document names an allocation with no code printed
    # against it anywhere; forcing this non-null previously caused the AI
    # extraction to fabricate one (see app.extraction.local_plan's SCHEMA
    # docstring). site_name is the fallback identity for deduplication
    # when this is null - see ingest_local_plan.py's _dedup_key.
    policy_reference: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "HOM 2.30"
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
    #
    # KNOWN V1 LIMITATION (documented per Sprint 1 CTO review, not fixed in
    # this amendment): this is a single nullable FK, so V1 supports at most
    # ONE confirmed Site per allocation. An allocation can conceptually
    # correspond to several Sites (a large allocation delivered as separate
    # physical parcels/phases, or split across more than one planning
    # application that was never itself consolidated into one Site) - V1
    # has no way to represent that; only the single best match is kept. A
    # future specification should introduce an explicit many-to-many
    # relationship table (allocation_id, site_id, relationship_type: full |
    # partial | phased, confidence) rather than widening this column -
    # see specifications/003-policy-intelligence-v1.md Sec.5 and the
    # partial-delivery reasoning in app.extraction.local_plan.
    # assess_delivery_scope, which already works around this limitation at
    # the UNIT-COUNT level (comparing minimum_dwellings against whatever the
    # one matched Site's applications total) without a real multi-Site
    # relationship underneath it.
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

    policy_reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    """A single URL/document being watched for change - the foundation for
    Part 8 (Sprint 1) / Part 3 (Sprint 2)'s continuous monitoring. Checking
    a source (fetching it, hashing its content, comparing to content_hash)
    is a separate concern (app.policy.monitor) from this table, which just
    holds the current watched state.

    Sprint 2 generalisation ("Greater Manchester Policy Intelligence
    Framework", Part 3): owned by a COUNCIL first (council_code, always
    set), with an OPTIONAL link to a specific LocalPlan once one has
    actually been ingested. Sprint 1 required local_plan_id up front, which
    meant a council-level watch (a Local Plan landing page, a consultation
    portal - exactly the sources Part 3 names) couldn't be registered until
    after a plan already existed in the database - backwards for sources
    whose entire purpose is detecting a plan BEFORE anyone has manually
    ingested it. local_plan_id is set once ingest_local_plan.py links a
    specific document to a specific plan/version; council-level sources
    (a landing page watching for "has anything changed at all") keep it
    null indefinitely, and that's a valid, expected steady state, not a
    half-finished registration."""

    __tablename__ = "monitored_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    council_code: Mapped[str] = mapped_column(ForeignKey("councils.code"))
    local_plan_id: Mapped[int | None] = mapped_column(ForeignKey("local_plans.id"), nullable=True)

    url: Mapped[str] = mapped_column(String(500))
    final_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # after redirects, when different
    # landing_page | adopted_plan | emerging_plan | timetable |
    # consultation_portal | examination_library | policies_map |
    # evidence_library | pdf | other (Sprint 2, Part 3) plus, since Sprint 3B
    # ("AI Local Plan Evidence Extraction", Part 1): local_development_scheme |
    # annual_monitoring_report | housing_delivery_statement | housing_trajectory |
    # five_year_supply_statement | housing_need_assessment | inspectors_report |
    # main_modifications | adoption_statement, plus, since the housing-supply
    # monitoring amendment ("Add monitored housing supply and delivery
    # reports", Part 2) - these are specifically INDEX/DISCOVERY pages this
    # source_type describes (a page LISTING reports, not a report itself -
    # individual discovered reports are their own MonitoredReport rows):
    # monitoring_page | housing_land_supply_page | amr_page |
    # policy_document_library - see
    # app.policy.document_selection.DOCUMENT_TYPE_TO_CATEGORIES for how each
    # maps to an evidence-extraction category. Still a free string, not a DB
    # enum, so the vocabulary can keep growing without a migration.
    # Sprint 1's "webpage" is kept as an accepted synonym for landing_page
    # for backwards compatibility with Stockport's existing registration,
    # not removed).
    source_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)

    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # sha256 hex digest
    published_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    last_checked: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_check: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_changed: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ok | error | stale | never_checked - a quick-glance signal for "is
    # this source still reachable", independent of whether its content has
    # changed. "stale" (vs a fresh "error") means it's been failing for
    # long enough that the LAST successful check is itself old - see
    # app.policy.monitor.check_source.
    monitoring_health: Mapped[str] = mapped_column(String(20), default="never_checked")
    # How often this source is expected to be worth re-checking, in days -
    # a real per-source setting (a fast-moving consultation portal vs a
    # rarely-changing adopted plan don't need the same cadence). Originally
    # recorded but not enforced by any scheduler; the housing-supply
    # monitoring amendment ("Add monitored housing supply and delivery
    # reports") is what finally reads this via next_check_due below - see
    # app.policy.report_cadence.compute_next_check_due, whose per-source-
    # type defaults populate this field going forward.
    monitoring_frequency_days: Mapped[int] = mapped_column(Integer, default=7)
    # The next datetime this source is actually due a check - computed and
    # stored explicitly (rather than re-derived from last_checked +
    # monitoring_frequency_days on every query) so "which sources are due"
    # is a simple, indexable filter. Null means "never checked, due now".
    next_check_due: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A council-stated or inferred month/window a new edition is expected
    # (e.g. "October", "Q4") - free text, since councils state this with
    # wildly inconsistent precision. When set and current, compute_next_
    # check_due tightens the cadence to weekly regardless of source type,
    # since a source is most likely to actually change during its own
    # expected publication window.
    expected_publication_window: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # When app.policy.report_discovery last found a genuinely NEW
    # MonitoredReport via this source - distinct from last_changed (this
    # source's own index-page content hash changing) since a page's HTML
    # can change (styling, unrelated text) without any new document
    # actually appearing, and a new document can appear without the
    # index page's raw hash necessarily being what's watched.
    last_report_discovered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Sources are registered via config/policy_sources.yaml (see
    # app.policy.sources), never hardcoded in monitoring logic - this flag
    # is how one gets deactivated (a document moved/retired) without
    # deleting its row and losing its check history.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # --- Sprint 3D ("Policy Document Coverage & Discovery") ---
    # A richer, document-level classification than source_type above -
    # source_type is the coarse ROUTING label app.policy.document_selection
    # already depends on for extraction eligibility (untouched by this
    # sprint); policy_document_type is app.policy.document_types'
    # PolicyDocumentType vocabulary (Part 2), covering map/SPD/framework
    # types source_type has no rules for. Populated for the case where the
    # SOURCE ITSELF is the artifact (e.g. a directly-registered interactive
    # map/GIS viewer URL with no separate document link to discover
    # underneath it) - see app.policy.coverage, which reads this alongside
    # MonitoredReport.policy_document_type when building the per-council
    # inventory.
    policy_document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # The source's own title/label as found, preserved verbatim alongside
    # the normalised policy_document_type (Part 2: "preserve the raw source
    # label") - same "never collapse raw wording without retaining it"
    # principle as every other classification field in this codebase.
    policy_document_type_raw_label: Mapped[str | None] = mapped_column(String(300), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    council: Mapped["Council"] = relationship(back_populates="monitored_sources")
    local_plan: Mapped["LocalPlan | None"] = relationship(back_populates="monitored_sources")
    reports: Mapped[list["MonitoredReport"]] = relationship(back_populates="monitored_source")


class MonitoredReport(Base):
    """A single discovered evidence DOCUMENT - an individual AMR, housing
    land supply statement, trajectory, HDT action plan, LDS, inspector's
    report, or adoption statement (housing-supply monitoring amendment,
    "Add monitored housing supply and delivery reports", Part 1).

    Deliberately a SEPARATE entity from MonitoredSource, not a reuse of it:
    MonitoredSource represents a watched LOCATION (an index/landing page,
    mutated in place - its content_hash is overwritten on every check,
    because there is only ever one "current" state of a page). A Report is
    the opposite shape - every discovered EDITION of a document is its own
    permanent row, never overwritten, because Part 1 explicitly requires
    "preserve all historic reports" and Part 5 requires never deleting or
    overwriting a previous year's evidence. Superseding a report sets
    status="superseded" and superseded_by_id on the OLD row; the new
    edition is always a brand new row, never a mutation of the old one.

    monitored_source_id records WHICH index page (if any) this report was
    discovered via - null for reports registered directly (e.g. the Local
    Plan's own MonitoredSource-registered document, or a manually-added
    one), matching MonitoredSource's own existing local_plan_id nullability
    reasoning."""

    __tablename__ = "monitored_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    council_code: Mapped[str] = mapped_column(ForeignKey("councils.code"))
    local_plan_id: Mapped[int | None] = mapped_column(ForeignKey("local_plans.id"), nullable=True)
    monitored_source_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_sources.id"), nullable=True)

    # local_plan | authority_monitoring_report | housing_land_supply_statement |
    # housing_delivery_report | housing_trajectory |
    # housing_delivery_test_action_plan | local_development_scheme |
    # inspector_report | adoption_statement - see
    # app.policy.report_discovery.classify_report_type (deterministic
    # keyword rules, never AI - Part 2) and
    # app.policy.document_selection.DOCUMENT_TYPE_TO_CATEGORIES for routing.
    # "inspector_report" is the canonical spelling here; MonitoredSource's
    # pre-existing "inspectors_report" (with an s) is kept as a synonym in
    # the routing table, not renamed, to avoid disturbing Sprint 3B rows.
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # "auto" (a deterministic rule matched confidently) or "needs_review"
    # (Part 2.8 - no rule produced a safe classification, or the URL/title
    # was too ambiguous to trust). A needs_review report still exists as a
    # row with all its other fields populated - never silently dropped.
    classification_status: Mapped[str] = mapped_column(String(20), default="auto")
    # Which deterministic rule matched (e.g. "housing_land_supply_keywords") -
    # kept for the same "every decision must be explainable" reason
    # app.policy.document_selection keeps precedence explainable; null when
    # classification_status is needs_review.
    matched_classification_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)

    title: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # The period the report's OWN figures cover (e.g. "2023/24") - distinct
    # from base_date (the single date a position, like five-year supply, is
    # calculated FROM) and publication_date (when the document itself was
    # released) - Part 5 explicitly ranks reporting_period/base_date above
    # publication/download date for deciding which report is current.
    reporting_period: Mapped[str | None] = mapped_column(String(50), nullable=True)
    base_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    publication_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    url: Mapped[str] = mapped_column(String(500))
    final_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # current | superseded - never deleted either way (Part 1/Part 5).
    status: Mapped[str] = mapped_column(String(20), default="current")
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_reports.id"), nullable=True)
    # auto (same-URL hash change - unambiguous, this IS the same document
    # slot) or needs_review (a different URL that LOOKS like a newer
    # edition of this one - Part 2.6, always queued rather than guessed,
    # since matching two different URLs as "the same report" is inherently
    # more failure-prone than a same-URL hash diff). Null while current.
    supersession_method: Mapped[str | None] = mapped_column(String(20), nullable=True)

    last_checked: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_check: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_changed: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monitoring_health: Mapped[str] = mapped_column(String(20), default="never_checked")
    next_check_due: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Part 4 ("trigger extraction only on change"): the content_hash and
    # prompt version AI extraction last actually ran against - compared
    # against this report's CURRENT content_hash/the running prompt
    # version to decide whether extraction is due, without re-deriving it
    # from PolicyChangeEvent history on every check. See
    # app.policy.extract_plan_evidence.should_extract.
    last_extracted_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_extracted_prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_extracted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Sprint 3D ("Policy Document Coverage & Discovery") ---
    # See MonitoredSource.policy_document_type's docstring for the
    # source_type-vs-policy_document_type distinction - this is the
    # DOCUMENT-level classification (app.policy.document_types), the
    # primary place Part 2's fuller vocabulary (policies_map,
    # interactive_map, allocation_map, masterplan, SPD...) actually lands,
    # since a MonitoredReport is one specific discovered document.
    policy_document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    policy_document_type_raw_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Where this document has actually been downloaded to on local disk -
    # null until a real download happens (app.policy.document_discovery.
    # download_policy_document), mirroring Document.local_path. This is
    # the coverage engine's (app.policy.coverage) "Downloaded?" signal -
    # distinct from merely being discovered/registered, since a report row
    # can exist (a link was found and classified) with nothing fetched yet.
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    discovered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    council: Mapped["Council"] = relationship()
    local_plan: Mapped["LocalPlan | None"] = relationship()
    monitored_source: Mapped["MonitoredSource | None"] = relationship(back_populates="reports")
    superseded_by: Mapped["MonitoredReport | None"] = relationship(remote_side=[id])


class PolicyChangeEvent(Base):
    """A single detected change in Policy Intelligence data - the log Part 9
    (change detection) writes to, and simultaneously the Part 11 review
    queue: a queue is just the rows here with review_status="needs_review",
    not a separate table duplicating the same shape. Deliberately never
    overwritten - each detected change is its own row, so the full change
    history is reconstructable from this table alone.

    Sprint 1 CTO-review amendment ("Protect trusted state from ambiguous
    changes"): for anything NOT auto-applied, the underlying LocalPlan/
    LocalPlanSite row is left completely unchanged at the moment this event
    is created - proposed_data is what WOULD be applied, not what already
    has been. See app.policy.review.approve_change/reject_change for the
    only code paths allowed to apply it."""

    __tablename__ = "policy_change_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_plan_id: Mapped[int | None] = mapped_column(ForeignKey("local_plans.id"), nullable=True)
    allocation_id: Mapped[int | None] = mapped_column(ForeignKey("local_plan_sites.id"), nullable=True)
    monitored_source_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_sources.id"), nullable=True)
    # Housing-supply monitoring amendment ("Add monitored housing supply and
    # delivery reports") - set for report_discovered/report_superseded/
    # report_classification_needs_review/report_supersession_needs_review
    # events, whose target is a MonitoredReport row rather than a
    # LocalPlan/LocalPlanSite. app.policy.review's approve_change/
    # reject_change gained a third branch for this target - see there.
    monitored_report_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_reports.id"), nullable=True)

    # new_plan_version | stage_change | adoption | withdrawal | new_allocation |
    # allocation_removed | allocation_retained | allocation_amended |
    # capacity_changed | source_content_changed | plan_evidence_proposed
    # (Sprint 3B) plus, since the housing-supply monitoring amendment:
    # report_discovered | report_superseded |
    # report_classification_needs_review | report_supersession_needs_review -
    # see app.policy.change_detection.EVENT_TYPES.
    event_type: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON-encoded {field_name: proposed_value} - exactly what
    # app.policy.review.approve_change would setattr onto the target
    # LocalPlan/LocalPlanSite row if approved. Null for event types with
    # nothing to apply (allocation_retained, source_content_changed - a raw
    # hash change says THAT something changed, not what, so there's no
    # concrete field value to propose without a human re-reading it first).
    proposed_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source evidence, kept at the top level (not just buried in
    # proposed_data) so a reviewer can see where a proposed change came from
    # without parsing JSON. confidence is deliberately nullable and mostly
    # null today - AI extraction in this platform is schema-structured, not
    # confidence-scored, so there is no real number to put here yet for
    # most event types; the column exists as honest infrastructure for when
    # one becomes available, not a fabricated placeholder.
    source_document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # --- Sprint 3B ("AI Local Plan Evidence Extraction") additions - real
    # evidence for events proposed by app.extraction.plan_evidence, always
    # null for the allocation/status events Sprint 1/2 already produce
    # (those never had a numeric confidence or a verbatim excerpt to give). ---
    source_document_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # The verbatim sentence/table row the value was read from - short
    # enough for a reviewer to check quickly, but never blank when a value
    # is present (Part 5: "Do not store only an AI explanation without the
    # underlying evidence").
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "ai_structured_extraction"
    extraction_model: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "gpt-4o-mini"
    extraction_prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extracted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # High-confidence, unambiguous changes (a brand new allocation/plan, or
    # one confirmed unchanged) are applied immediately at detection time;
    # everything else is queued here with the TRUSTED row left untouched
    # until a human calls app.policy.review.approve_change or reject_change -
    # see app.policy.change_detection.classify_confidence.
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


class VisualEvidence(Base):
    """One rendered, source-linked page image showing a Site's or
    Allocation's physical extent or proposed layout (Sprint 3C,
    "Allocation and Site-Plan Image Extraction"). Evidence, not geometry -
    this table never stores a boundary, an acreage, or any GIS geometry,
    only a picture of a specific page of a specific real document, with
    full provenance back to it.

    Every relationship below is nullable and independent - a single image
    may belong to an Application, a Site, an Allocation, a LocalPlan, or
    any combination (Part 2: "do not force every image to belong to every
    object"). Two different SOURCE lineages are both nullable and mutually
    exclusive in practice: document_id for a planning-application document
    (see Document), monitored_report_id for a Local Plan / monitored
    source document (see MonitoredReport) - never both set for the same
    row, since a given rendered page only ever came from one real document.

    Nothing is ever deleted: a source document changing at the same URL
    gets its old images marked status="superseded" (superseded_by_id
    points at the fresh row), never overwritten or removed - the exact
    same pattern MonitoredReport already established for report editions."""

    __tablename__ = "visual_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- source lineage (exactly one of these two is normally set) ---
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    monitored_report_id: Mapped[int | None] = mapped_column(ForeignKey("monitored_reports.id"), nullable=True)

    # --- target object(s) this image is evidence for - all independent,
    # all nullable until a match is confirmed (Part 2/Part 8) ---
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True)
    local_plan_id: Mapped[int | None] = mapped_column(ForeignKey("local_plans.id"), nullable=True)
    allocation_id: Mapped[int | None] = mapped_column(ForeignKey("local_plan_sites.id"), nullable=True)

    # --- provenance, kept at the top level (not just derivable via the
    # source_id FKs) so a reviewer/UI never has to join back through
    # Document/MonitoredReport just to show where an image came from -
    # same reasoning as PolicyChangeEvent's own source_document_title/url. ---
    source_document_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_page: Mapped[int] = mapped_column(Integer)

    # allocation_map | site_location_plan | red_line_boundary |
    # blue_line_boundary | proposed_site_layout | masterplan |
    # phasing_plan | parameter_plan | access_plan | policies_map_extract |
    # development_framework | other_site_visual | unknown - see
    # app.visuals.IMAGE_TYPES. Never label red_line_boundary/
    # blue_line_boundary unless the visual evidence itself supports it
    # (Part 3) - app.visuals.classification's prompt enforces this, not a
    # DB constraint, since the vocabulary must stay a free string for the
    # same reason MonitoredSource.source_type does (room to grow without a
    # migration).
    image_type: Mapped[str] = mapped_column(String(50), default="unknown")
    # The source document's own label for this drawing where available
    # (a title-block string, a document name) - kept verbatim alongside
    # the normalised image_type, same "never collapse raw wording into a
    # normalised field without retaining it" principle as Sprint 3B's
    # plan-status normalisation.
    raw_classification_label: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Storage keys/paths, not raw bytes - kept as plain strings deliberately
    # (not a dedicated "storage backend" abstraction) so swapping local
    # disk for object storage later only means changing what these strings
    # point at and how app.visuals.rendering resolves them, not the schema.
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # sha256 of the SOURCE document's own bytes - Part 14's idempotency/
    # change-detection key ("the source document hash changes"). Distinct
    # from page_render_hash below, which additionally covers the page
    # number and render version, so a hash change can be attributed to
    # either cause independently.
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # sha256 of (file_hash, source_page, render version) - Part 14's other
    # trigger ("the page-render version changes"). Two rows can share a
    # file_hash (same source PDF, different pages) but never a
    # page_render_hash, which is what actually gates re-rendering/re-
    # classification idempotency in app.visuals.pipeline.
    page_render_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    extraction_method: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "ai_vision_classification"
    extraction_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extraction_prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Deterministic Stage 1 reason this PAGE was even considered a
    # candidate before any AI call was spent on it (Part 5: "store why
    # each candidate page was selected") - e.g. "text matched 'red line
    # boundary'; drawing number found". Distinct from the AI's own
    # classification reason, which lives in candidate_reason's counterpart
    # inside the stored extraction_confidence/review flow - kept here as
    # the pre-AI justification for cost/audit purposes.
    candidate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # needs_review | confirmed | rejected - nothing here ever auto-applies
    # itself the way plan_evidence_proposed facts can (Part 9/Part 10):
    # displaying the WRONG image is a worse failure than a wrong number,
    # so every AI classification starts needs_review and only a human
    # confirm/reject call (app.visuals.review) ever moves it - no
    # confidence threshold skips that step.
    review_status: Mapped[str] = mapped_column(String(20), default="needs_review")
    # True only for a human-confirmed OR highest-ranked-candidate image
    # selected as the one to show by default for its (object, purpose) -
    # see app.visuals.primary_selection. Never more than one primary per
    # object in practice, enforced by app.visuals.primary_selection always
    # clearing any previous primary before setting a new one, not a DB
    # constraint (an object with zero linked images has nothing to enforce
    # against anyway).
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    # current | superseded - Part 14: "retain prior visual records and
    # mark them superseded rather than deleting them" when the source PDF
    # changes at the same URL. Mirrors MonitoredReport's own status/
    # superseded_by_id pattern exactly.
    status: Mapped[str] = mapped_column(String(20), default="current")
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("visual_evidence.id"), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # Free text, not a FK to a users table - this remains a single-user
    # tool with no authentication (explicitly out of scope this sprint),
    # so "confirmed_by" is just a short label the reviewer types/selects,
    # kept for audit completeness rather than real multi-user attribution.
    confirmed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document | None"] = relationship()
    monitored_report: Mapped["MonitoredReport | None"] = relationship()
    site: Mapped["Site | None"] = relationship()
    application: Mapped["Application | None"] = relationship()
    local_plan: Mapped["LocalPlan | None"] = relationship()
    allocation: Mapped["LocalPlanSite | None"] = relationship()
    superseded_by: Mapped["VisualEvidence | None"] = relationship(remote_side=[id])
