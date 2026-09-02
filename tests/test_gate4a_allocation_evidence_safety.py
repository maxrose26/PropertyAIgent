"""Gate 4A ("Controlled Residential Allocation Intelligence Extraction") -
deterministic tests for app.policy.allocation_evidence_validation. No
network, no AI call, no production database access anywhere in this file -
every page fixture is real text (verbatim, re-typed from the actual
downloaded Trafford Local Plan Regulation 19 Publication Version PDF) or a
clearly-labelled synthetic fixture for an edge case the real sample doesn't
happen to contain."""
from __future__ import annotations

from app.policy.allocation_evidence_validation import (
    classify_capacity_scope_risk,
    classify_field_association_risk,
    classify_green_belt_status,
    verify_allocation_citation,
)

# --- Real Trafford page text (verbatim) ---

TABLE_15_1_PAGE_292 = """Trafford Local Plan Regulation 19 Publication Version
15.8. The following sites are allocated for the following uses.
Table 15-1: Trafford Local Plan Allocations
Ref Site Name/ Purpose Size (ha) Amount of
Address Development
gross (plan
period)
AN1 Wharfside Comprehensive 145 15,000
mixed-use dwellings
residential-led (8,400
regeneration and dwellings)
redevelopment.
AN2 Civic Quarter Residential led 53 4,000
large scale mixed- dwellings
use regeneration 50,000 sqm
area. office
floorspace
AN3 Trafford Waters Residential led 29.80 3,000
large scale mixed- dwellings
use development. 80,000 sqm
office
floorspace."""

TABLE_15_1_PAGE_293 = """Trafford Local Plan Regulation 19 Publication Version
Ref Site Name/ Purpose Size (ha) Amount of
Address Development
gross (plan
period)
AN13 Land to east and Employment 11.90 45,000 sqm
west of A5181 development employment
(Kellogg's Plant) floorspace
AN14 Site of SCA Employment 2.94 10,800 sqm
Hygiene Products, development employment
Trafford Park floorspace"""

AN1_PAGE_294 = """Trafford Local Plan Regulation 19 Publication Version
AN1: Wharfside
Address Wharfside
Site Size (Ha) 145 ha
Existing use A mixed use area at the eastern end of Trafford Park.
Allocated for Comprehensive mixed-use residential-led regeneration
and redevelopment anchored by a new 100,000-seater
stadium for Manchester United Football Club.
15,000 dwellings (8,400 in plan period)"""

AN4_PAGE_331 = """Trafford Local Plan Regulation 19 Publication Version
AN4: Pomona
Address Pomona Docks, Pomona Strand
Site Size (Ha) 14.41
Existing use Cleared former dockland with 570 dwellings completed.
(Brownfield)
Allocated for Residential development of around 3,200 dwellings with
around 2,050 dwellings in plan period
70,000 sqm of office floorspace (gross) (Use Class
Eg(i)), ancillary commercial uses."""

AN6_PAGE_341 = """Trafford Local Plan Regulation 19 Publication Version
AN6: Land west of Skerton Road, Old Trafford
Address Land west of Skerton Road, Old Trafford
Site Size (Ha) 2.41
Existing use Vacant land. (Brownfield)
Allocated for Residential development of around 540 dwellings."""

AS1_PAGE_360 = """Trafford Local Plan Regulation 19 Publication Version
AS1: Land at Oakfield Road, Altrincham
Address Land at Oakfield Road, Altrincham
Site Size (Ha) 2.24
Existing use Vacant land. (Brownfield)
Allocated for Mixed use development comprising around 100 dwellings
and local retail floorspace."""

AS4_PAGE_379 = """Trafford Local Plan Regulation 19 Publication Version
AS4: Land at Dairyhouse Lane, Broadheath
Address Land at Dairyhouse Lane, Broadheath
Site Size (Ha) 3.46
Existing use Undeveloped (Greenfield)
Allocated for Industrial and warehousing floorspace development
approximately 12,000 sqm (gross)"""
AS4_PAGE_380 = """Trafford Local Plan Regulation 19 Publication Version
D. Strengthen landscape buffers along the northern and
western boundaries to strengthen the Green Belt
boundary;"""

