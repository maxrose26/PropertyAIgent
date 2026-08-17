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
    # Sprint 3E ("Joint Plan Support and Bury Allocation Reconciliation",
    # Part 1) - every Council this plan is linked to, including the
    # council_code above (which is kept, unremoved, as the backwards-
    # compatible lead/legacy authority - see LocalPlanCouncil's own
    # docstring for why council_code is not simply replaced).
    council_links: Mapped[list["LocalPlanCouncil"]] = relationship(
        back_populates="local_plan", cascade="all, delete-orphan"
    )


class LocalPlanCouncil(Base):
    """Sprint 3E ("Joint Plan Support and Bury Allocation Reconciliation",
    Part 1) - additive many-to-many join between LocalPlan and Council, for
    genuinely joint/multi-authority plans (Places for Everyone: one adopted
    plan, nine participating Greater Manchester authorities) that
    LocalPlan.council_code alone cannot represent, since it is a single
    non-nullable foreign key.

    LocalPlan.council_code is deliberately NOT removed by this sprint (per
    the brief: "keep it temporarily as a backwards-compatible lead/legacy
    field") - every piece of code written before this sprint that reads
    LocalPlan.council_code directly keeps working unchanged. This table is
    the source of truth for "which councils does this plan apply to" going
    forward; council_code is a convenience snapshot of ONE of those rows
    (normally the one with is_lead_authority=True, or the authority the
    plan happened to be ingested under first for a plan not yet linked here
    at all).

    A single-authority plan (Stockport's own Local Plan, Bury's own Local
    Plan) gets exactly one LocalPlanCouncil row, matching council_code -
    joint-plan support does not change how an ordinary plan is modelled,
    only adds the ability for a plan to have more than one such row.

    See app.policy.joint_plans for the config-driven (config/joint_plans.
    yaml) linking logic, and scripts/migrate_joint_plan_support.py for the
    idempotent backfill that populates this table for plans that predate
    it."""

    __tablename__ = "local_plan_councils"
    __table_args__ = (UniqueConstraint("local_plan_id", "council_code", name="uq_local_plan_council"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_plan_id: Mapped[int] = mapped_column(ForeignKey("local_plans.id"))
    council_code: Mapped[str] = mapped_column(ForeignKey("councils.code"))

    # participating_authority | lead_authority | host_authority | legacy_owner
    # - "legacy_owner" is what the migration backfill assigns to the
    # existing LocalPlan.council_code authority for a plan that has no
    # config/joint_plans.yaml entry (i.e. every single-authority plan) -
    # distinguishes "this is the one authority a plan has always belonged
    # to" from "this authority is one of several confirmed participants in
    # a genuinely joint plan" (role="participating_authority",
    # role="lead_authority" for the plan's designated lead where a joint
    # plan's own documents name one).
    role: Mapped[str] = mapped_column(String(30), default="legacy_owner")
    is_lead_authority: Mapped[bool] = mapped_column(Boolean, default=False)

    joined_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Free text - where this link's authority came from (a config entry
    # citing the plan's own participating-authorities table/foreword, or
    # "backfilled from LocalPlan.council_code" for the legacy_owner case) -
    # every join row must be traceable to why it exists, not just asserted.
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    local_plan: Mapped["LocalPlan"] = relationship(back_populates="council_links")
    council: Mapped["Council"] = relationship()


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
    # --- Pilot Readiness PR-2 ("Existing Allocation <-> Site Matches") -
    # human review provenance for a Site-match decision, mirroring
    # VisualEvidence.confirmed_by/confirmed_at/rejection_reason's already-
    # established pattern (app.visuals.review.confirm_image/reject_image)
    # rather than inventing a new shape. See app.policy.site_match_review
    # for the two functions allowed to set these. match_review_note covers
    # BOTH a confirm's supporting-evidence rationale and a reject's reason
    # (a rejected match's matched_site_id/match_confidence are cleared by
    # reject_site_match, so the note is what preserves which candidate was
    # rejected and why - unlike VisualEvidence, an allocation-Site match
    # being wrong means the relationship itself is false, not just a low-
    # quality image of a still-real relationship, so nothing keeps pointing
    # at a Site a human said this allocation is NOT). ---
    confirmed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # auto_applied | needs_confirmation | confirmed | rejected - set
    # whenever a change is ambiguous enough to need a human look (Part 11's
    # review queue is PolicyChangeEvent rows with review_status=
    # needs_review; this field is the allocation's OWN current review state,
    # e.g. after a low-confidence Site match or an ambiguous status derived
    # by migration).
    review_status: Mapped[str] = mapped_column(String(30), default="auto_applied")

    # --- Sprint 3E ("Joint Plan Support and Bury Allocation Reconciliation",
    # Part 5) - never set at ingestion or migration time, only ever by an
    # approved PolicyChangeEvent (event_type="duplicate_name_reconciliation_
    # proposed", see app.policy.allocation_reconciliation) once a human has
    # confirmed what a same-named row across two plans actually is. Null
    # means "not reviewed" - never defaulted to "genuine" or "duplicate"
    # automatically, since guessing either way is exactly the silent-
    # misclassification risk this field exists to avoid.
    #
    # genuine_allocation | contextual_reference | duplicate_of_other_plan |
    # uncertain_needs_review
    duplicate_classification: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Free-text reasoning + the source excerpt the classification was based
    # on - never a bare label with no evidence (same "no unexplainable
    # decision" principle as progression_reasons above).
    duplicate_classification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

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


class AllocationRelationship(Base):
    """Sprint 3E ("Joint Plan Support and Bury Allocation Reconciliation",
    Part 6) - records that two LocalPlanSite rows refer to the same
    physical strategic site (or otherwise reference one another) WITHOUT
    merging them into one record. Exists specifically because two
    allocation rows sharing a name is not proof they're the same thing
    (Part 6: "Do not treat two policy records as one simply because their
    names match") - equally, when primary-source evidence DOES confirm
    they're the same site (as it does for Bury's Seedfield/Walshaw/Elton
    Reservoir rows against their Places for Everyone JPA8/JPA9/JPA7
    counterparts - see app.policy.allocation_reconciliation), that fact
    needs somewhere to live that isn't silent deletion or a guessed merge.

    Both allocations named in a relationship keep their own independent
    identity, source document, capacity figure, status and progression
    signal forever - this table only ever ADDS a documented cross-
    reference on top, never removes or overwrites either row."""

    __tablename__ = "allocation_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_allocation_id: Mapped[int] = mapped_column(ForeignKey("local_plan_sites.id"))
    # Nullable - a relationship's target is not always another specific
    # allocation ROW (e.g. Bury's "Castle Road (Unsworth)" row references a
    # sub-parcel described in Places for Everyone's Northern Gateway
    # allocation narrative, not a separate JPA-coded row that exists in
    # this database at all - see the real finding this was built for).
    to_allocation_id: Mapped[int | None] = mapped_column(ForeignKey("local_plan_sites.id"), nullable=True)

    # same_physical_site | referenced_by | superseded_by |
    # implemented_through_joint_plan | uncertain
    relationship_type: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provenance - same top-level-not-buried-in-JSON reasoning as
    # PolicyChangeEvent's own source fields.
    source_document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # needs_review | confirmed | rejected - a relationship record is itself
    # a proposal until a human confirms it, same review discipline as every
    # other ambiguous link in this codebase (PolicyChangeEvent, LocalPlanSite.
    # review_status). Never "auto_applied" - Part 6 explicitly rules out
    # ever inferring sameness automatically from a name match alone.
    review_status: Mapped[str] = mapped_column(String(30), default="needs_review")

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    from_allocation: Mapped["LocalPlanSite"] = relationship(foreign_keys=[from_allocation_id])
    to_allocation: Mapped["LocalPlanSite | None"] = relationship(foreign_keys=[to_allocation_id])


class AllocationSiteRelationship(Base):
    """Stage 2D ("Many-to-Many Relationship Foundation") - the additive
    many-to-many join between LocalPlanSite (allocation) and Site that
    LocalPlanSite.matched_site_id (a single nullable FK) has never been
    able to represent. This is the exact table that field's own model
    comment (see matched_site_id, above) already proposed - "a future
    many-to-many relationship table (allocation_id, site_id,
    relationship_type: full | partial | phased, confidence)" - and that
    specifications/003-policy-intelligence-v1.md Sec.5 records as a known
    V1 limitation, not implemented until now.

    NOT the same table as AllocationRelationship, immediately above -
    that one links two LocalPlanSite rows to each other (allocation <->
    allocation, e.g. two plans' rows for the same physical strategic
    site); this one links a LocalPlanSite to a Site (allocation <->
    planning site). Confirmed structurally incompatible before this
    class was added: AllocationRelationship's two FKs both target
    local_plan_sites.id, neither targets sites.id, so it cannot be
    repurposed for this relationship without misusing it - a new table
    was the only correct option, not a schema decision taken lightly.

    SEMANTIC INVARIANT (Stage 2D Section 1) - a row here means ONLY:
    "this Site is evidenced as relating to this allocation." It does
    NOT mean the Site covers the whole allocation, consumes all
    allocation capacity, is the only development on the allocation, or
    that any capacity is committed or unavailable - none of that is
    computed or asserted anywhere in this model or the module that
    writes it (app.policy.allocation_site_relationships).

    matched_site_id COMPATIBILITY (Stage 2D Section 5) - mirrors the
    LocalPlanCouncil/LocalPlan.council_code precedent (Sprint 3E, "Joint
    Plan Support") exactly: matched_site_id is kept, unremoved, as a
    backwards-compatible convenience/primary pointer - every piece of
    code written before this table existed keeps working unchanged. This
    table is the authoritative SET of every accepted Site relationship
    for an allocation (one row per allocation when there's exactly one,
    many rows for a genuinely multi-Site allocation); matched_site_id is
    a snapshot of ONE of those Sites (normally whichever was first
    accepted), never a claim that it is the only or whole-covering one.

    relationship_type is currently ALWAYS "unknown_scope" for every row
    this table's own writer (Stage 2D) ever creates - deliberately, not
    an oversight: neither the legacy matched_site_id backfill nor Stage
    2C's document-evidence categories (EXPLICIT_REFERENCE etc.) ever
    determine whether a Site covers the WHOLE allocation, one PHASE of
    it, or just a PARTIAL parcel - they only ever establish that a
    relationship exists at all. Asserting "whole_site"/"partial"/"phase"
    without evidence that actually says so would be exactly the kind of
    unearned inference this platform's product principles rule out. The
    bounded vocabulary (related | partial | phase | whole_site |
    unknown_scope) exists for a FUTURE evidence source that can genuinely
    distinguish scope (e.g. document text saying "Phase 1 of..." or "the
    whole of allocation X") - not built in this task."""

    __tablename__ = "allocation_site_relationships"
    __table_args__ = (UniqueConstraint("allocation_id", "site_id", name="uq_allocation_site_relationship"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    allocation_id: Mapped[int] = mapped_column(ForeignKey("local_plan_sites.id"))
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))

    # related | partial | phase | whole_site | unknown_scope - see class
    # docstring: every row this table's current writer creates uses
    # "unknown_scope", since no current evidence source determines scope.
    relationship_type: Mapped[str] = mapped_column(String(20), default="unknown_scope")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Why this relationship exists, at the coarse level a human/report
    # needs first - e.g. "legacy_matched_site_id_backfill",
    # "document_confirmed_site", "fuzzy_supported_by_document",
    # "multiple_document_supported_sites". See app.policy.
    # allocation_site_relationships for the exact bounded vocabulary.
    evidence_basis: Mapped[str] = mapped_column(String(50))
    # The specific Stage 2C evidence category (EXPLICIT_REFERENCE,
    # STRONG_CONTEXTUAL_REFERENCE, ...) for document-sourced rows; null
    # for the legacy matched_site_id backfill, which predates that
    # classification entirely.
    evidence_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Provenance FKs, both nullable independently - a legacy backfill row
    # has neither; a document-evidenced row normally has both. Never a
    # second copy of the document's own text: evidence_snippet below
    # reuses the SAME short, already-bounded snippet Stage 2C's own
    # _snippet() computed, per Section 9's explicit "do not duplicate
    # entire document text" instruction.
    evidence_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    evidence_application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True)
    evidence_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    # auto_applied | needs_confirmation | confirmed | rejected - same
    # bounded vocabulary as LocalPlanSite.review_status, reused rather
    # than invented, for whatever future review UI eventually acts on a
    # specific relationship row (out of scope for this task - see
    # app.policy.allocation_site_relationships' own module docstring for
    # what IS wired up now). confirmed_by/confirmed_at/note fields are
    # deliberately NOT added here - no confirm/reject flow writes them
    # yet, and adding unused provenance columns "because a sibling model
    # has them" is exactly what Stage 2D Section 3 warns against ("do not
    # blindly use suggested fields... add only what is necessary").
    review_status: Mapped[str] = mapped_column(String(30), default="auto_applied")

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Deliberately no back_populates on LocalPlanSite/Site (mirrors
    # LocalPlanSite.matched_site's own existing precedent, immediately
    # below - Site has never had a reverse collection for that FK either)
    # - callers query this table directly via app.policy.
    # allocation_site_relationships rather than through an ORM collection
    # attribute on either parent class, keeping this an additive change
    # that touches no existing model class body.
    allocation: Mapped["LocalPlanSite"] = relationship(foreign_keys=[allocation_id])
    site: Mapped["Site"] = relationship(foreign_keys=[site_id])
    evidence_document: Mapped["Document | None"] = relationship(foreign_keys=[evidence_document_id])
    evidence_application: Mapped["Application | None"] = relationship(foreign_keys=[evidence_application_id])


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

    # Extraction attempt state (AI Processing Reliability & Backlog
    # Throughput) - exists purely so a permanently-unextractable Application
    # (no usable document text - a scanned PDF, say) doesn't re-enter the
    # bounded daily extraction backlog forever, while a genuine, transient
    # AI/API failure still does, after a short cooldown. NULL/0 means "never
    # attempted, or already has scheme_intelligence" - scheme_intelligence
    # itself remains the sole SUCCESS signal (see stage_extraction), these
    # fields are only ever consulted for applications that don't have one
    # yet. Deliberately NOT a permanent blacklist: nothing here prevents a
    # future process (a document actually changing, a manual refresh, the
    # next evidence-freshness architecture) from clearing
    # extraction_last_outcome and re-opening the application - see
    # app.extraction.run_extraction's OUTCOME_* constants for the exact
    # values written here.
    extraction_last_outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    extraction_last_attempted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extraction_attempt_count: Mapped[int] = mapped_column(Integer, default=0)

    # Document discovery state (Evidence Completeness Foundation, PR A;
    # amended pre-merge, "Partial Initial Document Acquisition Recovery") -
    # records the most recent time Property AIgent successfully COMPLETED
    # the intended document-discovery/acquisition pass for this
    # application, independently of how many (if any) useful documents
    # that pass produced. NULL means "never successfully completed" -
    # deliberately distinct from the old ~Application.documents.any()
    # signal (see stage_documents), which conflated "has stored documents"
    # with "discovery has run", and distinct from evidence sufficiency
    # (see app.pipeline.evidence.is_evidence_sufficient) - an application
    # can be genuinely checked and still be evidence-insufficient, and
    # must NOT be re-checked daily merely because it's insufficient (that
    # is a future PR's job - material-change detection, the 90-day
    # fallback, or manual refresh - not routine Daily Discovery).
    #
    # This does NOT merely mean "the portal listing endpoint returned
    # successfully" - a listing can succeed while one or more of the
    # documents it identified as intended-to-download still fails to
    # download (a broken/timed-out portal file, say). In that case this
    # field is deliberately left un-advanced, so the application remains
    # eligible for the very next Daily Discovery run to retry ONLY the
    # still-missing document(s) - already-successful documents are
    # recognised by identity (see app.pipeline.evidence.
    # document_identity_key) and never re-downloaded. See
    # discover_and_store_documents_for_application's own
    # acquisition_complete tracking for the exact rule, including its one
    # known limitation (idox_anite/Bury councils cannot currently surface
    # an individual per-document download failure to that function at
    # all, since get_anite_documents silently drops a failed row instead
    # of returning it - a pre-existing architectural gap, not introduced
    # by this amendment, left for a later operational-recovery PR).
    #
    # Legacy rows (every Application that existed before this field was
    # added) are deliberately left NULL FOREVER by migration - never
    # backfilled to "now", and, since the second pre-merge amendment
    # ("Legacy Document-State Truthfulness"), never inferred from
    # historical Document.downloaded_at values either. An earlier version
    # of this migration backfilled legacy rows to MAX(downloaded_at)
    # across their existing Document rows - that was rejected in review:
    # under the pre-PR-A architecture, a Document row only ever proves
    # "one document was downloaded once", never "a complete intended
    # acquisition pass finished" (this field's own approved definition,
    # above) - some legacy applications may have had other intended
    # documents that failed or were never even discovered, with no
    # reliable record of that either way. Stamping ANY value here for
    # those rows would misrepresent unknown completeness as a genuine
    # completed check. See documents_legacy_unverified, immediately below,
    # for how rollout safety (not re-queuing ~708 legacy documented
    # applications for routine Daily Discovery the moment this migrates)
    # is achieved WITHOUT touching this field's own truthful meaning.
    documents_last_checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Legacy document-state rollout marker (PR A, second pre-merge
    # amendment, "Legacy Document-State Truthfulness") - a narrowly-scoped
    # ROLLOUT-SAFETY flag only, deliberately NOT a general workflow-state
    # field. True means: this Application already had >=1 Document row
    # before this amendment's migration ran, and there is no genuine
    # evidence a completed acquisition pass ever happened under
    # documents_last_checked_at's real semantic - completeness is UNKNOWN
    # (neither "recently checked" nor "definitely never checked"). False
    # means either a genuinely new application (nothing to prove either
    # way) or a legacy application that has SINCE been explicitly,
    # successfully rechecked - discover_and_store_documents_for_application
    # clears this flag the moment it stamps a genuine
    # documents_last_checked_at (see that function's own comment),
    # permanently moving the row into normal, non-legacy state; the flag
    # is never set back to True afterwards.
    #
    # app.pipeline.run_weekly.DOCUMENT_DISCOVERY_ELIGIBLE excludes any row
    # where this is True, so legacy documented applications are never
    # picked up by ROUTINE Daily Discovery after rollout - only by an
    # explicit, individually-targeted recheck (a future PR B material-
    # change trigger, 90-day fallback, or manual refresh calling
    # discover_and_store_documents_for_application directly - none of
    # which are implemented by this amendment, only made possible by it).
    # See app.db.session._backfill_documents_legacy_unverified for the
    # migration that sets this for existing rows.
    documents_legacy_unverified: Mapped[bool] = mapped_column(Boolean, default=False)

    # PR B1 ("Material Application-State Detection + Persisted Refresh
    # Signal") - the smallest persisted signal for PR B's overall
    # intelligence-freshness architecture, deliberately four flat columns
    # rather than a new event-log table (same established pattern as
    # extraction_last_outcome/extraction_last_attempted_at/
    # extraction_attempt_count above - a conceptually similar "does this
    # need reprocessing" signal already solved this way in this codebase).
    #
    # evidence_refresh_required means EXACTLY "a targeted evidence check
    # should eventually happen for this application" - it does NOT mean
    # "AI is stale" (that determination belongs to a later PR, once B2
    # actually knows whether the evidence itself changed) and it does NOT
    # mean "documents are known to be missing" (that is PR A's own,
    # separate documents_last_checked_at/documents_legacy_unverified
    # concern, untouched by this field). B1 only ever SETS this to True
    # (via app.pipeline.material_change.detect_material_application_change
    # finding a genuine change) - it never clears it; consuming/resetting
    # the signal once a refresh actually happens is a later PR's job
    # entirely, not implemented here.
    evidence_refresh_required: Mapped[bool] = mapped_column(Boolean, default=False)
    # Comma-joined app.pipeline.material_change reason code(s) (e.g.
    # "decision_granted", or "decision_granted,unit_count_changed" if
    # more than one fired in the same pass) - deterministic reason codes,
    # not free text, per PR B's own "prefer deterministic reason codes"
    # instruction. Overwritten (not appended to) on each newly-detected
    # change - this is not an event log, just "why is the signal
    # currently set", so the latest genuine reason is always what's
    # stored; see this module's own migration notes for why no historical
    # change-event table was introduced for this.
    evidence_refresh_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Trigger provenance (PR B design, Part I) - B1 only ever writes
    # "material_change" here. Deliberately a plain string, not an enum
    # column, so a future PR can add "periodic_staleness"/"manual"/
    # "system_recovery" values without a schema change - this field
    # exists specifically so those future triggers can share the SAME
    # persisted signal rather than each inventing their own.
    evidence_refresh_trigger: Mapped[str | None] = mapped_column(String(30), nullable=True)
    evidence_refresh_requested_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # PR B2 (Targeted Evidence Refresh) - the truthful OUTCOME of the most
    # recent targeted check app.pipeline.evidence_refresh actually
    # ATTEMPTED in response to evidence_refresh_required (whether or not it
    # completed successfully). One of app.pipeline.evidence_refresh's four
    # OUTCOME_* constants (new_material_evidence | checked_no_new_evidence |
    # portal_unavailable | acquisition_incomplete). NULL means "no targeted
    # refresh has ever run for this application" - distinct from evidence_
    # refresh_required itself, which B2 DOES clear on a successful check
    # (new evidence found or genuinely none) but deliberately never on
    # portal_unavailable/acquisition_incomplete, so the row remains
    # retryable - see evidence_refresh_required's own comment for why B1's
    # reason/trigger/requested_at fields above are left untouched either
    # way (an audit trail of what last triggered the request, not a
    # queue-position marker).
    evidence_refresh_last_outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # PR B2 FINAL pre-merge amendment ("Truthful Refresh Timestamp") - means
    # EXACTLY "the most recent time PropertyAIgent successfully COMPLETED
    # the requested targeted evidence check for this application" - i.e.
    # advances ONLY alongside evidence_refresh_last_outcome being new_
    # material_evidence or checked_no_new_evidence. It is deliberately NOT
    # "the most recent refresh attempt", NOT "the most recent time a
    # refresh started", and NOT "the most recent portal failure" - a
    # portal_unavailable/acquisition_incomplete outcome leaves this field
    # completely unchanged (across any number of consecutive failed
    # attempts), so a future freshness check (e.g. a 90-day fallback) can
    # safely measure "time since we last genuinely learned something" from
    # this one field, without needing to cross-reference evidence_refresh_
    # last_outcome to know whether that measurement is trustworthy.
    evidence_refresh_last_checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The B3 handoff signal (PR B2, Part 13) - set ONLY when a targeted
    # refresh outcome is new_material_evidence, i.e. genuinely new,
    # relevant portal evidence was found and stored. Deliberately a
    # timestamp, not a boolean "intelligence_refresh_required" flag - a
    # flag B2 itself never clears again would become permanently stuck
    # True the moment ANY future B3 improvement changes what "consumed"
    # means, whereas a future B3 can always compare this timestamp against
    # its own last-processed timestamp to decide staleness, and update/
    # clear it once it has actually acted on it. B2 never regenerates AI or
    # touches SchemeIntelligence itself - this field is purely the
    # truthful record that new evidence exists for B3 to look at.
    material_evidence_changed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # PR B3 (Evidence-Driven AI Intelligence Refresh) - the B3 freshness
    # watermark: the newest material_evidence_changed_at value that has
    # already been successfully incorporated into the currently-LIVE
    # SchemeIntelligence/Site Summary for this application. B3 eligibility
    # (app.pipeline.run_weekly.INTELLIGENCE_REFRESH_ELIGIBLE) is exactly
    # "material_evidence_changed_at is set, and is newer than this field (or
    # this field is still NULL)". Deliberately compared against material_
    # evidence_changed_at, NOT evidence_refresh_required - B1/B2's own
    # eligibility flag means "the portal should be checked", a materially
    # different question from "has the live AI intelligence incorporated
    # the evidence B2 already confirmed is new" (see this task's own Part 6).
    # Only ever advanced by a FULLY successful atomic refresh (app.
    # extraction.intelligence_refresh.refresh_intelligence_for_application) -
    # stamped to the exact material_evidence_changed_at value just
    # incorporated (not utcnow()), so a later, still-newer material_
    # evidence_changed_at (a second material event arriving before this one
    # was ever processed) is never silently skipped. Left completely
    # unchanged on any AI/validation/summary failure - see that function's
    # own docstring for the exact atomic-replacement contract.
    intelligence_evidence_processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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

    # Stage 3B ("Forward Allocation-Reference Evidence Scan") scan-state
    # marker - NULL means "not yet scanned for allocation-reference
    # evidence". Mirrors Application.documents_last_checked_at's own
    # established pattern (a plain nullable timestamp, not a boolean) for
    # the same reason: it records WHEN a check last completed, not just
    # whether one ever did. Audited before adding this: Document has no
    # existing timestamp/hash/version field suitable for this (only
    # downloaded_at, which means something else - when the file was
    # fetched, not when any downstream processing looked at its text) -
    # this is the smallest additive field that makes incremental,
    # idempotent scanning possible. Only ever set by app.policy.
    # allocation_evidence_scan on successful processing of this document -
    # left NULL on failure so a failed document remains eligible for retry
    # on the next run (see that module's own docstring for the full
    # design). Existing Document rows are effectively immutable once
    # extracted_text is set (no code path mutates it after the fact - a
    # material change produces a new Document row, mirroring
    # MonitoredReport's own "new edition is always a new row" convention)
    # so a simple NULL-check is sufficient; no content-hash comparison is
    # needed unless that assumption is later found to be wrong.
    allocation_evidence_scanned_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    # Text, not String(200) - LLM-narrated free text like its sibling
    # site_evidence below, not a short categorical value; confirmed real
    # extracted content already exceeds 200 chars (PostgreSQL migration:
    # SQLite never enforced this bound at all, so it went unnoticed until
    # Postgres's real VARCHAR(200) constraint rejected an insert).
    existing_use: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    # --- PR B3 (Evidence-Driven AI Intelligence Refresh) -----------------
    # Planning-outcome + affordable-housing intelligence that B2's targeted
    # evidence refresh can surface but the original 3-LLM-call extraction
    # pipeline above never asked about (recommendation direction, formal
    # refusal/withdrawal reasoning, and - the explicit Product Owner
    # requirement this PR adds - affordable housing/tenure treated as
    # first-class intelligence, not free text buried inside affordable_
    # classification_reason). All nullable/additive; NULL on every row this
    # PR's own migration does not touch (no historical value is ever
    # fabricated - see app.extraction.intelligence_refresh's own module
    # docstring). Only ever written by app.extraction.intelligence_refresh.
    # refresh_intelligence_for_application, as part of one atomic
    # replacement - never partially updated.

    # The B1 material_change reason (see app.pipeline.material_change)
    # whose evidence this row's CURRENT content reflects - mirrors
    # Application.evidence_refresh_reason but on the intelligence side:
    # "why does this intelligence look the way it does", for observability
    # and future auditing. Comma-joined if more than one reason fired in
    # the pass that produced this content (same format as B1's own field).
    latest_material_event: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # approval | refusal | unclear - ONLY ever set from genuine officer/
    # committee recommendation evidence (Parts 18-19: "never map
    # recommendation directly to formal determination"). NULL means no
    # recommendation evidence has been processed for this row yet - not
    # the same claim as "unclear" (evidence exists but is directionless).
    recommendation_direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # True while a recommendation exists but no separate formal decision
    # evidence has confirmed the outcome; False once Granted/Refused/
    # Withdrawn is evidenced; NULL when this row has no B3 refresh content
    # at all yet (distinct from "known False" - see field comment above).
    formal_decision_outstanding: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Evidenced refusal reasoning (Part 16) - NULL/empty means no reliable
    # reason was identified, never fabricated. Free text, matching this
    # model's own established style for narrated LLM output (e.g.
    # site_evidence, affordable_classification_reason above).
    refusal_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Evidenced withdrawal reasoning (Part 17) - same "never invent" rule.
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The affordable-housing SECURITY/AUTHORITY state (Part 12) - a
    # materially different question from affordable_data_status above
    # (which only ever means "did we find affordable DATA", e.g.
    # affordable_percentage_found/insufficient_evidence). One of
    # app.extraction.intelligence_refresh.AFFORDABLE_HOUSING_STATUSES:
    # proposed | policy_required | officer_recommended | committee_position
    # | agreed | conditioned | legally_secured | subject_to_viability_review
    # | unknown. The one hard commercial rule this field exists to enforce:
    # Property AIgent must never describe a merely-proposed position as
    # legally_secured - only an executed S106/operative Deed of Variation
    # may justify that value (see build_refresh_prompt's own instructions).
    affordable_housing_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Short evidence-grounded narrative of the CURRENT affordable housing
    # position, including an explicit description of what changed from the
    # previous position where evidenced (Part 13) - e.g. "The executed S106
    # secures 35% affordable housing (Social Rent/Shared Ownership 70/30),
    # a different split from the applicant's earlier 40% proposal." Free
    # text, not a second copy of affordable_tenure_split_final - this is
    # the narrated CHANGE/STATUS story, that field is the raw data value.
    affordable_housing_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Historical B3 rebuild completion marker (app.extraction.
    # historical_rebuild) - deliberately SEPARATE from Application.
    # intelligence_evidence_processed_at, which means "the latest
    # material_evidence_changed_at incorporated into live intelligence" (a
    # B1/B2/B3 freshness concept). Historical rebuild is not a planning-
    # change event and must never fabricate that field - see this module's
    # own docstring for why. intelligence_rebuild_version records which
    # named B3 standard (e.g. "b3_v1") last successfully regenerated this
    # row via the historical runner; intelligence_rebuilt_at records when.
    # Both NULL means never rebuilt. A future B3 standard upgrade bumps the
    # version string to make every row eligible again, independent of
    # whether B1/B2 ever fires for it.
    intelligence_rebuild_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    intelligence_rebuilt_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    # Text, not String(300) - this field's own purpose is to keep the
    # source document's wording "verbatim", which a length cap contradicts
    # by construction; confirmed real content already exceeds 300 chars
    # (same PostgreSQL migration finding as SchemeIntelligence.existing_use
    # above - SQLite never enforced the bound at all).
    raw_classification_label: Mapped[str | None] = mapped_column(Text, nullable=True)

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

    # --- Sprint 3F ("Allocation Policy Page Extraction", Part 7) - the raw
    # deterministic identification facts a page's own text carried, kept
    # regardless of whether they resolved to a confident allocation_id
    # match (Part 7: "No provenance may be lost" - a reviewer looking at a
    # needs_review row with allocation_id still null should still be able
    # to see WHAT identifier/title the page itself printed). Populated by
    # app.visuals.allocation_identifiers via app.visuals.matching.
    # match_allocation_reference, never invented. ---
    detected_allocation_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detected_allocation_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # exact_policy_reference | normalised_policy_reference |
    # exact_allocation_title | policy_reference | site_name |
    # document_application_inheritance | None - which tier of
    # app.visuals.matching actually decided allocation_id/site_id (or that
    # nothing did) - distinct from extraction_confidence above, which is
    # the AI vision model's own confidence in the IMAGE classification,
    # not this deterministic matching decision.
    match_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

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


class ScrapeRun(Base):
    """One attempted run of the Planning Application scraper pipeline
    (app.pipeline.run_weekly) for one council - the operational evidence
    Pilot Readiness PR-2 ("Production Freshness & Core Data Integrity",
    Part 6) needs to answer "is this council's data actually fresh" as a
    question distinct from "does this council have recent Application
    activity" (Part 7: "Scraper execution health and source activity are
    different concepts" - a council can genuinely have zero new
    Applications in a healthy run, and a stalled scraper can sit next to
    old-but-real Application data that looks superficially fine).

    No equivalent tracking existed anywhere in this codebase before this
    sprint - MonitoredSource/MonitoredReport track POLICY source
    monitoring (a different pipeline, already covered), and
    Application.first_seen_at/last_seen_at only ever reflect the data
    itself, never whether the run that touched it actually succeeded. This
    is therefore new, deliberately minimal state (Part 6: "Only add
    schema/state if there is a genuine missing operational requirement"),
    not a duplicate of anything that already exists.

    Written by scripts/run_daily_councils.py (the production orchestrator
    entry point), one row per attempted council per invocation - never
    updated in place mid-run beyond the one create-then-finalise sequence
    a single attempt naturally involves, and never deleted (an append-only
    run history, same "nothing silently overwritten" discipline as
    AllocationVersion/LocalPlanStatusHistory)."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    council_code: Mapped[str] = mapped_column(ForeignKey("councils.code"))

    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # running | success | partial | failed - "partial" is a real,
    # meaningful distinct outcome (see run_weekly.py's own per-month
    # try/except in stage_scrape: one month failing doesn't fail the
    # whole run) - never collapsed into a binary success/failure.
    status: Mapped[str] = mapped_column(String(20), default="running")

    # Application row count for this council, queried immediately before
    # and after the subprocess runs - the orchestrator's own before/after
    # diff, not anything run_weekly.py itself reports (no change to that
    # script's internals was needed for this). "Discovered" (net new rows)
    # is what's actually measurable this way; "updated" (an existing row's
    # non-identity fields changing) is not cheaply measurable from outside
    # the pipeline without a second, wider query, so is deliberately left
    # null here rather than approximated - see this model's own field
    # comment on applications_updated below.
    applications_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applications_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Always net-new rows (applications_after - applications_before) once
    # both are known - a denormalised convenience the orchestrator fills
    # in directly, not a generated column (portable across SQLite/Postgres
    # without a dialect-specific expression).
    applications_discovered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Deliberately left unset (None) by every current writer - an existing
    # Application row's non-identity fields (status/decision/documents)
    # changing is real but not cheaply measurable from outside the
    # pipeline via a before/after count the way new rows are; a future
    # sprint that wants this would need run_weekly.py itself to report it,
    # not the orchestrator guessing from row counts alone. Kept as a named
    # column now (rather than added later) so this model's shape doesn't
    # need to change again once that's built.
    applications_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Free text - the subprocess's own stderr tail on failure, or a short
    # human-readable summary on success/partial. Never silently discarded
    # on failure (Part 6: "failure/error state" is an explicit requirement).
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # scheduled | manual - who/what triggered this attempt, so a manually
    # re-run council after an operator noticed staleness isn't confused
    # with the daily production schedule actually having run.
    triggered_by: Mapped[str] = mapped_column(String(20), default="scheduled")

    council: Mapped["Council"] = relationship()


class IntelligenceRun(Base):
    """One attempted run of the bounded Intelligence Processing job
    (scripts.run_intelligence_processing) - the operational evidence Pilot
    Readiness PR-2's final pre-merge amendment ("Continuous Intelligence
    Processing" / "Observability") needs to answer "is genuinely
    outstanding AI extraction/summary work actually getting processed" as
    a question distinct from ScrapeRun above (which only ever answers "did
    scraping/document-collection succeed" - Daily Discovery never invokes
    AI by design, see run_daily_councils.py's own docstring).

    Deliberately mirrors ScrapeRun's shape (append-only, one row per
    invocation of the whole job - not per council/application, since the
    job's own workload cap is applied across all councils in one run, not
    per council) rather than introducing a new observability pattern -
    "reuse existing architecture where possible" (CLAUDE.md)."""

    __tablename__ = "intelligence_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # running | success | partial | failed (AI Processing Reliability &
    # Backlog Throughput - was unconditionally "success" whenever the run
    # reached its own end, even with most planned extractions failing; now
    # mirrors ScrapeRun/AcquisitionHealth's own "any known unresolved
    # failure counts" policy - see process_intelligence_backlog's
    # _classify_run_status for the exact rule). "failed" is still reserved
    # for the job itself not meaningfully running at all (missing API key
    # with outstanding work, or a top-level crash) - one item failing still
    # never aborts the rest of the run (Part 5: "one failed extraction does
    # not corrupt remaining work"), it now just means the run is reported
    # "partial" rather than a misleading "success".
    status: Mapped[str] = mapped_column(String(20), default="running")

    # Extraction (Application -> SchemeIntelligence) counters.
    # candidates_inspected: every row the bounded candidate-scan looked at
    # this run (including ones classified no_usable_text below) - always
    # >= extractions_attempted, bounded by the scan cap (see stage_
    # extraction's own docstring), never a full-table scan.
    extractions_candidates_inspected: Mapped[int] = mapped_column(Integer, default=0)
    # attempted/succeeded/failed only ever count GENUINE attempts - i.e. an
    # application that had usable document text and an LLM call sequence
    # was actually started. no_usable_text is its own bucket, deliberately
    # excluded from both attempted and failed - it is not an AI failure,
    # see app.extraction.run_extraction.OUTCOME_NO_USABLE_TEXT.
    extractions_attempted: Mapped[int] = mapped_column(Integer, default=0)
    extractions_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    extractions_no_usable_text: Mapped[int] = mapped_column(Integer, default=0)
    extractions_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Scheme-summary (Site.status_summary) counters.
    summaries_attempted: Mapped[int] = mapped_column(Integer, default=0)
    summaries_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    summaries_failed: Mapped[int] = mapped_column(Integer, default=0)

    # PR B3 (Evidence-Driven AI Intelligence Refresh) - a THIRD, independent
    # counter family, distinct from extractions_* (brand-new SchemeIntelligence,
    # Application.scheme_intelligence IS NULL) and summaries_* (routine
    # Site-history-grown trigger, unrelated to B2 evidence). refresh_*
    # counts app.pipeline.run_weekly.stage_intelligence_refresh's own work:
    # an EXISTING SchemeIntelligence row whose Application.material_
    # evidence_changed_at is newer than its intelligence_evidence_
    # processed_at watermark. succeeded means the full atomic replacement
    # (intelligence + Site Summary + watermark) committed; failed means any
    # part of it did not, and the previous live intelligence/summary/
    # watermark were left completely untouched (see app.extraction.
    # intelligence_refresh's own atomic-replacement contract).
    refresh_candidates_inspected: Mapped[int] = mapped_column(Integer, default=0)
    refresh_attempted: Mapped[int] = mapped_column(Integer, default=0)
    refresh_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    refresh_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Backlog still outstanding AFTER this run - the bounded-workload
    # mechanism's whole point (Part 6/8): a large backlog is deliberately
    # NOT drained in one run, so this is what tells an operator "there is
    # still more to do, expect N further bounded runs" rather than that
    # being invisible between runs.
    applications_backlog_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sites_backlog_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Free text - short human-readable summary, or the job-level error on
    # a "failed" run. Same discipline as ScrapeRun.detail.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    triggered_by: Mapped[str] = mapped_column(String(20), default="scheduled")
