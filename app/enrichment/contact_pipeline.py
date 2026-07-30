"""End-to-end company + contact enrichment for one applicant/developer name.

Order: Companies House match+officers (always, cheap and reliable for
identity/PSC/ownership data regardless of website) -> website domain via
OpenAI's web-search-grounded lookup (tried first - proven more reliable at
avoiding aggregator-domain false positives than the SerpAPI heuristic
scorer, see openai_company_lookup's module docstring), falling back to the
SerpAPI scorer (own name, then active corporate PSC/parent name) only if
that doesn't produce a confident domain -> Apollo people-search (primary
contact source) -> Hunter domain-search (fallback / fills gaps) -> Hunter
pattern-generated + verified emails for any CH director Apollo/Hunter
didn't surface directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enrichment import apollo_client, companies_house, hunter_client, news_contact_lookup, openai_company_lookup, website_finder


@dataclass
class EnrichedContact:
    full_name: str
    job_title: str | None
    email: str | None
    phone: str | None
    source: str  # apollo | hunter | generated | news_article
    verification_status: str | None
    match_score: float | None
    linkedin_url: str | None = None
    source_url: str | None = None  # set for source=news_article
    source_context: str | None = None  # set for source=news_article


def _generate_and_verify_email(
    hunter_api_key: str, domain: str, pattern: str, full_name: str
) -> tuple[str | None, str | None]:
    """Shared by the CH-director fallback and the news-contact block below -
    both end up in the same situation (a real name, a known domain/pattern,
    no email yet) and should be handled identically. Returns (email,
    verification_status)."""
    parts = full_name.strip().split()
    if len(parts) < 2:
        return None, None
    first, last = parts[0], parts[-1]
    generated = hunter_client.generate_email(first, last, domain, pattern)
    if not generated:
        return None, None
    try:
        verification = hunter_client.verify_email(hunter_api_key, generated)
    except Exception:
        verification = {}
    return generated, verification.get("status")


def _find_linkedin(
    openai_client: OpenAI | None, serpapi_key: str | None, full_name: str, company_name: str,
    job_title: str | None = None,
) -> str | None:
    """OpenAI's web-search-grounded lookup tried first, falling back to
    website_finder.find_person_linkedin's SerpAPI-based search - confirmed
    real cases both ways: OpenAI found and cross-verified a genuine profile
    (Sebastian Burrow) that SerpAPI's title-substring check couldn't
    confidently confirm, while also correctly declining a fictional negative
    control rather than guessing. Kept the SerpAPI path as a fallback rather
    than removing it, since it's a different (cheaper, no LLM call) method
    that may occasionally succeed where the other doesn't."""
    if openai_client:
        try:
            result = openai_company_lookup.confirm_linkedin_profile(openai_client, full_name, company_name, job_title)
            if result.linkedin_url and result.confidence in ("high", "medium"):
                return result.linkedin_url
        except Exception:
            pass
    if serpapi_key:
        try:
            return website_finder.find_person_linkedin(serpapi_key, full_name, company_name)
        except Exception:
            pass
    return None


@dataclass
class EnrichmentResult:
    company_name_raw: str
    ch_company_number: str | None
    ch_name: str | None
    ch_status: str | None
    ch_incorporation_date: str | None
    ch_registered_address: str | None
    ch_match_confidence: float | None
    verified_domain: str | None
    domain_verification_status: str | None
    domain_matched_via_parent: str | None = None
    domain_source: str | None = None  # openai | serpapi | serpapi_parent
    officers: list[companies_house.OfficerRecord] = field(default_factory=list)
    persons_with_significant_control: list[companies_house.PSCRecord] = field(default_factory=list)
    contacts: list[EnrichedContact] = field(default_factory=list)


