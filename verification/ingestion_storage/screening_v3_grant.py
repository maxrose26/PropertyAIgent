"""Grant vocabulary for an explicitly selected screening-v3 registration (proposal section 2.3). Pure, no I/O, importable on any platform.

A v1 registration's grant is never touched. A v3 registration adds exactly two things to the grant: the list of configuration digests the registration authorises (`screening_configs`) and the v3 admission outcomes
in `completion_outcomes['SCREENING']`. Everything else (keys, contracts, bindings, expiry, allowances, login names) is built by the unchanged owner code."""
from app.ingestion.listing_screening import RULE_V3, ROUTING_VOCABULARY, screening_plan_binding


def apply_screening(grant, rule):
    """Add the v3 vocabulary to a grant dict in place (and return it). Refuses anything but a v3 rule, and refuses to be applied twice."""
    _, config_sha256 = screening_plan_binding(rule)
    if 'screening_configs' in grant:
        raise ValueError('SCREENING_CONFIGS_ALREADY_SET')
    grant['screening_configs'] = [config_sha256]
    outcomes = grant['completion_outcomes']['SCREENING']
    grant['completion_outcomes']['SCREENING'] = list(outcomes) + [a for a in sorted(ROUTING_VOCABULARY[RULE_V3]) if a not in outcomes]
    return grant
