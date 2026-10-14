"""Pure discovery accounting; no source access, persistence, models or ranking.

Source-specific qualification is supplied by reviewed adapters, never inferred
from HTTP success. This module cannot authorise a source or production writes.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import math
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

from app.scrapers.unit_filter import qualify

RULE_VERSION = 'stage4-discovery-v1'
COUNCILS = frozenset({'bolton', 'bury', 'manchester', 'oldham', 'rochdale',
                     'salford', 'stockport', 'tameside', 'wigan'})
# These are destination restrictions, NOT evidence that enumeration is qualified.
SOURCE_ROOTS = {
    'bolton': ('paplanning.bolton.gov.uk', '/online-applications/'),
    'bury': ('planning.bury.gov.uk', '/online-applications/'),
    'oldham': ('planningpa.oldham.gov.uk', '/online-applications/'),
    'stockport': ('planning.stockport.gov.uk', '/PlanningData-live/'),
    'tameside': ('publicaccess.tameside.gov.uk', '/online-applications/'),
    'wigan': ('planning.wigan.gov.uk', '/online-applications/'),
    'manchester': ('arcusbe.manchester.gov.uk', '/pr/'),
    'rochdale': ('account.rochdale.gov.uk', '/pr/'),
    'salford': ('salfordcitycouncil.my.site.com', '/pr/'),
}
DISCOVERY_FIELDS = frozenset({'proposal', 'address', 'application_type',
    'received_date', 'validated_date', 'publication_date', 'units', 'bedspaces',
    'unit_metric', 'unit_scope', 'status', 'decision', 'decision_date',
    'parent_reference', 'related_reference'})
FIELD_STATES = frozenset({'PRESENT_VALUE', 'PRESENT_BLANK', 'NOT_PRESENT',
                         'CONFLICTING', 'UNPARSEABLE', 'UNKNOWN'})

COMMITTEE_ORIGINS = {
    'bolton': 'bolton.moderngov.co.uk',
    'bury': 'councildecisions.bury.gov.uk',
    'manchester': 'democracy.manchester.gov.uk',
    'oldham': 'committees.oldham.gov.uk',
    'rochdale': 'democracy.rochdale.gov.uk',
    'salford': 'sccdemocracy.salford.gov.uk',
    'tameside': 'tameside.moderngov.co.uk',
    'wigan': 'wigan.moderngov.co.uk',
}


@dataclass(frozen=True)
class ExactTriggerEvidence:
    """Qualified official trigger, independent of date-window enumeration.

    Reviewed callers must acquire both trigger and portal evidence. This value
    grants no execution authority and must never advance a coverage watermark.
    """
    council: str
    reference: str
    source_url: str
    displayed_references: tuple[str, ...]
    body_sha256: str

    def __post_init__(self):
        import re
        u = urlsplit(self.source_url)
        if (self.council not in COMMITTEE_ORIGINS or u.scheme != 'https'
                or u.hostname != COMMITTEE_ORIGINS[self.council]
                or u.port not in (None, 443) or u.username or u.password
                or u.fragment or len(self.source_url) > 2048
                or not (u.path.startswith('/documents/')
                        or u.path == '/ieListDocuments.aspx')
                or re.search(r'[\s\\]', self.source_url)
                or any(p in {'.', '..'} for p in u.path.split('/'))):
            raise ValueError('trigger destination')
        if (account_identity(self.council, self.displayed_references, frozenset())[1]
                != self.reference or not re.fullmatch('[0-9a-f]{64}', self.body_sha256)):
            raise ValueError('trigger identity/provenance')

    def audit(self):
        return {'mode': 'EXACT_TRIGGER', 'council': self.council,
                'reference': self.reference, 'source': self.source_url,
                'sha256': self.body_sha256, 'enumeration_complete': False,
                'coverage_watermark_advanced': False}


class Completeness(str, Enum):
    COMPLETE = 'COMPLETE'
    INCOMPLETE = 'INCOMPLETE'
    FAILED = 'FAILED'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True)
class Literal:
    state: str
    value: str | None
    locator: str

    def __post_init__(self):
        if self.state not in FIELD_STATES or not self.locator or len(self.locator) > 256:
            raise ValueError('field state/provenance')
        if self.value is not None and (not isinstance(self.value, str) or len(self.value) > 8192):
            raise ValueError('field value bound')
        if self.state == 'PRESENT_VALUE':
            if not isinstance(self.value, str) or not self.value.strip():
                raise ValueError('missing literal value')
        elif self.state == 'PRESENT_BLANK':
            if self.value is not None and (not isinstance(self.value, str) or self.value.strip()):
                raise ValueError('nonblank blank')
        elif self.value is not None:
            raise ValueError('unqualified value')


@dataclass(frozen=True)
class WindowEvidence:
    council: str
    run_id: str
    requested_start: date
    requested_end: date
    applied_start: date | None
    applied_end: date | None
    date_semantics: str
    source_contract: str | None
    applied_evidence: str | None
    terminal_evidence: str | None
    pages: int
    unique_references: int
    requests: int
    observed_bytes: int | None
    elapsed_seconds: float
    explicit_zero: bool = False
    capped: bool = False
    failure: str | None = None
    accounting_complete: bool = True

    def __post_init__(self):
        if self.council not in COUNCILS or not self.run_id:
            raise ValueError('council/run not admitted')
        if self.requested_end < self.requested_start:
            raise ValueError('inverted interval')
        if self.date_semantics not in {'RECEIVED', 'VALIDATED', 'PUBLICATION'}:
            raise ValueError('date semantics')
        if any(type(n) is not int or n < 0 for n in
               (self.pages, self.unique_references, self.requests)):
            raise ValueError('invalid accounting')
        if self.observed_bytes is not None and (type(self.observed_bytes) is not int or self.observed_bytes < 0):
            raise ValueError('invalid bytes')
        if not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError('invalid duration')
        if self.explicit_zero and self.unique_references:
            raise ValueError('zero/result conflict')

    @property
    def outcome(self):
        if self.failure:
            return Completeness.INCOMPLETE if self.pages else Completeness.FAILED
        if self.capped or not self.accounting_complete:
            return Completeness.INCOMPLETE
        if not (self.source_contract and self.applied_evidence and self.date_semantics):
            return Completeness.UNKNOWN
        if (self.applied_start, self.applied_end) != (self.requested_start, self.requested_end):
            return Completeness.UNKNOWN
        if not self.terminal_evidence or not self.pages or not self.requests:
            return Completeness.INCOMPLETE
        if not self.unique_references and not self.explicit_zero:
            return Completeness.UNKNOWN
        return Completeness.COMPLETE


def completed_through(previous: date, windows: list[WindowEvidence], *, council: str,
                      date_semantics: str) -> date:
    """Advance across contiguous COMPLETE intervals; never leap over a gap."""
    cursor = previous
    for w in sorted(windows, key=lambda w: w.requested_start):
        if w.council != council or w.date_semantics != date_semantics:
            raise ValueError('mixed coverage ledger')
        if w.outcome == Completeness.COMPLETE and w.requested_start <= cursor + timedelta(days=1):
            cursor = max(cursor, w.requested_end)
    return cursor


def candidate_materiality(proposal: Literal, *, threshold: int = 10) -> dict:
    """Existing qualification is evidence, never a hard discovery exclusion.

    A relationship may be unknown even for a small/admin proposal. Without
    qualified relationship exclusion evidence retain it for qualification.
    This intentionally conservative first version makes no confident exclusions.
    """
    if proposal.state != 'PRESENT_VALUE':
        return {'outcome': 'POTENTIALLY_MATERIAL', 'reason': proposal.state,
                'rule_version': RULE_VERSION, 'qualification': None}
    q = qualify(proposal.value, threshold)
    # Existing unit extractor can represent non-residential units/bedspaces.
    # Do not upgrade to confirmed residential materiality here.
    return {'outcome': 'POTENTIALLY_MATERIAL',
            'reason': 'QUALIFICATION_REQUIRED' if q.qualifies else 'RELATIONSHIP_OR_MATERIALITY_UNRESOLVED',
            'rule_version': RULE_VERSION, 'qualification': q.classification}


def account_identity(council: str, displayed_references: tuple[str, ...],
                     known: frozenset[tuple[str, str]]) -> tuple[str, str | None]:
    if council not in COUNCILS:
        raise ValueError('council not admitted')
    if not displayed_references or any(not isinstance(r, str) or not r.strip() for r in displayed_references):
        return 'WITHHELD_INSUFFICIENT_IDENTITY', None
    # No case/punctuation normalization that might collapse distinct identities.
    refs = set(displayed_references)
    if len(refs) != 1:
        return 'WITHHELD_CONFLICT', None
    ref = next(iter(refs))
    if len(ref) > 100 or ref != ref.strip() or any(ord(c) < 32 for c in ref):
        return 'WITHHELD_INSUFFICIENT_IDENTITY', None
    return ('ALREADY_KNOWN' if (council, ref) in known else 'NEW_CANDIDATE'), ref


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def prospective_calendar(frozen_at: datetime) -> dict:
    if frozen_at.tzinfo is None:
        raise ValueError('aware freeze required')
    local = frozen_at.astimezone(ZoneInfo('Europe/London')).date()
    first = local + timedelta(days=7 - local.weekday())
    return {'timezone': 'Europe/London', 'week_one': (first, first + timedelta(days=6)),
            'week_two': (first + timedelta(days=7), first + timedelta(days=13)),
            'backfill_audit_not_before': first + timedelta(days=21)}


def latency_seconds(discovered_at: datetime, published_at: datetime | None):
    if published_at is None:
        return None
    if discovered_at.tzinfo is None or published_at.tzinfo is None:
        raise ValueError('invalid publication clock')
    discovered_utc = discovered_at.astimezone(timezone.utc)
    published_utc = published_at.astimezone(timezone.utc)
    if published_utc > discovered_utc:
        raise ValueError('invalid publication clock')
    return (discovered_utc - published_utc).total_seconds()


@dataclass(frozen=True)
class DiscoveryEnvelope:
    """Reviewed adapter output; not a user-controlled production command."""
    council: str
    reference: str
    source_url: str
    source_record_id: str
    discovered_at: datetime
    window: WindowEvidence
    displayed_references: tuple[str, ...]
    body_sha256: str
    fields: tuple[tuple[str, Literal], ...]
    site_relationship: str = 'UNKNOWN'
    application_role: str = 'UNKNOWN'

    def __post_init__(self):
        import re
        if self.council != self.window.council or self.council not in COUNCILS:
            raise ValueError('identity council')
        if account_identity(self.council, self.displayed_references, frozenset())[1] != self.reference:
            raise ValueError('source identity not qualified')
        u = urlsplit(self.source_url)
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.fragment:
            raise ValueError('source URL')
        host, prefix = SOURCE_ROOTS[self.council]
        if (u.hostname != host or u.port not in (None, 443) or not u.path.startswith(prefix)
                or len(self.source_url) > 2048 or re.search(r'[\s\\%]', u.path)
                or any(p in {'.', '..'} for p in u.path.split('/'))):
            raise ValueError('source destination not admitted')
        if not self.source_record_id or len(self.source_record_id) > 256 or not re.fullmatch('[0-9a-f]{64}', self.body_sha256):
            raise ValueError('source provenance')
        if self.discovered_at.tzinfo is None:
            raise ValueError('discovery clock')
        if any(k not in DISCOVERY_FIELDS or not isinstance(v, Literal) for k, v in self.fields):
            raise ValueError('unapproved discovery field')
        if len({k for k, _ in self.fields}) != len(self.fields):
            raise ValueError('duplicate field')
        if self.site_relationship != 'UNKNOWN':
            raise ValueError('this initial path cannot assert site relationships')
        if self.application_role not in {'SUBSTANTIVE', 'VARIATION', 'RESERVED_MATTERS',
                'DISCHARGE_CONDITION', 'OTHER_RELATED_APPLICATION', 'UNKNOWN'}:
            raise ValueError('application role')

    def audit(self, known: frozenset[tuple[str, str]]) -> dict:
        proposal = dict(self.fields).get('proposal', Literal('UNKNOWN', None, 'capture-scope:proposal-unobserved'))
        return {'council': self.council, 'reference': self.reference,
                'source': self.source_url, 'source_record_id': self.source_record_id,
                'discovered_at': self.discovered_at.isoformat(), 'run_id': self.window.run_id,
                'requested_interval': [self.window.requested_start.isoformat(), self.window.requested_end.isoformat()],
                'applied_interval': [d.isoformat() if d else None for d in (self.window.applied_start, self.window.applied_end)],
                'date_semantics': self.window.date_semantics, 'identity_evidence': list(self.displayed_references),
                'provenance_sha256': self.body_sha256,
                'fields': {k: {'state': v.state, 'value': v.value, 'locator': v.locator} for k, v in self.fields},
                'materiality': candidate_materiality(proposal),
                'classification': account_identity(self.council, self.displayed_references, known)[0],
                'site_relationship': self.site_relationship, 'application_role': self.application_role,
                'completeness': self.window.outcome.value}


def compare_denominator(eligible: frozenset[tuple[str, str]] | None,
                       detected: frozenset[tuple[str, str]],
                       known: frozenset[tuple[str, str]]) -> dict:
    """The independently frozen eligible set must be supplied by the reviewer."""
    if eligible is None:
        return {'denominator': None, 'detected': None, 'missed': None, 'recall': None}
    new = eligible - known
    found, missed = new & detected, new - detected
    return {'denominator': len(new), 'detected': len(found), 'missed': sorted(missed),
            'already_known': len(eligible & known),
            'recall': len(found) / len(new) if new else None}
