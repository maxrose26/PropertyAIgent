"""Qualifying-scheme filter.

Ported from the prototype's extract_all_applications.py. Runs against the
proposal text returned by the search-results listing, before any documents
are downloaded, so we only spend document-download/AI-extraction effort on
applications that are plausibly 10+ unit residential schemes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

UNIT_COUNT_PATTERNS = [
    # "dwellinghouse(s)" - the formal legal term UK planning proposals often
    # use instead of "house(s)"/"dwelling(s)" - confirmed a real case ("2no.
    # semi-detached 3 bedroom dwellinghouses") where its absence meant no
    # pattern here could match at all, so a genuine 2-unit scheme (well under
    # the 10-unit threshold) fell through to the REVIEW_KEYWORDS fallback via
    # "outline application" and wrongly qualified.
    r"(\d+)\s*(?:apartments|flats|dwellings|dwellinghouses|houses|homes|new homes|units|residential units)",
    # Singular form ("1 four bed dwelling", "1 detached house") with an optional
    # short descriptive phrase (bedroom count, "detached", etc.) in between -
    # without this, a single-unit application falls through to the much
    # noisier REVIEW_KEYWORDS fallback below (e.g. any "outline application"
    # gets flagged, which is nearly all of them regardless of size). The
    # negative lookahead guards against "unit(s)" meaning a measurement unit
    # rather than a dwelling - confirmed a real case: an application form's
    # own Planning Portal reference number ("PP-14236922") sat immediately
    # before a "unit sq. metres" area-field label, and got read as
    # "14236922 units".
    r"(\d+)\s*(?:\w+[\s-]+){0,3}(?:apartments?|flats?|dwellings?|dwellinghouses?|houses?|homes?|units?)\b(?!\s*(?:sq\.?|square|m2|metres?|meters?|hectares?|ha)\b)",
    r"(\d+)\s*self-contained\s*(?:apartments|flats|dwellings|units)",
    r"(\d+)\s*residential\s*(?:apartments|flats|dwellings|units)",
    r"(?:apartments|flats|dwellings|houses|homes|units)\s*(?:comprising|of|for)?\s*(\d+)",
    r"(?:erection|construction|development|conversion).*?(\d+)\s*(?:apartments|flats|dwellings|houses|homes|units)",
    r"build to rent.*?(\d+)\s*(?:apartments|flats|homes|units)",
    r"btr.*?(\d+)\s*(?:apartments|flats|homes|units)",
    # Specialist/supported accommodation is often sized by headcount rather
    # than "units" - confirmed a 3-person supported-living scheme falling
    # through to the REVIEW_KEYWORDS net (via "supported living") purely
    # because "3 Adults" didn't match any dwelling-word pattern above.
    r"(\d+)\s*(?:adults?|residents?|people|persons?|service users?|bedspaces?)\b",
    # Structured application-form field ("Number of dwellings: 24",
    # "Total units proposed | 24") - the free-text proposal patterns above
    # miss this, but it's the cheapest reliable signal for confirming a
    # scheme that has no number anywhere in its portal proposal summary
    # (see unit_confirmation_status / stage_confirm_units).
    r"number\s*of\s*(?:residential\s*)?(?:units|dwellings|houses|flats|apartments)[^\d\n]{0,40}?(\d+)",
    r"(?:total\s*)?(?:units|dwellings)\s*proposed[^\d\n]{0,20}?(\d+)",
    # A large strategic scheme's headline figure is often stated as a
    # parenthetical cap straight after the use-class listing, not adjacent
    # to the dwelling-word itself - confirmed a real case (Stockport
    # DC/089402 et al, a ~2,150-dwelling cross-boundary strategic site
    # shared with Tameside): "residential dwellings (up to 2,150), local
    # centres...". None of the patterns above match since the number
    # follows "dwellings" through a "(up to " gap wider than they allow.
    # Plain \d+ (not comma-aware) - normalise_text already strips
    # thousand-separator commas before any pattern here ever runs.
    r"(?:apartments?|flats?|dwellings?|dwellinghouses?|houses?|homes?|units?)\s*\(?\s*up\s*to\s*(\d+)\)?",
]

EXCLUDE_CATEGORIES = {
    "variation_or_amendment",
    "condition_discharge_or_details",
    "non_target_admin_or_minor",
    # A boundary consultation is a notification about ANOTHER council's own
    # application, not a real opportunity on this council's own patch - it
    # duplicates (or, for an unreachable council like Trafford, can't even be
    # cross-checked against) that other council's own listing. Previously
    # these were still shown with a warning banner (see reconcile.py's
    # external_consultation_source handling) rather than excluded outright,
    # but confirmed real user feedback: they clutter results and should be
    # dropped entirely, the same as any other non-substantive filing.
    "external_consultation",
    "screening_or_scoping_opinion",
}

# Purely commercial/industrial development that happens to mention generic
# planning terms like "outline application" was slipping through the
# REVIEW_KEYWORDS net below (confirmed: a self-storage facility and a hotel
# conversion both got flagged as possible 10+ unit housing schemes). Only
# excludes when there's NO residential signal word at all, so genuine
# mixed-use residential+retail schemes aren't wrongly dropped.
NON_RESIDENTIAL_KEYWORDS = [
    "self storage", "self-storage", "storage facility",
    "hotel accommodation", "hotel development", "erection of a hotel", "erection of hotel",
    "industrial units", "industrial development", "warehouse", "distribution centre", "distribution warehouse",
    "storage and distribution",
    "retail units", "retail development", "supermarket", "office development", "office accommodation",
    # Confirmed a real case: a power station's reserved matters application
    # ("for the access, appearance, scale, layout and landscaping for up to
    # 40MW of the 200MW consented...") wrongly qualified since "reserved
    # matters" is treated as unambiguous in the REVIEW_KEYWORDS fallback -
    # nothing in NON_RESIDENTIAL_KEYWORDS covered energy-generation schemes
    # at all. "mw"/"megawatt" are checked as their own regex below (tied to
    # a number, word-boundary aware) rather than added here, since a bare
    # substring check risks false positives.
    "power station", "energy centre", "energy generation", "solar farm", "battery storage",
    # Confirmed a real case: a commercial-only outline application ("mid-tech
    # units", multi-storey car park, Use Classes E/B2/C1 - no C3 housing
    # anywhere) also wrongly qualified via the same "outline
    # application"/"reserved matters" unambiguous-match path.
    "mid-tech",
]

_MEGAWATT_RE = re.compile(r"\b\d+\s*mw\b", re.I)

RESIDENTIAL_SIGNAL_WORDS = ["dwelling", "house", "flat", "apartment", "residential", "home", "housing"]
# Bare substring checks against short common words are fragile - "house" is
# a substring of "warehouse", so a plain `"house" in text` check treats an
# INDUSTRIAL/WAREHOUSE building as if it had residential content, exactly
# cancelling out the is_non_residential exclusion it's meant to feed.
# Confirmed a real case: "erection of an industrial/warehouse building
# (unit 8)" was correctly flagged as containing the non-residential keyword
# "warehouse", but ALSO wrongly registered a "residential signal" via that
# same word, keeping it from being excluded.
_RESIDENTIAL_SIGNAL_RE = re.compile(
    r"\b(?:dwellings?|houses?|flats?|apartments?|residential|homes?|housing)\b", re.I
)


def _has_residential_signal(proposal_norm: str) -> bool:
    return bool(_RESIDENTIAL_SIGNAL_RE.search(proposal_norm))


def is_non_residential(proposal_norm: str) -> bool:
    has_non_residential = (
        any(kw in proposal_norm for kw in NON_RESIDENTIAL_KEYWORDS) or bool(_MEGAWATT_RE.search(proposal_norm))
    )
    return has_non_residential and not _has_residential_signal(proposal_norm)


REVIEW_KEYWORDS = [
    "residential development",
    "major residential",
    "housing development",
    "outline application",
    "outline planning",
    "reserved matters",
    "comprehensive redevelopment",
    "regeneration",
    "masterplan",
    "build to rent",
    "btr",
    "mixed use",
    "mixed-use",
    "section 106",
    "s106",
    "affordable housing",
    "supported living",
    "extra care",
]

# Several REVIEW_KEYWORDS ("mixed use", "regeneration", "masterplan", "s106")
# are common in purely commercial or hospitality applications too - confirmed
# a real case: "Change of use...to a mixed use of cafe restaurant and
# drinking establishment (Sui Generis)" matched "mixed use" and got treated
# as a possible 10+ unit housing scheme, which then went through full AI
# extraction and came back with a nonsense "80 units" (misread from an
# unrelated figure in the documents, e.g. seating capacity). These phrases
# only mean "possible housing" when paired with an actual residential signal
# word somewhere in the text.
#
# Deliberately NOT included here: "outline application" / "outline planning"
# / "reserved matters". Those two stages apply just as often to a later
# phase of an already-known residential scheme (e.g. "Reserved matters
# application for landscaping following outline approval DC/077409" -
# genuinely a real housing phase, but its own text has no residential word
# at all since it's just describing the landscaping details) - confirmed
# requiring a residential word for these specifically would have wrongly
# excluded 7 real, already-verified qualifying schemes with no evidence any
# of them were false positives. "mixed use"/"regeneration"/"masterplan"/
# "s106"/"comprehensive redevelopment" caused zero such regressions when
# checked against the same existing data, so only those stay ambiguous.
AMBIGUOUS_REVIEW_KEYWORDS = {
    "comprehensive redevelopment", "regeneration", "masterplan",
    "mixed use", "mixed-use", "section 106", "s106",
}

# Confirmed real false positives (A/26/100295/FULL: "Change of use from a
# domestic dwelling to mixed use as a dwelling house..."; A/26/100653/FULL:
# "Change of use to a mixed use as a dwelling..."; A/26/100471/FULL: same
# pattern with "dwellinghouse"; A/26/100980/PDG: "...mixed use as a flat at
# first floor...") where the "mixed use" REVIEW_KEYWORDS match paired with a
# SINGULAR dwelling/flat noun ("as a dwelling", not "as dwellings") - always,
# in practice, a single-property change of use, not a multi-unit scheme that
# just omitted its count. Tried a broader "no plural dwelling noun anywhere"
# heuristic first, but confirmed it wrongly excluded several already-verified
# real schemes (e.g. FUL/354904/25, a confirmed 149-unit scheme, whose
# proposal text is just "erection of a residential development..." - a
# project-scale description, not a reference to a single physical unit) -
# reverted to matching this exact "mixed use as a singular dwelling/flat"
# phrasing instead of trying to infer singularity from absence alone.
SINGLE_UNIT_MIXED_USE_RE = re.compile(
    r"mixed use as an?\s+(?:domestic\s+)?(?:dwelling(?:\s?house)?|flat)\b", re.I
)
# Confirmed real false positive (A/26/100394/FULL: "...create additional
# self-contained residential unit") - singular "unit" with "additional",
# unambiguously a one-unit addition to an existing development.
SINGLE_RESIDENTIAL_UNIT_ADDITION_RE = re.compile(
    r"additional\s+self[- ]contained\s+residential\s+unit\b", re.I
)


def normalise_text(text: str | None) -> str:
    text = str(text or "").lower()
    # "No. of dwellings: 24" means "Number of dwellings" - preserve that
    # BEFORE the generic "no."/"no " stripping below (which exists for the
    # other meaning of "no.", as in "1 no. four bed dwelling" == "1 four bed
    # dwelling") would otherwise delete the "no" entirely and silently break
    # the "number of X" application-form pattern in UNIT_COUNT_PATTERNS.
    text = text.replace("no. of", "number of")
    text = text.replace("no.", "no")
    # Replace with a space, not "" - confirmed a real case: UK planning text
    # very commonly glues the count straight onto "no." with no space
    # ("2no. semi-detached dwellinghouses", "48no. affordable dwellings").
    # Deleting "no " outright (rather than replacing it with a boundary
    # space) fused the digit directly onto the following word - "48no.
    # affordable" became "48affordable" - which no UNIT_COUNT_PATTERNS regex
    # can match (they all require whitespace right after the digit), so the
    # application fell through to the much noisier REVIEW_KEYWORDS fallback
    # instead of being confirmed/excluded by its own stated count. A real
    # 2-unit scheme ("2no. dwellinghouses") slipped through the 10-unit
    # threshold gate this way.
    text = text.replace("no ", " ")
    # Strip thousand-separator commas between digits ("1,560" -> "1560") -
    # confirmed a real case where leaving the comma in place meant "(\d+)"
    # only matched the digits AFTER it: "equivalent to 1,560 homes per year"
    # (a borough-wide annual housing delivery target from a Local Plan
    # policy summary, nothing to do with the actual scheme) produced a
    # candidate of exactly "560" - a fabricated number that doesn't even
    # appear in the source text, since the "1," was silently dropped rather
    # than joined. Also fixed "26,500 dwellings" -> spurious "500" the same
    # way. This doesn't make policy-target numbers correct (see
    # POLICY_TARGET_CONTEXT_RE below for that), just no longer wrong in a
    # second, compounding way.
    return re.sub(r"(?<=\d),(?=\d)", "", text)


def extract_unit_count(text: str | None) -> int | None:
    normalised = normalise_text(text)
    counts = extract_unit_counts(text)
    return max(counts) if counts else None


# No genuine single UK planning application has ever proposed anywhere near
# this many units - the largest strategic urban extensions top out in the
# low thousands. Anything above this is essentially always a reference
# number, grid reference, or similar false match rather than a real unit
# count - confirmed a real case where a Planning Portal reference number
# ("PP-14236922") got read as a unit count.
MAX_PLAUSIBLE_UNITS = 5000

# Application forms are full of dates ("Date notice served: 08/09/2025") and
# plan-period years ("adopted Local Plan 2022-2039"), and the headcount
# pattern's "persons?" alternative in particular is loose enough to read
# "...2025\nPerson family name:..." (a date sitting right before an
# ownership-certificate form field) as "2025 persons" - confirmed a real
# case where this pushed a fabricated 2025-unit total past the genuine
# candidates (410/407) sitting right there in the same document. No real UK
# scheme's unit count coincides with a calendar year, so exclude the range
# outright rather than trying to special-case every date format.
YEAR_LIKE_RANGE = range(1990, 2036)

# UK planning statements near-universally open with a Local Plan policy-
# context section quoting the borough's own housing delivery figures - e.g.
# "a minimum requirement of 26,500 dwellings over the plan period 2022-2039,
# equivalent to 1,560 homes per year" - confirmed present in 149 of 1,106
# extracted documents in this database. These numbers sit directly next to
# the same "dwellings"/"homes" keywords the count patterns look for, so
# without this check they compete on equal footing with the scheme's own
# actual unit count. Checked against a window of text AROUND each match
# (not just an exact phrase match), since the number and the qualifying
# phrase don't always sit in a fixed order relative to each other.
POLICY_TARGET_CONTEXT_RE = re.compile(
    r"per\s*(?:year|annum)|objectively\s*assessed\s*need|housing\s*requirement|"
    r"requirement\s*of|over\s*the\s*plan\s*period|local\s*plan\s*period|housing\s*target|"
    r"housing\s*need|delivery\s*target|annual\s*(?:housing\s*)?requirement|"
    # 5-year housing land supply calculations are just as universal a policy-
    # context boilerplate as the "per year" figures above - confirmed a real
    # case: "the council's January 2025 addendum confirms a claimed
    # deliverable supply of only 2523 dwellings...5.5 years' supply" (a
    # borough-wide land-supply figure, nothing to do with the scheme).
    r"deliverable\s*supply|housing\s*land\s*supply|years?\W{0,3}supply|"
    # Large strategic sites are routinely delivered by multiple separate
    # applications/developers, each covering one part - their own documents
    # commonly restate the WIDER allocation's total for context. Confirmed a
    # real case: "the site forms the north-western corner of a more
    # extensive site for the delivery of around 1450 dwellings" - the
    # application itself is only a fraction of that 1450. Also catches
    # reserved-matters/phase applications that restate a parent outline
    # consent's total ("pursuant to outline application 91352/14... up to
    # 1700 dwellings") the same way.
    r"more\s*extensive\s*site|wider\s*allocation|wider\s*site|part\s*of\s*a\s*wider|"
    r"pursuant\s*to\s*outline|"
    # NOT "outline (planning) (consent|application|permission)" alone, even
    # though that would have caught a real case ("the outline consent is
    # for...up to 1700 dwellings" on a Reserved Matters filing) - confirmed
    # this is genuinely unsafe: a HYBRID application ("(1) FULL PERMISSION
    # FOR...164 DWELLINGS; AND (2) OUTLINE PERMISSION FOR...86 DWELLINGS")
    # has its own outline component right next to a genuine full-permission
    # figure, and excluded BOTH - silently losing an entire real 250-unit
    # scheme from qualifying at all. "pursuant to outline" above is narrow
    # enough to stay safe; bare "outline...permission" is not.
    # Masterplan/allocation "vision" statements restate the wider site's
    # target using yet more phrasings: "the allocation is for a total of
    # 1450 dwellings", "the allocated site is identified to deliver c. 1450
    # homes", "1. make provision for around 2350 new homes".
    r"allocation\s*is\s*for|identified\s*to\s*deliver|make\s*provision\s*for|"
    # Strategic/masterplan capacity statements for a wider area (a whole town
    # centre, not this specific application) - confirmed a real case
    # (Tameside 25/00972/FUL, a genuine 102-dwelling scheme): "the delivery
    # framework identifies significant potential for new housing, stating
    # that the town centre could accommodate up to 1000 new dwellings, with
    # a similar future windfall cap" wrongly became the scheme's own total
    # via the new "up to N" UNIT_COUNT_PATTERNS entry, since nothing here
    # previously covered this phrasing. "windfall" alone is a safe, distinct
    # planning-policy term (a borough's windfall housing allowance/site) with
    # no legitimate use describing one specific application's own count.
    r"delivery\s*framework|could\s*accommodate|windfall|"
    # Brownfield-register / SHLAA-style site-capacity assessments cite an
    # ASSESSED theoretical capacity for the site, not what this specific
    # application actually proposes - confirmed a real case, same Tameside
    # application as above, in the SAME Planning Statement: "the application
    # site (ref: H-STANTH-032) is identified as brownfield, assessed as
    # suitable for 210 net apartments" competed directly against the
    # Application Form's own explicit "Total proposed residential units 102"
    # field, and wrongly won since housing_mix.py takes the largest
    # candidate when no portal-estimate exists to disambiguate.
    r"assessed\s*as\s*suitable\s*for|identified\s*as\s*brownfield",
    re.I,
)
POLICY_TARGET_CONTEXT_WINDOW = 90

# Small schemes (frequently Permission in Principle / prior-approval style
# applications) are very often phrased in words, not digits - confirmed a
# real case: "Permission in principle for residential development of up to
# nine dwellings" produced no digit-based candidate at all, so the housing-
# mix regex pass fell back to unrelated document numbers instead (see
# POLICY_TARGET_CONTEXT_RE above - the actual failure mode for that case).
# Covers one to twenty, plus standalone tens - compound word-numbers above
# ninety-nine essentially never appear in this domain, real large schemes
# are always written in digits.
WORD_TO_NUMBER = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
WORD_UNIT_COUNT_RE = re.compile(
    rf"\b({'|'.join(WORD_TO_NUMBER)})\b\s*(?:\w+[\s-]+){{0,3}}"
    rf"(?:apartments?|flats?|dwellings?|dwellinghouses?|houses?|homes?|units?)\b",
    re.I,
)


# A labeled "Total proposed units" summary field on the Application Form
# itself is a structurally different, more trustworthy source than any
# other number in the document set - it's the applicant's own explicit
# declaration of scheme size, not a number that happens to sit near a
# dwelling-word in free-text prose (which is everything UNIT_COUNT_PATTERNS
# otherwise matches, undifferentiated). Confirmed a real case (Tameside
# 25/00972/FUL): the Application Form stated "Total proposed residential
# units 102" while the Planning Statement separately discussed both a wider
# town-centre capacity ("up to 1000 new dwellings") and a brownfield-
# register site assessment ("assessed as suitable for 210 net apartments")
# - two DIFFERENT wrong numbers, from two different sentences, both of which
# individually looked exactly as legitimate as any other UNIT_COUNT_PATTERNS
# match and could recur in some other unanticipated phrasing again. Explicit
# "proposed" (in either word order) deliberately excludes the same form's
# adjacent "Total existing residential units" field, which describes what's
# being demolished, not what's being built.
STRUCTURED_TOTAL_RE = re.compile(
    r"total\s*(?:number\s*of\s*)?proposed\s*(?:residential\s*)?"
    r"(?:units|dwellings|apartments|houses|homes)\s*[:\-]?\s*(\d+)"
    r"|"
    r"total\s*(?:residential\s*)?(?:units|dwellings|apartments|houses|homes)\s*proposed\s*[:\-]?\s*(\d+)",
    re.I,
)


def extract_structured_total(text: str | None) -> int | None:
    """The single most trustworthy unit-count signal available, when
    present - see STRUCTURED_TOTAL_RE. Returns the first match; a real
    Application Form only ever states its own total once."""
    normalised = normalise_text(text)
    match = STRUCTURED_TOTAL_RE.search(normalised)
    if not match:
        return None
    value_str = match.group(1) or match.group(2)
    try:
        value = int(value_str.replace(",", ""))
    except (ValueError, TypeError):
        return None
    return value if 0 < value <= MAX_PLAUSIBLE_UNITS else None


def _is_policy_target_context(normalised: str, start: int, end: int) -> bool:
    window_start = max(0, start - POLICY_TARGET_CONTEXT_WINDOW)
    window_end = min(len(normalised), end + POLICY_TARGET_CONTEXT_WINDOW)
    return bool(POLICY_TARGET_CONTEXT_RE.search(normalised[window_start:window_end]))


def _is_reference_code(normalised: str, start: int) -> bool:
    """Drawing/document reference numbers ("21383-thp-u8-xx-dr-a-1021_p03")
    routinely sit in lists right before the word "unit" used as a plot/
    building LABEL ("Unit 8 office plans"), not a dwelling count - confirmed
    a real case: "...dr-a-1021_p03\\n- unit 8 roof plan..." read as "1021
    units". A genuine stated unit count is never written glued directly
    onto a preceding hyphen with no space - that formatting is
    characteristic of reference codes, not prose describing a scheme."""
    return start > 0 and normalised[start - 1] == "-"


def extract_unit_counts(text: str | None) -> list[int]:
    """All candidate unit counts found, not just the max - lets callers with
    a trusted reference figure (e.g. the portal-listing estimate) pick the
    closest candidate instead of blindly taking the largest number, which
    can latch onto an unrelated figure mentioned nearby for context (e.g. a
    much bigger wider-area allocation cited as background in a document)."""
    normalised = normalise_text(text)
    counts: list[int] = []

    for pattern in UNIT_COUNT_PATTERNS:
        for match in re.finditer(pattern, normalised):
            if _is_policy_target_context(normalised, match.start(), match.end()):
                continue
            if _is_reference_code(normalised, match.start()):
                continue
            try:
                value = int(match.group(1).replace(",", ""))
            except (ValueError, IndexError):
                continue
            if value in YEAR_LIKE_RANGE:
                continue
            if 0 < value <= MAX_PLAUSIBLE_UNITS:
                counts.append(value)

    for match in re.finditer(WORD_UNIT_COUNT_RE, normalised):
        if _is_policy_target_context(normalised, match.start(), match.end()):
            continue
        counts.append(WORD_TO_NUMBER[match.group(1).lower()])

    return counts


VARIATION_OF_OBLIGATION_RE = re.compile(
    r"(?:variation|modification|removal)\s+of\s+.{0,60}?"
    # Confirmed a real case ("Variation of the original Draft Section 106
    # Agreement between Trafford Borough Council and...") that the
    # obligation(s)-only pattern missed entirely - UK planning practice uses
    # "Section 106 Agreement" and "planning obligation(s)" near-
    # interchangeably for the same legal instrument, but only the latter was
    # covered. Scoped to "section 106/s106 ... agreement" specifically
    # (not a bare "agreement") to avoid over-matching unrelated legal terms.
    r"(?:obligations?|(?:section\s*106|s\.?\s*106)\s*(?:planning\s*)?agreement)\b",
    re.I,
)

# Boundary consultations: a neighbouring authority (e.g. Rossendale, which
# borders Bury) notifies Bury of an application under s.100/Article 18
# because the site sits near/across the boundary. The proposal text on
# OUR portal is only Bury's copy of the consultation notice - it does not
# carry the real application's documents (S106, viability, officer report),
# so any affordable-housing split our AI extraction derives from it is
# unreliable, not a genuine "0 affordable" answer. Confirmed a real case:
# "Article 18 consultation from Rossendale Borough Council (ref 2022/0451) -
# ...238 no. residential dwellings..." reconciled to a confident-looking
# "0 / 238" affordable split purely because no real supporting documents
# were available to extract from.
#
# Salford's register (Arcus-based, distinct from the Idox councils) phrases
# the exact same situation differently - confirmed real cases: "Consultation
# request from Manchester City Council for application no: 143164/FO/2025",
# "...from Tameside Metropolitan Borough Council for application no:
# 21/011...", "...from Trafford Council for Application No: 117953/OUT/25" -
# same underlying issue, just "consultation request from X for application
# no: Y" instead of "X consultation from Y (ref Z)". Both trigger phrasings
# and both reference-citation styles are matched here.
EXTERNAL_CONSULTATION_RE = re.compile(
    r"(?:(?:article\s*18|s\.?\s?100|section\s*100)\s*consultation\s*from|consultation\s*request\s*from)\s*"
    # Spelled-out "...Borough/City/Metropolitan Borough/District Council" OR
    # the same thing abbreviated ("MBC", "BC", "CC") - confirmed a real case
    # (Bury 72357: "Article 18 Consultation from Tameside MBC (ref
    # 21/01171/OUT)") where the spelled-out-only version silently failed to
    # match, since "MBC" never contains the literal word "council" at all.
    r"([A-Za-z][A-Za-z\s]*?(?:(?:borough|city|metropolitan\s*borough|district)?\s*council|M?BC|CC))"
    r"\s*(?:\(?ref\.?:?\s*|for\s+application\s*(?:no\.?|number)\s*:?\s*)([\w/.\-]+)\)?",
    re.I,
)


# "Continued use of THE property/a dwellinghouse as..." is a lawful-use /
# certificate-of-lawfulness-style question about ONE already-existing
# dwelling, not a development proposal - confirmed a real case: "Continued
# use of the property as a mixed use of a dwellinghouse (Use Class C3) and
# short term let accommodation (sui generis)" wrongly qualified because
# "dwellinghouse" contains "house"/"dwelling" as substrings, satisfying the
# residential-signal-word check the "mixed use" ambiguity guard requires -
# correct in the literal sense (it IS about a dwelling), but this is
# unambiguously a single unit by the grammar alone (singular "the
# property"/"a dwellinghouse"), never a 10+ unit scheme, regardless of what
# residential words appear nearby. Checked before any keyword-based category
# below so it can't be reached via a different path either.
SINGLE_DWELLING_CONTINUED_USE_RE = re.compile(
    r"continued use of (?:the|this|a|an) (?:property|dwelling|dwellinghouse|premises|house|flat|building)\b",
    re.I,
)

# A Screening/Scoping Opinion just asks the council whether an EIA is
# required for a future application - not itself a development proposal, and
# confirmed to typically have no applicant and no real documents on the
# portal (e.g. OTH/2025/1189: "Applicant" field blank, 4 files on the
# portal, 0 of them useful for extraction) despite its proposal text stating
# a real-looking unit count ("...residential development...c. 275
# dwellings...") that would otherwise cheerfully qualify it as a 275-unit
# scheme. These were previously kept in results (as an early pipeline
# signal, with affordable data marked not-yet-applicable) but confirmed real
# user feedback: they clutter results with schemes that have no actual
# application behind them yet, and should be dropped entirely like any other
# non-substantive filing - the real application, if/when submitted, gets
# scraped and qualified in its own right.
SCREENING_OR_SCOPING_OPINION_RE = re.compile(r"\b(?:eia\s*)?(?:screening|scoping)\s*opinion\b", re.I)


def _is_trailing_parenthetical_mention(text: str, match: re.Match) -> bool:
    """True when the screening/scoping phrase sits inside a closing
    parenthetical annotation at/near the end of an otherwise-complete
    sentence (e.g. "...biodiversity net gain (Environmental Impact
    Assessment Screening Opinion Request)") rather than being the actual
    subject of the proposal. Confirmed two real cases (Stockport DC/097770,
    DC/097614) where a genuine "Residential development for up to 250/195
    dwellings..." application merely noted, in parens, that it was
    accompanied by a screening opinion request - excluding these entirely
    (as the many genuine screening-only requests should be) would have
    dropped two real qualifying schemes."""
    open_paren = text.rfind("(", 0, match.start())
    if open_paren == -1:
        return False
    close_paren = text.find(")", match.end())
    if close_paren == -1:
        return False
    # The nearest "(" before the match must be the one actually wrapping
    # it - if that segment already contains a ")" (or a nested "("), the
    # match sits outside/after that unrelated parenthetical (e.g. "(EIA)
    # Screening Opinion" - a regulatory-citation aside, not the wrapper).
    between = text[open_paren + 1:match.start()]
    if ")" in between or "(" in between:
        return False
    trailing = text[close_paren + 1:].strip()
    return len(trailing) < 20


def extract_external_consultation(proposal: str | None) -> tuple[str, str] | None:
    """Returns (council_name, reference) if the proposal text is a
    cross-authority consultation notice citing another council's own
    application, else None."""
    match = EXTERNAL_CONSULTATION_RE.search(str(proposal or ""))
    if not match:
        return None
    return match.group(1).strip().title(), match.group(2).strip()


def classify_application_category(proposal: str | None) -> str:
    proposal_norm = normalise_text(proposal)

    if EXTERNAL_CONSULTATION_RE.search(str(proposal or "")):
        return "external_consultation"

    screening_match = SCREENING_OR_SCOPING_OPINION_RE.search(str(proposal or ""))
    if screening_match and not _is_trailing_parenthetical_mention(str(proposal or ""), screening_match):
        return "screening_or_scoping_opinion"

    if SINGLE_DWELLING_CONTINUED_USE_RE.search(str(proposal or "")):
        return "non_target_admin_or_minor"

    # Checked here, before any residential/specialist-housing keyword match
    # below - a Certificate of Lawfulness confirms an EXISTING use/structure
    # is lawful, it is never itself a new development proposal, regardless
    # of what else the proposal text mentions. Confirmed a real case:
    # "Application for a lawful development certificate for proposed use of
    # a single dwelling...as supported living accommodation for 6
    # occupants" matched "supported living" first (a REVIEW_KEYWORDS hit)
    # since this check previously sat at the very end of this function,
    # wrongly qualifying a single-property use-class question as a possible
    # 10+ unit scheme.
    if "lawful development certificate" in proposal_norm:
        return "non_target_admin_or_minor"

    if any(x in proposal_norm for x in [
        "variation of condition", "vary condition",
        "minor material amendment", "non-material amendment", "non material amendment",
        # Wigan's own term for what's otherwise a standard non-material
        # amendment (confirmed real case, reference suffix "/NMAS" -
        # Non-Material Amendment Standard - on a "Working Amendment
        # Application" with no other matching phrase in its text).
        "working amendment",
        # A Deed of Variation modifies an existing S106/planning obligation's
        # legal terms - not a new development proposal. Confirmed a real
        # case where this qualified purely because its own text described
        # the ORIGINAL scheme being varied (e.g. "...relating to the
        # erection of 150 dwellings..."), which reads exactly like a
        # genuine new-build proposal to the residential-keyword checks
        # below unless caught here first. Checked as a direct phrase rather
        # than folded into VARIATION_OF_OBLIGATION_RE below since "deed of
        # variation" doesn't reliably appear near the word "obligation"
        # within that regex's window.
        "deed of variation",
    ]):
        return "variation_or_amendment"

    # "Variation of S106 Agreement Obligations..." - the portal's own
    # Application Type field (checked by is_administrative_application_type
    # further downstream, once further-info details are available) is the
    # authoritative signal for this, but proposal text alone should already
    # catch it too - confirmed a real case where this exact phrasing had no
    # Application Type field available at all (a recovered historical scrape
    # that predates that field being captured), and slipped through here via
    # the "s106"/"section 106" REVIEW_KEYWORDS fallback instead.
    if VARIATION_OF_OBLIGATION_RE.search(proposal_norm):
        return "variation_or_amendment"

    if any(x in proposal_norm for x in [
        "discharge of condition", "approval of details",
        "pursuant to condition", "condition attached",
        # "Condition discharge application to discharge condition(s) N" -
        # confirmed real, common phrasing (Wigan: 10+ real applications in
        # one site's history alone) that "discharge of condition" above
        # doesn't catch - reversed word order ("condition discharge" not
        # "discharge of condition") and no "of" before "condition(s)".
        # Without this, these were silently classified "unknown" - not
        # excluded, just invisible to the portal-native "has construction
        # actually started" progress-signal check (see
        # lapse_tracking.PROGRESS_SIGNAL_CATEGORIES), understating real,
        # substantial site activity as "lapsed" instead of "underway".
        "condition discharge", "discharge condition",
    ]):
        return "condition_discharge_or_details"

    if "reserved matters" in proposal_norm:
        return "reserved_matters"

    if any(x in proposal_norm for x in ["outline application", "outline planning", "outline permission"]):
        return "outline_application"

    if any(x in proposal_norm for x in ["build to rent", "btr"]):
        return "build_to_rent"

    if any(x in proposal_norm for x in ["affordable housing", "social housing", "extra care", "supported living"]):
        return "affordable_or_specialist_housing"

    if any(x in proposal_norm for x in ["mixed use", "mixed-use", "commercial and residential"]):
        return "mixed_use"

    if any(x in proposal_norm for x in [
        "residential development", "erection", "construction",
        "dwellings", "apartments", "flats", "homes", "houses",
    ]):
        return "primary_residential"

    if any(x in proposal_norm for x in [
        "lawful development certificate", "prior approval", "advertisement consent",
        "tree works", "telecommunications", "fire station", "mosque", "islamic centre",
    ]):
        return "non_target_admin_or_minor"

    return "unknown"


@dataclass
class QualificationResult:
    unit_count: int | None
    category: str
    classification: str
    qualifies: bool


# The portal's own "Application Type" field (only available after fetching
# Further Information - see idox_portal.fetch_application_detail) is a far
# more reliable signal than keyword-matching free-text proposals: confirmed
# a "Variation of S106 Agreement Obligations" application slipped through
# purely because its proposal text contains "S106", which is a
# REVIEW_KEYWORDS hit regardless of what the application actually is. These
# Application Type values mean "this is not a new development proposal" -
# it's a legal/administrative modification of an existing permission -
# regardless of what the free-text proposal happens to mention.
ADMINISTRATIVE_APPLICATION_TYPES = [
    "modification of obligation", "variation of obligation", "deed of variation",
    "discharge of condition", "variation of condition", "removal of condition",
    "non-material amendment", "non material amendment", "confirmation of compliance",
    "certificate of lawfulness", "approval of details", "section 73", "s73",
    # Salford's portal exposes this as a structured Application Type value
    # (distinct from the proposal-text-based EXTERNAL_CONSULTATION_RE match,
    # which already catches the same thing via wording - this is a backup
    # signal via the portal's own field, for phrasing variants the regex
    # doesn't happen to cover).
    "adjoining authority consultation",
    # Backup structured-field signal for SCREENING_OR_SCOPING_OPINION_RE
    # (e.g. Idox's own "Application type: Screening Opinion" field) -
    # catches any screening/scoping request whose proposal text phrasing the
    # regex doesn't happen to cover.
    "screening opinion", "scoping opinion",
]


def is_administrative_application_type(application_type: str | None) -> bool:
    normalised = str(application_type or "").lower()
    return any(kw in normalised for kw in ADMINISTRATIVE_APPLICATION_TYPES)


def qualify(proposal: str | None, unit_threshold: int = 10) -> QualificationResult:
    proposal_norm = normalise_text(proposal)
    unit_count = extract_unit_count(proposal)
    category = classify_application_category(proposal)

    if category in EXCLUDE_CATEGORIES:
        return QualificationResult(unit_count, category, "Excluded - secondary/admin", False)

    if is_non_residential(proposal_norm):
        return QualificationResult(unit_count, category, "Excluded - non-residential", False)

    if unit_count is not None and unit_count < unit_threshold:
        return QualificationResult(unit_count, category, f"Ignore - under {unit_threshold} units", False)

    if unit_count is not None and unit_count >= unit_threshold:
        return QualificationResult(unit_count, category, f"Confirmed - {unit_threshold}+ units", True)

    matched_review_keywords = [kw for kw in REVIEW_KEYWORDS if kw in proposal_norm]
    if matched_review_keywords:
        has_residential_signal = _has_residential_signal(proposal_norm)
        has_unambiguous_match = any(kw not in AMBIGUOUS_REVIEW_KEYWORDS for kw in matched_review_keywords)
        if has_unambiguous_match or has_residential_signal:
            if unit_count is None and (
                SINGLE_UNIT_MIXED_USE_RE.search(proposal_norm)
                or SINGLE_RESIDENTIAL_UNIT_ADDITION_RE.search(proposal_norm)
            ):
                return QualificationResult(unit_count, category, "Excluded - likely single-unit change of use", False)
            return QualificationResult(unit_count, category, f"Review - possible {unit_threshold}+ housing", True)

    return QualificationResult(unit_count, category, "Ignore", False)
