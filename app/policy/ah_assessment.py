"""Read-only AH claim contract. Stored numbers alone never establish evidence.

There is deliberately no prose parser, arithmetic correction, database writer,
network client or inferred source/date in this module.
"""
from dataclasses import asdict, dataclass, field
import json
from app.policy.ah_count_threshold import assess_count_threshold, _number


@dataclass(frozen=True)
class AHClaim:
    value: float | None = None
    lower: float | None = None
    upper: float | None = None
    qualifier: str = 'unknown'
    state: str = 'unknown'
    application_reference: str | None = None
    scope_type: str = 'unclear'
    scope_label: str | None = None
    stage: str | None = None
    document_id: str | None = None
    source_url: str | None = None
    document_date: str | None = None
    passage: str | None = None
    review_reason: str | None = None

    @property
    def qualified(self):
        if self.state not in ('verified', 'estimated'):
            return False
        if not (self.application_reference and self.scope_label
                and self.scope_type in ('whole_site', 'phase', 'plot', 'component')
                and (self.document_id or self.source_url) and self.passage):
            return False
        if self.qualifier == 'exact':
            return self.state == 'verified' and _number(self.value) is not None and self.lower is None and self.upper is None
        if self.qualifier == 'approximate':
            return _number(self.value) is not None and self.lower is None and self.upper is None
        if self.qualifier == 'range':
            lo, hi = _number(self.lower), _number(self.upper)
            return lo is not None and hi is not None and lo <= hi and self.value is None
        if self.qualifier == 'at_least':
            return _number(self.lower) is not None and self.upper is None and self.value is None
        if self.qualifier == 'up_to':
            return _number(self.upper) is not None and self.lower is None and self.value is None
        return False

    def threshold(self, threshold, direction, *, whole_scheme=True):
        result = assess_count_threshold(threshold=threshold, direction=direction,
            qualifier=self.qualifier, qualified=self.qualified,
            value=self.value, lower=self.lower, upper=self.upper)
        # A named component is useful for a minimum lead but never establishes
        # a whole-scheme maximum (nor whole-scheme failure of a minimum).
        if whole_scheme and self.scope_type != 'whole_site' and result != 'unknown':
            if direction == 'maximum' and result in ('meets', 'likely_meets'):
                return 'investigate'
            if direction == 'minimum' and result == 'does_not_meet':
                return 'investigate'
        return result


@dataclass(frozen=True)
class TenureClaim:
    name: str
    claim: AHClaim = field(default_factory=AHClaim)


