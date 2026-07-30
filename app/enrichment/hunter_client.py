"""Hunter.io client: domain-search contact discovery, plus email-pattern
generation + verification for known directors Hunter didn't surface directly.

Ported from hunter_target_contact_finder.py / detect_email_pattern.py /
generate_director_emails.py / verify_generated_emails_hunter.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

HUNTER_BASE = "https://api.hunter.io/v2"

# These are senior enough on their own regardless of domain wording -
# a Managing Director at a small land-promotion SME is often the direct
# decision-maker even without "land" literally in the title.
ALWAYS_RELEVANT_TITLES = ["managing director", "development director"]

# Otherwise require a senior-role word AND a relevant-domain word together -
# titles vary in phrasing ("Director of Land and Planning" vs "Land and
# Planning Director" vs "Land Director"), so matching on fixed multi-word
# phrases missed real matches. No bare "director"/"manager" alone: that
# matched Finance Director, Customer Service Manager etc.
SENIOR_ROLE_WORDS = ["director", "head of", "manager"]
RELEVANT_DOMAIN_WORDS = ["land", "planning", "acquisition", "development"]

# A contact needs an exact CH-director-name match (+200) or a real role hit
# to be worth surfacing - below this, Hunter's domain-search just returns
# whoever's on the company's website (Rental Assistant, L&D Specialist...).
MIN_RELEVANT_SCORE = 50.0


def _score_position(position: str) -> float:
    position = position.lower()
    if any(t in position for t in ALWAYS_RELEVANT_TITLES):
        return 140
    has_role = any(w in position for w in SENIOR_ROLE_WORDS)
    has_domain = any(w in position for w in RELEVANT_DOMAIN_WORDS)
    return 100 if (has_role and has_domain) else 0


@dataclass
class HunterContact:
    full_name: str
    job_title: str | None
    email: str | None
    confidence: int
    score: float


def domain_search(api_key: str, domain: str, limit: int = 10) -> dict:
    response = requests.get(
        f"{HUNTER_BASE}/domain-search",
        params={"domain": domain, "api_key": api_key, "limit": limit},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data", {})


def score_contact(contact: dict, director_names: list[str]) -> float:
    score = 0.0
    full_name = f"{contact.get('first_name') or ''} {contact.get('last_name') or ''}".strip().lower()

    for director in director_names:
        if director.strip().lower() == full_name:
            score += 200
            break

    score += _score_position(contact.get("position") or "")

    if contact.get("type") == "personal":
        score += 25

    score += min(contact.get("confidence", 0) or 0, 100) / 5
    return score


def get_scored_contacts(api_key: str, domain: str, director_names: list[str], top_n: int = 5) -> list[HunterContact]:
    data = domain_search(api_key, domain)
    emails = data.get("emails", [])

    scored = []
    for e in emails:
        contact = HunterContact(
            full_name=f"{e.get('first_name') or ''} {e.get('last_name') or ''}".strip(),
            job_title=e.get("position"),
            email=e.get("value"),
            confidence=e.get("confidence", 0) or 0,
            score=score_contact(e, director_names),
        )
        scored.append(contact)

    scored = [c for c in scored if c.score >= MIN_RELEVANT_SCORE]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_n]


def detect_pattern(api_key: str, domain: str) -> str | None:
    data = domain_search(api_key, domain)
    return data.get("pattern")


def generate_email(first_name: str, last_name: str, domain: str, pattern: str) -> str | None:
    first = first_name.strip().lower()
    last = last_name.strip().lower()
    if not first or not last:
        return None

    replacements = {
        "{first}": first,
        "{last}": last,
        "{f}": first[0] if first else "",
        "{l}": last[0] if last else "",
    }
    local_part = pattern
    for token, value in replacements.items():
        local_part = local_part.replace(token, value)
    return f"{local_part}@{domain}"


def verify_email(api_key: str, email: str) -> dict:
    response = requests.get(
        f"{HUNTER_BASE}/email-verifier",
        params={"email": email, "api_key": api_key},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data", {})
