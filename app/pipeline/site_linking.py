"""Consolidate planning applications that refer to the same physical site.

UK planning process routinely generates multiple separate portal references
for one real scheme - an EIA screening opinion, a scoping opinion, an
ancillary certificate for an adjacent parcel - all before (or alongside) the
actual full application. Left alone, each becomes its own lead. This module
links them together, tiered by confidence so only high-confidence links are
applied automatically:

  1. exact_address     - normalised address strings match exactly -> auto-link
  2. parent_reference   - proposal text explicitly cites another application's
                          reference number, and that application exists -> auto-link
  3. suggested_fuzzy    - same postcode district + high address similarity,
                          but no explicit textual link -> flagged for manual
                          confirm/reject, NOT auto-linked (address text alone
                          is too unreliable to safely auto-merge distinct sites)
  4. created            - no match at any tier -> becomes a new Site
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Application, Site

NOISE_PREFIXES = [
    "land adjacent to", "land to the rear of", "land to the front of",
    "land east of", "land west of", "land north of", "land south of",
    "land at", "site at", "site of", "the former", "former",
]

_FORMATTED_REF = r"([A-Za-z0-9]+(?:[/-][A-Za-z0-9]+){1,4})"

PARENT_REFERENCE_PATTERNS = [
    # Full formatted references (e.g. "A/12/76665") FIRST - checked before
    # the bare-digit patterns below since a formatted reference always
    # contains a trailing bare-digit substring that would otherwise match
    # too early and lose the prefix. Confirmed a real case (Wigan,
    # A/26/100520/RMMAJ citing "pursuant to outline planning permission
    # A/12/76665") where the old bare-digit-only patterns would have
    # extracted just "76665" - missing the "A/12/" prefix Wigan's own
    # reference format requires for an exact match, which real Idox
    # reference-search fields generally expect.
    rf"pursuant to outline planning permission\s*\(?(?:ref\.?|reference)?\s*:?\s*{_FORMATTED_REF}\)?",
    # Same "pursuant to permission/approval" phrasing but without the word
    # "outline" and with a formatted (not bare-digit) reference - confirmed
    # real case (Wigan A/26/100797/RMMAJ): "submitted pursuant to planning
    # permission A/21/92036/OUTMAJ allowed by appeal reference...".
    rf"pursuant to (?:planning )?(?:permission|approval)\s*\(?(?:ref\.?|reference)?\s*{_FORMATTED_REF}\)?",
    # "following [outline/hybrid/full/reserved matters] approval ref: X" -
    # confirmed real case (Stockport DC/084620, a 124-dwelling Phase 2
    # reserved matters application): "following hybrid approval ref:
    # DC/060928" - the old pattern below only recognised the word "outline"
    # and only a bare digit reference, missing both a formatted reference
    # (DC/060928) and any approval type other than "outline" (a hybrid
    # application - part outline, part full - is a common way large
    # strategic multi-phase sites get their first permission).
    rf"following (?:outline|hybrid|full|reserved matters)?\s*approval\s*(?:ref\.?|reference)?\s*:?\s*\(?{_FORMATTED_REF}\)?",
    r"following outline approval\s*\(?(\d{4,6})\)?",
    r"pursuant to (?:planning )?(?:permission|approval)\s*\(?(?:ref\.?|reference)?\s*(\d{4,6})\)?",
    r"pursuant to planning permission\s*\(?(\d{4,6})\)?",
    r"reserved matters.{0,60}?\((\d{4,6})\)",
    r"discharge of condition.{0,80}?planning permission\s*\(?(\d{4,6})\)?",
    r"variation of condition.{0,80}?\(?(\d{4,6})\)?",
    # "Reserved matters ... relating to (approved) application/app no. X" and
    # "in association with application X" - confirmed real cases (Oldham
    # RES/355347/25, RES/355397/25, RES/355437/25, RES/356154/26) where the
    # citation phrasing doesn't use "pursuant to" at all.
    rf"relating to (?:approved )?app(?:lication)?\s*(?:no\.?)?\s*\(?{_FORMATTED_REF}\)?",
    rf"in association with application\s*\(?{_FORMATTED_REF}\)?",
]

FUZZY_SCORE_THRESHOLD = 70.0  # 0-100, rapidfuzz token_set_ratio


def normalise_address(address: str) -> str:
    text = (address or "").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for prefix in NOISE_PREFIXES:
        if text.startswith(prefix + " "):
            text = text[len(prefix):].strip()
            break
    return text


POSTCODE_RE = re.compile(r"\b([A-Za-z]{1,2}\d{1,2}[A-Za-z]?)\s*(\d[A-Za-z]{2})\b")


def extract_postcode_district(address: str) -> str | None:
    match = POSTCODE_RE.search(address or "")
    return match.group(1).upper() if match else None


def extract_full_postcode(address: str) -> str | None:
    match = POSTCODE_RE.search(address or "")
    return f"{match.group(1).upper()} {match.group(2).upper()}" if match else None


def extract_parent_reference(proposal: str) -> str | None:
    for pattern in PARENT_REFERENCE_PATTERNS:
        match = re.search(pattern, proposal or "", flags=re.I)
        if match:
            return match.group(1)
    return None


def _references_match(cited_ref: str, actual_reference: str) -> bool:
    """A cited reference doesn't always match the target's full reference
    string exactly - confirmed a real case (Trafford): a reserved matters
    filing cited its parent by bare numeric ID ("103844"), but Trafford's
    own reference format for that application is "103844/HYB/21" (suffixed
    with an application-type code). Bare-digit citations are the older,
    common style across several councils, so treat "cited ref is the
    numeric-prefix of the actual reference, followed by a real separator"
    as a match too, not just an exact string match. The separator
    requirement (not a bare substring check) keeps this from matching an
    unrelated reference that merely starts with the same digits."""
    cited_ref = (cited_ref or "").strip()
    if not cited_ref:
        return False
    return actual_reference == cited_ref or actual_reference.startswith(cited_ref + "/")


def _create_site(session: Session, application: Application, normalised: str) -> Site:
    site = Site(
        council_code=application.council_code,
        canonical_address=normalised,
        display_address=application.address or normalised,
        postcode=extract_full_postcode(application.address or ""),
    )
    session.add(site)
    session.flush()  # need site.id before linking
    return site


def link_application_to_site(session: Session, application: Application) -> None:
    if application.site_id is not None or application.site_link_method is not None:
        return  # already processed (idempotent)

    if not application.address:
        site = _create_site(session, application, "")
        application.site_id = site.id
        application.site_link_method = "created"
        return

    normalised = normalise_address(application.address)

    # Tier 1: exact address match within the same council
    existing_site = session.execute(
        select(Site).where(Site.council_code == application.council_code, Site.canonical_address == normalised)
    ).scalar_one_or_none()
    if existing_site:
        application.site_id = existing_site.id
        application.site_link_method = "exact_address"
        return

    # Tier 2: explicit parent-reference mention in the proposal text
    parent_ref = extract_parent_reference(application.proposal or "")
    if parent_ref:
        parent_app = session.execute(
            select(Application).where(
                Application.council_code == application.council_code,
                or_(Application.reference == parent_ref, Application.reference.like(f"{parent_ref}/%")),
            )
        ).scalars().first()
        if parent_app and parent_app.site_id:
            application.site_id = parent_app.site_id
            application.site_link_method = "parent_reference"
            return

    # Tier 2b: reverse direction - some OTHER already-sited application cites
    # THIS application's own reference as ITS parent. Tier 2 above only
    # checks once, at the moment an application is first processed, so it
    # can never retroactively re-link a citing child once its parent shows
    # up later (e.g. run_weekly.stage_fetch_missing_parents backfilling a
    # parent that predates the council's scraping window, well after the
    # child that cites it was already scraped and sited). Confirmed a real
    # case: Wigan's North Leigh reserved matters filing was already linked
    # to its own site months before its outline parent (A/12/76665) was
    # ever fetched - without this, the parent gets its own separate site
    # instead of joining the scheme it's actually part of.
    citing_children = session.execute(
        select(Application).where(
            Application.council_code == application.council_code, Application.site_id.isnot(None),
        )
    ).scalars().all()
    for child in citing_children:
        if _references_match(extract_parent_reference(child.proposal or "") or "", application.reference):
            application.site_id = child.site_id
            application.site_link_method = "parent_reference"
            return

    # Tier 3: suggested fuzzy match - same postcode district + high address similarity.
    # Not auto-applied: flagged for manual confirm/reject via suggested_site_id.
    postcode_district = extract_postcode_district(application.address)
    if postcode_district:
        candidates = session.execute(
            select(Site).where(Site.council_code == application.council_code)
        ).scalars().all()

        best_site, best_score = None, 0.0
        for site in candidates:
            if extract_postcode_district(site.canonical_address) != postcode_district:
                continue
            score = fuzz.token_set_ratio(normalised, site.canonical_address)
            if score > best_score:
                best_site, best_score = site, score

        if best_site and best_score >= FUZZY_SCORE_THRESHOLD:
            application.site_link_method = "suggested_fuzzy"
            application.site_link_confidence = round(best_score / 100.0, 3)
            application.suggested_site_id = best_site.id
            return

    # Tier 4: no match anywhere - this becomes a new site
    site = _create_site(session, application, normalised)
    application.site_id = site.id
    application.site_link_method = "created"


def confirm_suggested_link(session: Session, application: Application) -> None:
    """User confirmed a suggested_fuzzy candidate is the same site."""
    if application.suggested_site_id is None:
        return
    application.site_id = application.suggested_site_id
    application.site_link_method = "suggested_fuzzy"  # keep provenance that it started as a suggestion


def reject_suggested_link(session: Session, application: Application) -> None:
    """User rejected a suggested_fuzzy candidate - it's actually a distinct site."""
    normalised = normalise_address(application.address or "")
    site = _create_site(session, application, normalised)
    application.site_id = site.id
    application.site_link_method = "created"
    application.suggested_site_id = None
    application.site_link_confidence = None