@dataclass(frozen=True)
class AHAssessment:
    count: AHClaim = field(default_factory=AHClaim)
    alternatives: tuple[AHClaim, ...] = ()
    reported_percentage: float | None = None
    percentage_review_reason: str | None = None
    reported_tenure: str | None = None
    tenures: tuple[TenureClaim, ...] = ()
    reported_evidence: str | None = None
    source_claims: tuple[dict, ...] = ()
    selection_reason: str | None = None
    relationships: tuple[dict, ...] = ()

    def search(self, minimum=None, maximum=None, *, whole_scheme=True):
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError('Minimum exceeds maximum')
        if minimum is None and maximum is None:
            return 'unfiltered'
        def one(claim):
            outcomes = [claim.threshold(limit, direction, whole_scheme=whole_scheme)
                        for direction, limit in (('minimum', minimum), ('maximum', maximum))
                        if limit is not None]
            if 'does_not_meet' in outcomes:
                return 'does_not_meet'
            if 'unknown' in outcomes:
                return 'unknown'
            if 'investigate' in outcomes:
                return 'investigate'
            return 'likely_meets' if 'likely_meets' in outcomes else 'meets'
        if self.count.state == 'conflicting' or self.alternatives:
            # Each alternative must satisfy BOTH constraints. An unsupported
            # alternative prevents a firm exclusion; never cherry-pick bounds.
            claims = self.alternatives or (self.count,)
            results = [one(c) for c in claims]
            return 'does_not_meet' if all(r == 'does_not_meet' for r in results) else 'investigate'
        return one(self.count)

    def payload(self):
        return asdict(self)

    def fingerprint_payload(self):
        result=self.payload()
        # Relationship identity and effective claims matter; prose review notes
        # are retained for explanation without invalidating paid evaluations.
        result['relationships']=[{k:v for k,v in r.items() if k!='reason'} for r in result['relationships']]
        return result

    def columns(self):
        c = self.count
        return {'AH Reported Percentage': self.reported_percentage, 'AH Reported Count': c.value, 'AH Lower Bound': c.lower,
                'AH Upper Bound': c.upper, 'AH Qualifier': c.qualifier,
                'AH Evidence State': c.state, 'AH Qualified': c.qualified,
                'AH Scope': c.scope_label, 'AH Scope Type': c.scope_type,
                'AH Application': c.application_reference, 'AH Stage': c.stage,
                'AH Source': c.source_url, 'AH Document ID': c.document_id,
                'AH Document Date': c.document_date, 'AH Passage': c.passage,
                'AH Review': c.review_reason, 'AH Reported Evidence': self.reported_evidence,
                'AH Reported Tenure': self.reported_tenure,
                'AH Percentage Review': self.percentage_review_reason,
                'AH Explicit Tenure Claims': json.dumps([asdict(t) for t in self.tenures], sort_keys=True),
                'AH Conflicting Claims': json.dumps([asdict(c) for c in self.alternatives], sort_keys=True),
                'AH Source Claims': json.dumps(self.source_claims, sort_keys=True),
                'AH Claim Relationships': json.dumps(self.relationships, sort_keys=True),
                'AH Selection Reason': self.selection_reason}

    def label(self):
        c = self.count
        value = (f'{c.lower}–{c.upper}' if c.qualifier == 'range' else
                 f'at least {c.lower}' if c.qualifier == 'at_least' else
                 f'up to {c.upper}' if c.qualifier == 'up_to' else
                 str(c.value) if c.value is not None else 'unknown')
        unverified = '; reported; source and scope unverified' if c.value is not None and not c.qualified else ''
        reason = f'; {self.selection_reason}' if self.selection_reason else ''
        alternatives = ('; alternatives: ' + '; '.join(
            f'{a.value if a.value is not None else str(a.lower) + "–" + str(a.upper)} ({a.qualifier}; {a.scope_label}; document {a.document_id}; {a.state})'
            for a in self.alternatives)) if self.alternatives else ''
        relationships=''.join(f'; {r["action"]} claim {r["from"]} → {r["to"]}: {r["reason"]}' for r in self.relationships)
        return f'{value} affordable homes — {c.qualifier}, {c.state}{unverified}; {c.scope_label or "scope unknown"}; {c.application_reference or "application unknown"}; {c.stage or "stage unknown"}; source {c.document_id or c.source_url or "unlinked"}; document date {c.document_date or "unknown"}{reason}{alternatives}{relationships}'


def legacy_assessment(intelligence=None, *, application_reference=None,
                      scope_type='unclear', scope_label=None, fields=None):
    """Preserve legacy extraction verbatim, without fabricating qualification.

    Current SchemeIntelligence has no count-level document link, qualifier,
    bounds or source date. Its generic confidence and narrative are not a
    structured claim. No extraction timestamp is substituted for source date.
    """
    def get(name):
        return fields.get(name) if fields is not None and name in fields else getattr(intelligence, name, None)
    reason = 'Count-level source, qualifier and scope evidence not linked; reported value is unverified.'
    return AHAssessment(
        count=AHClaim(value=get('affordable_units_final'), application_reference=application_reference,
                      scope_type=scope_type, scope_label=scope_label,
                      stage=get('affordable_housing_status'), review_reason=reason),
        reported_percentage=get('affordable_percentage_final'),
        percentage_review_reason=get('affordable_status_note'),
        reported_tenure=get('affordable_tenure_split_final'),
        reported_evidence=get('affordable_classification_evidence'))
