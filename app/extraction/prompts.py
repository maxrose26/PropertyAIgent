"""LLM extraction prompts and JSON schemas.

Ported verbatim from the prototype's
scripts/AI Master Planning Extraction/ai_extract_project_entities.py,
ai_extract_site_development_intelligence.py and
ai_affordable_evidence_classifier.py - these prompts are already tuned
against real UK planning-document language, so wording is kept unchanged.
"""
from __future__ import annotations

MODEL = "gpt-4o-mini"
SLEEP_BETWEEN_CALLS = 0.5

# ---------------------------------------------------------------------------
# Project entities
# ---------------------------------------------------------------------------

ENTITIES_SCHEMA = {
    "name": "project_entities_extraction",
    "schema": {
        "type": "object",
        "properties": {
            "portal_applicant_name": {"type": ["string", "null"]},
            "portal_applicant_address": {"type": ["string", "null"]},
            "applicant_company": {"type": ["string", "null"]},
            "applicant_person": {"type": ["string", "null"]},
            "developer": {"type": ["string", "null"]},
            "landowner": {"type": ["string", "null"]},
            "site_owner": {"type": ["string", "null"]},
            "planning_agent": {"type": ["string", "null"]},
            "planning_consultant": {"type": ["string", "null"]},
            "architect": {"type": ["string", "null"]},
            "project_manager": {"type": ["string", "null"]},
            "housing_association": {"type": ["string", "null"]},
            "registered_provider": {"type": ["string", "null"]},
            "registered_provider_status": {
                "type": "string",
                "enum": ["named", "not_yet_confirmed", "not_applicable", "unknown"],
            },
            "contractor": {"type": ["string", "null"]},
            "consultant_team": {"type": ["string", "null"]},
            "entity_relationship_notes": {"type": ["string", "null"]},
            "source_evidence": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": [
            "portal_applicant_name", "portal_applicant_address", "applicant_company",
            "applicant_person", "developer", "landowner", "site_owner", "planning_agent",
            "planning_consultant", "architect", "project_manager", "housing_association",
            "registered_provider", "registered_provider_status", "contractor", "consultant_team",
            "entity_relationship_notes", "source_evidence", "confidence",
        ],
        "additionalProperties": False,
    },
}


def build_entities_prompt(
    reference: str, address: str, proposal: str, application_type: str,
    portal_applicant_name: str, portal_applicant_address: str, notes: str,
) -> str:
    return f"""
You are extracting project entity intelligence from UK planning application documents.

Planning reference:
{reference}

Portal metadata:
- Site address: {address}
- Proposal: {proposal}
- Application type/classification: {application_type}
- Portal applicant name: {portal_applicant_name}
- Portal applicant address: {portal_applicant_address}

Your job is to identify the real project entities where clearly stated.

Important rules:
- Do NOT invent company names.
- Only extract names explicitly stated.
- Use null where unclear.

developer rules - the portal's "applicant" is very often the planning agent
or consultant submitting on someone else's behalf, NOT the company that will
actually build/deliver the scheme. But don't over-apply that suspicion either
- confirmed a real misclassification (PA/2026/0539, Crescent Investments LLC
Limited) where the model wrongly reasoned "the applicant is likely acting as
the agent" purely because a DIFFERENT company (Euan Kellie Property
Solutions) was ALSO named as planning_agent elsewhere in the documents -
that's not evidence of anything on its own. A scheme routinely has both a
developer AND a separate professional agent it instructed - having two named
firms doesn't make the applicant one of them. Do not assume applicant =
developer OR applicant = agent without real evidence either way:
- Actively check the documents (planning statement's introduction/background
  section, cover letter, S106 agreement's defined parties, decision notice)
  for an explicit statement of who the developer is - e.g. "the applicant is
  a leading developer of...", "on behalf of [X], who will deliver...", "the
  developer, [X], proposes...". Use this even if it takes more than a
  surface read - this is worth verifying properly, not skipping when not
  immediately obvious.
- Only treat the applicant as the agent (not the developer) if the
  applicant's OWN NAME closely matches, or a document explicitly states it
  IS, the planning_agent/planning_consultant. The mere existence of a
  SEPARATELY-named agent elsewhere in the documents is not evidence the
  applicant is also an agent - a professional-services-sounding agent name
  (words like "Planning", "Property Solutions", "Consulting", "Associates",
  "Chartered") alongside a company/SPV-style applicant name is the NORMAL
  pattern for a developer instructing its own agent, not a signal the
  applicant is itself the agent.
- A company/SPV-style applicant name (contains Ltd, Limited, LLC, Holdings,
  Investments, Developments, Properties, Group, Estates, etc., and isn't a
  planning-consultancy-sounding name per the above) is more likely than not
  the developer, or an SPV set up specifically to hold/deliver this scheme -
  default to setting developer to this name unless the documents clearly say
  otherwise. Such SPVs are frequently a subsidiary of a larger parent
  developer/group - check the documents for wording like "a subsidiary of...",
  "part of the... Group", "trading as..." naming that parent, and record it
  in entity_relationship_notes if found (the SPV name itself still goes in
  developer/applicant_company - the parent is additional context, not a
  replacement).
- If no separate agent is named anywhere and the portal applicant is itself
  clearly a housebuilder/developer/property company (not an individual, not
  a firm whose name signals planning consultancy) delivering the scheme in
  its own right, developer may be set to the same value as applicant_company
  - but state that reasoning explicitly in entity_relationship_notes so it's
  clear this was inferred, not stated outright.
- If still genuinely unresolved after checking the above, leave developer
  null rather than guessing - a wrong developer name is worse than a blank
  one for outreach purposes.

registered_provider_status rules - a scheme can promise affordable housing
will go to "a Registered Provider" without ever naming which one (common at
outline/full application stage before a nominations agreement is signed):
- named = a specific Registered Provider or Housing Association company
  name is stated somewhere in the documents.
- not_yet_confirmed = the documents state affordable units will be
  transferred/delivered/managed by "a Registered Provider" (or similar,
  e.g. references to a future "nomination procedure" or "RP to be
  appointed") WITHOUT ever naming a specific company - registered_provider
  stays null in this case, this status is what explains why.
- not_applicable = no affordable housing component in this scheme at all
  (no RP would be expected).
- unknown = can't tell from the available documents either way.

Documents:
{notes}
"""


