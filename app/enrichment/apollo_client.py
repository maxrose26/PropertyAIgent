"""Apollo people-search client.

NEW for this rebuild - the prototype only ever prepared a candidate CSV for
a manual Apollo step and never actually called the API. This wires it in as
the primary contact source: search Apollo for people at the verified
company domain, filtered to acquisition/land decision-maker job titles.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

APOLLO_SEARCH_URL = "https://api.apollo.io/v1/mixed_people/search"

# No bare "director" catch-all - that matches Finance Director, HR Director,
# IT Director etc. and defeats the point of filtering by title at all.
TARGET_TITLES = [
    "land director", "development director", "land manager", "acquisitions manager",
    "acquisitions director", "managing director", "planning director", "development manager",
    "head of land", "land and planning director",
    "director of land", "director of development", "director of planning",
]


@dataclass
class ApolloContact:
    full_name: str
    job_title: str | None
    email: str | None
    phone: str | None
    linkedin_url: str | None


def search_people_by_domain(api_key: str, domain: str, titles: list[str] | None = None, per_page: int = 10) -> list[ApolloContact]:
    payload = {
        "q_organization_domains": domain,
        "person_titles": titles or TARGET_TITLES,
        "page": 1,
        "per_page": per_page,
    }
    response = requests.post(
        APOLLO_SEARCH_URL,
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    people = response.json().get("people", [])

    contacts = []
    for person in people:
        phone = None
        phone_numbers = person.get("phone_numbers") or []
        if phone_numbers:
            phone = phone_numbers[0].get("sanitized_number") or phone_numbers[0].get("raw_number")

        contacts.append(
            ApolloContact(
                full_name=person.get("name", ""),
                job_title=person.get("title"),
                email=person.get("email"),
                phone=phone,
                linkedin_url=person.get("linkedin_url"),
            )
        )
    return contacts
