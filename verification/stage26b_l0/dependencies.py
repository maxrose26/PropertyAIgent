"""Typed attribution of already-resolved facts, not a matcher or source selector."""
from __future__ import annotations
from collections import Counter
import datetime as dt

DIRECT = 'DIRECT_FACTUAL_DEPENDENCY'
CONTEXT = 'CONTEXT_DEPENDENCY'
DISCOVERY = 'DISCOVERY_RELATIONSHIP'
TYPES = frozenset((DIRECT, CONTEXT, DISCOVERY))
TRUTH = frozenset(('VERIFIED_FACT', 'RETAINED_HISTORICAL_FACT', 'MOCKED_EXPECTATION',
                   'UNRESOLVED', 'DISCOVERY_CANDIDATE'))


def edge(*, subject_key, site_id, application, dependency_type, fields, consumers,
         reason, truth='RETAINED_HISTORICAL_FACT', operative_role='context',
         documents=(), verification_observation=None):
    """One relationship has one type. Different fields can have distinct edges.

    Application identity comes from actual loaded relationships, never proximity,
    count subtraction or date recency. An application can support distinct edges.
    """
    if dependency_type not in TYPES or truth not in TRUTH:
        raise ValueError('Unsupported dependency/truth type')
    if not fields or not consumers or not reason:
        raise ValueError('Unexplained dependency')
    if application['site_id'] != site_id or not application.get('reference'):
        raise ValueError('Evidence identity/site mismatch')
    if dependency_type == DISCOVERY and truth != 'DISCOVERY_CANDIDATE':
        raise ValueError('Discovery is not accepted evidence')
    observed = verification_observation or application
    if (observed['id'], observed['site_id'], observed['reference']) != (
            application['id'], site_id, application['reference']):
        raise ValueError('Verification attribution mismatch')
    # Separate metadata observations cannot silently certify different facts.
    for k in ('status', 'decision', 'decision_issued_date'):
        if observed.get(k) != application.get(k):
            raise ValueError('Different retained planning fact; no freshness transfer')
    verified = observed.get('status_verified_at')
    return dict(subject_key=subject_key, site_id=site_id,
                application_id=application['id'], reference=application['reference'],
                council=application['council_code'], dependency_type=dependency_type,
                supported_fields=sorted(set(fields)), consumers=sorted(set(consumers)),
                reason=reason, truth=truth, operative_role=operative_role,
                status_verified_at=verified,
                verification_state='UNKNOWN' if not verified else 'STATUS_VERIFIED_AS_OF',
                verification_scope='planning_status_and_decision_only',
                supported_fields_verification='UNKNOWN unless separately source-qualified',
                source_url=application.get('summary_url'), document_ids=sorted(set(documents)),
                generated_intelligence_dependency='candidate_only_not_regeneration_authority',
                uncertainty=['Not a new council verification', 'Current production membership unverified'])


def establishes_fact(dependency, field, *, application_id, reference):
    """Only direct attribution can support an accepted fact for this exact source."""
    return (dependency['dependency_type'] == DIRECT
            and field in dependency['supported_fields']
            and dependency['application_id'] == application_id
            and dependency['reference'] == reference
            and dependency['truth'] in {'VERIFIED_FACT', 'RETAINED_HISTORICAL_FACT'})


def material_fields_changed(before, after):
    """Fixture evaluation only: delegate status materiality to production normaliser.

    Do not build a second material-change detector. This helper exercises only the
    status/date concepts in L0; other facts require their existing consumer.
    """
    from app.pipeline.material_change import _classify_planning_state
    changed = []
    if _classify_planning_state(before.get('decision'), before.get('status')) != \
            _classify_planning_state(after.get('decision'), after.get('status')):
        changed.append('planning_status')
    if before.get('decision_issued_date') != after.get('decision_issued_date'):
        changed.append('decision_issued_date')
    return tuple(changed)


def risk_cohort(*, contradiction=False, decision_sensitive=False, buyer_facing=False,
                substantive=False, missing_verification=False, context_gap=False,
                generated_dependency=False):
    """Specification 031 cohorts, never fit/valuation/commercial ranking."""
    cohort = (1 if contradiction else 2 if decision_sensitive and buyer_facing else
              3 if (decision_sensitive and substantive) or context_gap else
              4 if buyer_facing and missing_verification else 5)
    reasons = [name for name, value in (
        ('authoritative_contradiction', contradiction),
        ('decision_sensitive_buyer_facing_fact', decision_sensitive and buyer_facing),
        ('missing_successful_verification', missing_verification),
        ('context_relationship_gap', context_gap),
        ('dependent_generated_intelligence', generated_dependency)) if value]
    return dict(cohort=cohort, reasons=reasons or ['deferred_settled_or_administrative'])


def priority_key(item):
    """Missing is its own tier; oldest first only within equivalent cohort."""
    verified = item.get('status_verified_at')
    instant = dt.datetime.fromisoformat(verified).timestamp() if verified else 0
    return (item['cohort'], 0 if not verified else 1, instant,
            item['council'], item['reference'], item['application_id'])


def summarise(edges):
    return dict(total=len(edges), by_type=dict(sorted(Counter(e['dependency_type'] for e in edges).items())),
                subjects_with_application_edges=len({e['subject_key'] for e in edges}),
                applications=len({e['application_id'] for e in edges}),
                direct_status_applications=len({e['application_id'] for e in edges
                    if e['dependency_type'] == DIRECT and 'planning_status' in e['supported_fields']}))