# ---------------------------------------------------------------------------
# Site development intelligence
# ---------------------------------------------------------------------------

SITE_INTELLIGENCE_SCHEMA = {
    "name": "site_development_intelligence",
    "schema": {
        "type": "object",
        "properties": {
            "site_area_ha": {"type": ["number", "null"]},
            "density_dph": {"type": ["number", "null"]},
            "development_type": {
                "type": "string",
                "enum": [
                    "apartments", "houses", "mixed_apartments_and_houses", "build_to_rent",
                    "retirement_living", "extra_care", "supported_living", "student_accommodation",
                    "care_home", "affordable_housing", "mixed_affordable_and_market_housing",
                    "mixed_retirement_and_market_housing", "mixed_specialist_and_market_housing",
                    "mixed_use_residential", "conversion", "unknown",
                ],
            },
            "development_type_notes": {"type": ["string", "null"]},
            "housing_typology": {"type": ["string", "null"]},
            "specialist_housing_type": {"type": ["string", "null"]},
            "allocation_status": {
                "type": "string",
                "enum": [
                    "allocated_site", "part_of_wider_allocation", "regeneration_area",
                    "town_centre_or_local_centre", "brownfield_register", "strategic_site",
                    "not_stated", "unknown",
                ],
            },
            "allocation_reference": {"type": ["string", "null"]},
            "allocation_name": {"type": ["string", "null"]},
            "site_allocation_policy": {"type": ["string", "null"]},
            "existing_use": {"type": ["string", "null"]},
            "proposed_use": {"type": ["string", "null"]},
            "evidence": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": [
            "site_area_ha", "density_dph", "development_type", "development_type_notes",
            "housing_typology", "specialist_housing_type", "allocation_status",
            "allocation_reference", "allocation_name", "site_allocation_policy",
            "existing_use", "proposed_use", "evidence", "confidence",
        ],
        "additionalProperties": False,
    },
}