def enrich_company(
    company_name: str,
    ch_api_key: str,
    serpapi_key: str | None,
    apollo_api_key: str | None,
    hunter_api_key: str | None,
    openai_client: OpenAI | None = None,
    site_address: str | None = None,
    proposal_summary: str | None = None,
) -> EnrichmentResult:
    match = companies_house.best_match(ch_api_key, company_name)

    officers: list[companies_house.OfficerRecord] = []
    pscs: list[companies_house.PSCRecord] = []
    if match:
        officers = companies_house.get_active_officers(ch_api_key, match.company_number)
        pscs = companies_house.get_persons_with_significant_control(ch_api_key, match.company_number)
        # Cross-reference each officer's OTHER directorships - reveals SPV
        # networks a single company lookup can't show (confirmed a real
        # case: one director of a small applicant company turned out to
        # also direct 4 other "Holdings"-style companies).
        for officer in officers:
            if not officer.appointments_url:
                continue
            try:
                other = companies_house.get_officer_other_appointments(ch_api_key, officer.appointments_url)
            except Exception:
                continue
            officer.other_appointments = [
                a["company_name"] for a in other
                if a["company_name"] and a.get("company_number") != match.company_number and not a.get("resigned_on")
            ]

    result = EnrichmentResult(
        company_name_raw=company_name,
        ch_company_number=match.company_number if match else None,
        ch_name=match.ch_name if match else None,
        ch_status=match.status if match else None,
        ch_incorporation_date=match.incorporation_date if match else None,
        ch_registered_address=match.registered_address if match else None,
        ch_match_confidence=match.confidence if match else None,
        verified_domain=None,
        domain_verification_status=None,
        officers=officers,
        persons_with_significant_control=pscs,
    )

    canonical_name = match.ch_name if match else company_name
    director_names = [o.full_name for o in officers]

    def _corroborated_by_real_contacts(domain: str) -> bool:
        """A real, independently-sourced contact (Apollo's people directory,
        or Hunter's own domain-search - specifically NOT a pattern-generated
        guess, which requires no corroborating evidence to produce) actually
        existing at a candidate domain is the strongest signal available
        that a parent/officer-tier match is genuinely the right company,
        not a coincidental name collision. Confirmed necessary by two real
        false positives that got past OpenAI's own "high confidence"
        self-report (see _verify_candidate's docstring): "Brownian Limited"
        (a property SPV) matched to brownianmotion.co.uk, a completely
        unrelated camera-equipment rental company, purely on the shared
        word "Brownian"; "Hollins Homes (Macclesfield) Limited" matched to
        hollinshomes.co.uk, which turned out to be an unclaimed Squarespace
        parking page with no real content at all - a domain-name match
        alone, even from the stronger of the two lookup mechanisms, isn't
        reliable enough for these two structurally weaker tiers (a
        coincidental side-directorship, not real ownership)."""
        if apollo_api_key:
            try:
                if apollo_client.search_people_by_domain(apollo_api_key, domain):
                    return True
            except Exception:
                pass
        if hunter_api_key:
            try:
                if hunter_client.get_scored_contacts(hunter_api_key, domain, director_names):
                    return True
            except Exception:
                pass
        return False

    def _verify_candidate(
        candidate_name: str, ch_number: str | None, openai_only: bool = False
    ) -> tuple[str | None, str | None]:
        """Try OpenAI's web-search-grounded lookup first, falling back to the
        SerpAPI heuristic scorer - proven more reliable at avoiding
        aggregator-domain false positives (confirmed: SerpAPI matched "Peel
        Land Developments Limited" to vat-search.co.uk, then to a DIFFERENT
        unrelated company's page on checkfree.co.uk on the next attempt -
        two wrong aggregators in a row - while a web-search-enabled model
        correctly found peelland.co.uk on the first try, because it can read
        a result's actual page content rather than just score title/snippet
        text against the company name). Used against every candidate name
        this function tries (the applicant's own name, a corporate PSC
        parent, an officer's other directorships) - confirmed a real case
        (BROWNIAN LIMITED, one of several other directorships on a QP2 Ltd
        officer) where SerpAPI's scorer found nothing usable but OpenAI
        confidently identified brownianmotion.co.uk - this fallback tier
        used to only ever try SerpAPI, silently losing exactly the cases
        SerpAPI is worst at.

        openai_only skips the SerpAPI fallback entirely - for the officer's-
        other-directorships tier specifically (see below), which turned out
        to be a real liability: SerpAPI's "N significant name terms found in
        the domain" heuristic is fine for distinctive company names, but an
        officer's unrelated side-directorship is often a short, generic SPV
        name (confirmed real false positives: "VC Picasso Limited" ->
        picasso-design.co.uk, an unrelated design studio; "Front Holdings
        Ltd" -> frontrowholdings.com, matching on a substring of a
        different company's name; "Amica Trading Limited" ->
        amicatrading.com.au, a same-named but unrelated Australian company)
        - in all three, OpenAI correctly found nothing confident, and it was
        specifically the SerpAPI fallback that produced a wrong "verified".
        A corporate PSC parent is a real ownership relationship and doesn't
        share this risk, so only the officer tier is restricted this way.
        Returns (domain, source) or (None, None)."""
        if openai_client:
            try:
                ai_result = openai_company_lookup.confirm_developer_and_website(openai_client, candidate_name, ch_number)
            except Exception:
                ai_result = None
            if (
                ai_result and ai_result.website_domain and ai_result.confidence in ("high", "medium")
                and not website_finder.is_bad_domain(ai_result.website_domain)
            ):
                return website_finder.normalise_domain(ai_result.website_domain), "openai"
        if serpapi_key and not openai_only:
            website = website_finder.find_and_verify_website(serpapi_key, candidate_name)
            if website.status == "verified":
                return website.domain, "serpapi"
        return None, None

    domain, source = _verify_candidate(canonical_name, match.company_number if match else None)
    if domain:
        result.verified_domain = domain
        result.domain_verification_status = "verified"
        result.domain_source = source

    # SPV-style company names (very common in property development - a
    # one-off "Newco Investments Limited" vehicle set up to hold one site)
    # frequently have no web presence of their own at all - confirmed real
    # cases where every result for the SPV's own name was third-party
    # company-lookup noise. But Companies House's own PSC/officer data
    # already tells us who actually owns or runs it, and the real people ARE
    # often findable - just under a related company's own web presence, not
    # the SPV's. Tries, in order: each active CORPORATE PSC (confirmed real
    # case: Peel Land Developments Limited -> its corporate parent, Peel L&P
    # Land Holdings Limited, whose director turned out to be listed on
    # LinkedIn as "Deputy Finance Director at Peel L&P Group" - not at the
    # SPV itself), then each officer's OTHER current directorships
    # (confirmed real case: QP2 Ltd, whose only PSC is an individual with no
    # corporate parent to try at all, but whose sole director/PSC is ALSO a
    # current director of several other named companies - already fetched
    # above for the "Also director of" column, previously only ever
    # displayed, never used for lookup). Both tiers deduplicated/capped -
    # a director sitting on many boards shouldn't burn unbounded API calls.
    if not result.verified_domain:
        corporate_pscs = [p for p in pscs if p.kind in ("corporate-entity", "legal-person") and not p.ceased]
        for parent in corporate_pscs:
            domain, source = _verify_candidate(parent.name, None)
            if domain and _corroborated_by_real_contacts(domain):
                result.verified_domain = domain
                result.domain_verification_status = "verified"
                result.domain_matched_via_parent = parent.name
                result.domain_source = f"{source}_parent"
                break

        MAX_OFFICER_CANDIDATES = 6
        if not result.verified_domain:
            other_names: list[str] = []
            seen_names: set[str] = set()
            for officer in officers:
                for other_name in officer.other_appointments:
                    key = other_name.strip().lower()
                    if key in seen_names:
                        continue
                    seen_names.add(key)
                    other_names.append(other_name)

            for other_name in other_names[:MAX_OFFICER_CANDIDATES]:
                domain, source = _verify_candidate(other_name, None, openai_only=True)
                if domain and _corroborated_by_real_contacts(domain):
                    result.verified_domain = domain
                    result.domain_verification_status = "verified"
                    result.domain_matched_via_parent = other_name
                    result.domain_source = f"{source}_officer"
                    break

    if not result.verified_domain and serpapi_key:
        # Nothing verified at any tier - still record the SPV's own best
        # (low-confidence) SerpAPI guess as "review", same as before, so the
        # UI can show what was found rather than a bare "not found".
        website = website_finder.find_and_verify_website(serpapi_key, canonical_name)
        result.verified_domain = website.domain
        result.domain_verification_status = website.status
        result.domain_source = "serpapi"

        # A "review" guess is still the CORRECT domain fairly often - the
        # term-matching scorer just can't recognise it confidently. Confirmed
        # a real case: "Hollins Strategic Land" -> hsland.co.uk is genuinely
        # the company's own site (a live team page naming real CH officers
        # by name), but scored "review" because none of "hollins"/
        # "strategic"/"land" appear as substrings of the abbreviated domain
        # "hsland" except "land" alone - one match short of the 2-term bar.
        # Previously this meant Apollo/Hunter were never even tried, and a
        # genuinely correct match sat unused. Same real-contact corroboration
        # check as the parent/officer tiers promotes it to "verified" if it
        # turns out to be right, rather than leaving a correct domain stuck
        # at low confidence forever.
        if website.domain and website.status == "review" and _corroborated_by_real_contacts(website.domain):
            result.domain_verification_status = "verified"

    director_names = [o.full_name for o in officers]
    contacts: list[EnrichedContact] = []
    # Detected once and reused by both the CH-director email-generation
    # fallback below AND the news-contact block further down - previously
    # only the CH-director block ever generated/verified an email, so a
    # news-sourced contact (who by definition has no email at all coming out
    # of the web search) was left with nothing even when the same domain's
    # pattern was already known.
    email_pattern: str | None = None

    # "review" means the scorer itself wasn't confident this is the right
    # domain (fewer than 2 significant company-name terms matched) - only
    # "verified" is trustworthy enough to spend Apollo/Hunter calls against.
    # Confirmed a real case: "Crescent Investments LLC Limited" matched
    # okredo.co.uk (a company-information lookup site, not their real
    # website) with zero name terms in the domain, correctly scored
    # "review" - but this check previously only asked "is there any domain
    # string at all", so Apollo/Hunter still searched it and (unsurprisingly)
    # found nobody, since it isn't actually the company's own domain. This
    # gate ONLY covers the domain-based sources below (Apollo/Hunter) - the
    # news-contact search further down needs no domain at all, so it isn't
    # gated by this and can still run when domain-finding failed entirely.
    if result.verified_domain and result.domain_verification_status == "verified":
        if apollo_api_key:
            try:
                for c in apollo_client.search_people_by_domain(apollo_api_key, result.verified_domain):
                    contacts.append(
                        EnrichedContact(
                            full_name=c.full_name, job_title=c.job_title, email=c.email, phone=c.phone,
                            source="apollo", verification_status=None, match_score=None,
                            linkedin_url=c.linkedin_url,
                        )
                    )
            except Exception:
                pass  # Apollo failures shouldn't block the rest of enrichment

        if hunter_api_key and len(contacts) < 3:
            try:
                for c in hunter_client.get_scored_contacts(hunter_api_key, result.verified_domain, director_names):
                    if any(existing.email == c.email for existing in contacts):
                        continue
                    # Hunter doesn't return LinkedIn directly - look it up for
                    # contacts that scored well enough to be worth the search.
                    linkedin_url = _find_linkedin(openai_client, serpapi_key, c.full_name, company_name, c.job_title)
                    contacts.append(
                        EnrichedContact(
                            full_name=c.full_name, job_title=c.job_title, email=c.email, phone=None,
                            source="hunter", verification_status=None, match_score=c.score,
                            linkedin_url=linkedin_url,
                        )
                    )
            except Exception:
                pass

        if hunter_api_key:
            try:
                email_pattern = hunter_client.detect_pattern(hunter_api_key, result.verified_domain)
            except Exception:
                email_pattern = None

        # For CH directors nobody found an email for yet, try pattern-generation + verification
        if email_pattern and director_names:
            found_names = {c.full_name.strip().lower() for c in contacts}
            for name in director_names:
                if name.strip().lower() in found_names:
                    continue
                generated, verification = _generate_and_verify_email(hunter_api_key, result.verified_domain, email_pattern, name)
                # "invalid" is Hunter's own confirmed-bounce signal, not just
                # an inconclusive check - confirmed a real case (Hollins
                # Strategic Land, wrongly matched to a squarespace parking
                # page via the officer tier) where every single generated
                # address came back "invalid" and was saved anyway, since
                # this previously only checked whether an email string was
                # produced at all, never whether verification actually
                # passed. A guessed pattern nobody can send mail to is worse
                # than showing nothing - it looks like a real find.
                if not generated or verification == "invalid":
                    continue
                contacts.append(
                    EnrichedContact(
                        full_name=name, job_title=None, email=generated, phone=None,
                        source="generated", verification_status=verification, match_score=None,
                    )
                )

    # News coverage of THIS specific scheme routinely names a development/
    # land director even when that person has no Apollo/Hunter footprint at
    # all - a genuinely different discovery channel (public press, not
    # directory/email-pattern data), and especially valuable for exactly the
    # kind of company (a young SPV with no independent web presence) that
    # Apollo/Hunter struggle with most. Only attempted when scheme context
    # is available (the caller passes the site address the applicant/
    # developer name was extracted for) - not gated on domain verification.
    if openai_client and site_address:
        try:
            news_contacts = news_contact_lookup.find_scheme_news_contacts(
                openai_client, canonical_name, site_address, proposal_summary
            )
        except Exception:
            news_contacts = []
        existing_names = {c.full_name.strip().lower() for c in contacts}
        for nc in news_contacts:
            if nc.confidence == "low":
                continue
            if nc.full_name.strip().lower() in existing_names:
                continue

            # A news article rarely states a work email or LinkedIn URL -
            # confirmed a real case (Sebastian Burrow, Strategic Land
            # Director at Bellway) where the contact was correctly found but
            # unusable for outreach with no email/LinkedIn attached. Same
            # domain/pattern already known from the block above, so this is
            # free to attempt - falls back to the AI's own confidence if no
            # email could be generated/verified.
            email, email_status = (None, None)
            if hunter_api_key and email_pattern and result.verified_domain:
                email, email_status = _generate_and_verify_email(
                    hunter_api_key, result.verified_domain, email_pattern, nc.full_name
                )
            linkedin_url = _find_linkedin(openai_client, serpapi_key, nc.full_name, canonical_name, nc.job_title)

            contacts.append(
                EnrichedContact(
                    full_name=nc.full_name, job_title=nc.job_title, email=email, phone=None,
                    source="news_article", verification_status=email_status or nc.confidence, match_score=None,
                    source_url=nc.source_url, source_context=nc.context, linkedin_url=linkedin_url,
                )
            )

    result.contacts = contacts
    return result


