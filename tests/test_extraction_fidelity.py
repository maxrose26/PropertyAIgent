"""Extraction fidelity tests (Sprint 2, onboarding Bury) - confirms the
real fabrication bug found and fixed while onboarding Bury cannot recur.
See specifications/003-policy-intelligence-v1.md Sec.9 for the full
narrative: an AI extraction run, faced with a required policy_reference
field and a site named in prose with no code printed against it, invented
one by copying this schema's own example format. policy_reference is now
nullable end-to-end; these tests cover the schema and the deduplication
logic that had to change alongside it.
"""
from __future__ import annotations

from app.db.models import LocalPlanSite
from app.extraction.local_plan import SCHEMA


def test_policy_reference_is_nullable_in_the_extraction_schema():
    prop = SCHEMA["schema"]["properties"]["sites"]["items"]["properties"]["policy_reference"]
    assert "null" in prop["type"]


def test_policy_reference_is_still_a_required_key_even_though_nullable():
    # strict-mode structured outputs require every property to be present
    # in "required" - nullable just means the VALUE can be null, not that
    # the key can be omitted.
    required = SCHEMA["schema"]["properties"]["sites"]["items"]["required"]
    assert "policy_reference" in required


def test_local_plan_site_accepts_a_null_policy_reference(session):
    row = LocalPlanSite(
        council_code="testcouncil", policy_reference=None, site_name="Named but uncoded site",
        plan_name="Test Plan", plan_status="draft",
    )
    session.add(row)
    session.commit()
    assert row.id is not None
    assert row.policy_reference is None


def test_dedup_key_falls_back_to_site_name_when_reference_is_null():
    from ingest_local_plan import _dedup_key

    assert _dedup_key("HOM 2.30", "Sanderling Road") == "HOM 2.30"
    key_a = _dedup_key(None, "Seedfield")
    key_b = _dedup_key(None, "Walshaw")
    assert key_a != key_b  # two different unreferenced sites must not collide

    key_a_again = _dedup_key(None, "Seedfield")
    assert key_a == key_a_again  # but the same site name is stable across calls
