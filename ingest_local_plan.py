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

Re-running for a council/plan you've already ingested never deletes and
replaces its rows, and - since the Sprint 1 CTO-review amendment ("Protect
trusted state from ambiguous changes") - never silently overwrites an
existing LocalPlan/LocalPlanSite's trusted fields either:

  - Brand new plans and brand new allocations are safe by construction
    (there's no existing trusted value to protect) and are written
    immediately.
  - Everything else a fresh extraction disagrees with an EXISTING plan or
    allocation about (a status/stage change, a capacity change, an
    allocation that's vanished from this run's page range) is queued as a
    PolicyChangeEvent with review_status="needs_review" and a
    proposed_data payload - the actual LocalPlan/LocalPlanSite row is left
    completely untouched until a human calls
    app.policy.review.approve_change or reject_change.

Site-matching and geocoding (matched_site_id, match_confidence, latitude,
longitude) are a separate concern from plan/allocation CONTENT and are
still recomputed and applied on every run, same as before this amendment -
see the module docstring reasoning in app.policy.review for why that
distinction is deliberate.
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
from app.db.models import LocalPlan, LocalPlanSite, PolicyChangeEvent, Site
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


def _dedup_key(policy_reference: str | None, site_name: str) -> str:
    """Allocations are matched across ingestion runs primarily by
    policy_reference, but that field is legitimately nullable now (Sprint
    2, onboarding Bury) - a council's own document can name a site with no
    code printed against it anywhere (see app.extraction.local_plan's
    SCHEMA docstring for the real case this fixed). Falling back to
    site_name for the DEDUP KEY only - never stored as the actual
    policy_reference value - keeps two different uncoded sites from
    colliding into "the same" allocation just because neither has one."""
    return policy_reference if policy_reference else f"__unref__:{site_name}"


def _allocation_snapshot(row: LocalPlanSite) -> dict:
    return {
        "policy_reference": _dedup_key(row.policy_reference, row.site_name),
        "minimum_dwellings": row.minimum_dwellings,
        "indicative_capacity": row.indicative_capacity,
        "maximum_capacity": row.maximum_capacity,
        "allocation_status": row.allocation_status,
    }


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

    new_plan_snapshot = {"plan_version": args.plan_version, "status": normalised_status}

    if plan is None:
        # A brand-new plan has no existing trusted value to protect -
        # writing it immediately is exactly as safe as a new_allocation.
        plan = LocalPlan(
            council_code=args.council, plan_name=args.plan_name, plan_version=args.plan_version,
            status=normalised_status, raw_status=raw_status, source_webpage=args.source_url,
        )
        session.add(plan)
        session.commit()  # assigns plan.id
        session.add(PolicyChangeEvent(
            local_plan_id=plan.id, event_type="new_plan_version", old_value=None, new_value=args.plan_version,
            detail="First time this Local Plan has been recorded.",
            proposed_data=json.dumps(new_plan_snapshot), source_document_url=args.source_url,
            auto_applied=True, review_status="auto_applied",
        ))
        plan_events_applied = ["new_plan_version"]
    else:
        old_plan_snapshot = _plan_snapshot(plan)
        plan_diff_events = diff_plan(old_plan_snapshot, new_plan_snapshot)
        plan_events_applied = []
        for event in plan_diff_events:
            session.add(PolicyChangeEvent(
                local_plan_id=plan.id, event_type=event["event_type"],
                old_value=event["old_value"], new_value=event["new_value"], detail=event["detail"],
                proposed_data=json.dumps(new_plan_snapshot), source_document_url=args.source_url,
                auto_applied=False, review_status="needs_review",
            ))
            # NOT applying plan.status/plan_version here - an EXISTING
            # plan's own trusted status only changes via
            # app.policy.review.approve_change, never automatically at
            # ingest time (see module docstring).
        if plan_diff_events:
            print(f"[local-plan] {args.council}: plan-level change(s) detected ({[e['event_type'] for e in plan_diff_events]}) "
                  f"- queued for review, current plan status left unchanged")
    # source_webpage/last_checked are operational bookkeeping (which
    # document we're currently pointed at), not trusted plan CONTENT - safe
    # to update unconditionally.
    plan.source_webpage = args.source_url
    plan.last_checked = dt.datetime.now(dt.timezone.utc)
    session.commit()

    text = extract_pdf_page_range(args.pdf, first_page, last_page)
    extracted = extract_local_plan_sites(client, text)
    print(f"[local-plan] {args.council}: extracted {len(extracted)} allocated sites from pages {args.pages}")

    site_candidates = session.execute(select(Site).where(Site.council_code == args.council)).scalars().all()
    council_name = get_council(args.council).name

    existing_rows = {
        _dedup_key(r.policy_reference, r.site_name): r for r in session.execute(
            select(LocalPlanSite).where(LocalPlanSite.local_plan_id == plan.id)
        ).scalars().all()
    }
    old_dicts = [_allocation_snapshot(r) for r in existing_rows.values()]

    derived_status, derived_note = derive_allocation_status_from_plan_status(raw_status)
    new_dicts = [{
        "policy_reference": _dedup_key(s["policy_reference"], s["site_name"]),
        "minimum_dwellings": s["minimum_dwellings"],
        "indicative_capacity": None,
        "maximum_capacity": None,
        # For an EXISTING allocation, the extraction schema doesn't itself
        # produce a status, so this compares the current DB value against
        # itself (never a spontaneous diff) - allocation_amended only ever
        # fires from a status change made some other way (e.g. a previously
        # approved change). New allocations get the derived default.
        "allocation_status": existing_rows[_dedup_key(s["policy_reference"], s["site_name"])].allocation_status
        if _dedup_key(s["policy_reference"], s["site_name"]) in existing_rows else derived_status,
    } for s in extracted]

    allocation_events = diff_allocations(old_dicts, new_dicts)
    events_by_ref: dict[str, list[dict]] = {}
    for event in allocation_events:
        events_by_ref.setdefault(event["policy_reference"], []).append(event)

    matched_count = 0
    geocoded_count = 0
    queued_count = 0
    seen_refs: set[str] = set()

    for s in extracted:
        ref = _dedup_key(s["policy_reference"], s["site_name"])
        seen_refs.add(ref)
        row = existing_rows.get(ref)
        events = events_by_ref.get(ref, [])

        matched_site, score = match_to_existing_site(s["site_name"], site_candidates)
        if matched_site:
            matched_count += 1

        if not (matched_site and matched_site.latitude and matched_site.longitude):
            time.sleep(NOMINATIM_MIN_INTERVAL_SECONDS)
        coords = geocode_local_plan_site(s["site_name"], council_name, matched_site)
        if coords:
            geocoded_count += 1

        if row is None:
            # New allocation - nothing existing to protect, write it now.
            # policy_reference stores the TRUE extracted value (may be
            # None) - ref (the dedup key) is only ever used for dict
            # lookups/matching, never persisted as the field itself.
            row = LocalPlanSite(
                council_code=args.council, local_plan_id=plan.id,
                policy_reference=s["policy_reference"], site_name=s["site_name"], minimum_dwellings=s["minimum_dwellings"],
                category=s["category"], plan_name=args.plan_name, plan_status=args.plan_status,
                allocation_status=derived_status, raw_allocation_status=derived_note,
                source_document_url=args.source_url, source_page=first_page,
                review_status="auto_applied",
            )
            session.add(row)
            session.flush()  # assigns row.id
            for event in events:  # a single new_allocation event, per diff_allocations
                session.add(PolicyChangeEvent(
                    local_plan_id=plan.id, allocation_id=row.id, event_type=event["event_type"],
                    old_value=event["old_value"], new_value=event["new_value"], detail=event["detail"],
                    proposed_data=json.dumps(_allocation_snapshot(row)), source_document_url=args.source_url,
                    source_page=first_page, auto_applied=True, review_status="auto_applied",
                ))
            signal, reasons = classify_progression(plan.status, row.allocation_status, present_in_latest_version=True)
            row.progression_signal = signal
            row.progression_reasons = json.dumps(reasons)
            row.progression_computed_at = dt.datetime.now(dt.timezone.utc)
            tag = "new"
        else:
            # Existing allocation - apply only what's safe (nothing changed
            # this run - "allocation_retained"), queue everything else.
            row_changed = False
            for event in events:
                confidence = classify_confidence(event["event_type"])
                if event["event_type"] == "capacity_changed":
                    proposed = {
                        "minimum_dwellings": s["minimum_dwellings"],
                        "indicative_capacity": None, "maximum_capacity": None,
                    }
                elif event["event_type"] == "allocation_amended":
                    proposed = {"allocation_status": row.allocation_status}  # see new_dicts comment above
                else:  # allocation_retained
                    proposed = None

                session.add(PolicyChangeEvent(
                    local_plan_id=plan.id, allocation_id=row.id, event_type=event["event_type"],
                    old_value=event["old_value"], new_value=event["new_value"], detail=event["detail"],
                    proposed_data=json.dumps(proposed) if proposed else None,
                    source_document_url=args.source_url, source_page=first_page,
                    auto_applied=confidence == "auto_applied", review_status=confidence,
                ))
                if confidence == "needs_review":
                    row.review_status = "needs_review"
                    row_changed = True

            # Fields the diff doesn't gate at all (cosmetic re-wording, not
            # a materially trust-sensitive fact) stay auto-updated, same as
            # before this amendment.
            row.site_name = s["site_name"]
            row.category = s["category"]
            row.plan_name = args.plan_name
            row.plan_status = args.plan_status
            row.source_document_url = args.source_url
            row.source_page = first_page

            tag = "queued for review" if row_changed else "unchanged"

        row.matched_site_id = matched_site.id if matched_site else None
        row.match_confidence = score if matched_site else None
        if coords:
            row.latitude, row.longitude = coords
        if tag == "queued for review":
            queued_count += 1

        match_tag = f"matched -> site {matched_site.id} (score={score:.0f})" if matched_site else "no application yet"
        geo_tag = "geocoded" if coords else "NOT geocoded"
        display_ref = s["policy_reference"] or "(no code printed)"
        print(f"  [{tag:16}] {display_ref:20} {s['site_name']:45} {s['minimum_dwellings']!s:>6}  {match_tag} | {geo_tag}")

    # Allocations that existed before this ingest but weren't in this run's
    # extraction - never deleted, never reclassified as "removed" here
    # (that's an ambiguous change, per the amendment's own examples) - only
    # a PolicyChangeEvent is queued; the allocation's own status and
    # progression signal are left exactly as they were until a human
    # approves the removal.
    removed_count = 0
    for ref, row in existing_rows.items():
        if ref in seen_refs:
            continue
        removed_count += 1
        row.review_status = "needs_review"
        for event in events_by_ref.get(ref, []):  # exactly one: allocation_removed
            session.add(PolicyChangeEvent(
                local_plan_id=plan.id, allocation_id=row.id, event_type=event["event_type"],
                old_value=event["old_value"], new_value=event["new_value"], detail=event["detail"],
                proposed_data=json.dumps({"allocation_status": "removed"}),
                source_document_url=args.source_url, auto_applied=False, review_status="needs_review",
            ))
        queued_count += 1

    session.commit()
    print(f"\n[local-plan] {args.council}: {len(extracted)} sites in latest extraction, {matched_count} matched to "
          f"an existing application, {geocoded_count} geocoded, {queued_count} change(s) queued for review "
          f"(trusted state left unchanged), {removed_count} previously-stored allocation(s) not seen this run")


if __name__ == "__main__":
    main()
