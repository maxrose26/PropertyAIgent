"""Deterministic evidence-report discovery (housing-supply monitoring
amendment, "Add monitored housing supply and delivery reports", Part 2).

Fetches a council's registered index page (a monitoring page, evidence
library, housing land supply page, AMR page, planning-policy document
library - see MonitoredSource.source_type), finds linked documents, and
classifies each by TITLE/URL keyword rules alone - never AI. Part 2 is
explicit: "Do not use AI for link discovery or report-type classification
unless deterministic rules cannot produce a safe result" - and even then,
an unsafe/ambiguous result is queued for review (classification_status=
"needs_review"), never guessed by an LLM.

Every discovered document becomes its own permanent MonitoredReport row
(see that model's own docstring for why - full historic retention, Part
1/Part 5). Re-running discovery against an unchanged index page registers
nothing new (Part 2.4/Part 7's idempotency requirement) - only genuinely
new URLs create a row.
"""
from __future__ import annotations

import datetime as dt
import json
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MonitoredReport, MonitoredSource, PolicyChangeEvent
from app.policy.change_detection import classify_source_check, compute_content_hash
from app.policy.document_types import classify_policy_document_type
from app.policy.report_cadence import compute_next_check_due, is_due

DEFAULT_TIMEOUT_SECONDS = 15
STALE_AFTER_DAYS = 7
# Some council sites (confirmed live: stockport.gov.uk) return 403 to the
# default python-requests user agent while serving the identical page fine
# to an ordinary browser - a real finding from this amendment's own live
# validation (Part 8), not a hypothetical. A plain, honest browser-like
# user agent is enough to fix it; shared with app.policy.monitor so both
# modules' outbound requests behave the same way against the same sites.
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"}

_DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx")

# Ordered most-specific-first: a link is classified by the FIRST rule that
# matches, since several patterns overlap (e.g. a housing delivery test
# action plan's title also contains "housing delivery"). Each rule is
# (report_type, keyword_groups) where keyword_groups is an AND of ORs - the
# combined title+URL text must contain at least one keyword from EVERY
# group, which is what lets e.g. "adoption statement" require both an
# "adoption" word AND a "statement/notice" word rather than matching any
# document that merely mentions adoption once in passing.
_CLASSIFICATION_RULES: list[tuple[str, list[list[str]]]] = [
    ("adoption_statement", [["adoption"], ["statement", "notice"]]),
    ("inspector_report", [["inspector"], ["report"]]),
    ("housing_delivery_test_action_plan", [["housing delivery test", "hdt"], ["action plan"]]),
    ("housing_trajectory", [["trajectory"]]),
    ("housing_land_supply_statement", [["housing land supply", "5yhls", "five year", "five-year", "5-year", "5 year"]]),
    ("authority_monitoring_report", [["authority monitoring report", "authoritys monitoring report", "annual monitoring report", " amr ", "amr.pdf", "amr-", "-amr"]]),
    ("housing_delivery_report", [["housing delivery"]]),
    ("local_development_scheme", [["local development scheme", " lds "]]),
    ("local_plan", [["local plan"]]),
]


def classify_report_type(title_or_link_text: str | None, url: str) -> tuple[str | None, str | None]:
    """Returns (report_type, matched_rule_name). report_type is None when
    no rule matches confidently - Part 2.8: ambiguous classification must
    be queued for review, never guessed."""
    # Apostrophes stripped, not just lower-cased: a real live document from
    # this amendment's own pilot validation ("Authority's Monitoring Report
    # March 2026", the actual official Stockport title) was missed by the
    # AMR rule because "authority's monitoring report" != "authority
    # monitoring report" - councils use the possessive form at least as
    # often as the bare one, and stripping the apostrophe from both the
    # haystack and the keywords below handles either spelling uniformly.
    raw_text = f" {(title_or_link_text or '').lower()} {url.lower()} "
    haystack = raw_text.replace("'", "").replace("’", "")
    for report_type, keyword_groups in _CLASSIFICATION_RULES:
        if all(any(kw in haystack for kw in group) for group in keyword_groups):
            return report_type, f"{report_type}_keywords"
    return None, None