def build_site_intelligence_prompt(reference: str, notes: str) -> str:
    return f"""
You are extracting UK planning site and development intelligence.

Planning reference:
{reference}

Extract ONLY facts stated in the documents.
Do not guess.
Return null where information is not clearly stated.

Prioritise evidence from:
1. Planning Statement
2. Design and Access Statement
3. Officer Report / Committee Report
4. Application Form
5. Decision Notice

Extract:
- site area in hectares
- density in dwellings per hectare / dph
- development type
- housing typology
- specialist housing type
- whether the site is allocated or part of a larger allocation
- allocation policy references
- existing use
- proposed use

Development type rules:
- apartments = flats/apartments only
- houses = houses/dwellings only
- mixed_apartments_and_houses = both general houses and general apartments
- build_to_rent = stated BTR/private rented sector scheme
- retirement_living = retirement apartments/later living only
- extra_care = extra care housing only
- supported_living = supported/specialist accommodation only
- student_accommodation = student housing
- care_home = C2 care home/nursing home
- affordable_housing = scheme described mainly as affordable housing only
- mixed_affordable_and_market_housing = affordable homes plus private/open-market homes
- mixed_retirement_and_market_housing = retirement/later living plus private/open-market homes
- mixed_specialist_and_market_housing = supported/extra care/specialist homes plus private/open-market homes
- mixed_use_residential = residential plus commercial/community/retail/etc
- conversion = conversion/change of use of existing building
- unknown = unclear

IMPORTANT:
If a scheme contains both specialist accommodation and general market housing,
do NOT classify it as only retirement_living, supported_living, extra_care, houses, or apartments.

Use one of:
- mixed_retirement_and_market_housing
- mixed_specialist_and_market_housing
- mixed_affordable_and_market_housing

Explain the split in development_type_notes.

Allocation status rules:
- allocated_site = site itself is allocated in local plan
- part_of_wider_allocation = documents say site forms part of a wider allocation/masterplan
- regeneration_area = explicitly in regeneration area/framework
- town_centre_or_local_centre = explicitly in town/local centre
- brownfield_register = explicitly stated
- strategic_site = strategic site/growth location
- not_stated = no allocation mentioned
- unknown = unclear/conflicting

If density is not stated but total units and site area are both clearly stated,
calculate density_dph = total units / site area ha.

Documents:
{notes}
"""


# ---------------------------------------------------------------------------
# Affordable evidence classifier
# ---------------------------------------------------------------------------

AFFORDABLE_SCHEMA = {
    "name": "affordable_evidence_classification",
    "schema": {
        "type": "object",
        "properties": {
            "total_units_context": {"type": ["integer", "null"]},
            "application_context_status": {
                "type": "string",
                "enum": [
                    "full_or_outline_application", "reserved_matters", "variation_of_condition",
                    "non_material_amendment", "discharge_of_condition", "screening_or_scoping",
                    "prior_approval", "site_access_only", "unknown",
                ],
            },
            "affordable_data_status": {
                "type": "string",
                "enum": [
                    "affordable_units_found", "affordable_percentage_found", "all_units_affordable",
                    "no_affordable_required", "offsite_or_commuted_sum", "viability_reduction",
                    "parent_application_needed", "not_expected_for_application_type",
                    "insufficient_evidence",
                ],
            },
            "affordable_units": {"type": ["integer", "null"]},
            "affordable_percentage": {"type": ["number", "null"]},
            "private_units": {"type": ["integer", "null"]},
            "affordable_tenure_split": {"type": ["string", "null"]},
            "reason": {"type": "string"},
            "evidence": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": [
            "total_units_context", "application_context_status", "affordable_data_status",
            "affordable_units", "affordable_percentage", "private_units",
            "affordable_tenure_split", "reason", "evidence", "confidence",
        ],
        "additionalProperties": False,
    },
}

RESOLVED_AFFORDABLE_STATUSES = {
    "no_affordable_required",
    "offsite_or_commuted_sum",
    "all_units_affordable",
    "not_expected_for_application_type",  # e.g. EIA screening/scoping opinions, prior approvals
    "parent_application_needed",  # affordable position is set by a parent application, not this one
}


