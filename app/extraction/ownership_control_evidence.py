"""Stage 4B - deterministic ownership/control evidence extraction (Sections
3-4 of the Stage 4B task).

READ ONLY / PURE FUNCTIONS. Nothing in this module writes to the database
or calls OpenAI/Companies House/Land Registry/any external service - it
only ever reads Document.extracted_text already held in the corpus and
returns plain dataclasses. Persistence (via app.enrichment.
control_entities.create_control_relationship_if_absent) is a separate,
explicit step a caller opts into - mirrors Stage 2C's own "READ ONLY"
discipline (app.policy.allocation_document_evidence) exactly.

TWO independent deterministic sources, kept in two functions rather than
one combined pass since they operate on different document types and have
completely different regex vocabularies:

1. detect_ownership_certificate() - application_form documents. Targets
   the "Ownership Certificates and Agricultural Land Declaration"
   (Article 14, Town and Country Planning (Development Management
   Procedure) (England) Order 2015) section every full/outline
   application form carries.

2. extract_s106_control_evidence() - s106 documents. Targets defined-role
   clauses ("... ABC Limited ... (the "Owner")" / '"the Developer" means
   ...') and Land Registry title numbers.

CERTIFICATE DETECTION SAFETY (Stage 4B Section 3's own explicit
instruction): the word "Certificate A" (or B/C/D) appears in EVERY
application form's boilerplate question ("Please answer the following
questions to determine which Certificate of Ownership you need to
complete: A, B, C or D") regardless of which certificate was actually
selected - Stage 4A confirmed this exact sentence is present in the large
majority of the 444 forms that mention certificates at all. Classifying a
form as CERTIFICATE_A purely because "Certificate A" occurs anywhere in
its text would therefore be almost meaningless - it would fire on nearly
every form. This module instead requires a certificate LETTER to appear
in close proximity to an actual first-person CERTIFICATION verb ("I
certify", "hereby certify", "the applicant certifies", ...) - the
generated PDF's own declaration text, which (per the standard 1APP portal
behaviour) only ever includes the ONE certificate's full legal wording
that was actually completed, not all four - and explicitly EXCLUDES any
letter occurring inside the known boilerplate question sentence before
even attempting that proximity check. If more than one letter is
confidently matched (OCR noise, or a genuinely unusual document), or the
certificate section exists but no letter can be confidently resolved at
all, the result is CERTIFICATE_UNKNOWN, never a guessed letter - "fail
closed" per the task's own explicit instruction.

S106 DEFINED-ROLE SAFETY: only a clause that itself DEFINES a role
("(2) ABC Limited ... (the "Owner")" or '"the Owner" means ABC Limited')
is treated as evidence - a bare LATER reference like "successors in title
to the Owner" or "the Owner shall pay..." never creates a NEW party
attribution on its own (it presupposes a definition established
elsewhere, which this module either already captured from the SAME
document's own defining clause, or has not - it never guesses)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.db.models import Document

# --- Certificate detection --------------------------------------------------

CERTIFICATE_A = "CERTIFICATE_A"
CERTIFICATE_B = "CERTIFICATE_B"
CERTIFICATE_C = "CERTIFICATE_C"
CERTIFICATE_D = "CERTIFICATE_D"
CERTIFICATE_UNKNOWN = "CERTIFICATE_UNKNOWN"
NO_CERTIFICATE_EVIDENCE = "NO_CERTIFICATE_EVIDENCE"

_CERT_SECTION_MARKER_RE = re.compile(
    r"ownership certificates? and agricultural land declaration|certificate of ownership|certificates? under article 1[24]",
    re.IGNORECASE,
)
# The known boilerplate QUESTION sentence every 1APP form carries -
# excluded from letter-proximity scanning so it can never itself supply a
# positive match (Stage 4A confirmed this exact wording verbatim in real
# production forms).
_CERT_BOILERPLATE_QUESTION_RE = re.compile(
    r"please answer the following questions? to determine which certificate of ownership you need to complete:?\s*a,?\s*b,?\s*c\s*or\s*d\.?",
    re.IGNORECASE,
)
_CERT_LETTER_RE = re.compile(r"\bcertificate\s+([abcd])\b", re.IGNORECASE)
_CERTIFY_PHRASES = (
    "i certify", "certify that", "hereby certify", "the applicant certifies",
    "we certify", "this is to certify", "i/we certify",
)
_CERT_PROXIMITY_CHARS = 300
_CERT_SNIPPET_RADIUS = 150


@dataclass
class CertificateDetectionResult:
    document_id: int
    application_id: int
    certificate_type: str  # CERTIFICATE_A/B/C/D | CERTIFICATE_UNKNOWN | NO_CERTIFICATE_EVIDENCE
    confidence: str | None  # high | None (None for UNKNOWN/NO_EVIDENCE)
    snippet: str | None
    method: str = "deterministic_regex"


def _excluded_spans(text_low: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _CERT_BOILERPLATE_QUESTION_RE.finditer(text_low)]


def _in_excluded_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def detect_ownership_certificate(document: Document) -> CertificateDetectionResult | None:
    """Pure function - no Session, no I/O. Returns None only when the
    document has no usable extracted_text at all (nothing to classify,
    distinct from NO_CERTIFICATE_EVIDENCE which means "usable text
    found, but no certificate section present in it")."""
    if not document.extracted_text or not document.extracted_text.strip():
        return None

    text = document.extracted_text
    text_low = text.lower()

    if not _CERT_SECTION_MARKER_RE.search(text_low):
        return CertificateDetectionResult(
            document_id=document.id, application_id=document.application_id,
            certificate_type=NO_CERTIFICATE_EVIDENCE, confidence=None, snippet=None,
        )

    excluded = _excluded_spans(text_low)
    confident_hits: dict[str, str] = {}  # letter -> snippet
    for m in _CERT_LETTER_RE.finditer(text_low):
        if _in_excluded_span(m.start(), excluded):
            continue
        window_start = max(0, m.start() - _CERT_PROXIMITY_CHARS)
        window_end = min(len(text_low), m.end() + _CERT_PROXIMITY_CHARS)
        window = text_low[window_start:window_end]
        if any(phrase in window for phrase in _CERTIFY_PHRASES):
            letter = m.group(1).upper()
            if letter not in confident_hits:
                snip_start = max(0, m.start() - _CERT_SNIPPET_RADIUS)
                snip_end = min(len(text), m.end() + _CERT_SNIPPET_RADIUS)
                confident_hits[letter] = text[snip_start:snip_end].strip()

    if len(confident_hits) == 1:
        (letter, snippet), = confident_hits.items()
        return CertificateDetectionResult(
            document_id=document.id, application_id=document.application_id,
            certificate_type=f"CERTIFICATE_{letter}", confidence="high", snippet=snippet,
        )

    # Zero confident letters (section exists but selection undetermined)
    # or more than one (ambiguous/conflicting) - both fail closed.
    any_snippet = next(iter(confident_hits.values()), None)
    return CertificateDetectionResult(
        document_id=document.id, application_id=document.application_id,
        certificate_type=CERTIFICATE_UNKNOWN, confidence=None, snippet=any_snippet,
    )


# --- S106 deterministic legal evidence --------------------------------------

S106_DEFINED_OWNER = "S106_DEFINED_OWNER"
S106_DEFINED_DEVELOPER = "S106_DEFINED_DEVELOPER"
S106_DEFINED_MORTGAGEE = "S106_DEFINED_MORTGAGEE"

_ROLE_TERMS = {"Owner": "OWNER", "Developer": "DEVELOPER", "Mortgagee": "MORTGAGEE"}
_ROLE_EVIDENCE_CATEGORY = {
    "OWNER": S106_DEFINED_OWNER, "DEVELOPER": S106_DEFINED_DEVELOPER, "MORTGAGEE": S106_DEFINED_MORTGAGEE,
}

# A name-like token: starts with a capital letter, allows the usual
# company-name punctuation, 2-80 chars - deliberately loose on its own,
# only ever accepted when adjacent to a defining clause (see below), never
# used to scan free prose in isolation.
_NAME_TOKEN = r"[A-Z][A-Za-z0-9&,\.\'\-\s]{2,80}?"

# Pattern A: recital style - "NAME ... (the "Owner")" - the defined term's
# own parenthetical wrapper is found FIRST, then the name is searched for
# BACKWARD from it. Real S106 recitals routinely separate the name from
# its defined term with a lengthy "(company number ...) whose registered
# office is at ..." clause (confirmed in real production S106 text during
# Stage 4A), so requiring tight regex adjacency between name and term (as
# a single combined pattern would) misses almost every real recital - a
# two-step "find the term, then look backward for the nearest genuine
# name" is used instead.
#
# SAFETY (found via real production text, not merely anticipated):
# requiring only "the last Title Case run before the term" is NOT safe -
# confirmed two real false positives during development: (1) a
# registered-office ADDRESS ("Petersgate, Stockport, England, SK1 1AR")
# being picked over the actual company name further back, and (2) the
# literal phrase "Company number 12851676" being picked because "Company"
# alone was (wrongly) in the organisation-indicator list. Both are fixed
# by (a) requiring a STRONG, specific legal-entity suffix - Limited/Ltd/
# LLP/PLC/Council only, deliberately excluding the bare word "Company" -
# and (b) DROPPING the earlier "fall back to any multi-word Title Case
# run" behaviour entirely: if no strong-suffix candidate is found in the
# backward window, this pattern reports NOTHING rather than guessing at
# an address or a person's name. This intentionally narrows Pattern A to
# organisation-named parties only (never a private individual) - a
# reliable individual-name detector was judged too failure-prone for a
# deterministic regex pass; see this module's own report notes for the
# resulting Stage 4C bounded-AI recommendation.
_DEFINING_PARENTHETICAL_RE = re.compile(
    r"[\(‘’“”\"']{1,2}\s*(?:the\s+)?(?P<role>Owner|Developer|Mortgagee)\s*[\)‘’“”\"']{1,2}",
)
# A candidate name-phrase: a run of capitalised/numeric tokens, allowing
# only a small set of lowercase joiner words (of/and/&) - deliberately
# stops at the FIRST unrelated lowercase word (e.g. "whose", "at",
# "registered") rather than greedily spanning into a following prose
# clause or address, which is exactly how a real S106 recital separates a
# company name from its "whose registered office is at ..." clause.
_NAME_CANDIDATE_RE = re.compile(
    r"[A-Z][\w&'\-]*(?:\s+(?:[A-Z][\w&'\-]*|\d[\w&'\-]*|of|and|&))*",
)
_STRONG_ORG_SUFFIX_RE = re.compile(r"\b(Limited|Ltd|LLP|PLC|Council)\b", re.IGNORECASE)
_COMPANY_NUMBER_PHRASE_RE = re.compile(r"^company\s+number\s+\d+$", re.IGNORECASE)
_RECITAL_BACKWARD_WINDOW_CHARS = 250

# Pattern B: definitions-schedule style - '"the Owner" means NAME' /
# '"Owner" means NAME'. Same strong-suffix requirement as Pattern A
# (applied after capture, below) - a description like '"the Owner" means
# the person(s) named in Schedule 1' must never be reported as if
# "the person(s) named in Schedule 1" were itself a party's name.
_TERM_MEANS_NAME_RE = re.compile(
    r"[‘’“”\"']?(?:the\s+)?(?P<role>Owner|Developer|Mortgagee)[‘’“”\"']?\s+means\s+(?P<name>" + _NAME_TOKEN + r")[.,;]",
)

_TITLE_NUMBER_RE = re.compile(r"title\s+number\s+([A-Za-z]{0,3}\d{3,8})", re.IGNORECASE)
_S106_SNIPPET_RADIUS = 150


def _truncate_at_org_suffix(name: str) -> str:
    """Stage 4B final amendment ("S106 Entity-Name Cleanliness"): a
    legal-entity suffix (Limited/Ltd/LLP/PLC/Council) is, as a matter of
    real UK naming convention, always the FINAL word of the entity's own
    name - nothing legitimate follows it within the same name (a company
    is never called "ABC Limited Something Else"; "X Borough Council" is
    likewise always terminal). A real S106 recital routinely continues
    PAST that point into a "whose registered office is at ..." or "of
    <address>" clause that this module's own candidate regex (which
    allows " of "/" and " as name-continuation joiners, so it doesn't
    truncate at ordinary connecting words within a genuine longer name)
    can otherwise capture as if it were still part of the name - the real
    production example found during Stage 4B development: "WIGAN BOROUGH
    COUNCIL of Town Hall Library Street Wigan WN1 1YN". Truncating at the
    END of the suffix word itself is a safe, narrow, high-confidence fix
    - it never changes a name that doesn't already contain one of these
    specific suffix words, and it never removes anything BEFORE the
    suffix (an ordinary word earlier in a legitimate name, e.g. "Trafford
    Housing Trust Limited", is untouched since the suffix there already
    IS the last word)."""
    m = _STRONG_ORG_SUFFIX_RE.search(name)
    if m is None:
        return name
    return name[:m.end()]


@dataclass
class S106PartyEvidenceHit:
    document_id: int
    application_id: int
    role: str  # OWNER | DEVELOPER | MORTGAGEE
    evidence_category: str
    entity_name_raw: str
    snippet: str
    method: str = "deterministic_regex"


@dataclass
class S106TitleNumberHit:
    document_id: int
    application_id: int
    title_number: str
    snippet: str


def _clean_name(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip(" \t\n\r.,;:-")


def extract_s106_defined_parties(document: Document) -> list[S106PartyEvidenceHit]:
    """Pure function - no Session, no I/O. Only ever returns a hit for a
    name found INSIDE a genuine defining clause (recital or definitions-
    schedule shape) - a bare later reference such as 'successors in title
    to the Owner' matches neither pattern and is therefore never
    reported, by construction (Stage 4B Section 4's own explicit
    example)."""
    if not document.extracted_text or not document.extracted_text.strip():
        return []
    text = document.extracted_text
    hits: list[S106PartyEvidenceHit] = []
    seen: set[tuple[str, str]] = set()

    for m in _DEFINING_PARENTHETICAL_RE.finditer(text):
        role_term = m.group("role")
        role = _ROLE_TERMS.get(role_term.capitalize())
        if role is None:
            continue

        window_start = max(0, m.start() - _RECITAL_BACKWARD_WINDOW_CHARS)
        preceding = text[window_start:m.start()]
        # Trim to after the last clause boundary so a name-like run from
        # an EARLIER, unrelated sentence/party is never picked up.
        boundary = max(preceding.rfind("."), preceding.rfind(";"), preceding.rfind("\n"))
        if boundary != -1:
            preceding = preceding[boundary + 1:]

        candidates = [c.group(0) for c in _NAME_CANDIDATE_RE.finditer(preceding)]
        org_candidates = [
            c for c in candidates
            if _STRONG_ORG_SUFFIX_RE.search(c) and not _COMPANY_NUMBER_PHRASE_RE.match(c.strip())
        ]
        if not org_candidates:
            continue  # no confident organisation name found - report nothing, never guess
        # Isolate the entity from any trailing "of <address>"/registered-
        # office clause the candidate regex's own "of"/"and" joiners can
        # otherwise sweep in (see _truncate_at_org_suffix's own docstring
        # for the real production example this fixes).
        name = _clean_name(_truncate_at_org_suffix(org_candidates[-1]))
        # A bare suffix word alone ("Limited", "Council") is a truncated
        # match, not a usable name - reject rather than report a
        # meaningless single-word "company name" (found against real
        # production text, where the clause-boundary trim occasionally
        # lands immediately before the suffix word itself).
        if len(name) < 4 or len(name.split()) < 2:
            continue

        key = (role, name.lower())
        if key in seen:
            continue
        seen.add(key)
        start = max(0, m.start() - _S106_SNIPPET_RADIUS)
        end = min(len(text), m.end() + _S106_SNIPPET_RADIUS)
        hits.append(S106PartyEvidenceHit(
            document_id=document.id, application_id=document.application_id, role=role,
            evidence_category=_ROLE_EVIDENCE_CATEGORY[role], entity_name_raw=name,
            snippet=text[start:end].strip(),
        ))

    for m in _TERM_MEANS_NAME_RE.finditer(text):
        role_term = m.group("role")
        role = _ROLE_TERMS.get(role_term.capitalize())
        raw_name = _clean_name(m.group("name"))
        if not _STRONG_ORG_SUFFIX_RE.search(raw_name) or _COMPANY_NUMBER_PHRASE_RE.match(raw_name):
            continue  # same "never guess an individual/description as a name" rule as Pattern A
        # Same trailing-address isolation as Pattern A - a "means" clause
        # can equally continue into "... Limited of 2 Park Road, ..."
        # before its terminating punctuation.
        name = _clean_name(_truncate_at_org_suffix(raw_name))
        if role is None or len(name) < 4 or len(name.split()) < 2:
            continue
        key = (role, name.lower())
        if key in seen:
            continue
        seen.add(key)
        start = max(0, m.start() - _S106_SNIPPET_RADIUS)
        end = min(len(text), m.end() + _S106_SNIPPET_RADIUS)
        hits.append(S106PartyEvidenceHit(
            document_id=document.id, application_id=document.application_id, role=role,
            evidence_category=_ROLE_EVIDENCE_CATEGORY[role], entity_name_raw=name,
            snippet=text[start:end].strip(),
        ))

    return hits


def extract_s106_title_numbers(document: Document) -> list[S106TitleNumberHit]:
    """Pure function - no Session, no I/O."""
    if not document.extracted_text or not document.extracted_text.strip():
        return []
    text = document.extracted_text
    hits: list[S106TitleNumberHit] = []
    seen: set[str] = set()
    for m in _TITLE_NUMBER_RE.finditer(text):
        title_number = m.group(1).upper()
        if title_number in seen:
            continue
        seen.add(title_number)
        start = max(0, m.start() - _S106_SNIPPET_RADIUS)
        end = min(len(text), m.end() + _S106_SNIPPET_RADIUS)
        hits.append(S106TitleNumberHit(
            document_id=document.id, application_id=document.application_id,
            title_number=title_number, snippet=text[start:end].strip(),
        ))
    return hits
