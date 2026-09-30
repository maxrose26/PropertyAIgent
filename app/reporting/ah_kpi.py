"""Compact buyer-facing AH count; evidence prose belongs outside the KPI."""


def affordable_count_kpi(assessment):
    claim = assessment.count
    if (not claim.qualified or claim.scope_type != 'whole_site'
            or assessment.alternatives or claim.state == 'conflicting'):
        return 'N/A'
    def number(value):
        numeric = float(value)
        return str(int(numeric)) if numeric.is_integer() else str(numeric)
    if claim.qualifier == 'exact':
        return number(claim.value)
    if claim.qualifier == 'approximate':
        return f'Approx. {number(claim.value)}'
    if claim.qualifier == 'at_least':
        return f'{number(claim.lower)}+'
    if claim.qualifier == 'range':
        return f'{number(claim.lower)}–{number(claim.upper)}'
    if claim.qualifier == 'up_to':
        return f'Up to {number(claim.upper)}'
    return 'N/A'
