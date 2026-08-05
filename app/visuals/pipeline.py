"""Orchestration pipeline for visual-evidence extraction (Sprint 3C,
"Allocation and Site-Plan Image Extraction", Part 14 idempotency + Part 16
performance/cost control). Wires every other app.visuals module
(document_selection -> page_detection -> rendering -> classification ->
matching) into real VisualEvidence rows. This is what
python -m app.visuals.extract_site_plans (this package's CLI, Part 15)
calls.

Idempotency (Part 14): before rendering or classifying anything, a page's
identity hash (rendering.compute_page_render_hash, derived from the
SOURCE FILE's own hash - never the rendered image's bytes) is checked
against any existing VisualEvidence row for the same page. An unchanged
page is skipped entirely - no re-render, no AI call, no duplicate row, no
reset review state. A page is only reprocessed when its source file
actually changed (a different file_hash), the render or classification
pipeline version bumped, or --force was passed explicitly. A REJECTED
image is never reprocessed automatically even under --force, since a
human's rejection is a deliberate decision this pipeline never silently
overturns on its own (Part 10).

Cost/performance control (Part 16): PipelineLimits caps how many pages
per document and how many AI classifications a single run will do - a run
stops accepting new work once a limit is hit rather than running
unbounded, and reports that in PipelineStats.limit_reached.

Every module up to this point is a pure function operating on already-
loaded objects - this is the one file in the package that actually
touches a database session and calls the real OpenAI client.
"""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from sqlalchemy import select

from app.db.models import Application, Document, LocalPlan, LocalPlanSite, MonitoredReport, Site, VisualEvidence
from app.visuals.classification import PROMPT_VERSION as CLASSIFICATION_PROMPT_VERSION
from app.visuals.classification import classify_page
from app.visuals.document_selection import select_candidate_documents
from app.visuals.matching import match_document_visual, match_report_visual, match_stored_identifiers
from app.visuals.page_detection import detect_candidate_pages_in_pdf
from app.visuals.primary_selection import compute_primary_flags
from app.visuals.rendering import RENDER_VERSION, compute_file_hash, compute_page_render_hash, render_page

# gpt-4o-mini vision pricing is usage-based on image tokens, which vary
# with resolution - this is a best-effort per-image estimate (matching
# app.policy.extract_plan_evidence's own "not billing-accurate" caveat for
# its text-extraction cost estimate), not a guarantee. OpenAI's own usage
# dashboard is the source of truth for actual spend.
_ESTIMATED_COST_PER_IMAGE_USD = 0.01

DEFAULT_MAX_PAGES_PER_DOCUMENT = 20
DEFAULT_MAX_AI_CLASSIFICATIONS_PER_RUN = 200


@dataclasses.dataclass
class PipelineLimits:
    max_pages_per_document: int = DEFAULT_MAX_PAGES_PER_DOCUMENT
    max_ai_classifications: int = DEFAULT_MAX_AI_CLASSIFICATIONS_PER_RUN


@dataclasses.dataclass
class PipelineStats:
    documents_scanned: int = 0
    documents_skipped_not_candidate: int = 0
    pages_considered: int = 0
    pages_rendered: int = 0
    ai_classifications_run: int = 0
    useful_visuals_found: int = 0
    visuals_linked: int = 0
    visuals_queued_for_review: int = 0
    duplicates_skipped: int = 0
    limit_reached: bool = False
    errors: list = dataclasses.field(default_factory=list)

    @property
    def estimated_ai_cost_usd(self) -> float:
        return round(self.ai_classifications_run * _ESTIMATED_COST_PER_IMAGE_USD, 4)


def _existing_visual_for_page(
    session, *, document_id: int | None, monitored_report_id: int | None, scope_local_plan_id: int | None, page_number: int,
) -> VisualEvidence | None:
    """document_id/monitored_report_id scope the lookup to one specific
    source row's own images, same as everywhere else in this module. When
    BOTH are None (the --local-plan-id/--allocation-id CLI scopes,
    process_local_plan_pdf, which have no Document or MonitoredReport row
    to scope by at all) scope_local_plan_id is required instead - without
    it, this query would match source_page alone across the ENTIRE table,
    colliding with any unrelated document/report whose own page 1
    (say) happens to already have a row, silently treating a brand new
    Local Plan page as "the same" as a completely unrelated image."""
    query = select(VisualEvidence).where(VisualEvidence.source_page == page_number, VisualEvidence.status == "current")
    if document_id is not None:
        query = query.where(VisualEvidence.document_id == document_id)
    elif monitored_report_id is not None:
        query = query.where(VisualEvidence.monitored_report_id == monitored_report_id)
    else:
        query = query.where(
            VisualEvidence.document_id.is_(None),
            VisualEvidence.monitored_report_id.is_(None),
            VisualEvidence.local_plan_id == scope_local_plan_id,
        )
    return session.execute(query).scalars().first()