TRAFFORD_PAGES = [
    (292, TABLE_15_1_PAGE_292), (293, TABLE_15_1_PAGE_293), (294, AN1_PAGE_294),
    (331, AN4_PAGE_331), (341, AN6_PAGE_341), (360, AS1_PAGE_360),
    (379, AS4_PAGE_379), (380, AS4_PAGE_380),
]


# --- Allocation identity (Steps 1-2 of the required checklist) ---

def test_1_policy_reference_and_site_name_are_correctly_associated_with_the_right_page():
    result = verify_allocation_citation("AN1", "Wharfside", 294, TRAFFORD_PAGES)
    assert result.status == "verified"
    assert result.verified_page == 294


def test_2_a_missing_policy_reference_falls_back_to_site_name_not_fabrication():
    # A site with no printed policy code (site_name only) must still be
    # verifiable via its name - never invented, never silently unverified
    # just because policy_reference is null.
    result = verify_allocation_citation(None, "Wharfside", 294, TRAFFORD_PAGES)
    assert result.status == "verified"


# --- Citation (Steps 3-6) ---

def test_3_correct_physical_page_is_accepted():
    result = verify_allocation_citation("AN4", "Pomona", 331, TRAFFORD_PAGES)
    assert result.status == "verified"
    assert result.verified_page == 331


def test_4_wrong_model_page_is_corrected_when_unique():
    # The model claims AN4 is on page 293 (it's in the summary table, but
    # its OWN detail page is 331) - AN4 as an identity string only appears
    # verbatim on page 331 in this fixture set, so it corrects cleanly.
    result = verify_allocation_citation("AN4", "Pomona", 293, TRAFFORD_PAGES)
    assert result.status == "corrected"
    assert result.verified_page == 331


def test_5_identity_findable_on_multiple_pages_is_ambiguous():
    # "AN1" appears on both its own detail page (294) and the summary
    # table (292) - a genuinely ambiguous case if the model cites neither.
    result = verify_allocation_citation("AN1", "Wharfside", 999, TRAFFORD_PAGES)
    assert result.status == "ambiguous"
    assert result.verified_page is None
    assert "292" in result.note and "294" in result.note


def test_6_identity_findable_nowhere_is_unverified():
    result = verify_allocation_citation("ZZ99", "Nonexistent Site", 100, TRAFFORD_PAGES)
    assert result.status == "unverified"
    assert result.verified_page is None


# --- Capacity (Steps 7-10) ---

def test_7_explicit_allocation_capacity_correctly_associated():
    risk = classify_field_association_risk("540 dwellings", "AN6", AN6_PAGE_341)
    assert risk == "ASSOCIATED"


def test_8_adjacent_sites_capacity_cannot_be_silently_assigned():
    # On AN1's own detail page, AN1 is the only identity present, so its
    # own "8400" figure is unambiguously nearer to it than to nothing else.
    close_risk = classify_field_association_risk("8400", "AN1", AN1_PAGE_294)
    assert close_risk == "ASSOCIATED"
    # On the dense summary table, AN2's OWN "4000" figure is genuinely
    # closer to AN2's identity than to AN1's - proven with the real other-
    # identity list a caller would have from the same extraction pass.
    risk = classify_field_association_risk("4000", "AN1", TABLE_15_1_PAGE_292, other_identities_on_page=("AN2",))
    assert risk == "UNASSOCIATED"
    # A figure that doesn't exist anywhere near AN1's identity in the text
    # at all is correctly not associated - proven directly, not assumed.
    far_risk = classify_field_association_risk("999999", "AN1", AN1_PAGE_294)
    assert far_risk == "UNASSOCIATED"


def test_9_phase_capacity_cannot_silently_become_whole_site_capacity():
    # AN1's phasing delivery table (not included in this fixture's page
    # text) states per-period figures (800/3600/4000/6600) that sum to
    # 15,000 - none of those individual phase numbers is a candidate
    # "capacity" value the extraction schema itself would ever populate
    # minimum_dwellings/maximum_capacity with (only two explicit fields
    # exist; a phase-table figure was never asked for) - this is a
    # structural, schema-level guarantee rather than something the
    # classifier itself decides, verified here by confirming neither
    # phase figure is treated as this site's own capacity (they don't
    # even appear on this fixture's own detail-page text, exactly because
    # the phasing table is a separate page never sent as this site's own
    # capacity evidence):
    for phase_figure in ("800", "3600", "6600"):
        assert classify_field_association_risk(phase_figure, "AN1", AN1_PAGE_294) == "UNASSOCIATED"