def upsert_company_from_enrichment(session: Session, name: str, enrichment: EnrichmentResult):
    """Write an EnrichmentResult into companies/officers/contacts, matching
    an existing Company by CH number first, then normalised name. Shared by
    the automatic weekly-pipeline enrichment stage and the Streamlit
    on-demand "Unlock contacts" button, so both stay in sync."""
    from app.db.models import Company, Contact, Officer, PersonWithSignificantControl  # local import: avoids a UI/pipeline -> db import cycle

    normalized = companies_house.normalise_name(name)
    existing = None
    if enrichment.ch_company_number:
        existing = session.execute(
            select(Company).where(Company.ch_company_number == enrichment.ch_company_number)
        ).scalar_one_or_none()
    if existing is None:
        existing = session.execute(select(Company).where(Company.name_normalized == normalized)).scalar_one_or_none()

    if existing is None:
        existing = Company(name_raw=name, name_normalized=normalized)
        session.add(existing)

    # `or existing.X` on every field, not just ch_company_number: this used
    # to only guard the company number, so a second, partial enrichment call
    # against an already-enriched company (e.g. a manually-recorded news
    # contact with no CH/domain lookup attached) would silently wipe real
    # Companies House/website data with None. Every field here should only
    # ever add information, never destroy it.
    existing.ch_company_number = enrichment.ch_company_number or existing.ch_company_number
    existing.ch_status = enrichment.ch_status or existing.ch_status
    existing.ch_incorporation_date = enrichment.ch_incorporation_date or existing.ch_incorporation_date
    existing.ch_registered_address = enrichment.ch_registered_address or existing.ch_registered_address
    existing.ch_match_confidence = enrichment.ch_match_confidence or existing.ch_match_confidence
    existing.verified_domain = enrichment.verified_domain or existing.verified_domain
    existing.domain_verification_status = enrichment.domain_verification_status or existing.domain_verification_status
    existing.domain_matched_via_parent = enrichment.domain_matched_via_parent or existing.domain_matched_via_parent
    existing.domain_source = enrichment.domain_source or existing.domain_source
    session.flush()

    existing_officers_by_name = {o.full_name: o for o in existing.officers}
    for officer in enrichment.officers:
        new_other_appointments = ", ".join(officer.other_appointments) or None
        existing_officer = existing_officers_by_name.get(officer.full_name)
        if existing_officer is not None:
            # A second enrichment run can discover fields the first one
            # didn't have yet (other_appointments is new as of this
            # session) - confirmed a real case where re-running against an
            # already-enriched company silently kept the officer's
            # cross-appointments blank forever, since only brand-new
            # officers were ever written.
            existing_officer.other_appointments = new_other_appointments or existing_officer.other_appointments
            continue
        session.add(
            Officer(company_id=existing.id, full_name=officer.full_name, role=officer.role,
                     appointed_on=officer.appointed_on, resigned_on=officer.resigned_on,
                     other_appointments=new_other_appointments)
        )

    existing_psc_names = {p.name for p in existing.persons_with_significant_control}
    for psc in enrichment.persons_with_significant_control:
        if psc.name in existing_psc_names:
            continue
        session.add(
            PersonWithSignificantControl(
                company_id=existing.id, name=psc.name, kind=psc.kind,
                natures_of_control=", ".join(psc.natures_of_control) or None,
                ceased=psc.ceased, identification_company_number=psc.identification_company_number,
            )
        )

    # Matches an incoming contact against an existing row by email first
    # (the strongest identity signal), falling back to (name, source) -
    # confirmed real cases needing BOTH: (1) a news_article contact
    # (Sebastian Burrow, Bellway) found with no email/LinkedIn before those
    # lookups existed, whose later-found email was silently discarded by an
    # earlier version of this function that only ever checked for exact
    # duplicates, and (2) contacts that ALREADY had an email from a prior
    # run (so they matched on email and were treated as "nothing to do")
    # whose LinkedIn URL a later run's improved lookup could newly supply -
    # matching by email alone isn't enough once the row being updated
    # already has non-null fields elsewhere. Whenever a match is found, any
    # newly-found field is filled in via `or` fallback (a safe no-op when
    # this run found nothing new for that particular field) rather than
    # creating a duplicate row or leaving the existing one stale forever.
    existing_by_key = {(c.full_name, c.source): c for c in existing.contacts}
    existing_by_email = {c.email: c for c in existing.contacts if c.email}
    for contact in enrichment.contacts:
        target = existing_by_email.get(contact.email) if contact.email else None
        if target is None:
            target = existing_by_key.get((contact.full_name, contact.source))

        if target is not None:
            target.email = contact.email or target.email
            target.phone = contact.phone or target.phone
            target.linkedin_url = contact.linkedin_url or target.linkedin_url
            target.job_title = contact.job_title or target.job_title
            target.source_url = contact.source_url or target.source_url
            target.source_context = contact.source_context or target.source_context
            target.verification_status = contact.verification_status or target.verification_status
            target.match_score = contact.match_score if contact.match_score is not None else target.match_score
            continue

        new_contact = Contact(
            company_id=existing.id, full_name=contact.full_name, job_title=contact.job_title,
            email=contact.email, phone=contact.phone, source=contact.source,
            verification_status=contact.verification_status, match_score=contact.match_score,
            linkedin_url=contact.linkedin_url, source_url=contact.source_url,
            source_context=contact.source_context,
        )
        session.add(new_contact)
        # Keep both lookup maps current within this same call - otherwise a
        # second incoming contact matching this brand-new row (e.g. the
        # same person appearing via two sources in one enrichment run)
        # would wrongly insert ANOTHER duplicate instead of updating it.
        existing_by_key[(contact.full_name, contact.source)] = new_contact
        if contact.email:
            existing_by_email[contact.email] = new_contact

    return existing