def _is_unchanged(existing: VisualEvidence, page_render_hash: str) -> bool:
    """An existing row counts as "already up to date" only when it was
    produced from the SAME source content AND the SAME classification
    prompt version - either changing means Part 14's reprocess triggers
    apply."""
    return (
        existing.page_render_hash == page_render_hash
        and existing.extraction_prompt_version == CLASSIFICATION_PROMPT_VERSION
    )


def _recompute_primary_for_site(session, site_id: int) -> None:
    images = list(session.execute(select(VisualEvidence).where(VisualEvidence.site_id == site_id, VisualEvidence.status == "current")).scalars())
    flags = compute_primary_flags(images, "site")
    for image in images:
        image.is_primary = flags.get(image.id, False)


def _recompute_primary_for_allocation(session, allocation_id: int) -> None:
    images = list(
        session.execute(select(VisualEvidence).where(VisualEvidence.allocation_id == allocation_id, VisualEvidence.status == "current")).scalars()
    )
    flags = compute_primary_flags(images, "allocation")
    for image in images:
        image.is_primary = flags.get(image.id, False)


def _extract_single_page_text(pdf_path: str, page_number: int) -> str:
    import pdfplumber

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if 1 <= page_number <= len(pdf.pages):
                return pdf.pages[page_number - 1].extract_text() or ""
    except Exception:
        pass
    return ""


