"""Explicit synthetic source evidence for matching tests; never a storage adapter."""
from app.policy.ah_assessment import AHAssessment, AHClaim


def verified_count(value):
    return AHAssessment(count=AHClaim(
        value=value, qualifier="exact", state="verified",
        application_reference="SYNTHETIC/AH", scope_type="whole_site",
        scope_label="Whole synthetic scheme", stage="proposed",
        document_id="synthetic-test-document", document_date="2026-09-01",
        source_url="https://example.invalid/ah-test",
        passage=f"Synthetic test evidence: {value} affordable homes in the whole scheme.",
    ))