def build_affordable_classifier_prompt(
    reference: str, proposal: str, application_type: str, status: str, decision: str,
    applicant_name: str, applicant_address: str,
    total_units: int | None, existing_affordable_units: int | None,
    existing_private_units: int | None, existing_affordable_pct: float | None,
    existing_tenure: str, snippets_text: str,
) -> str:
    return f"""
You are classifying affordable housing evidence from UK planning documents.

Planning reference:
{reference}

Portal context:
- Proposal: {proposal}
- Application Type: {application_type}
- Status: {status}
- Decision: {decision}
- Applicant Name: {applicant_name}
- Applicant Address: {applicant_address}

Known housing context from prior extraction:
- total_units: {total_units}
- existing_affordable_units_estimate: {existing_affordable_units}
- existing_private_units_estimate: {existing_private_units}
- existing_affordable_percentage_estimate: {existing_affordable_pct}
- existing_affordable_tenure_estimate: {existing_tenure}

Use the known housing context as context only.
If snippets clearly contradict estimates, trust snippets.

Important:
Some records are NOT full applications.

application_context_status rules - check the Proposal text carefully for
these signal words BEFORE assuming it's a full/outline application:
- "screening opinion", "scoping opinion", "EIA screening", "EIA scoping",
  "screening request", "scoping report" -> screening_or_scoping
- "reserved matters" -> reserved_matters
- "variation of condition", "vary condition" -> variation_of_condition
- "non-material amendment", "non material amendment" -> non_material_amendment
- "discharge of condition", "approval of details" -> discharge_of_condition
- "prior approval" -> prior_approval
- "lawful development certificate", "certificate of lawfulness" -> site_access_only
- otherwise, if it's an outline or full application for the development itself -> full_or_outline_application

Rules:
- Extract affordable units only if explicitly stated.
- Extract affordable percentage only if explicitly stated or directly calculable.
- If all units are affordable:
  affordable_data_status = all_units_affordable
  affordable_units = total units
  affordable_percentage = 100
- Do not assume policy percentages.
- If only off-site contribution exists:
  classify as offsite_or_commuted_sum
- If viability reduced affordable housing:
  classify as viability_reduction, and state the ACTUAL post-reduction
  position in affordable_units/affordable_percentage - e.g. if a viability
  assessment concluded the policy-compliant figure (say 15 units, 7.5%) is
  unviable and the scheme is being delivered as 100% market housing instead,
  report affordable_units = 0, NOT the original pre-reduction figure that
  was demonstrated unviable. If the viability assessment reduced affordable
  housing to some lower but still non-zero number, report that reduced
  number, not the original ask.
- If parent permission needed:
  classify as parent_application_needed
- If application_context_status is reserved_matters: reserved matters
  (layout, scale, appearance, landscaping) does NOT itself decide the
  affordable housing mix - that is fixed at the parent OUTLINE permission's
  own decision/S106 agreement, cited in the proposal text (e.g. "pursuant to
  outline planning permission A/12/76665"). Default to
  parent_application_needed for reserved matters UNLESS the documents you
  were actually given explicitly restate a specific affordable unit count or
  percentage FOR THIS reserved matters phase - do not assume affordable
  detail is simply missing just because this particular filing doesn't
  redecide it.
- If application_context_status is screening_or_scoping or prior_approval:
  affordable housing detail is not expected at this stage - classify as
  not_expected_for_application_type rather than insufficient_evidence,
  UNLESS the documents genuinely do state an affordable position anyway.
- If no usable evidence and affordable data genuinely should be expected:
  classify as insufficient_evidence
- If affordable_data_status is not_expected_for_application_type or
  parent_application_needed: leave affordable_units AND private_units null -
  do not populate a specific unit count for a stage where the affordable
  position has not actually been itemised yet, e.g. do not report
  "100% affordable" just because total_units_context is the only figure
  available at this stage. HOWEVER, if the documents mention a POLICY or
  S106 affordable percentage requirement that applies to the site (even one
  set by the parent outline permission, not decided by this filing itself) -
  e.g. "the site is subject to a policy requirement for a minimum of 25%
  affordable housing" - still report that percentage in affordable_percentage
  and name the requirement's source (policy/S106/parent reference) in
  reason/evidence. A stated-but-not-yet-itemised percentage is real,
  useful information for a reader deciding whether to chase this scheme -
  discarding it just because this specific filing doesn't break it into
  units would hide a genuine, sourced figure.
- Never report a specific affordable_units number unless either (a) the
  documents state it directly, or (b) you can show the arithmetic
  (affordable_percentage% of total_units_context) in evidence - do not
  report a stray number from an unrelated part of the documents as if it
  were the affordable unit count. If you cannot show that derivation,
  leave affordable_units null and report the percentage alone instead.

Affordable evidence snippets:
{snippets_text}
"""