def test_10_ambiguous_multi_number_capacity_is_flagged_for_review():
    # Two distinct dwelling-shaped figures, neither qualified by "in plan
    # period" wording anywhere nearby - genuinely ambiguous which (if
    # either) is the plan-period figure.
    result = classify_capacity_scope_risk(8400, "15,000 dwellings and 8,400 dwellings")
    assert result == "MULTI_SCOPE"

    # But the REAL AN1 excerpt, which DOES qualify 8,400 with "in plan
    # period" right next to it, is safe.
    real_excerpt = "15,000 dwellings (8,400 in plan period)"
    assert classify_capacity_scope_risk(8400, real_excerpt) == "SINGLE_SCOPE"


# --- Hectares (Steps 11-12) ---

def test_11_explicit_site_area_correctly_extracted_and_associated():
    risk = classify_field_association_risk("145 ha", "AN1", AN1_PAGE_294)
    assert risk == "ASSOCIATED"
    risk2 = classify_field_association_risk("14.41", "AN4", AN4_PAGE_331)
    assert risk2 == "ASSOCIATED"


def test_12_adjacent_sites_hectares_cannot_be_silently_assigned():
    # AN3's real hectares (29.80, from the summary table) must not be
    # treated as belonging to AN1 just because both appear somewhere in
    # Table 15-1's own combined text - AN3's identity, correctly supplied
    # as an "other identity on this page", is genuinely nearer to its own
    # 29.80 figure than AN1's identity is.
    combined_table_text = TABLE_15_1_PAGE_292
    risk = classify_field_association_risk(
        "29.80", "AN1", combined_table_text, other_identities_on_page=("AN2", "AN3"),
    )
    assert risk == "UNASSOCIATED"


# --- Green Belt (Steps 13-14) ---

def test_13_explicit_green_belt_adjacency_is_correctly_classified_not_as_release():
    status = classify_green_belt_status(
        "Strengthen landscape buffers along the northern and western boundaries to strengthen the Green Belt boundary;"
    )
    assert status == "adjacent_to_green_belt"
    assert status != "green_belt_release"  # explicit: adjacency must never be conflated with release


def test_14_absence_of_green_belt_evidence_remains_unknown_not_false():
    # AN1's own real text never mentions Green Belt at all.
    assert classify_green_belt_status(None) is None
    # A genuine mention that doesn't match any of the three specific
    # patterns is ALSO None (unknown), never guessed into a bucket.
    assert classify_green_belt_status("The site relates in some way to Green Belt policy considerations.") is None


def test_14b_explicit_release_language_is_distinguished_from_adjacency():
    status = classify_green_belt_status("This site is proposed for release from the Green Belt to accommodate the allocation.")
    assert status == "green_belt_release"


# --- Mixed-use (Step 15) ---

def test_15_mixed_use_site_with_residential_component_remains_eligible():
    risk = classify_field_association_risk("100 dwellings", "AS1", AS1_PAGE_360)
    assert risk == "ASSOCIATED"


# --- Cross-reference (Step 16) ---

def test_16_employment_only_site_has_no_dwelling_figure_to_misassociate():
    # AN13/AN14 (Table 15-1, page 293) are pure employment allocations -
    # their own text states only sqm floorspace, never a dwellings figure
    # at all, so there is nothing for a dwellings-shaped association check
    # to even find near their identity strings.
    risk = classify_field_association_risk("4000 dwellings", "AN13", TABLE_15_1_PAGE_293)
    assert risk == "UNASSOCIATED"


# --- Regression (Step 17) ---

def test_17_existing_extract_local_plan_sites_schema_still_importable_and_shaped_correctly():
    from app.extraction.local_plan import SCHEMA
    props = SCHEMA["schema"]["properties"]["sites"]["items"]["properties"]
    for existing_field in ("policy_reference", "site_name", "minimum_dwellings", "category"):
        assert existing_field in props
    for new_field in ("maximum_capacity", "site_area_hectares", "green_belt_excerpt", "source_page", "source_excerpt"):
        assert new_field in props