def _process_pdf_pages(
    session, client, *, pdf_path: str, council_code: str, document_id: int | None,
    monitored_report_id: int | None, scope_local_plan_id: int | None = None,
    source_document_title: str | None, source_document_url: str | None,
    match_fn, limits: PipelineLimits, stats: PipelineStats, force: bool, dry_run: bool = False,
) -> None:
    """match_fn(page_text: str) -> dict, a closure the caller binds to the
    right matching strategy (app.visuals.matching.match_document_visual
    for an Application Document, or match_report_visual for a Local Plan
    MonitoredReport). scope_local_plan_id is required whenever BOTH
    document_id and monitored_report_id are None (process_local_plan_pdf's
    direct-PDF path, Part 15's --local-plan-id/--allocation-id scopes) -
    see _existing_visual_for_page for why."""
    if document_id is None and monitored_report_id is None and scope_local_plan_id is None:
        raise ValueError("_process_pdf_pages needs scope_local_plan_id when neither document_id nor monitored_report_id is set")

    try:
        source_file_hash = compute_file_hash(pdf_path)
    except OSError as exc:
        stats.errors.append(f"could not read {pdf_path}: {exc}")
        return

    try:
        # Stage 1 scans the WHOLE document, unbounded - it's pure text/
        # vector-content inspection with no network or AI cost, so
        # truncating it would silently miss a genuine candidate page that
        # happens to sit past an early cutoff (confirmed in pilot testing:
        # a real allocation map on page 106 of a 219-page Local Plan was
        # never reached when this scan itself was capped at 20-25 pages).
        # limits.max_pages_per_document instead caps candidates AFTER
        # detection - the expensive step (rendering + AI classification)
        # this limit actually exists to bound, per Part 16.
        candidates = detect_candidate_pages_in_pdf(pdf_path)[: limits.max_pages_per_document]
    except Exception as exc:
        stats.errors.append(f"page detection failed for {pdf_path}: {exc}")
        return
    stats.pages_considered += len(candidates)

    if document_id is not None:
        render_id = document_id
    elif monitored_report_id is not None:
        render_id = monitored_report_id
    else:
        render_id = f"localplan{scope_local_plan_id}"
    touched_site_ids: set[int] = set()
    touched_allocation_ids: set[int] = set()

    for candidate in candidates:
        if stats.ai_classifications_run >= limits.max_ai_classifications:
            stats.limit_reached = True
            break

        page_number = candidate["page_number"]
        page_render_hash = compute_page_render_hash(source_file_hash, page_number, RENDER_VERSION)

        existing = _existing_visual_for_page(
            session, document_id=document_id, monitored_report_id=monitored_report_id,
            scope_local_plan_id=scope_local_plan_id, page_number=page_number,
        )
        if existing is not None and existing.review_status == "rejected":
            # A human's rejection is never silently overturned, even with
            # --force (Part 10).
            stats.duplicates_skipped += 1
            continue
        if existing is not None and not force and _is_unchanged(existing, page_render_hash):
            stats.duplicates_skipped += 1
            continue

        # Reaching this point already means "this page needs fresh
        # processing" - every unchanged/rejected case above already
        # `continue`d past it. render_page's OWN idempotency check keys on
        # storage path alone (council/document/page/render-version), not
        # file content, so it would otherwise happily hand back a stale
        # cached image left over from a PREVIOUS version of this same
        # source file - force=True here (independent of the pipeline's own
        # `force` argument) makes sure a genuine content change actually
        # gets re-rendered, not just re-classified against an old picture.
        render_result = render_page(pdf_path, page_number, council_code, render_id, force=True)
        if render_result is None:
            stats.errors.append(f"page {page_number} of {pdf_path}: rendering failed or refused")
            continue
        stats.pages_rendered += 1

        try:
            classification = classify_page(client, render_result["image_path"])
        except Exception as exc:
            stats.errors.append(f"page {page_number} of {pdf_path}: classification failed: {exc}")
            continue
        stats.ai_classifications_run += 1

        if classification["is_useful"]:
            stats.useful_visuals_found += 1

        page_text = _extract_single_page_text(pdf_path, page_number)
        match = match_fn(page_text)
        if any(match.get(key) for key in ("site_id", "application_id", "local_plan_id", "allocation_id")):
            stats.visuals_linked += 1
        stats.visuals_queued_for_review += 1

        # A reprocessed page is NEVER a mutation of the old row - always a
        # brand new one, with the old row marked superseded (Part 14:
        # "changed source at same URL -> supersede, never delete"), the
        # exact same pattern already established for MonitoredReport. This
        # preserves full history (including whatever review decision was
        # made against the old version) rather than silently overwriting it.
        # Fields are populated below BEFORE flushing, since source_page and
        # other columns are NOT NULL - flushing a still-empty row fails.
        row = VisualEvidence(document_id=document_id, monitored_report_id=monitored_report_id)

        row.site_id = match.get("site_id")
        row.application_id = match.get("application_id")
        row.local_plan_id = match.get("local_plan_id")
        row.allocation_id = match.get("allocation_id")
        if row.site_id is not None:
            touched_site_ids.add(row.site_id)
        if row.allocation_id is not None:
            touched_allocation_ids.add(row.allocation_id)
        row.source_document_title = source_document_title
        row.source_document_url = source_document_url
        row.source_page = page_number
        row.image_type = classification["image_type"]
        row.raw_classification_label = "; ".join(candidate["reasons"]) or None
        row.image_path = render_result["image_path"]
        row.thumbnail_path = render_result["thumbnail_path"]
        row.image_width = render_result["image_width"]
        row.image_height = render_result["image_height"]
        row.file_hash = render_result["file_hash"]
        row.page_render_hash = page_render_hash
        row.extraction_method = "ai_vision"
        row.extraction_model = classification["model"]
        row.extraction_prompt_version = classification["prompt_version"]
        row.extraction_confidence = classification["confidence"]
        row.candidate_reason = "; ".join(candidate["reasons"])
        # Sprint 3F ("Allocation Policy Page Extraction", Part 7) - the
        # deterministic identification/matching facts, kept regardless of
        # whether allocation_id ended up set (a needs_review row with no
        # confident match still shows a reviewer exactly what identifier/
        # title the page itself printed, and how the matcher scored it).
        row.detected_allocation_reference = match.get("detected_allocation_reference")
        row.detected_allocation_title = match.get("detected_allocation_title")
        row.match_method = match.get("match_method")
        row.match_confidence = match.get("match_confidence")
        # Every AI classification always starts needs_review - Part 9/10:
        # showing the WRONG image is a worse failure than a wrong number,
        # so nothing here is ever auto-applied regardless of confidence.
        row.review_status = "needs_review"

        if not dry_run:
            session.add(row)
            if existing is not None:
                existing.status = "superseded"
                session.flush()  # need row.id before it can be recorded as the supersessor
                existing.superseded_by_id = row.id

    # Recompute which image is primary for every object touched this run
    # (Part 9) - a new or newly-reclassified image can change the ranking,
    # so this always re-derives from scratch rather than only ever setting
    # the new row's own flag.
    if not dry_run:
        for site_id in touched_site_ids:
            _recompute_primary_for_site(session, site_id)
        for allocation_id in touched_allocation_ids:
            _recompute_primary_for_allocation(session, allocation_id)

    if dry_run:
        session.rollback()  # discard anything staged/mutated above - Part 15: "write nothing to the database"
    else:
        session.commit()


