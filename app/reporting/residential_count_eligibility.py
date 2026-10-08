"""Request-local residential metric/scope exclusion; never derives a replacement count.

Kept outside the frozen CountAssessment module to preserve v6/v7/v8 oracles.
"""
from dataclasses import dataclass
from app.reporting.commercial_evidence import known_unit_count

@dataclass(frozen=True)
class CountEligibility:
    """Request-local claim containment, not a replacement count/extraction engine.

    None means no affirmative contradiction identified, NOT source verification.
    Raw SI, AH fields, subject identity and matching policy remain untouched.
    """
    reason: str | None = None

    @property
    def eligible(self):
        return self.reason is None


def residential_count_eligibility(application, value=None):
    """Reject affirmative metric/scope contradictions in the application proposal.

    No count is repaired from text. Missing/ambiguous text preserves the existing
    uncertainty contract. Restrict negative evidence to the subject's proposal,
    never an address, development-type guess, unrelated document or parent SI.
    """
    import re
    text = (getattr(application, "proposal", None) or "").lower()
    # Explicit dwelling-creation clauses counter incidental bridges/commercial
    # space/works. 'Erection of replacement porches' is not dwelling creation.
    noun = r"(?:dwellings?|homes?|houses?|apartments?|flats?|bungalows?)\b"
    quantum = r"(\d+)\s*(?:no\.?\s*)?(?:[a-z]+(?:-[a-z]+)*\s+){0,4}?" + noun
    # Only affirmative creation clauses, never demolition/existing stock counts.
    prefix = (r"\b(?:erection|construction|provision|development|conversion)\s+"
              r"(?:(?:of|to|into|comprising)\s+)?"
              r"(?:retirement living community comprising\s+)?"
              r"(?:up to\s+|approximately\s+|approx\.?\s+)?")
    # Trim a trailing parent citation only after current-scope evidence. Some
    # portals put the citation BEFORE the actual description; keep that text.
    ancillary_action = re.search(
        r"\b(?:reserved matters(?: application)?(?: approval)?(?: for)?|"
        r"application for reserved matters approval for|"
        r"(?:approval|provision|construction|erection) of)\s+"
        r"(?:associated\s+)?(?:landscaping(?: works)?|infrastructure(?: works)?)\b",
        text,
    ) or re.match(r"\s*landscaping(?: works)?\b", text)
    before_parent = re.split(r"\bpursuant to\b|\bof hybrid application\b", text, maxsplit=1)[0]
    if ancillary_action:
        before_parent = re.split(r"\b(?:adjoining|adjacent to|associated with|in connection with)\s+(?:(?:the|a)\s+)?(?:erection|construction|development|infrastructure|phase)\b|\bfor parent scheme\b", before_parent, maxsplit=1)[0]
    if ancillary_action or re.search(prefix + quantum, before_parent) or re.search(
        r"\b(?:bridges|footbridges|porches|commercial building|acoustics building)\b", before_parent):
        text = before_parent
    creation_matches = list(re.finditer(prefix + quantum, text))
    if not creation_matches:
        creation_matches = list(re.finditer(
            r"\b(?:conversion|change of use)\s+[^.;]{0,100}?\b(?:to|into)\s+" + quantum, text))
    if not creation_matches:
        creation_matches = list(re.finditer(r"\bdevelopment of land for\s+" + quantum, text))
    if not creation_matches:
        # A building-creation clause can place its residential quantum after
        # height/use details. Require an explicit new development/building and
        # a containing connective; incidental demolition/works are not creation.
        building_creation = (
            r"\b(?:erection|construction|provision|development)\s+(?:of\s+)?"
            r"(?:a\s+|an\s+)?(?:new\s+)?(?:(?:[0-9]+|[a-z]+)[ -](?:storey|story)\s+)?"
            r"(?:(?:mixed-use|residential|apartment|new)\s+)?"
            r"(?:development|building|block)\b[^.;]{0,160}?"
            r"\b(?:with|containing|comprising|providing)\s+" + quantum
        )
        creation_matches = list(re.finditer(building_creation, text))
    creation = bool(creation_matches)
    if not creation:
        # The application action, not the mere word 'landscaping', establishes
        # an ancillary scope. Parent citations cannot supply its own homes.
        if ancillary_action:
            return CountEligibility("ancillary_works_scope")
        if re.search(r"\b(?:porches|roofs?|windows?|cladding|repairs|refurbishment)\b", text) and re.search(
            r"\b(?:existing\b|to\s+\d+\s+(?:dwellings|homes|houses))", text):
            return CountEligibility("existing_stock_works")
        if re.search(r"\b(?:pedestrian\s+(?:crossings|bridges)|footbridges?|crossings/bridges)\b", text):
            return CountEligibility("ancillary_works_scope")
        if re.search(r"\bcommercial building\b|\buse class(?:es)?\s+b[28]\b|\bacoustics (?:building|metrology)\b", text):
            return CountEligibility("non_residential_scope")

    # A definite multi-component description can disprove a component masquerading
    # as a total. Summation here is a rejection test only; it never supplies a value.
    numbers = [int(m.group(1)) for m in creation_matches]
    additive = len(creation_matches) == 1
    if len(creation_matches) == 2:
        link = text[creation_matches[0].end():creation_matches[1].start()]
        link = re.sub(r"\(class c3\)", "", link)
        additive = bool(re.fullmatch(r"\s*(?:,?\s*and|together with)\s+", link))
    if creation:
        # An explicit joined additional residential component only. Never sum
        # demolition, old permissions or numbers in unrelated policy context.
        end = creation_matches[-1].end()
        extra = re.match(r"\s*(?:,?\s*and|together with)\s+" + quantum, text[end:])
        if extra:
            numbers.append(int(extra.group(1)))
        # Bamford describes communal facilities between its explicit components.
        extra = re.search(r"\btogether with\s+" + quantum, text[end:])
        if extra and int(extra.group(1)) not in numbers:
            numbers.append(int(extra.group(1)))
    known = known_unit_count(value)
    if creation and additive and len(numbers) == 2 and known in numbers and known != sum(numbers):
        return CountEligibility("component_not_whole")
    # Do not compare one creation clause against other quantity-bearing text:
    # it may be a varied/partial/historic quantity, not the whole proposal.
    all_numbers = re.findall(quantum, text)
    if creation and len(numbers) == 1 and len(all_numbers) == 1 and known is not None and known != numbers[0]:
        return CountEligibility("proposal_count_conflict")
    return CountEligibility()


def eligible_residential_scalar(application, value):
    """Legacy read adapters share the same gate, never a fallback around it."""
    return value if residential_count_eligibility(application, value).eligible else None
