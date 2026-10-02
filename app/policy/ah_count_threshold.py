"""Pure discovery thresholds. Callers must establish evidence and scope first.

This module neither modifies claims nor supplies a statistical interval.
Unqualified legacy values must not be passed as qualified evidence.
"""
from decimal import Decimal, InvalidOperation


def _number(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def assess_count_threshold(*, threshold, direction, qualifier, qualified=False,
                           value=None, lower=None, upper=None):
    """Return meets/likely_meets/investigate/does_not_meet/unknown.

    exact requires verified evidence; approximate requires source-linked
    qualified evidence. Explicit bounds are never expanded. Conflict handling
    and component-to-opportunity selection belong to the claim adapter.
    """
    limit = _number(threshold)
    if limit is None or direction not in ('minimum', 'maximum'):
        raise ValueError('Require a nonnegative finite threshold and valid direction')
    if not qualified:
        return 'unknown'
    minimum = direction == 'minimum'
    if qualifier in ('exact', 'approximate'):
        count = _number(value)
        if count is None:
            return 'unknown'
        if qualifier == 'exact':
            meets = count >= limit if minimum else count <= limit
            return 'meets' if meets else 'does_not_meet'
        # Reject ambiguous representation rather than discard explicit bounds.
        if lower is not None or upper is not None:
            raise ValueError('Use a source-bound qualifier when bounds are supplied')
        band_low, band_high = limit * Decimal('0.9'), limit * Decimal('1.1')
        if band_low <= count <= band_high:
            return 'investigate'
        meets = count > band_high if minimum else count < band_low
        return 'likely_meets' if meets else 'does_not_meet'
    if qualifier == 'range':
        lo, hi = _number(lower), _number(upper)
        if lo is None or hi is None or lo > hi:
            return 'unknown'
    elif qualifier == 'at_least':
        lo, hi = _number(lower), None
        if lo is None:
            return 'unknown'
    elif qualifier == 'up_to':
        lo, hi = None, _number(upper)
        if hi is None:
            return 'unknown'
    else:
        return 'unknown'
    if minimum:
        if lo is not None and lo >= limit:
            return 'likely_meets'
        if hi is not None and hi < limit:
            return 'does_not_meet'
    else:
        if hi is not None and hi <= limit:
            return 'likely_meets'
        if lo is not None and lo > limit:
            return 'does_not_meet'
    return 'investigate'