def process_document(
    session, client, document: Document, limits: PipelineLimits, stats: PipelineStats,
    force: bool = False, dry_run: bool = False,
) -> None:
    """Processes ONE already-selected candidate Document (caller runs it
    through app.visuals.document_selection first for a discovery run;
    an explicitly-targeted single document may skip that gate)."""
    stats.documents_scanned += 1
    if not document.local_path:
        stats.errors.append(f"document {document.id} has no local_path - nothing to render")
        return

    application = document.application
    council_code = application.council_code if application else None
    if council_code is None:
        stats.errors.append(f"document {document.id} has no resolvable council code - skipped")
        return

    match_fn = lambda _page_text: match_document_visual(document)
    _process_pdf_pages(
        session, client, pdf_path=document.local_path, council_code=council_code, document_id=document.id,
        monitored_report_id=None, source_document_title=document.document_name, source_document_url=document.source_url,
        match_fn=match_fn, limits=limits, stats=stats, force=force, dry_run=dry_run,
    )


def process_report(
    session, client, report: MonitoredReport, pdf_path: str, limits: PipelineLimits, stats: PipelineStats,
    force: bool = False, dry_run: bool = False,
) -> None:
    """Processes ONE Local Plan MonitoredReport against an already-
    downloaded local pdf_path - MonitoredReport has no local_path column
    of its own (Local Plan source files are supplied per-invocation, the
    same "you already have this PDF locally" shape as
    app.policy.extract_plan_evidence's --pdf argument, not an automated
    fetch this codebase doesn't otherwise do)."""
    stats.documents_scanned += 1
    allocations: list[LocalPlanSite] = []
    if report.local_plan_id is not None:
        allocations = list(
            session.execute(select(LocalPlanSite).where(LocalPlanSite.local_plan_id == report.local_plan_id)).scalars()
        )

    match_fn = lambda page_text: match_report_visual(report, page_text, allocations)
    _process_pdf_pages(
        session, client, pdf_path=pdf_path, council_code=report.council_code, document_id=None,
        monitored_report_id=report.id, source_document_title=report.title, source_document_url=report.final_url or report.url,
        match_fn=match_fn, limits=limits, stats=stats, force=force, dry_run=dry_run,
    )


def process_local_plan_pdf(
    session, client, local_plan: LocalPlan, pdf_path: str, limits: PipelineLimits, stats: PipelineStats,
    force: bool = False, dry_run: bool = False, allocation_scope: LocalPlanSite | None = None,
) -> None:
    """Processes a Local Plan's own PDF directly against pdf_path, for the
    --local-plan-id and --allocation-id CLI scopes (Part 15) - these have
    no MonitoredReport row of their own in the common case (a plan is
    often registered as a single MonitoredSource, not per-report), so this
    mirrors process_report's shape without requiring one. allocation_scope,
    if given (the --allocation-id scope), restricts matching to just that
    one allocation rather than every allocation in the plan - the same
    "only consider matches within what was explicitly asked for" principle
    process_document already applies by scoping to one Document."""
    stats.documents_scanned += 1
    if allocation_scope is not None:
        allocations = [allocation_scope]
    else:
        allocations = list(
            session.execute(select(LocalPlanSite).where(LocalPlanSite.local_plan_id == local_plan.id)).scalars()
        )

    # match_report_visual only ever reads .local_plan_id off its "report"
    # argument - a real MonitoredReport isn't required, just something
    # that duck-types the one attribute it uses.
    plan_ref = SimpleNamespace(local_plan_id=local_plan.id)
    match_fn = lambda page_text: match_report_visual(plan_ref, page_text, allocations)
    _process_pdf_pages(
        session, client, pdf_path=pdf_path, council_code=local_plan.council_code, document_id=None,
        monitored_report_id=None, scope_local_plan_id=local_plan.id,
        source_document_title=local_plan.plan_name, source_document_url=None,
        match_fn=match_fn, limits=limits, stats=stats, force=force, dry_run=dry_run,
    )


