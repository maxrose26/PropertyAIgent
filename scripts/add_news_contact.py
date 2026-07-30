"""Manually record a contact discovered from a news article, attached to a
company and (optionally) linked to a specific application/site.

No news-discovery automation exists yet (no per-scheme search, no scraping) -
this is the manual capture step: fetch/read an article yourself, then run
this to persist the useful bits (name, title, company, source URL) the same
way a paid Apollo/Hunter enrichment would, just sourced differently.

Usage:
    python -m scripts.add_news_contact --company "Bloor Homes (North West) Ltd" \
        --name "Tom Loomes" --title "Senior Planning Manager" \
        --url "https://www.manchestereveningnews.co.uk/news/greater-manchester-news/new-100m-masterplan-could-see-31127184" \
        --application DC/095134 --council stockport --role developer
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import Application, ApplicationCompany
from app.db.session import get_session, init_db
from app.enrichment.contact_pipeline import EnrichedContact, EnrichmentResult, upsert_company_from_enrichment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--title", default=None)
    parser.add_argument("--url", required=True)
    parser.add_argument("--application", default=None, help="Application reference to link this company to")
    parser.add_argument("--council", default=None, help="Council code (required if --application given)")
    parser.add_argument("--role", default="developer",
                         help="applicant | developer | agent | landowner | architect | housing_association")
    args = parser.parse_args()

    init_db()
    session = get_session()

    result = EnrichmentResult(
        company_name_raw=args.company, ch_company_number=None, ch_name=None, ch_status=None,
        ch_incorporation_date=None, ch_registered_address=None, ch_match_confidence=None,
        verified_domain=None, domain_verification_status=None, officers=[],
        contacts=[EnrichedContact(
            full_name=args.name, job_title=args.title, email=None, phone=None,
            source="news_article", verification_status=None, match_score=None, source_url=args.url,
        )],
    )
    company = upsert_company_from_enrichment(session, args.company, result)

    if args.application:
        application = session.execute(
            select(Application).where(
                Application.reference == args.application, Application.council_code == args.council,
            )
        ).scalar_one_or_none()
        if application is None:
            print(f"No application {args.council}/{args.application} found - company/contact saved without a link")
        else:
            existing_link = session.execute(
                select(ApplicationCompany).where(
                    ApplicationCompany.application_id == application.id,
                    ApplicationCompany.company_id == company.id,
                    ApplicationCompany.role == args.role,
                )
            ).scalar_one_or_none()
            if existing_link is None:
                session.add(ApplicationCompany(application_id=application.id, company_id=company.id, role=args.role))
                print(f"Linked {args.company} to {args.council}/{args.application} as {args.role}")

    session.commit()
    print(f"Saved: {args.name} ({args.title or 'no title'}) at {args.company}, sourced from {args.url}")


if __name__ == "__main__":
    main()