def extract_document_links(html: str, base_url: str) -> list[dict]:
    """Returns [{"url": absolute_url, "link_text": text}, ...], deduped by
    URL, restricted to links that look like an actual document rather than
    navigation/unrelated page links - a bare "Home" or "Contact us" link is
    never a candidate report."""
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        if not absolute.lower().split("?")[0].endswith(_DOCUMENT_EXTENSIONS):
            continue
        text = a.get_text(strip=True) or href
        seen.setdefault(absolute, text)
    return [{"url": url, "link_text": text} for url, text in seen.items()]


def register_discovered_reports(session: Session, source: MonitoredSource, links: list[dict]) -> dict:
    """For each discovered link: a URL already known to this source (any
    status - current or superseded, since a superseded row still means
    "already seen") is skipped - discovery only ever registers genuinely
    NEW urls; an existing report's own content changing is
    check_report_for_changes' job, not this function's. Returns counts:
    {"new_reports", "auto_classified", "needs_review"}."""
    existing_urls = {
        r.url for r in session.execute(
            select(MonitoredReport).where(MonitoredReport.monitored_source_id == source.id)
        ).scalars().all()
    }

    counts = {"new_reports": 0, "auto_classified": 0, "needs_review": 0}
    now = dt.datetime.now(dt.timezone.utc)

    for link in links:
        if link["url"] in existing_urls:
            continue

        report_type, matched_rule = classify_report_type(link["link_text"], link["url"])
        classification_status = "auto" if report_type else "needs_review"
        # Sprint 3D ("Policy Document Coverage & Discovery", Part 2) - a
        # SEPARATE, broader classification alongside the extraction-
        # routing one above. A document classify_report_type can't place
        # (a Policies Map, an SPD, a masterplan - none of these are AI
        # extraction targets, so classify_report_type correctly has no
        # rule for them) can still be usefully typed here for the
        # coverage engine (app.policy.coverage) to know it exists at all -
        # this never affects classification_status/extraction eligibility
        # above, which is unchanged.
        policy_document_type, _ = classify_policy_document_type(link["link_text"], link["url"])

        report = MonitoredReport(
            council_code=source.council_code, local_plan_id=source.local_plan_id,
            monitored_source_id=source.id, source_type=report_type,
            classification_status=classification_status, matched_classification_rule=matched_rule,
            policy_document_type=policy_document_type, policy_document_type_raw_label=link["link_text"],
            title=link["link_text"], url=link["url"], status="current",
            next_check_due=compute_next_check_due(report_type or "other"),
        )
        session.add(report)
        session.flush()  # assigns report.id

        session.add(PolicyChangeEvent(
            local_plan_id=source.local_plan_id, monitored_source_id=source.id, monitored_report_id=report.id,
            event_type="report_discovered" if report_type else "report_classification_needs_review",
            old_value=None, new_value=report_type or link["url"],
            detail=(
                f"New report discovered at {link['url']!r}, classified as {report_type!r} via {matched_rule!r}."
                if report_type else
                f"New document discovered at {link['url']!r} ({link['link_text']!r}) - no deterministic "
                f"classification rule matched; needs a human to confirm its report type."
            ),
            source_document_url=link["url"],
            auto_applied=bool(report_type), review_status="auto_applied" if report_type else "needs_review",
            detected_at=now,
        ))

        # Part 2.6 ("mark previous reports superseded where a clear later
        # edition exists"): a confidently-classified new report of the
        # SAME type for the SAME council/plan as an existing "current"
        # report is a plausible newer edition - but matching two different
        # URLs as "the same report" is inherently more failure-prone than
        # a same-URL hash diff (check_report_for_changes' auto case), so
        # this is ALWAYS queued for a human to confirm, never auto-applied
        # (Part 2.8).
        if report_type:
            existing_current = session.execute(
                select(MonitoredReport).where(
                    MonitoredReport.council_code == source.council_code,
                    MonitoredReport.source_type == report_type,
                    MonitoredReport.status == "current",
                    MonitoredReport.id != report.id,
                )
            ).scalars().all()
            for candidate in existing_current:
                session.add(PolicyChangeEvent(
                    local_plan_id=source.local_plan_id, monitored_source_id=source.id, monitored_report_id=candidate.id,
                    event_type="report_supersession_needs_review",
                    old_value=candidate.url, new_value=report.url,
                    detail=f"New {report_type} report discovered at {report.url!r} may be a newer edition of "
                           f"report {candidate.id} ({candidate.url!r}) - needs a human to confirm before the "
                           f"older report is marked superseded.",
                    proposed_data=json.dumps({"status": "superseded", "superseded_by_id": report.id}),
                    source_document_url=report.url,
                    auto_applied=False, review_status="needs_review", detected_at=now,
                ))

        counts["new_reports"] += 1
        counts["auto_classified" if report_type else "needs_review"] += 1

    if counts["new_reports"]:
        source.last_report_discovered_at = now
    source.next_check_due = compute_next_check_due(source.source_type, source.expected_publication_window, now)
    session.commit()
    return counts