def run_for_application(
    session, client, application: Application, limits: PipelineLimits, stats: PipelineStats,
    force: bool = False, dry_run: bool = False,
) -> None:
    documents = list(session.execute(select(Document).where(Document.application_id == application.id)).scalars())
    candidates = select_candidate_documents(documents)
    stats.documents_skipped_not_candidate += len(documents) - len(candidates)
    for candidate in candidates:
        process_document(session, client, candidate["document"], limits, stats, force=force, dry_run=dry_run)


def run_for_site(
    session, client, site: Site, limits: PipelineLimits, stats: PipelineStats, force: bool = False, dry_run: bool = False,
) -> None:
    for application in site.applications:
        run_for_application(session, client, application, limits, stats, force=force, dry_run=dry_run)


def run_for_council(
    session, client, council_code: str, limits: PipelineLimits, stats: PipelineStats, force: bool = False, dry_run: bool = False,
) -> None:
    applications = list(session.execute(select(Application).where(Application.council_code == council_code)).scalars())
    for application in applications:
        run_for_application(session, client, application, limits, stats, force=force, dry_run=dry_run)


# --- Sprint 3G ("Places for Everyone Allocation Onboarding", Part 4/5) -----
#
# Deterministic RE-matching of already-extracted VisualEvidence rows
# against a Local Plan's CURRENT (possibly since-grown) set of allocations -
# never touches rendering or Vision classification at all, reusing exactly
# the stored detected_allocation_reference/detected_allocation_title
# (Sprint 3F) every extraction pass already wrote. This is what makes
# onboarding new LocalPlanSite rows for a plan that already has extracted
# images (Places for Everyone) cheap: the 156 images already exist, already
# carry their own identifier text - only the matching DECISION needs
# rerunning, not the $1.56 of Vision calls that produced them.

# A "secondary page" (Part 5 - title page -> illustration -> masterplan ->
# policy page) with no identifier of its own belongs to the immediately
# preceding identified allocation's page, but only within a bounded window -
# confirmed against real data (Sprint 3G live research: Places for
# Everyone's own JPA 30 "New Carrington" spread its capacity figures 2-3
# pages after its title page) - generous enough for that real case, bounded
# enough that a page far past a title never gets silently attributed to it.
SECONDARY_PAGE_WINDOW = 10


@dataclasses.dataclass
class RematchStats:
    candidates_considered: int = 0
    newly_linked: int = 0
    secondary_page_suggestions: int = 0
    skipped_confirmed: int = 0
    skipped_rejected: int = 0
    unmatched: int = 0


def _find_proximity_anchor(page_number: int, anchors: list[tuple[int, int]]) -> int | None:
    """anchors: [(page, allocation_id), ...] of every CONFIDENTLY-matched
    current page for this plan, already sorted by page ascending. Returns
    the allocation_id this page falls under, or None. A page belongs to
    the NEAREST anchor at or before it - never an anchor AFTER it (a
    secondary page always follows its own title page, never precedes it,
    per the real observed document structure) - and only within
    SECONDARY_PAGE_WINDOW pages, so a page far past the last known
    allocation's own span is correctly left unmatched rather than
    silently attributed to it."""
    candidate: tuple[int, int] | None = None
    for page, allocation_id in anchors:
        if page <= page_number:
            candidate = (page, allocation_id)
        else:
            break
    if candidate is None:
        return None
    anchor_page, allocation_id = candidate
    if page_number - anchor_page > SECONDARY_PAGE_WINDOW:
        return None
    return allocation_id


