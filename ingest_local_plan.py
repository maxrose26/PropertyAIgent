"""One-off ingestion of a council's Local Plan housing site allocations -
see app.extraction.local_plan for why this can't be a generic scraper like
the rest of this project's councils: there's no portal, no consistent
format, and plans sit at different adoption stages, so each council needs
its PDF and page range identified by hand once, then this script does the
extraction/matching/storage.

    python ingest_local_plan.py --council stockport \\
        --pdf data/local_plans/stockport/LocalPlan.pdf \\
        --pages 110-111 --plan-name "Stockport Local Plan" --plan-status draft \\
        --source-url "https://live-iag-static-assets.s3.eu-west-1.amazonaws.com/pdf/Local+Plan+evidence/LocalPlan.pdf"

Re-running for a council you've already ingested replaces its existing rows
(the whole point of a status like "draft" is that it can change before the
next check) rather than accumulating duplicates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import time

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import delete, select

from app.config import get_council
from app.db.models import LocalPlanSite, Site
from app.db.session import get_session, init_db
from app.enrichment.epc_lookup import NOMINATIM_MIN_INTERVAL_SECONDS
from app.extraction.local_plan import (
    extract_local_plan_sites,
    extract_pdf_page_range,
    geocode_local_plan_site,
    match_to_existing_site,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--council", required=True)
    parser.add_argument("--pdf", required=True, help="Path to the downloaded Local Plan PDF")
    parser.add_argument("--pages", required=True, help="1-indexed inclusive page range, e.g. 110-111")
    parser.add_argument("--plan-name", required=True)
    parser.add_argument("--plan-status", required=True, choices=["draft", "emerging", "examination", "adopted"])
    parser.add_argument("--source-url", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    first_page, last_page = (int(p) for p in args.pages.split("-"))

    load_dotenv(override=True)
    init_db()
    session = get_session()
    client = OpenAI()

    session.execute(delete(LocalPlanSite).where(LocalPlanSite.council_code == args.council))

    text = extract_pdf_page_range(args.pdf, first_page, last_page)
    sites = extract_local_plan_sites(client, text)
    print(f"[local-plan] {args.council}: extracted {len(sites)} allocated sites from pages {args.pages}")

    candidates = session.execute(select(Site).where(Site.council_code == args.council)).scalars().all()
    council_name = get_council(args.council).name

    matched_count = 0
    geocoded_count = 0
    for s in sites:
        matched_site, score = match_to_existing_site(s["site_name"], candidates)
        if matched_site:
            matched_count += 1

        # Nominatim is only skipped when the matched site already has its
        # own coordinates - every other case (unmatched, or matched but
        # ungeocoded) falls through to a real Nominatim call inside
        # geocode_local_plan_site, so the politeness delay applies there too.
        if not (matched_site and matched_site.latitude and matched_site.longitude):
            time.sleep(NOMINATIM_MIN_INTERVAL_SECONDS)
        coords = geocode_local_plan_site(s["site_name"], council_name, matched_site)
        if coords:
            geocoded_count += 1

        session.add(LocalPlanSite(
            council_code=args.council,
            policy_reference=s["policy_reference"],
            site_name=s["site_name"],
            minimum_dwellings=s["minimum_dwellings"],
            category=s["category"],
            plan_name=args.plan_name,
            plan_status=args.plan_status,
            source_document_url=args.source_url,
            source_page=first_page,
            matched_site_id=matched_site.id if matched_site else None,
            match_confidence=score if matched_site else None,
            latitude=coords[0] if coords else None,
            longitude=coords[1] if coords else None,
            extracted_at=dt.datetime.now(dt.timezone.utc),
        ))
        tag = f"matched -> site {matched_site.id} (score={score:.0f})" if matched_site else "no application yet"
        geo_tag = "geocoded" if coords else "NOT geocoded"
        print(f"  {s['policy_reference']:12} {s['site_name']:45} {s['minimum_dwellings']!s:>6}  {tag} | {geo_tag}")

    session.commit()
    print(f"\n[local-plan] {args.council}: {len(sites)} sites stored, {matched_count} matched to an existing "
          f"application, {geocoded_count} geocoded")


if __name__ == "__main__":
    main()
