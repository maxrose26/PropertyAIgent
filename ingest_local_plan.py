"""Ingestion of a council's Local Plan housing site allocations - see
app.extraction.local_plan for why this can't be a generic scraper like the
rest of this project's councils: there's no portal, no consistent format,
and plans sit at different adoption stages, so each council needs its PDF
and page range identified by hand once, then this script does the
extraction/matching/storage.

    python ingest_local_plan.py --council stockport \\
        --pdf data/local_plans/stockport/LocalPlan.pdf \\
        --pages 110-111 --plan-name "Stockport Local Plan" --plan-status draft \\
        --source-url "https://live-iag-static-assets.s3.eu-west-1.amazonaws.com/pdf/Local+Plan+evidence/LocalPlan.pdf"

Re-running for a council/plan you've already ingested no longer deletes and
replaces its rows (Policy Intelligence Foundation sprint, Part 9/10): the
freshly extracted allocations are diffed against what's already stored, the
PRE-CHANGE values are preserved as an AllocationVersion snapshot before
anything is overwritten, and every detected change (new/removed/amended
allocation, capacity change) is logged as a PolicyChangeEvent - see
app.policy.change_detection. High-confidence changes (a brand new
allocation, one confirmed unchanged) apply immediately; anything more
ambiguous is still applied (this script only ever runs because a document
was actually re-read) but flagged with review_status="needs_review" so a
human can confirm it before relying on it, rather than being silently
absorbed into "the site's current state" (Part 11 review queue).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import select

from app.config import get_council
from app.db.models import AllocationVersion, LocalPlan, LocalPlanSite, LocalPlanStatusHistory, PolicyChangeEvent, Site
from app.db.session import get_session, init_db
from app.enrichment.epc_lookup import NOMINATIM_MIN_INTERVAL_SECONDS
from app.extraction.local_plan import (
    extract_local_plan_sites,
    extract_pdf_page_range,
    geocode_local_plan_site,
    match_to_existing_site,
)
from app.policy.change_detection import classify_confidence, diff_allocations, diff_plan
from app.policy.progression import classify_progression
from app.policy.status import derive_allocation_status_from_plan_status, normalise_plan_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--council", required=True)
    parser.add_argument("--pdf", required=True, help="Path to the downloaded Local Plan PDF")
    parser.add_argument("--pages", required=True, help="1-indexed inclusive page range, e.g. 110-111")
    parser.add_argument("--plan-name", required=True)
    parser.add_argument("--plan-status", required=True, choices=["draft", "emerging", "examination", "adopted"],
                         help="Coarse status - kept for backwards compatibility with existing invocations. "
                              "Use --raw-status for a more specific real-world label to normalise from.")
    parser.add_argument("--raw-status", default=None,
                         help="The council's own status wording, e.g. 'Regulation 19 Proposed Submission' - "
                              "normalised into LocalPlan.status. Defaults to --plan-status if not given.")
    parser.add_argument("--plan-version", default=None, help="e.g. 'Regulation 18', 'Adopted 2024'")
    parser.add_argument("--source-url", required=True)
    return parser.parse_args()


def _plan_snapshot(plan: LocalPlan) -> dict:
    return {"plan_version": plan.plan_version, "status": plan.status}


def _allocation_snapshot(row: LocalPlanSite) -> dict:
    return {
        "policy_reference": row.policy_reference,
        "minimum_dwellings": row.minimum_dwellings,
        "indicative_capacity": row.indicative_capacity,
        "maximum_capacity": row.maximum_capacity,
        "allocation_status": row.allocation_status,
    }


def _snapshot_version(session, row: LocalPlanSite, change_reason: str) -> None:
    session.add(AllocationVersion(
        allocation_id=row.id, local_plan_id=row.local_plan_id,
        policy_reference=row.policy_reference, site_name=row.site_name,
        minimum_dwellings=row.minimum_dwellings, indicative_capacity=row.indicative_capacity,
        maximum_capacity=row.maximum_capacity, category=row.category,
        allocation_status=row.allocation_status, raw_allocation_status=row.raw_allocation_status,
        change_reason=change_reason,
    ))


def main() -> None:
    args = parse_args()
    first_page, last_page = (int(p) for p in args.pages.split("-"))
    raw_status = args.raw_status or args.plan_status
    normalised_status = normalise_plan_status(raw_status)

    load_dotenv(override=True)
    init_db()
    session = get_session()
    client = OpenAI()

    plan = session.execute(
        select(LocalPlan).where(
            LocalPlan.council_code == args.council,
            LocalPlan.plan_name == args.plan_name,
            LocalPlan.plan_version == args.plan_version,
        )
    ).scalar_one_or_none()

    plan_is_new = plan is None
    old_plan_snapshot = None if plan_is_new else _plan_snapshot(plan)

    if plan is None:
        plan = LocalPlan(
            council_code=args.council, plan_name=args.plan_name, plan_version=args.plan_version,
            status=normalised_status, raw_status=raw_status, source_webpage=args.source_url,
        )
        session.add(plan)
    else:
        plan.status = normalised_status
        plan.raw_status = raw_status
        plan.source_webpage = args.source_url
    plan.last_checked = dt.datetime.now(dt.timezone.utc)
    session.commit()  # assigns plan.id if newly created

    for event in diff_plan(old_plan_snapshot, _plan_snapshot(plan)):
        session.add(PolicyChangeEvent(
            local_plan_id=plan.id, event_type=event["event_type"],
            old_value=event["old_value"], new_value=event["new_value"], detail=event["detail"],
            auto_applied=classify_confidence(event["event_type"]) == "auto_applied",
            review_status=classify_confidence(event["event_type"]),
        ))
        if event["event_type"] in ("stage_change", "adoption", "withdrawal"):
            session.add(LocalPlanStatusHistory(
                local_plan_id=plan.id, status=plan.status, raw_status=plan.raw_status,
                plan_version=plan.plan_version, note=event["detail"],
            ))
    session.commit()

    text = extract_pdf_page_range(args.pdf, first_page, last_page)
    extracted = extract_local_plan_sites(client, text)
    print(f"[local-plan] {args.council}: extracted {len(extracted)} allocated sites from pages {args.pages}")

    site_candidates = session.execute(select(Site).where(Site.council_code == args.council)).scalars().all()
    council_name = get_council(args.council).name

    existing_rows = {
        r.policy_reference: r for r in session.execute(
            select(LocalPlanSite).where(LocalPlanSite.local_plan_id == plan.id)
        ).scalars().all()
    }
    old_dicts = [_allocation_snapshot(r) for r in existing_rows.values()]

    derived_status, derived_note = derive_allocation_status_from_plan_status(raw_status)
    new_dicts = [{
        "policy_reference": s["policy_reference"],
        "minimum_dwellings": s["minimum_dwellings"],
        "indicative_capacity": None,
        "maximum_capacity": None,
        "allocation_status": existing_rows[s["policy_reference"]].allocation_status
        if s["policy_reference"] in existing_rows else derived_status,
    } for s in extracted]

    allocation_events = diff_allocations(old_dicts, new_dicts)
    events_by_ref: dict[str, list[dict]] = {}
    for event in allocation_events:
        events_by_ref.setdefault(event["policy_reference"], []).append(event)

    matched_count = 0
    geocoded_count = 0
    seen_refs: set[str] = set()

    for s in extracted:
        ref = s["policy_reference"]
        seen_refs.add(ref)
        row = existing_rows.get(ref)
        events = events_by_ref.get(ref, [])
        confidence = classify_confidence(events[0]["event_type"]) if events else "auto_applied"

        matched_site, score = match_to_existing_site(s["site_name"], site_candidates)
        if matched_site:
            matched_count += 1

        if not (matched_site and matched_site.latitude and matched_site.longitude):
            time.sleep(NOMINATIM_MIN_INTERVAL_SECONDS)
        coords = geocode_local_plan_site(s["site_name"], council_name, matched_site)
        if coords:
            geocoded_count += 1

        if row is None:
            row = LocalPlanSite(
                council_code=args.council, local_plan_id=plan.id,
                policy_reference=ref, site_name=s["site_name"], minimum_dwellings=s["minimum_dwellings"],
                category=s["category"], plan_name=args.plan_name, plan_status=args.plan_status,
                allocation_status=derived_status, raw_allocation_status=derived_note,
                source_document_url=args.source_url, source_page=first_page,
                review_status=confidence,
            )
            session.add(row)
            session.flush()  # assigns row.id for the version snapshot below
            tag = "new"
        else:
            # Snapshot BEFORE overwriting, so the pre-change values are never
            # lost (Part 10) - even for fields that didn't change this run,
            # a full snapshot is cheap and keeps every version self-contained
            # to read on its own, not a diff against a diff.
            _snapshot_version(session, row, change_reason=events[0]["event_type"] if events else "reingested_unchanged")
            row.site_name = s["site_name"]
            row.minimum_dwellings = s["minimum_dwellings"]
            row.category = s["category"]
            row.plan_name = args.plan_name
            row.plan_status = args.plan_status
            row.source_document_url = args.source_url
            row.source_page = first_page
            row.review_status = confidence
            tag = "updated" if events and events[0]["event_type"] != "allocation_retained" else "unchanged"

        row.matched_site_id = matched_site.id if matched_site else None
        row.match_confidence = score if matched_site else None
        if coords:
            row.latitude, row.longitude = coords

        signal, reasons = classify_progression(
            plan.status, row.allocation_status,
            expected_adoption_date=_parse_date(plan.expected_adoption_date), present_in_latest_version=True,
        )
        row.progression_signal = signal
        row.progression_reasons = json.dumps(reasons)
        row.progression_computed_at = dt.datetime.now(dt.timezone.utc)

        for event in events:
            session.add(PolicyChangeEvent(
                local_plan_id=plan.id, allocation_id=row.id, event_type=event["event_type"],
                old_value=event["old_value"], new_value=event["new_value"], detail=event["detail"],
                auto_applied=classify_confidence(event["event_type"]) == "auto_applied",
                review_status=classify_confidence(event["event_type"]),
            ))

        match_tag = f"matched -> site {matched_site.id} (score={score:.0f})" if matched_site else "no application yet"
        geo_tag = "geocoded" if coords else "NOT geocoded"
        print(f"  [{tag:9}] {ref:12} {s['site_name']:45} {s['minimum_dwellings']!s:>6}  {match_tag} | {geo_tag}")

    # Allocations that existed before this ingest but weren't in this run's
    # extraction - never deleted (Part 10), left exactly as they are, but
    # flagged for a human to confirm whether they were genuinely dropped
    # from the plan or just outside this run's page range (Part 11).
    removed_count = 0
    for ref, row in existing_rows.items():
        if ref in seen_refs:
            continue
        removed_count += 1
        row.review_status = "needs_review"
        for event in events_by_ref.get(ref, []):
            session.add(PolicyChangeEvent(
                local_plan_id=plan.id, allocation_id=row.id, event_type=event["event_type"],
                old_value=event["old_value"], new_value=event["new_value"], detail=event["detail"],
                auto_applied=False, review_status="needs_review",
            ))
        signal, reasons = classify_progression(
            plan.status, row.allocation_status,
            expected_adoption_date=_parse_date(plan.expected_adoption_date), present_in_latest_version=False,
        )
        row.progression_signal = signal
        row.progression_reasons = json.dumps(reasons)
        row.progression_computed_at = dt.datetime.now(dt.timezone.utc)

    session.commit()
    print(f"\n[local-plan] {args.council}: {len(extracted)} sites in latest extraction, {matched_count} matched to "
          f"an existing application, {geocoded_count} geocoded, {removed_count} previously-stored allocation(s) "
          f"not seen this run (flagged for review, not deleted)")


def _parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


if __name__ == "__main__":
    main()