def rematch_local_plan_evidence(session, local_plan_id: int, dry_run: bool = False) -> RematchStats:
    """Re-matches every CURRENT, unlinked (allocation_id is None)
    VisualEvidence row for this Local Plan against its full current set of
    LocalPlanSite allocations - no rendering, no Vision call, no source PDF
    read at all. Two passes:

      1. Deterministic identifier/title re-match (Part 4) against each
         row's own already-stored detected_allocation_reference/
         detected_allocation_title, via match_stored_identifiers - the
         exact same priority tiers a fresh extraction uses, just replayed
         against a (now larger) allocation set.
      2. Secondary-page review suggestions (Part 5) for rows with NO
         identifier of their own at all, using page-proximity to an
         already-matched anchor - NEVER sets allocation_id (Part 5:
         "Never auto-link by page proximity alone"), only records a
         match_method/match_confidence suggestion a human can act on.

    Never touches a row whose review_status is "confirmed" or "rejected" -
    Part 8's "never overwrite confirmed evidence" applies to confirmed rows
    even when their own allocation_id happens to still be null (a human
    already finalised that row; this pass leaves it exactly as they left
    it), and a human's rejection is never silently reconsidered, matching
    every other reprocessing path in this codebase."""
    allocations = list(session.execute(select(LocalPlanSite).where(LocalPlanSite.local_plan_id == local_plan_id)).scalars())
    all_current = list(session.execute(
        select(VisualEvidence).where(VisualEvidence.local_plan_id == local_plan_id, VisualEvidence.status == "current")
    ).scalars())

    unlinked = [r for r in all_current if r.allocation_id is None]
    stats = RematchStats(candidates_considered=len(unlinked))

    touched_allocation_ids: set[int] = set()
    # Pass 1's outcome, tracked independently of the ORM objects themselves
    # (never read back off row.allocation_id) - this is what makes --dry-run
    # report EXACTLY what a real run would do: pass 2's anchor search below
    # must see pass 1's results even when dry_run=True leaves the actual
    # rows unmodified, or a dry-run preview would (and, before this fix,
    # did) undercount secondary-page suggestions relative to a real run.
    pass1_matches: dict[int, int] = {}  # VisualEvidence.id -> allocation_id

    for row in unlinked:
        if row.review_status == "rejected":
            stats.skipped_rejected += 1
            continue
        if row.review_status == "confirmed":
            stats.skipped_confirmed += 1
            continue
        match = match_stored_identifiers(row.detected_allocation_reference, row.detected_allocation_title, allocations)
        if match["allocation_id"] is not None:
            if not dry_run:
                row.allocation_id = match["allocation_id"]
                row.match_method = match["match_method"]
                row.match_confidence = match["match_confidence"]
            pass1_matches[row.id] = match["allocation_id"]
            stats.newly_linked += 1
            touched_allocation_ids.add(match["allocation_id"])

    # Anchors reflect pass 1's results (via pass1_matches) even in dry-run
    # mode, so a page just linked above can anchor a later secondary-page
    # suggestion in the same preview, identically to a real run.
    anchors = sorted(
        (
            (r.source_page, pass1_matches.get(r.id, r.allocation_id))
            for r in all_current
            if r.allocation_id is not None or r.id in pass1_matches
        ),
        key=lambda t: t[0],
    )
    for row in unlinked:
        if row.id in pass1_matches or row.review_status in ("rejected", "confirmed"):
            continue  # linked in pass 1, or already counted/skipped above
        if row.detected_allocation_reference or row.detected_allocation_title:
            # Has its own signal, but pass 1 found no allocation for it
            # (e.g. a not-yet-onboarded authority's own code) - a genuine
            # "still needs review", not a proximity case.
            stats.unmatched += 1
            continue

        suggested_allocation_id = _find_proximity_anchor(row.source_page, anchors)
        if suggested_allocation_id is not None:
            if not dry_run:
                row.match_method = "page_proximity_suggestion"
                row.match_confidence = 0.5
                # allocation_id intentionally left None (Part 5).
            stats.secondary_page_suggestions += 1
        else:
            stats.unmatched += 1

    if not dry_run:
        for allocation_id in touched_allocation_ids:
            _recompute_primary_for_allocation(session, allocation_id)
        session.commit()
    else:
        session.rollback()

    return stats