def discover_reports_for_source(session: Session, source: MonitoredSource, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Fetches source.url, extracts document links, and registers any
    genuinely new ones. Returns register_discovered_reports' counts plus
    "fetch_failed": bool."""
    now = dt.datetime.now(dt.timezone.utc)
    source.last_checked = now
    try:
        response = requests.get(source.url, timeout=timeout, headers=REQUEST_HEADERS)
        response.raise_for_status()
    except requests.RequestException:
        last_ok = source.last_successful_check
        stale = last_ok is None or (_naive(now) - _naive(last_ok)) > dt.timedelta(days=STALE_AFTER_DAYS)
        source.monitoring_health = "stale" if stale else "error"
        source.next_check_due = compute_next_check_due(source.source_type, source.expected_publication_window, now)
        session.commit()
        return {"new_reports": 0, "auto_classified": 0, "needs_review": 0, "fetch_failed": True}

    source.last_successful_check = now
    source.monitoring_health = "ok"
    new_hash = compute_content_hash(response.text)
    if classify_source_check(source.content_hash, new_hash) == "changed":
        source.last_changed = now
    source.content_hash = new_hash

    links = extract_document_links(response.text, response.url or source.url)
    counts = register_discovered_reports(session, source, links)
    counts["fetch_failed"] = False
    return counts


def _naive(value: dt.datetime) -> dt.datetime:
    # SQLite round-trips a stored tz-aware datetime as naive on read back -
    # the same fact app.policy.monitor's own _naive_utcnow works around.
    return value.replace(tzinfo=None) if value.tzinfo else value


def check_report_for_changes(session: Session, report: MonitoredReport, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Checks report.url for a content change. Returns "first_check",
    "unchanged", "changed", or "failed".

    On "changed": Part 2.5 ("detect documents replaced at the same URL
    through hashes") - the file at this exact URL was swapped for a new
    edition. This is unambiguous (it's still the same URL slot), so it is
    handled as an AUTO-applied supersession: a brand new MonitoredReport
    row is created for the new content, and THIS row is marked superseded
    - never a silent overwrite of the old row's own hash (Part 1:
    "preserve all historic reports")."""
    now = dt.datetime.now(dt.timezone.utc)
    report.last_checked = now

    try:
        response = requests.get(report.url, timeout=timeout, headers=REQUEST_HEADERS)
        response.raise_for_status()
    except requests.RequestException:
        last_ok = report.last_successful_check
        stale = last_ok is None or (_naive(now) - _naive(last_ok)) > dt.timedelta(days=STALE_AFTER_DAYS)
        report.monitoring_health = "stale" if stale else "error"
        report.next_check_due = compute_next_check_due(report.source_type or "other")
        session.commit()
        return "failed"

    report.last_successful_check = now
    report.monitoring_health = "ok"
    if response.url and response.url != report.url:
        report.final_url = response.url

    new_hash = compute_content_hash(response.text)
    outcome = classify_source_check(report.content_hash, new_hash)

    if outcome == "changed":
        report.last_changed = now
        new_report = MonitoredReport(
            council_code=report.council_code, local_plan_id=report.local_plan_id,
            monitored_source_id=report.monitored_source_id, source_type=report.source_type,
            classification_status=report.classification_status, matched_classification_rule=report.matched_classification_rule,
            # Sprint 3D - carried over from the superseded row, same as
            # every other classification field here: a same-URL content
            # swap is still the same DOCUMENT slot, so its Part 2
            # classification doesn't need re-deriving (title/URL haven't
            # changed even though the file's bytes have).
            policy_document_type=report.policy_document_type, policy_document_type_raw_label=report.policy_document_type_raw_label,
            title=report.title, url=report.url, final_url=report.final_url, content_hash=new_hash,
            status="current", next_check_due=compute_next_check_due(report.source_type or "other"),
        )
        session.add(new_report)
        session.flush()  # assigns new_report.id

        report.status = "superseded"
        report.superseded_by_id = new_report.id
        report.supersession_method = "auto"

        session.add(PolicyChangeEvent(
            local_plan_id=report.local_plan_id, monitored_report_id=new_report.id,
            event_type="report_superseded", old_value=report.content_hash, new_value=new_hash,
            detail=f"Document at {report.url!r} was replaced with a new edition (same-URL hash change) - "
                   f"report {report.id} marked superseded by new report {new_report.id}.",
            source_document_url=report.url,
            auto_applied=True, review_status="auto_applied", detected_at=now,
        ))
        # report.content_hash intentionally left as the OLD value - this
        # row is now a frozen historical record of the edition it actually
        # represented, not a live pointer to whatever's at the URL today.
    else:
        report.content_hash = new_hash

    report.next_check_due = compute_next_check_due(report.source_type or "other")
    session.commit()
    return outcome


def discover_reports_for_council(session: Session, council_code: str, timeout: int = DEFAULT_TIMEOUT_SECONDS, force: bool = False) -> dict:
    """Runs discover_reports_for_source for every active, due index-page
    MonitoredSource belonging to this council. Part 3: "the monitoring
    command should normally check only sources that are due" - force
    bypasses that filter for a manual recheck."""
    sources = session.execute(
        select(MonitoredSource).where(MonitoredSource.council_code == council_code, MonitoredSource.is_active.is_(True))
    ).scalars().all()

    totals = {"sources_checked": 0, "sources_skipped_not_due": 0, "new_reports": 0, "auto_classified": 0, "needs_review": 0, "failed": 0}
    for source in sources:
        if not force and not is_due(source.next_check_due):
            totals["sources_skipped_not_due"] += 1
            continue
        counts = discover_reports_for_source(session, source, timeout=timeout)
        totals["sources_checked"] += 1
        totals["new_reports"] += counts["new_reports"]
        totals["auto_classified"] += counts["auto_classified"]
        totals["needs_review"] += counts["needs_review"]
        if counts["fetch_failed"]:
            totals["failed"] += 1
    return totals


def check_reports_for_council(session: Session, council_code: str, timeout: int = DEFAULT_TIMEOUT_SECONDS, force: bool = False) -> dict:
    """Re-checks every "current"-status MonitoredReport for this council
    that's due, for a same-URL replacement (Part 2.5)."""
    reports = session.execute(
        select(MonitoredReport).where(MonitoredReport.council_code == council_code, MonitoredReport.status == "current")
    ).scalars().all()

    totals = {"reports_checked": 0, "reports_skipped_not_due": 0, "unchanged": 0, "superseded": 0, "failed": 0, "first_check": 0}
    for report in reports:
        if not force and not is_due(report.next_check_due):
            totals["reports_skipped_not_due"] += 1
            continue
        outcome = check_report_for_changes(session, report, timeout=timeout)
        totals["reports_checked"] += 1
        if outcome == "changed":
            totals["superseded"] += 1
        elif outcome == "failed":
            totals["failed"] += 1
        elif outcome == "first_check":
            totals["first_check"] += 1
        else:
            totals["unchanged"] += 1
    return totals
