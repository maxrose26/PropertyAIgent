"""V7 benchmark cases: FACTS first, then the Product Owner's INTENDED outcome (written before and independently of any implementation result).

Every expectation below is a PROPOSAL awaiting Product Owner review (APPROVED_BY_PRODUCT_OWNER stays False). If the implementation disagrees with an expectation the benchmark FAILS and
the expectation must NOT be edited to fit the code - the disagreement is reported for decision.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.policy.buyer_matching import (
    PHASING_CURRENT_EVIDENCED_PHASE as CURRENT, PHASING_CURRENTNESS_UNKNOWN as UNKNOWN, PHASING_HISTORICAL_ONLY as HISTORICAL, PHASING_NONE_IDENTIFIED as NONE,
    PLANNING_DELIVERY, STRATEGIC_LAND,
)
from app.policy.buyer_profiles import ADOPTED_ALLOCATION, PERMISSION_GRANTED

APPROVED_BY_PRODUCT_OWNER = False

STRONG, POSSIBLE, INSUFFICIENT, NOT_SUITABLE = "STRONG_FIT", "POSSIBLE_FIT", "INSUFFICIENT_EVIDENCE", "NOT_SUITABLE"
LABEL_CURRENT = "Phased delivery evidenced."
LABEL_UNKNOWN = "Phase evidence identified — current status unverified."


@dataclass(frozen=True)
class Subject:
    """One subject of a family: its explicit commercial facts, the shared phasing fact it is judged under, and the intended outcome."""
    opportunity_id: str
    facts: dict                                   # MatchingFacts overrides (explicit, deterministic)
    expect_fit: str
    expect_investigative: bool
    phasing: str | None = None                    # the shared acquisition-phasing state of the wider development (None = no fact supplied)
    phase_scope_key: str | None = None            # the subject IS this named phase scope (self-scope guard input)
    must_say: tuple = ()                          # phrases that must appear in the subject's reasons
    must_not_say: tuple = ()                      # phrases that must NOT appear


@dataclass(frozen=True)
class Case:
    case_id: str
    buyer: str
    title: str
    key_facts: str
    subjects: tuple
    expect_family_fit: str
    expect_family_investigative: bool
    expect_representative: str                    # opportunity id of the family representative
    expect_label: str | None                      # the family phasing label (None = no label)
    why: str                                      # why an acquisition professional should get this result
    optional: bool = False


def pd(**overrides):
    base = dict(opportunity_type=PLANNING_DELIVERY, unit_count=None, development_type_raw="houses", is_specialist_development=False, affordable_percentage=30.0,
                affordable_percentage_trusted=True, affordable_unit_count=None, planning_state=PERMISSION_GRANTED, has_identified_planning_activity=True,
                has_phasing_evidence=False, matched_to_site=True)
    base.update(overrides)
    return base


def site_id(n):
    return f"planning_delivery:site:{n}"


def phase_id(n, code):
    return f"planning_delivery:phase:{n}:{code}"


def oversized_parent(n, units, phasing, **kw):
    return Subject(site_id(n), pd(unit_count=units), INSUFFICIENT, True, phasing=phasing, **kw)


CASES = (
    Case("A_nesten_oversized_parent_with_current_buyer_sized_phase", "nesten_homes", "Nesten: 520-home parent, CURRENT 125-home phase",
         "Parent 520 homes (discovery max 220); Phase 1 = 125 homes; phasing CURRENT_EVIDENCED_PHASE",
         (oversized_parent(101, 520, CURRENT, must_say=("Phased delivery is evidenced", "Availability is unverified"),
                           must_not_say=("decomposition remains unverified",)),
          Subject(phase_id(101, 1), pd(unit_count=125), STRONG, False, phasing=CURRENT, phase_scope_key="1")),
         STRONG, False, phase_id(101, 1), LABEL_CURRENT,
         "The 520-home scheme is too big to buy as a whole, but a 125-home phase is squarely inside Nesten's 50-200 range: lead with the phase; keep the parent as an investigate-only line. "
         "Nothing says the phase is for sale."),
    Case("B_nesten_oversized_parent_currentness_unknown", "nesten_homes", "Nesten: 520-home parent, phase evidence of unknown currentness",
         "Parent 520 homes; phase evidence exists but an undated grant means currentness cannot be established; phasing PHASE_EVIDENCE_CURRENTNESS_UNKNOWN",
         (oversized_parent(102, 520, UNKNOWN, must_say=("current implementation status cannot be established",),
                           must_not_say=("Phased delivery is evidenced", "current phased delivery")),),
         INSUFFICIENT, True, site_id(102), LABEL_UNKNOWN,
         "Phase evidence exists but may be stale: investigate, and say the status is unverified; never present it as live phased delivery."),
    Case("C_nesten_oversized_parent_historical_phasing", "nesten_homes", "Nesten: 520-home parent, only historical phasing",
         "Parent 520 homes; phase permission's assumed implementation date has passed; phasing HISTORICAL_PHASE_ONLY",
         (oversized_parent(103, 520, HISTORICAL, must_say=("Historic phasing evidence", "no current phasing evidence has been identified", "implementation status is unverified"),
                           must_not_say=("Phased delivery is evidenced",)),),
         INSUFFICIENT, True, site_id(103), None,
         "Old phasing is history, not an opportunity signal: investigate the whole scheme but make no current-phasing claim and show no phasing label."),
    Case("D_nesten_oversized_parent_no_phasing_evidence", "nesten_homes", "Nesten: 520-home parent, no phasing evidence",
         "Parent 520 homes; no phase identified in the qualified records; phasing NONE_IDENTIFIED",
         (oversized_parent(104, 520, NONE, must_say=("No current phasing evidence has been identified", "decomposition remains unverified"),
                           must_not_say=("probably", "likely", "may contain", "Phased delivery is evidenced")),),
         INSUFFICIENT, True, site_id(104), None,
         "A big scheme with no evidenced phases is still worth a look, but we must not imply a buyer-sized phase exists."),
    Case("E_nesten_specialist_only_current_phase", "nesten_homes", "Nesten: 520-home parent, CURRENT phase is specialist-only",
         "Parent 520 homes; Phase 2 = 90 retirement-living (specialist) homes, a hard exclusion for Nesten; phasing CURRENT_EVIDENCED_PHASE",
         (oversized_parent(105, 520, CURRENT, must_say=("Phased delivery is evidenced",)),
          Subject(phase_id(105, 2), pd(unit_count=90, is_specialist_development=True, development_type_raw="retirement_living"), NOT_SUITABLE, False,
                  phasing=CURRENT, phase_scope_key="2")),
         INSUFFICIENT, True, site_id(105), LABEL_CURRENT,
         "The only evidenced phase is something Nesten never buys, so that phase is out - but that does not make the wider scheme a fit or show another phase exists: the parent stays an investigate-only lead."),
    Case("F_nesten_in_range_ordinary_subject", "nesten_homes", "Nesten: ordinary 120-home site (unchanged)",
         "Single site, 120 homes (preferred 50-200); phasing NONE_IDENTIFIED",
         (Subject(site_id(106), pd(unit_count=120), STRONG, False, phasing=NONE, must_not_say=("phasing", "decomposition", "phase")),),
         STRONG, False, site_id(106), None,
         "An in-range scheme is a plain fit; phasing wording must not appear because scale is not in question."),
    Case("G_national_housebuilder_oversized_parent_with_current_phase", "national_housebuilder", "National Housebuilder: 900-home parent, CURRENT 240-home phase",
         "Parent 900 homes (discovery max 550); Phase 1 = 240 homes (preferred 200-500); phasing CURRENT_EVIDENCED_PHASE",
         (oversized_parent(107, 900, CURRENT, must_say=("Phased delivery is evidenced",)),
          Subject(phase_id(107, 1), pd(unit_count=240), STRONG, False, phasing=CURRENT, phase_scope_key="1")),
         STRONG, False, phase_id(107, 1), LABEL_CURRENT,
         "Same logic as Nesten at a housebuilder's scale: the 240-home phase is the lead; the 900-home parent stays an investigate-only line."),
    Case("H_strategic_land_large_allocation_explicit_route", "strategic_land_buyer", "Strategic Land: 2,000-home adopted allocation",
         "Allocation 2,000 homes (preferred 100-300) with identified planning activity; the buyer's explicit large-allocation route applies; no planning-delivery phasing fact",
         (Subject("strategic_land:allocation:7",
                  dict(opportunity_type=STRATEGIC_LAND, unit_count=2000, development_type_raw=None, is_specialist_development=None, affordable_percentage=None,
                       affordable_percentage_trusted=False, affordable_unit_count=None, planning_state=ADOPTED_ALLOCATION, has_identified_planning_activity=True, matched_to_site=True,
                       has_phasing_evidence=False),
                  STRONG, True, phasing=None,
                  must_say=("strategic-land position in its own right", "Establish whether a suitable development parcel/phase could become available"),
                  must_not_say=("Phased delivery is evidenced", "Phase evidence", "phasing evidence has been identified", "decomposition remains unverified")),),
         STRONG, True, "strategic_land:allocation:7", None,
         "A strategic-land buyer wants the whole allocation position: it stays a strong fit by the explicit route (with the parcel question to investigate) and is not re-judged by planning-delivery phasing."),
    Case("I_housing_association_total_site_phasing_is_not_affordable_scope", "housing_association", "Housing Association: 520-home site, CURRENT phasing, affordable units unknown",
         "Parent 520 total homes; affordable-unit count not evidenced (metric is affordable units, preferred 50-300); phasing CURRENT_EVIDENCED_PHASE",
         (Subject(site_id(108), pd(unit_count=520, affordable_percentage=None, affordable_percentage_trusted=False, affordable_unit_count=None), INSUFFICIENT, False, phasing=CURRENT,
                  must_not_say=("Phased delivery is evidenced", "affordable package", "affordable units are available")),),
         INSUFFICIENT, False, site_id(108), None,
         "A housing association buys affordable homes: total-site scale and total-site phasing say nothing about an affordable package, so it must not become a lead or carry a phasing claim."),
    Case("J_nesten_below_discovery_minimum", "nesten_homes", "Nesten: 20-home site, below the discovery minimum",
         "Single site, 20 homes (discovery min 45; preferred 50-200); phasing CURRENT_EVIDENCED_PHASE on the wider development",
         (Subject(site_id(109), pd(unit_count=20), INSUFFICIENT, True, phasing=CURRENT, must_say=("below this buyer's discovery range",),
                  must_not_say=("phas", "aggregat", "decompos", "combin", "assemble")),),
         INSUFFICIENT, True, site_id(109), None,
         "Too small is a scale problem in the opposite direction: the wording must say 'below', and nothing may hint that phasing or combining sites could fix it."),
    Case("K_nesten_phase_inside_discovery_envelope_only", "nesten_homes", "Nesten: CURRENT phase of 210 homes (slightly above preferred max)",
         "Parent 520 homes; Phase 1 = 210 homes (preferred 50-200, discovery up to 220); phasing CURRENT_EVIDENCED_PHASE",
         (oversized_parent(110, 520, CURRENT),
          Subject(phase_id(110, 1), pd(unit_count=210), POSSIBLE, False, phasing=CURRENT, phase_scope_key="1")),
         POSSIBLE, False, phase_id(110, 1), LABEL_CURRENT,
         "A phase just over the preferred ceiling is a possible fit in its own right; it beats the investigate-only parent.", optional=True),
    Case("M_nesten_oversized_phase_subject_is_not_decomposed_again", "nesten_homes", "Nesten: a 520-home subject that IS a named phase",
         "Subject = Phase 1 itself, 520 homes; phasing CURRENT_EVIDENCED_PHASE (self-scope guard)",
         (Subject(phase_id(111, 1), pd(unit_count=520), INSUFFICIENT, True, phasing=CURRENT, phase_scope_key="1",
                  must_say=("own scope is a named phase",), must_not_say=("assess the evidenced phase scope(s) separately", "Phased delivery is evidenced")),),
         INSUFFICIENT, True, phase_id(111, 1), None,
         "A phase must not be told to look for phases inside itself, and the badge must not merely restate that the subject is a phase (Product Owner ruling on self-phase subjects).", optional=True),
)
